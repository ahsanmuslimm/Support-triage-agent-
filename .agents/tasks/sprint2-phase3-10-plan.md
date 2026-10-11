# Sprint 2 Implementation Plan: Phases 3–10

**Status:** Ready for implementation  
**Critical Fixes Required:** Import paths, autonomy_policies table wiring, entity verification logic

## Phase 3: Entity Extraction & Validation (Days 4–5)

### 3.1 Fix conftest.py import paths (CRITICAL)
- **What:** conftest.py fails on `from triage.api.main import create_app` because package not installed. Fix by adjusting sys.path and using relative imports, or mock create_app for tests that don't need it.
- **Files:** `services/api/tests/conftest.py`
- **Verify:** `pytest services/api/tests/test_classification.py::TestIntentClassifier::test_classify -v` passes without import errors

### 3.2 Implement RuleBasedEntityExtractor (regex patterns)
- **What:** Create extractor.py with regex patterns for ORDER_ID, AMOUNT, EMAIL, PHONE, ACCOUNT_ID, CREDIT_CARD, SSN. Extract with re.finditer(), return ExtractedEntity list with confidence=0.95.
- **Files:** `services/api/src/triage/entity/extractor.py`
- **Verify:** `pytest services/api/tests/test_entity_extraction.py::TestRuleBasedEntityExtractor -v` — 8 tests pass (extract ORDER_ID, AMOUNT, EMAIL, phone normalization, PII flagging, credit card masking, SSN masking, no match)

### 3.3 Implement MLEntityExtractor (HuggingFace NER)
- **What:** Create ml_extractor.py. Load `dslim/bert-base-multilingual-cased-ner-hrl` via transformers.pipeline("ner"). Map HF tags to custom types. Return entities with confidence scores.
- **Files:** `services/api/src/triage/entity/ml_extractor.py`
- **Verify:** Unit test: extract from message → verify confidence in [0, 1] and entity types mapped correctly

### 3.4 Implement EntityLinker (Shopify + DB)
- **What:** Create linker.py with `link()` method. For ORDER_ID: call Shopify API (mock in tests). For EMAIL/PHONE: query customers table. Return linked_id if found, None if not. Async operations.
- **Files:** `services/api/src/triage/entity/linker.py`
- **Verify:** Integration test: extract ORDER_ID → link to Shopify → linked_id set. Test cross-tenant isolation: order from tenant A cannot link to tenant B's customer DB.

### 3.5 Wire autonomy_policies table into DecisionMatrix (CRITICAL)
- **What:** Modify decision/matrix.py to load autonomy_policies from DB in __init__. Add `async def load_policies(db_session, tenant_id)`. DecisionMatrix._check_autonomy_policy_override() checks table first before hard-coded rules. Fallback to hard-coded if table load fails.
- **Files:** `services/api/src/triage/decision/matrix.py`
- **Verify:** Unit test: load policies from DB (or mock) → DecisionMatrix prefers DB policy over rule. No policy → falls through to rules.

### 3.6 Implement EntityValidator with verification logic (CRITICAL)
- **What:** Complete validator.py validation logic. Implement validate_for_tool(): (1) check confidence >= 0.8, (2) verify cross-tenant isolation (linked_tenant_id matches current tenant), (3) block unverified/low-confidence entities from tool binding. Return EntityValidationResult with valid=True/False and reason.
- **Files:** `services/api/src/triage/entity/validator.py`
- **Verify:** Unit tests: (1) confidence < 0.8 → invalid, (2) linked to other tenant → invalid, (3) unlinked entity (linked_id=None) → invalid, (4) confidence >= 0.8 + correct tenant → valid

### 3.7 Implement PIIRedactingExtractor (pseudonymization)
- **What:** Create pii_redactor.py. Wrap RuleBasedEntityExtractor and MLEntityExtractor. When is_pii=True, replace sensitive values with VAULT tokens (e.g., "VAULT_SSN_123"). Store mapping in PII vault (in-memory dict for now, backed by secure DB later). Return redacted text + mapping.
- **Files:** `services/api/src/triage/entity/pii_redactor.py`
- **Verify:** Unit test: extract "Call me at 555-1234" → pseudonym="VAULT_PHONE_001", original hidden

