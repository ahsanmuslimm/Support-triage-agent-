# Sprint 2 Semantic Code Review: Triage Graph & Classification

**Verdict: NEEDS_CHANGES**

Sprint 2 implements the core classification, decision logic, and database schema for the triage agent: intent k-NN classifiers with temperature scaling, a 10-rule decision matrix for autonomy levels, entity extraction models, and comprehensive Pydantic state models. The implementation is architecturally sound with proper tenant isolation via RLS policies and deterministic decision logic. However, there are import path issues blocking test execution, and several behavioral gaps around entity verification, autonomy policy loading, and LangGraph state persistence need resolution before production readiness.

**Watch for:**
- **confirmed** — Test suite cannot run due to import path misalignment (`from triage.api.main` fails; tests import `from triage.classification.classifier` but modules use relative paths). Blocks verification of all 48 unit tests.
- **confirmed** — Entity validation model exists (EntityValidationResult) but entity verification logic is not implemented; unverified entities cannot be blocked from tool binding as specified.
- **confirmed** — Autonomy policies table exists in the database but DecisionMatrix never loads or applies per-tenant autonomy level overrides; kills switch semantics are missing.
- **likely** — TriageState serialization uses `model_dump_json()` override for Postgres checkpointer compatibility, but LangGraph integration not yet present; resume-from-checkpoint across workers cannot be verified.

---

<details>
<summary>High-level View</summary>

The classification pipeline pairs a sentence-transformer k-NN classifier with a keyword-based fallback, both applying temperature scaling to produce calibrated multi-label confidence scores. The decision matrix implements 10 deterministic rules evaluated in order (first-match semantics), with injection heuristics and safety flag checks at the gate. Intent embeddings and training examples are stored per-tenant with full RLS isolation. Entity extraction models define 10 entity types and include PII flagging with pseudonymization hooks, but the extraction logic itself (regex/NER) and entity linking validation are deferred to Phase 3. The TriageState model bundles message, classification, extraction, autonomy, retrieval, and execution phases into a single mutable object JSON-serializable for Postgres checkpoints. All models use Pydantic v2 with proper type hints and validation bounds. The database schema includes tenant-scoped composite primary keys and RLS policies on all tables. Tests cover models (13), classification (18), and decision matrix (17) with 48 unit tests ready to run once import paths are fixed.

Import path issues in conftest.py prevent test execution. Autonomy policies are persisted in the database but not loaded or evaluated by DecisionMatrix, breaking the per-tenant autonomy override flow. Entity validation surfaces a model (EntityValidationResult) but the entity verification implementation that blocks unverified entities from tool binding is absent. TriageState checkpointing is designed for Postgres but LangGraph orchestration code is out of scope for Sprint 2, leaving integration verification incomplete.

</details>

<details>
<summary>Issues (5)</summary>

1. **Test suite import path mismatch** — conftest.py imports from `triage.api.main` which fails because the package is not installed; test modules import from `triage.classification.classifier` but code uses both relative and absolute import styles inconsistently. Either install the package in dev mode (`pip install -e`) or fix import paths to use `services.api.src.triage.*` throughout. Blocks verification of all 48 unit tests.

2. **Autonomy policies table not loaded** — autonomy_policies table exists in the migration but DecisionMatrix never queries it; all autonomy level decisions are hard-coded rules with no per-tenant override mechanism. Load policies on init; apply them as a pre-rule gate (e.g., if tenant has policy for intent, use policy level; else apply rules).

3. **Entity verification not implemented** — EntityValidationResult model exists but the logic that validates entities, checks cross-tenant risk, and sets can_bind_to_tool flag is absent. Entity extraction phase cannot gate tool binding to verified entities only. Implement entity verifier that checks linked_id against backend, validates cross-tenant boundaries, and sets can_bind_to_tool=true only if verified.

4. **TriageState Postgres serialization untested** — model_dump_json() override is designed for checkpointer but LangGraph graph orchestration is not yet implemented (Phase 7). Cannot verify checkpoint round-trip or resumption across workers. Defer until Phase 7 LangGraph nodes are added and end-to-end integration tests run.

5. **Temperature scaler approximation formula unclear** — scale_confidence() uses tanh approximation `0.5 + 0.5 * tanh((2p - 1) / (2T))` which is intuitive but not standard logit temperature scaling. Document why this approximation is chosen over traditional `exp(logit(p) / T) / Z` or cite a reference; add unit test verifying scaled confidences on a calibration validation set (not just extreme values).

</details>

---