### 3.8 Write entity extraction tests (20+ tests)
- **What:** Comprehensive test suite for all extractors, linker, validator, redactor. Cover: happy path, edge cases (empty text, special chars, long values), cross-tenant isolation, PII handling, injection patterns in entities.
- **Files:** `services/api/tests/test_entity_extraction.py`, `services/api/tests/test_entity_validator.py`
- **Verify:** `pytest services/api/tests/test_entity*.py -v --cov=services/api/src/triage/entity` — 25+ tests pass, coverage >= 85%

---

## Phase 4: RAG Pipeline (Days 5–6)

### 4.1 Implement DocumentChunker
- **What:** Create chunker.py. Chunk documents to 500 tokens with 100-token overlap. Use sentence tokenizer to preserve sentence boundaries. Return Chunk objects (text, start_idx, end_idx, token_count).
- **Files:** `services/api/src/triage/retrieval/chunker.py`
- **Verify:** Unit test: chunk 2000-token doc → 5 chunks of ~500 tokens, overlap=100. Boundaries on sentence edges.

### 4.2 Implement VectorSearch (pgvector + fallback)
- **What:** Create vector_search.py. Search knowledge_chunks table using pgvector (cosine similarity). If pgvector unavailable, fallback to in-memory numpy cosine similarity (load all chunks on init). Return top-k chunks ranked by similarity.
- **Files:** `services/api/src/triage/retrieval/vector_search.py`
- **Verify:** Integration test: embed query → pgvector search (or numpy fallback) → return top-k chunks with scores in [0, 1]

### 4.3 Implement BM25Search
- **What:** Create bm25_search.py using rank_bm25 library. Index knowledge_documents and knowledge_chunks. Search by keyword. Return ranked results.
- **Files:** `services/api/src/triage/retrieval/bm25_search.py`
- **Verify:** Unit test: search for "refund policy" → BM25 returns docs with "refund" + "policy"

### 4.4 Implement HybridRetrieval (RRF fusion)
- **What:** Create hybrid.py. Fuse BM25 + semantic search via Reciprocal Rank Fusion (RRF = 1 / (k + rank)). Weight equally (0.5 each) by default. Return merged, de-duplicated, re-ranked results.
- **Files:** `services/api/src/triage/retrieval/hybrid.py`
- **Verify:** Unit test: search for "order refund" → BM25 returns [doc1, doc2], semantic returns [doc2, doc3] → RRF fusion produces combined ranking

### 4.5 Write retrieval tests (15+ tests)
- **What:** Test suite for chunker, vector search, BM25, hybrid fusion. Cover edge cases (empty query, no results, tie scores).
- **Files:** `services/api/tests/test_retrieval.py`
- **Verify:** `pytest services/api/tests/test_retrieval.py -v` — 15+ tests pass

---

## Phase 5: Response Generation & Grounding (Days 6–7)

### 5.1 Implement ResponseGenerator (LiteLLM + Claude)
- **What:** Create generator.py. Initialize LiteLLM client pointing to Claude Opus via environment variable (CLAUDE_API_KEY). Implement `async generate_response(prompt, context, max_tokens)`. Include retry logic (exponential backoff, max 3 attempts). Log token usage and latency.
- **Files:** `services/api/src/triage/generation/generator.py`
- **Verify:** Unit test (mocked LLM): generate_response() → returns text response with token count. Test retry on transient failure.

### 5.2 Implement GroundednessScorer
- **What:** Create groundedness.py. Extract claims from generated response (NLP-based or simple heuristics). For each claim, check if it's grounded in retrieved context (substring match or semantic similarity). Score = claims_grounded / total_claims. Target >= 0.95.
- **Files:** `services/api/src/triage/generation/groundedness.py`
- **Verify:** Unit test: response "Order 123 was shipped on Monday" + context with "Order 123 shipped on 2024-10-01" → groundedness >= 0.95. Response with hallucination → groundedness < 0.95.

### 5.3 Implement OutputValidator
- **What:** Create validator.py. Implement validate_output(): check toxicity (detoxify library), PII leakage (regex + context matching), injection patterns, IAL compatibility (e.g., L1 agents don't send money-related statements). Block responses that fail validation.
- **Files:** `services/api/src/triage/generation/validator.py`
- **Verify:** Unit tests: response with profanity → blocked. Response with PII (email in open text) → blocked. IAL-compatible response → allowed.

### 5.4 Implement SafeResponseFallback
- **What:** Create fallback.py. If generation fails or validation blocks response, return safe template responses keyed by intent (e.g., "I'm unable to help with that right now. Let me connect you with a specialist.").
- **Files:** `services/api/src/triage/generation/fallback.py`
- **Verify:** Unit test: generation fails → fallback returns template. Validation fails → fallback returns template.

### 5.5 Write generation tests (10+ tests)
- **What:** Test suite for generator, groundedness, validator, fallback.
- **Files:** `services/api/tests/test_generation.py`
- **Verify:** `pytest services/api/tests/test_generation.py -v` — 10+ tests pass

---

## Phase 6: Tool Integration Framework (Days 7–8)

### 6.1 Implement ToolRegistry with built-in tools
- **What:** Create tools/registry.py. Define ToolSpec for each tool: send_email, create_ticket, issue_refund, reset_password, cancel_order, lookup_order. Each tool has: name, description, required_arguments (schema), autonomy_level_required, idempotency_key_field.
- **Files:** `services/api/src/triage/tools/registry.py`
- **Verify:** Unit test: ToolRegistry.get_tool("refund") → ToolSpec with correct schema and autonomy level

### 6.2 Implement ArgumentBinder (entity → tool args)
- **What:** Create argument_binder.py. Bind extracted entities to tool argument slots. E.g., for refund tool: ORDER_ID → order_id, AMOUNT → refund_amount, EMAIL → customer_email. Validate all required args are bound.
- **Files:** `services/api/src/triage/tools/argument_binder.py`
- **Verify:** Unit test: bind entities [ORDER_ID="123", AMOUNT="$50"] to refund tool → args={order_id="123", refund_amount=50.00}. Missing required arg → error.

### 6.3 Implement ToolExecutor with autonomy gate + saga
- **What:** Create executor.py. Implement execute_tool(): (1) check tool_autonomy_level <= current_autonomy_level, (2) gate via AutonomyGate, (3) log execution, (4) execute with idempotency key (prevent duplicate tool calls on retry), (5) return result or error. Implement saga compensation (refund reversal, ticket closure).
- **Files:** `services/api/src/triage/tools/executor.py`
- **Verify:** Unit test: attempt refund with L1 autonomy → blocked. Execute with L2 + idempotency key → succeeds. Duplicate call with same key → returns cached result (not re-executed).

### 6.4 Implement RetryPolicy
- **What:** Create retry.py. Implement exponential backoff: delay = base * (2 ** attempt), max_attempts=3, jitter. Configurable per tool.
- **Files:** `services/api/src/triage/tools/retry.py`
- **Verify:** Unit test: retry on transient error → exponential delays, max 3 attempts.

### 6.5 Write tool tests (12+ tests)
- **What:** Test suite for registry, argument binder, executor, retry.
- **Files:** `services/api/tests/test_tools.py`
- **Verify:** `pytest services/api/tests/test_tools.py -v` — 12+ tests pass

---

## Phase 7: LangGraph Orchestration (Days 8–9)

### 7.1 Implement TriageAgentGraph (StateGraph with 8 nodes)
- **What:** Create agent/graph.py. Build LangGraph StateGraph with TriageState. Implement 8 nodes:
  1. classify_intent: call classifier, populate intents
  2. extract_entities: call extractors, populate entities
  3. make_decision: call DecisionMatrix, set autonomy_level
  4. retrieve_context: call HybridRetrieval, populate retrieved_chunks
  5. generate_response: call ResponseGenerator, populate response_text
  6. validate_output: call OutputValidator, set response_valid
  7. execute_tools: call ToolExecutor if autonomy allows
  8. escalate: prepare escalation data if needed
- **Files:** `services/api/src/triage/agent/graph.py`, `services/api/src/triage/agent/nodes.py`
- **Verify:** Unit test: call graph.compile() → StateGraph compiles without error

### 7.2 Implement edge routing functions
- **What:** Create routing.py. Implement routing functions: route_on_confidence (low confidence → escalate), route_on_validation (validation failed → fallback or escalate), route_on_autonomy (autonomy L0 → escalate, L1+ → execute).
- **Files:** `services/api/src/triage/agent/routing.py`
- **Verify:** Unit test: low confidence → routes to escalate node. High confidence + validated → routes to execute_tools.

### 7.3 Implement GraphExecutor
- **What:** Create executor.py. Implement run_triage_agent(message, context) → async function. Initialize TriageState, run graph, return reasoning trace + final action.
- **Files:** `services/api/src/triage/agent/executor.py`
- **Verify:** Integration test: run end-to-end triage on sample message → graph completes, returns valid TriageState with all fields populated

### 7.4 Implement InMemorySaver checkpointer
- **What:** Use LangGraph's built-in InMemorySaver for state checkpointing. Store thread state per conversation ID for resumption across worker restarts.
- **Files:** Part of agent/executor.py
- **Verify:** Unit test: run graph, checkpoint state, resume from checkpoint → same state restored

### 7.5 Implement POST /v1/triage/run streaming endpoint
- **What:** Create api/endpoints/triage.py. Implement POST /v1/triage/run endpoint. Accept message, conversation_id, customer_id. Stream reasoning steps + final response. Integrate with GraphExecutor.
- **Files:** `services/api/src/triage/api/endpoints/triage.py`
- **Verify:** Integration test: POST /v1/triage/run with sample message → stream returns reasoning steps + response. Latency < 2s end-to-end.

### 7.6 Write LangGraph tests (8+ integration tests)
- **What:** Test suite for graph nodes, routing, executor, checkpoint, endpoint.
- **Files:** `services/api/tests/test_agent_graph.py`
- **Verify:** `pytest services/api/tests/test_agent_graph.py -v` — 8+ tests pass

---

## Phase 8: Routing & Escalation (Day 9)

### 8.1 Implement RoutingEngine
- **What:** Create routing/engine.py. Implement route(intent_name, skill_required) → agent_id. Query routing_rules table for intent. Lookup agent_skills table for agents with required skill. Pick agent with shortest queue (via load_balancer).
- **Files:** `services/api/src/triage/routing/engine.py`
- **Verify:** Unit test: route("refund") with 2 agents (one queue=5, one queue=2) → picks agent with queue=2

### 8.2 Implement LoadBalancer
- **What:** Create load_balancer.py. Implement pick_agent(skill): return agent with lowest queue_size. Handle stale assignments: if agent no response > SLA, reclaim ticket.
- **Files:** `services/api/src/triage/routing/load_balancer.py`
- **Verify:** Unit test: 3 agents with queue sizes [5, 2, 8] → picks agent with queue=2

### 8.3 Implement SLATracker
- **What:** Create sla.py. Implement calculate_deadline(intent, priority) → timestamp. Check if past deadline → breach. Log SLA metrics.
- **Files:** `services/api/src/triage/routing/sla.py`
- **Verify:** Unit test: calculate_deadline for "urgent" intent → 30 min in future. Check breach → True if past deadline.

### 8.4 Implement EscalationTrigger
- **What:** Create escalation.py. Implement should_escalate(triage_state) → bool + reason. Triggers: low confidence, failed validation, autonomy L0, entity validation failed, etc.
- **Files:** `services/api/src/triage/routing/escalation.py`
- **Verify:** Unit test: confidence < 0.5 → escalate=True. Validation failed → escalate=True.

### 8.5 Write routing tests (10+ tests)
- **What:** Test suite for routing engine, load balancer, SLA tracker, escalation.
- **Files:** `services/api/tests/test_routing.py`
- **Verify:** `pytest services/api/tests/test_routing.py -v` — 10+ tests pass

---

## Phase 9: Evaluation Harness & Golden Sets (Day 10)

### 9.1 Create golden dataset (50+ records)
- **What:** Create test/acceptance/golden_sets/sprint2_evaluation.jsonl with 50+ end-to-end triage scenarios. Each record: message, expected_intent(s), expected_entities, expected_action, expected_autonomy_level.
- **Files:** `services/api/tests/acceptance/golden_sets/sprint2_evaluation.jsonl`
- **Verify:** File exists, 50+ JSON records, each record has required fields

### 9.2 Implement intent evaluation harness
- **What:** Create ml/evals/runners/intent_runner.py. Run classifier on golden intents, compute accuracy, macro-F1, ECE. Target: accuracy >= 92%.
- **Files:** `ml/evals/runners/intent_runner.py`
- **Verify:** Run harness → outputs metrics, accuracy >= 92%

### 9.3 Implement retrieval evaluation harness
- **What:** Create ml/evals/runners/retrieval_runner.py. Run HybridRetrieval on golden queries, compute MRR, NDCG@5, Recall@10. Target: MRR >= 0.8.
- **Files:** `ml/evals/runners/retrieval_runner.py`
- **Verify:** Run harness → outputs metrics, MRR >= 0.8

### 9.4 Implement response evaluation harness
- **What:** Create ml/evals/runners/response_runner.py. Generate responses, compute groundedness (>= 0.95), toxicity (<= 0.05), relevance.
- **Files:** `ml/evals/runners/response_runner.py`
- **Verify:** Run harness → outputs metrics, groundedness >= 0.95

### 9.5 Create CI gate (threshold enforcement)
- **What:** Add GitHub Actions workflow or pre-commit hook that runs eval harness. Blocks merge if: intent accuracy < 92% OR MRR < 0.8 OR groundedness < 0.95.
- **Files:** `.github/workflows/eval_gate.yml` (or local script)
- **Verify:** Run workflow → passes if all thresholds met

---

## Phase 10: Acceptance Tests & E2E Scenarios (Day 10)

### 10.1 Implement J1: WISMO auto-resolve scenario
- **What:** Create test_j1_wismo_auto_resolve.py. Scenario: email message "Where is order ORDER-123?" → classify as order_status → extract ORDER_ID → retrieve context → generate response → validate (>= 0.95 groundedness) → respond in < 2s. No tool execution needed.
- **Files:** `services/api/tests/acceptance/test_j1_wismo_auto_resolve.py`
- **Verify:** Run test → passes, latency < 2s

### 10.2 Implement J2: Low-confidence escalation scenario
- **What:** Create test_j2_low_confidence_escalation.py. Scenario: ambiguous message → low intent confidence (< 0.7) → DecisionMatrix → L0 → escalate → create ticket + notify agent. Verify ticket created in DB.
- **Files:** `services/api/tests/acceptance/test_j2_low_confidence_escalation.py`
- **Verify:** Run test → passes, ticket created in database

### 10.3 Implement J3: Tool execution scenario
- **What:** Create test_j3_tool_execution.py. Scenario: chat message "Issue a $50 refund for order ORDER-123" → classify as refund → extract AMOUNT + ORDER_ID → DecisionMatrix → L2_CONFIRM (autonomy) → validate entities (>= 0.8 confidence) → execute refund tool → return confirmation. Verify idempotency (retry doesn't double-refund).
- **Files:** `services/api/tests/acceptance/test_j3_tool_execution.py`
- **Verify:** Run test → passes, refund executed once even on retry

### 10.4 Performance benchmarking
- **What:** Benchmark end-to-end latency (message in → response out) on all 3 scenarios. Target: p99 < 2s. Record results.
- **Files:** Integration with acceptance tests
- **Verify:** Latency metrics printed, all scenarios < 2s

### 10.5 Security & injection testing
- **What:** Add tests for: SQL injection patterns blocked by DecisionMatrix, XSS patterns flagged, prompt injection blocked, PII not leaked in response.
- **Files:** Augment test_j*.py with security test cases
- **Verify:** Injection tests pass (all attacks blocked)

---

## Dependency Requirements

### New dependencies to add to services/api/pyproject.toml:
```
langgraph>=0.0.20              # LangGraph orchestration
langchain>=0.1                 # LLM integrations
langchain-community>=0.0       # Community integrations
litellm>=1.0                   # LLM abstraction (Claude, etc.)
transformers>=4.30             # HuggingFace NER models
rank-bm25>=0.4.2              # BM25 keyword search
detoxify>=0.5                  # Toxicity detection
pgvector>=0.2                  # pgvector client
```

---

## Testing Strategy

**Total test coverage target:** 150+ unit + integration tests across all phases

| Phase | Test count | Key verifications |
|-------|-----------|-------------------|
| 3 (Entity) | 25+ | Extraction accuracy, cross-tenant isolation, entity validation, PII handling |
| 4 (RAG) | 15+ | Chunking, vector search, BM25, RRF fusion |
| 5 (Generation) | 10+ | LLM calls, groundedness, output validation, fallback |
| 6 (Tools) | 12+ | Tool registry, argument binding, autonomy gating, idempotency |
| 7 (LangGraph) | 8+ | Graph nodes, routing, end-to-end orchestration, checkpointing |
| 8 (Routing) | 10+ | Route selection, load balancing, SLA tracking, escalation |
| 9 (Evals) | N/A | Golden set evaluation, metric thresholds |
| 10 (Acceptance) | 3+ | J1, J2, J3 scenarios, latency benchmarks, security tests |

---

## Implementation Order & Dependencies

**Recommended implementation sequence (strict dependency order):**

1. **Phase 3 (Entity):** Must complete before Phase 6 (tools need validated entities)
   - Start with conftest.py fix (unblocks all tests)
   - Complete entity extraction, validation, linking

2. **Phase 4 (RAG):** Can start in parallel with Phase 3
   - Document chunking, vector/BM25 search, hybrid fusion

3. **Phase 5 (Generation):** Depends on Phase 4 (uses retrieved context)
   - LLM generation, groundedness scoring, output validation

4. **Phase 6 (Tools):** Depends on Phases 3 & 5
   - Entity binding to tool arguments, autonomy gating, tool execution

5. **Phase 7 (LangGraph):** Depends on Phases 3–6 (orchestrates all)
   - Build graph with all 8 nodes, endpoints, streaming

6. **Phase 8 (Routing):** Depends on Phase 7 (routes to agents after triage)
   - Routing engine, load balancer, SLA, escalation

7. **Phase 9 (Evals):** Runs in parallel, verifies Phases 3–5
   - Golden sets, evaluation harness, CI gates

8. **Phase 10 (Acceptance):** Depends on Phase 7 (uses full graph)
   - End-to-end scenarios J1, J2, J3, performance tests

---

## Verification Checklist per Phase

### Phase 3
- [ ] conftest.py imports fixed, all Phase 0–2 tests pass
- [ ] Entity extraction works (regex + ML fallback)
- [ ] Entity linker queries DB correctly (Shopify API mocked in tests)
- [ ] Entity validator gates low-confidence entities (< 0.8)
- [ ] autonomy_policies table wired into DecisionMatrix
- [ ] Cross-tenant isolation verified (tenant A order ≠ tenant B customer)
- [ ] 25+ tests pass, coverage >= 85%

### Phase 4
- [ ] Chunking preserves sentence boundaries
- [ ] Vector search returns top-k with scores
- [ ] BM25 returns keyword matches
- [ ] RRF fusion combines both search results
- [ ] 15+ tests pass

### Phase 5
- [ ] LLM client initialized, calls succeed (mocked)
- [ ] Groundedness scorer detects hallucinations (< 0.95)
- [ ] Output validator blocks toxicity + PII + injection
- [ ] Fallback templates return on validation fail
- [ ] 10+ tests pass

### Phase 6
- [ ] Tool registry has 6+ built-in tools
- [ ] Argument binder validates all required args present
- [ ] ToolExecutor gates on autonomy level
- [ ] Idempotency key prevents duplicate execution
- [ ] Saga compensation implemented for refund reversal
- [ ] 12+ tests pass

### Phase 7
- [ ] Graph has 8 nodes, compiles successfully
- [ ] Routing edges work (low conf → escalate, etc.)
- [ ] End-to-end run returns valid TriageState
- [ ] Checkpoint/resume works (InMemorySaver)
- [ ] POST /v1/triage/run endpoint works, latency < 2s
- [ ] Streaming returns reasoning steps
- [ ] 8+ integration tests pass

### Phase 8
- [ ] RoutingEngine picks lowest-queue agent
- [ ] LoadBalancer reclaims stale assignments
- [ ] SLATracker calculates deadlines correctly
- [ ] Escalation triggers on configured conditions
- [ ] 10+ tests pass

### Phase 9
- [ ] Golden dataset 50+ records created
- [ ] Intent eval: accuracy >= 92%
- [ ] Retrieval eval: MRR >= 0.8
- [ ] Response eval: groundedness >= 0.95
- [ ] CI gate blocks on threshold breach

### Phase 10
- [ ] J1 (WISMO auto-resolve): passes, latency < 2s
- [ ] J2 (escalation): ticket created, verified
- [ ] J3 (tool execution): refund executed once, idempotent
- [ ] Security tests pass (injection blocked, PII not leaked)
- [ ] p99 latency < 2s across all scenarios

---

## Key Decision: Per-Tenant Autonomy Policies

**Decision:** DecisionMatrix queries autonomy_policies table (per tenant, per intent) on each decide() call. If policy exists, it takes precedence over hard-coded rules. If table unavailable, falls back to hard-coded rules.

**Rationale:** Tenants must be able to customize autonomy levels without code changes. Example: Tenant A allows L3 auto-execute for order_status; Tenant B allows L1 only.

**Implementation:** Async method `DecisionMatrix.load_policies(db_session, tenant_id)` in Phase 3.5. Caching can be added later (Redis cache keyed by tenant_id + intent).

---

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| pgvector unavailable at runtime | In-memory numpy fallback (Phase 4) |
| LLM API failures | Exponential retry + safe fallback responses (Phase 5) |
| Tool execution idempotency failures | Explicit idempotency keys per tool call (Phase 6) |
| Cross-tenant data leaks | RLS policies + validator checks (Phase 3) |
| Low test coverage | 150+ tests + golden set evaluation (Phase 9) |
| Latency > 2s | Benchmark early, optimize hot paths (Phase 7–10) |

---

## Success Criteria (Sprint 2 Completion)

- ✅ All 10 phases implemented
- ✅ 150+ unit + integration tests, all passing
- ✅ Intent accuracy >= 92% on golden set
- ✅ Groundedness >= 0.95 on generated responses
- ✅ J1, J2, J3 acceptance scenarios pass
- ✅ End-to-end latency p99 < 2s
- ✅ Zero PII leaks, zero injection attacks
- ✅ Per-tenant autonomy policies wired into DecisionMatrix
- ✅ Entity verification gates tool binding on confidence >= 0.8
- ✅ Product, engineering, QA sign-offs obtained

---

## File Summary

**New files to create:** 40+  
**Modified files:** 5 (conftest.py, decision/matrix.py, pyproject.toml, entity/validator.py, API endpoints)  
**Test files:** 15+  
**Total lines of code (estimated):** 8,000–10,000  

---

**Plan prepared for implementation workflow**  
**Last updated:** 2024-11-01  
**Status:** Ready for Phase 3 start