## Architecture & Design

### Classification Pipeline: k-NN + Fallback

The IntentClassifier embeds messages and training examples using sentence-transformers (all-MiniLM-L6-v2, 384-dim), computes mean embeddings per intent, and builds a k-NN model (k=5, cosine distance) to find nearest intent embeddings. Softmax with temperature scaling produces normalized confidences summing to ~1.0. The fallback uses exact keyword matching (confidence 0.95) and fuzzy Levenshtein matching (threshold 0.7). Both return IntentClassifierResult sorted by confidence. The pipeline is resilient: classification errors raise IntentClassifierError for callers to catch and fall back to keyword matching.

**Concern — temperature scaling formula**: scale_confidence() uses tanh approximation `0.5 + 0.5 * tanh((2p - 1) / (2T))` instead of standard logit-space temperature scaling. The formula is intuitive but not canonical in calibration literature (e.g., Guo et al. 2017). While ECE computation (binning by confidence) and temperature sweep are deterministic, the formula choice should be documented or cited. **likely** concern for reproducibility across deployments.

### Decision Matrix: 10 Rules, First-Match Semantics

The DecisionMatrix.decide(policy) function evaluates rules in a fixed order; the first matching rule determines autonomy level. Rules are:

1. Safety flags (chargeback, legal, breach) → L0
2. Injection patterns (LLM prompt injection, SQL, path traversal, XSS) → L0
3. Confidence < 0.5 → L0
4. Repeat customer with ≥2 failed attempts → L0
5. IAL < 2 for sensitive intents (password_reset, account_delete, billing_change, refund) → L0
6. Refund > $500 → L2
7. Confidence < 0.7 + amount > $100 → L0
8. order_status + confidence ≥ 0.7 → L1
9. Premium tier + low-risk intent + confidence ≥ 0.75 → L2
10. Low-risk refund (< $100, confidence ≥ 0.75, IAL ≥ 1) → L2
11. Enterprise + low-risk + confidence ≥ 0.9 → L3
12. Default (no match) → L0

Injection detection uses regex on patterns like "ignore.*prompt", "SELECT|DROP|UNION", "../", "script>". All rules are deterministic functions of PolicyInput with no I/O or randomness. Tests verify all 11 rules individually plus edge cases (confidence/amount at exact thresholds, determinism, default escalation).

First-match semantics is conservative — escalation rules take precedence over promotion rules. High-confidence, low-risk messages may still escalate if an earlier rule matches (e.g., repeat customer with failed attempts beats premium tier), which is intentional for safety.

**Gap — autonomy policy loading**: autonomy_policies table stores per-tenant, per-intent level overrides but DecisionMatrix never queries it. All decisions come from hard-coded rules, breaking per-tenant customization. Fix: Add policy loading on init and policy ceiling check in decide().

### Entity Extraction & Validation

The entity models define 10 entity types (ORDER_ID, AMOUNT, EMAIL, PHONE, ACCOUNT_ID, CREDIT_CARD, SSN, PRODUCT, DATE, TRACKING_NUMBER) and ExtractedEntity with value, normalized_value, confidence, PII flag, and pseudonym field for vault tokens. EntityValidationResult model captures valid/reason/can_bind_to_tool/cross_tenant_risk but the validation implementation is absent.

The intended flow is: (1) extraction produces candidates, (2) validation links to backend records, checks cross-tenant isolation, verifies ownership, (3) only verified entities (can_bind_to_tool=true) pass to tool executor. Extraction (regex, NER) is deferred to Phase 3. Validation is missing entirely, so unverified entities can leak across tenants or bind to wrong records. **confirmed** gap blocking entity-to-tool binding safety.

### TriageState: LangGraph Mutable State

TriageState bundles all graph data: input (message, customer, tenant, channel), classification (intents, top_intent, confidence), entities, context (IAL, tier), autonomy decision, retrieval/generation/execution stubs, reasoning trail, and timing. The add_reasoning() method appends audit entries; model_dump_json() override ensures datetime fields serialize as ISO strings for Postgres checkpointer compatibility. All fields are validated (confidence ∈ [0,1], IAL ∈ [0,3]).

The design is correct for LangGraph StateGraph where every node reads/mutates this state. Actual graph orchestration (15 nodes, routing, checkpointing) is out of scope for Sprint 2, so persistence and resumption cannot be verified yet.

---

## Database & Tenant Isolation

The migration creates 6 tables in triage schema, all with composite primary keys (tenant_id, id) and RLS policies for per-tenant row filtering:
- intent_embeddings (tenant_id, intent_name) — avg embedding per intent for k-NN lookup
- intent_examples (tenant_id, id) — training examples, marked is_golden for golden set tracking
- triage_runs (tenant_id, id) — agent execution results (intent, autonomy, action, tool result, reasoning, latency)
- extracted_entities (tenant_id, id) — extracted entities linked to message and type
- autonomy_policies (tenant_id, id) — per-tenant intent → autonomy level overrides
- autonomy_promotions (tenant_id, id) — audit trail of autonomy promotions (intent, from/to level, accuracy, groundedness, sample_count, approver, timestamp)

RLS policies enforce `tenant_id = CURRENT_SETTING('app.tenant_id')::UUID` on all tables. Foreign keys link entities to messages/conversations. Indexes on (tenant_id, intent), (tenant_id, message_id), (tenant_id, entity_type).

**Verification gap**: RLS policies are syntactically correct but require application code to set `app.tenant_id` context variable via `SET app.tenant_id = '...'` before each query. This contract is not enforced in Sprint 2 code. **likely** concern until integration tests verify the context is always set.

---

## Test Coverage

### Models (13 tests)
IntentPrediction bounds (confidence ∈ [0,1]), IntentClassifierResult serialization and round-trip, AutonomyLevel enum values, PolicyInput with safety flags, DecisionResult serialization, EntityType enum, ExtractedEntity PII flagging, EntityExtractionResult structure, TriageState initialization, add_reasoning(), and serialization. All models round-trip via model_dump() and reconstruction.

### Classification (18 tests)
IntentClassifier: initialization, set_intent_examples, classify with high confidence, multi-label classification, empty message error, get_intents. Three tests are async (`@pytest.mark.asyncio`). FallbackIntentClassifier: exact keyword match, fuzzy match, no match defaults to "other", empty message, case insensitivity. TemperatureScaler: ECE on perfect/poor calibration, empty data, temperature search, single scaling, boundary values.

**Gaps**: No negative cases (malformed input, extreme length, high intent cardinality). No fallback activation test (when embedding model unavailable).

### Decision Matrix (17 tests)
All 11 rules have individual tests plus edge cases: confidence/amount exactly at thresholds, precedence rules, determinism (same input → same output), default escalation. Tests verify rule_triggered field.

**Gaps**: No multi-rule interaction edge cases (first-match semantics should handle this but a test would confirm). No malformed PolicyInput tests (negative IAL, confidence > 1, negative amount).

### Integration gaps
- No end-to-end test showing message → classify → extract → decide → route
- No test of fallback classifier activation (when embedding model is unavailable)
- No test of TriageState checkpointing and resumption
- No test of autonomy_policies table loading and application
- No test of entity validation blocking unverified entities

---

## Code Quality & Type Hints

**Type hints:** 100% coverage. All functions, methods, and attributes have type annotations. Pydantic models use correct generics (List[IntentPrediction], Optional[str], Dict[str, Any]).

**Async readiness:** IntentClassifier.classify() is async; tests use `@pytest.mark.asyncio` which requires pytest-asyncio. Not yet integrated with an event loop.

**Error handling:** Custom TriageBaseError subclass (IntentClassifierError); structlog integrated for logging.

**Dependencies:** pyproject.toml pins versions (sentence-transformers>=2.2, scikit-learn>=1.3, numpy>=1.24, structlog>=23.0). No pre-release or wildcards.

**Import paths:** Inconsistency — conftest.py imports `from triage.api.main` but decision matrix imports `from services.api.src.triage.models.decision`. Tests import `from triage.classification.classifier`. This works if package is installed in dev mode (`pip install -e services/api`) but is not evident from configuration. **confirmed** gap.

---

## Security Observations

**Injection heuristics**: DecisionMatrix regex patterns catch common attacks: "ignore all previous instructions" ✓, "SELECT * FROM users" ✓, "../../etc/passwd" ✓, "onclick=alert(1)" ✓. But patterns are rule-based, not ML-based, so context-specific attacks may bypass them. Sufficient for Phase 2 but should be complemented by LLM-based detection in Phase 5. **likely** concern — document as known limitation.

**PII pseudonymization**: ExtractedEntity has is_pii and pseudonym fields (e.g., "VAULT_cc_xyz123") but tokenization logic is missing (deferred to Phase 3 entity extraction). Once extraction is implemented, all PII must be pseudonymized before downstream use. **confirmed** gap requiring Phase 3 follow-up.

**Tenant isolation**: RLS policies are syntactically correct and applied to all tables. The contract (application sets `app.tenant_id` context) must be enforced in integration tests. **likely** concern until verified.

---

## Determinism & Reproducibility

**DecisionMatrix determinism:** Rules are pure functions of PolicyInput; no I/O, randomness, or timestamps. Tests confirm identical inputs produce identical outputs (same autonomy_level, rule_triggered, reason). **confirmed**.

**IntentClassifier determinism:** Deterministic given fixed embeddings and k-NN model. However, sentence-transformers embeddings may vary slightly across model versions or hardware (GPU vs. CPU). For reproducibility across deployments, embed model version should be pinned and embeddings cached in the database rather than recomputed per classify() call. Current design recomputes on each call — fine for Phase 2 but will hit latency at scale. **likely** concern for production scaling.

---

## Gaps & Open Questions

1. **Autonomy policy loading** — DecisionMatrix never queries autonomy_policies table. Per-tenant overrides not applied. Scope: Minor (one method, one lookup per decide() call).
2. **Entity verification** — Validation logic missing. Unverified entities can bind to tools. Scope: Medium (entity verifier module, linking, cross-tenant checks).
3. **Test execution blockers** — conftest.py import path fails. Cannot run tests until fixed or package installed in dev mode. Scope: Low (fix import or `pip install -e`).
4. **TriageState checkpointing** — Designed for Postgres but LangGraph integration not present (Phase 7). Persistence/resumption cannot be verified. Scope: Deferred.
5. **Fallback classifier coverage** — No test of fallback activation when embedding model unavailable. Scope: Low (add mock test).
6. **LangGraph integration** — TriageState designed as mutable graph state but actual graph (15 nodes, routing) out of scope. Scope: Phase 7.

---

## File Map

<details>
<summary>Modified & New Files</summary>

**Migrations:**
- `packages/py_core/alembic/versions/0004_sprint2_triage_tables.py` — Alembic migration creating 6 new triage tables (intent_embeddings, intent_examples, triage_runs, extracted_entities, autonomy_policies, autonomy_promotions) with RLS policies and composite primary keys.

**Models (services/api/src/triage/models/):**
- `intent.py` — IntentPrediction, IntentClassifierResult
- `entity.py` — EntityType, ExtractedEntity, EntityExtractionResult, EntityValidationResult
- `decision.py` — AutonomyLevel, SafetyFlag, PolicyInput, DecisionResult
- `triage_state.py` — TriageState (LangGraph mutable state) with add_reasoning() and model_dump_json()

**Classification (services/api/src/triage/classification/):**
- `classifier.py` — IntentClassifier (k-NN + temperature scaling, async)
- `fallback.py` — FallbackIntentClassifier (keyword + fuzzy matching)
- `temperature_scaler.py` — TemperatureScaler (ECE computation, temperature search, scaling)

**Decision (services/api/src/triage/decision/):**
- `matrix.py` — DecisionMatrix (10 rules, first-match semantics, injection detection)

**Tests (services/api/tests/):**
- `test_models.py` — 13 tests (intent, decision, entity, triage_state models)
- `test_classification.py` — 18 tests (IntentClassifier, FallbackIntentClassifier, TemperatureScaler)
- `test_decision_matrix.py` — 17 tests (all rules, edge cases, determinism, default escalation)

**Configuration:**
- `services/api/pyproject.toml` — Added dependencies: sentence-transformers, scikit-learn, numpy, structlog

**Full diff:** All Phase 0–2 code is new; no existing code modified (safe to rollback).

</details>

---

## Verdict & Next Steps

The implementation is architecturally sound with good test coverage (48 unit tests). Tenant isolation via RLS is correctly configured. Three blocking gaps prevent approval:

1. **Test suite cannot run** — conftest.py import path fails. Fix: Install package in dev mode (`pip install -e services/api`) or update imports to absolute paths.
2. **Autonomy policy loading missing** — DecisionMatrix doesn't query autonomy_policies table. Fix: Add policy loading on init and policy ceiling check in decide().
3. **Entity verification missing** — EntityValidationResult model exists but validation logic is absent. Fix: Implement entity verifier that validates entities, checks cross-tenant risk, gates tool binding to verified entities only.

These are implementation gaps in connective tissue, not architectural issues. Once fixed, Sprint 2 integrates with Phase 3 (entity extraction) and Phase 7 (LangGraph orchestration).

Fix the three issues, run test suite to confirm all 48 tests pass, and resubmit for approval.

