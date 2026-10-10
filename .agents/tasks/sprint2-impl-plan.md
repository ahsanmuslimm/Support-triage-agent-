# Sprint 2 Implementation Plan
**AI-Powered Support Triage Agent — Triage Graph & Classification Core**

**Document Version:** 1.0  
**Date:** October 2026  
**Target Duration:** 2 weeks (10 business days)  
**Team Size:** 2–3 developers  

---

## Executive Summary

Sprint 2 builds the **intelligent triage engine** that processes ingested messages into structured decisions. Grounded in Sprint 1's message ingestion pipeline and Sprint 0's database foundation, Sprint 2 implements:

1. **Multi-label intent classification** (k-NN + logistic regression over embeddings, ≥ 92% accuracy)
2. **Decision matrix** with autonomy levels L0–L3 (policy-driven, deterministic, 100% testable)
3. **Entity extraction & validation** (rule-based + ML NER, cross-tenant isolation)
4. **RAG pipeline** (document chunking, pgvector embedding search, hybrid BM25+semantic retrieval)
5. **Response generation & grounding** (LLM + groundedness guard, ≥ 0.95 target)
6. **Tool integration framework** (registry, argument binding, saga pattern, retry logic)
7. **LangGraph agent orchestration** (DAG with 8 nodes, routing, state machine)
8. **Routing & escalation engine** (skill-based, load-balanced, SLA tracking)
9. **Eval harness & golden sets** (intent, retrieval, response quality metrics)
10. **Acceptance gate** (end-to-end scenarios J1–J3, performance benchmarks, sign-offs)

**Out-of-the-box architecture:**
- **Classification**: Sentence-transformers embeddings (all-MiniLM-L6-v2, 384-dim) with temperature-scaled logistic head; deterministic keyword/fuzzy fallback
- **Decision**: Pure logic (no I/O), 30+ test cases, every path deterministic
- **Extraction**: Rule-based patterns (ORDER_ID, AMOUNT, EMAIL, PHONE) + ML NER fallback; PII pseudonymization
- **RAG**: pgvector semantic search + BM25 keyword search; RRF fusion; target MRR ≥ 0.8
- **Generation**: Claude Opus via LiteLLM; groundedness validation (≥ 0.95); toxicity, PII, injection guards
- **Tools**: Registry (refund, password_reset, cancel_order, etc.), argument binding from entities, autonomy gates, saga compensation
- **Graph**: LangGraph StateGraph (8 nodes, async execution, conditional routing, reasoning trail)
- **Routing**: Intent → skill required → agent with lowest queue; SLA tracking; stale assignment reclaim
- **Evals**: Golden sets (300+ intent, 150+ entity, 50+ response examples); CI integration; threshold gates
- **Acceptance**: 3 scenarios (WISMO auto-resolve, chat multi-intent, Zendesk refund+write-back); latency p99 < 2s; quality gates passing

**Success criteria:**
- Intent accuracy ≥ 92% top-1 on golden set
- Response groundedness ≥ 0.95 (no hallucinations)
- Triage latency p99 < 2s (end-to-end)
- All 3 acceptance scenarios passing
- Zero PII leaks, zero injection attacks
- All 10 deliverables implemented per spec
- Product, engineering, QA sign-offs obtained

---

## Architecture Decisions Recorded

| Decision | Rationale |
|---|---|
| **Embedding model: sentence-transformers/all-MiniLM-L6-v2** | Fast (33M params), accurate (MTEB top 5), multilingual, 384-dim suitable for pgvector. Pre-trained on NLI so captures intent semantics well. |
| **k-NN + temperature scaling for confidence** | Simple, interpretable, calibrated. Temperature scaling (ECE ≤ 0.05) ensures predicted confidences match actual accuracy. No need for complex ensemble early on; adds later if accuracy plateaus. |
| **Deterministic fallback (keyword/fuzzy)** | Guarantees graceful degradation if embedding model fails (OOM, tensor op crash). Fuzzy matching (Levenshtein) handles typos. No external dependencies in fallback. |
| **Decision matrix as pure logic (TDD)** | No I/O, no randomness in decision logic. Every rule deterministic and testable. Easy to audit, trace, and replay. Policy input document encapsulates all context needed. |
| **Entity validation before tool binding** | Unverified entities cannot bind to tools. Prevents injection attacks and typos from triggering refunds. Entities must have high confidence (≥ 0.8) and link to DB records (order exists, customer exists). |
| **Saga pattern for tool execution** | Idempotent tool calls (via idempotency keys) + compensation on failure. Ensures refund doesn't execute twice even if retry fires multiple times. |
| **LangGraph for orchestration** | Deterministic DAG vs. ReAct loops that may hallucinate. Explicit state machine (TriageState) carries context through nodes. Reasoning trail captured for audit. |
| **Hybrid retrieval (BM25 + semantic)** | BM25 excels at keyword matches (exact phrases, FAQ lookups); semantic excels at paraphrases and conceptual matches. RRF fusion combines both. Better recall than either alone. |
| **Groundedness guard (≥ 0.95)** | Blocks hallucinations before they reach customer. If claim can't be grounded in retrieved context, escalate instead of guessing. Conservative default; can loosen if eval shows no harm. |
| **Autonomy levels L0–L3** | Explicit gates: L0=read-only, L1=low-risk write, L2=medium-risk, L3=high-risk. Promotion based on accuracy (≥ 95%) + groundedness (≥ 0.95) + sample count (≥ 200). Auto-demotion on degradation (false-resolution > 5%). |
| **Eval-driven development** | Golden sets + threshold gates in CI. If new code drops intent accuracy below 92%, CI blocks the PR. Ensures quality doesn't regress. |
| **Multi-tenant isolation on extracted entities** | Cross-tenant leak prevention: entities are linked to specific tenant's records. Query to refund an order verifies order belongs to the customer's tenant. One misconfigured query can never leak order data across tenants. |
| **Per-intent autonomy policies** | Tenant can configure autonomy level per intent (refund=L2, order_status=L1, etc.). Enables gradual rollout: start conservative (L0), promote as confidence grows. |

---

## Monorepo & Package Layout (After Sprint 2)

**New directories created in Sprint 2:**

```
services/api/src/triage/
├── models/
│   ├── intent.py                    # S2.1: Intent taxonomy, IntentPrediction schema
│   ├── entity.py                    # S2.3: ExtractedEntity, EntityValidator
│   ├── decision.py                  # S2.2: PolicyInput, AutonomyLevel enum
│   ├── triage_state.py              # S2.7: TriageState Pydantic model (graph state)
│   ├── tool.py                      # S2.6: ToolSpec, ToolRegistry
│   ├── routing.py                   # S2.8: RoutingRule, SLADeadline
│   └── __init__.py
│
├── classification/                  # S2.1
│   ├── classifier.py                # IntentClassifier (k-NN + logistic head)
│   ├── fallback.py                  # FallbackIntentClassifier (keyword/fuzzy)
│   ├── temperature_scaler.py        # Temperature calibration (ECE minimization)
│   └── __init__.py
│
├── decision/                        # S2.2
│   ├── matrix.py                    # DecisionMatrix (30+ rules, pure logic)
│   ├── autonomy.py                  # AutonomyGate (enforcement), AutonomyPromoter
│   ├── promotion.py                 # Promotion workflow, criteria, demotion triggers
│   └── __init__.py
│
├── entity/                          # S2.3
│   ├── extractor.py                 # RuleBasedEntityExtractor (regex patterns)
│   ├── ml_extractor.py              # MLEntityExtractor (HuggingFace NER fallback)
│   ├── linker.py                    # EntityLinker (Shopify API, customer DB)
│   ├── validator.py                 # EntityValidator (confidence, cross-tenant, injection prevention)
│   ├── pii_redactor.py              # PIIRedactingExtractor (pseudonymization during extraction)
│   └── __init__.py
│
├── retrieval/                       # S2.4
│   ├── chunker.py                   # DocumentChunker (500 tokens, 100 overlap, semantic splits)
│   ├── vector_search.py             # VectorSearch (pgvector embedding lookup)
│   ├── bm25_search.py               # BM25Search (keyword matching, ranks documents)
│   ├── hybrid.py                    # HybridRetrieval (RRF fusion)
│   ├── ranker.py                    # RetrievalRanker (similarity scoring, relevance)
│   └── __init__.py
│
├── generation/                      # S2.5
│   ├── generator.py                 # ResponseGenerator (LLM + prompt template)
│   ├── groundedness.py              # GroundednessScorer (claim extraction + matching)
│   ├── validator.py                 # OutputValidator (toxicity, PII, injection, IAL filters)
│   ├── fallback.py                  # SafeResponseFallback (fallback on validation fail)
│   └── __init__.py
│
├── tools/                           # S2.6
│   ├── registry.py                  # ToolRegistry, ToolSpec definition
│   ├── executor.py                  # ToolExecutor (gate check, execute, log)
│   ├── argument_binder.py           # ArgumentBinder (entity → tool args)
│   ├── retry.py                     # RetryPolicy (exponential backoff, max 3 attempts)
│   ├── sagas.py                     # Saga pattern (compensation functions)
│   └── __init__.py
│
├── agent/                           # S2.7
│   ├── graph.py                     # TriageAgentGraph (LangGraph StateGraph)
│   ├── nodes.py                     # Node implementations (classify, extract, decide, gate, retrieve, generate, validate, execute, escalate)
│   ├── routing.py                   # Routing functions (route_on_autonomy, route_on_validation)
│   ├── executor.py                  # GraphExecutor (run_triage_agent, state initialization)
│   └── __init__.py
│
├── routing/                         # S2.8
│   ├── engine.py                    # RoutingEngine (intent → skill → agent)
│   ├── load_balancer.py             # LoadBalancer (queue size, rebalance, stale reclaim)
│   ├── sla.py                       # SLATracker (deadline calculation, breach detection)
│   ├── escalation.py                # EscalationTrigger (should_escalate, reasons)
│   └── __init__.py
│
├── api/
│   └── endpoints/
│       ├── triage.py                # S2.9: POST /v1/triage/simulate (dry-run endpoint)
│       └── __init__.py
│
└── tests/
    ├── test_classification.py       # S2.1 unit + integration tests
    ├── test_decision_matrix.py      # S2.2 unit tests (30+ rules)
    ├── test_entity_extraction.py    # S2.3 unit tests
    ├── test_retrieval.py            # S2.4 integration tests
    ├── test_generation.py           # S2.5 unit tests
    ├── test_tools.py                # S2.6 unit tests
    ├── test_agent_graph.py          # S2.7 integration tests
    ├── test_routing.py              # S2.8 unit tests
    ├── evals/
    │   ├── test_intent_eval.py      # S2.1 eval tests (golden set, ≥ 92% accuracy)
    │   ├── test_retrieval_eval.py   # S2.4 eval tests (MRR ≥ 0.8)
    │   ├── test_response_eval.py    # S2.5 eval tests (groundedness ≥ 0.95)
    │   ├── conftest.py              # Golden set fixtures, eval harness
    │   └── golden/
    │       ├── intents_v1.jsonl     # 300+ intent examples (S2.9)
    │       ├── entities_v1.jsonl    # 150+ entity extraction examples (S2.9)
    │       ├── conversations_v1.jsonl # 20 end-to-end scenarios (S2.9)
    │       └── injection_redteam.jsonl # 100 OWASP LLM Top 10 patterns (S2.2)
    └── acceptance/
        ├── test_j1_wismo_auto_resolve.py       # S2.10: J1 scenario
        ├── test_j2_chat_multi_intent.py        # S2.10: J2 scenario
        ├── test_j3_zendesk_refund_writeback.py # S2.10: J3 scenario
        └── conftest.py

packages/py_core/alembic/versions/
├── 0004_sprint2_triage_tables.py    # New migration: intent_embeddings, intent_examples, triage_runs, predictions, extracted_entities, generated_responses, autonomy_policies, autonomy_promotions, autonomy_demotions, routing_rules, agent_skills, tool_executions, knowledge_documents, knowledge_chunks

ml/
├── evals/
│   ├── golden/
│   │   ├── intents_v1.jsonl         # ✅ Created in S2.9
│   │   ├── entities_v1.jsonl        # ✅ Created in S2.9
│   │   ├── conversations_v1.jsonl   # ✅ Created in S2.9
│   │   └── injection_v1.jsonl       # ✅ Created in S2.2
│   ├── runners/
│   │   ├── intent_runner.py         # S2.1 eval runner
│   │   ├── retrieval_runner.py      # S2.4 eval runner
│   │   └── response_runner.py       # S2.5 eval runner
│   ├── reporters/
│   │   ├── intent_metrics.py        # Per-intent F1, macro-F1, ECE
│   │   ├── retrieval_metrics.py     # MRR, NDCG, Recall@k
│   │   └── response_metrics.py      # Groundedness, relevance, toxicity
│   └── tests/
│       ├── test_intent_classifier.py
│       ├── test_retrieval_eval.py
│       ├── test_response_generator.py
│       └── test_e2e_scenarios.py
```

---

## Database Migrations (Sprint 2)

**New migration: `0004_sprint2_triage_tables.py`**

```sql
-- Intent embeddings (for similarity search)
CREATE TABLE triage.intent_embeddings (
    tenant_id UUID PRIMARY KEY,
    intent_name VARCHAR(100) PRIMARY KEY,
    embedding vector(384),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    FOREIGN KEY (tenant_id) REFERENCES triage.tenants(id),
    UNIQUE(tenant_id, intent_name)
);
CREATE INDEX idx_intent_embeddings_vector ON triage.intent_embeddings USING ivfflat (embedding vector_cosine_ops);

-- Intent examples (training data for k-NN classifier)
CREATE TABLE triage.intent_examples (
    tenant_id UUID PRIMARY KEY,
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    intent_name VARCHAR(100) NOT NULL,
    example_text TEXT NOT NULL,
    is_golden BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    FOREIGN KEY (tenant_id) REFERENCES triage.tenants(id)
);
CREATE INDEX idx_intent_examples_intent ON triage.intent_examples(tenant_id, intent_name);

-- Triage runs (output of agent graph execution)
CREATE TABLE triage.triage_runs (
    tenant_id UUID PRIMARY KEY,
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id UUID NOT NULL,
    conversation_id UUID NOT NULL,
    top_intent VARCHAR(100),
    intent_confidence NUMERIC(3, 2),
    autonomy_level INTEGER,
    action VARCHAR(50), -- auto_resolve, escalate, tool_execute
    tool_executed VARCHAR(100),
    tool_result JSONB,
    latency_ms FLOAT,
    reasoning JSONB, -- Array of reasoning steps
    status VARCHAR(50), -- pending, completed, failed
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    FOREIGN KEY (tenant_id) REFERENCES triage.tenants(id),
    FOREIGN KEY (tenant_id, message_id) REFERENCES triage.messages(tenant_id, id),
    FOREIGN KEY (tenant_id, conversation_id) REFERENCES triage.conversations(tenant_id, id)
);
CREATE INDEX idx_triage_runs_message ON triage.triage_runs(tenant_id, message_id);
CREATE INDEX idx_triage_runs_conversation ON triage.triage_runs(tenant_id, conversation_id);

-- Extracted entities (from S2.3)
CREATE TABLE triage.extracted_entities (
    tenant_id UUID PRIMARY KEY,
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id UUID NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    value VARCHAR(255) NOT NULL,
    normalized_value VARCHAR(255),
    confidence NUMERIC(3, 2),
    linked_id BIGINT,
    is_pii BOOLEAN DEFAULT FALSE,
    pseudonym VARCHAR(255),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    FOREIGN KEY (tenant_id) REFERENCES triage.tenants(id),
    FOREIGN KEY (tenant_id, message_id) REFERENCES triage.messages(tenant_id, id)
);
CREATE INDEX idx_entities_message ON triage.extracted_entities(tenant_id, message_id);
CREATE INDEX idx_entities_type ON triage.extracted_entities(tenant_id, entity_type);

-- Generated responses (from S2.5)
CREATE TABLE triage.generated_responses (
    tenant_id UUID PRIMARY KEY,
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id UUID NOT NULL,
    intent VARCHAR(100),
    response_text TEXT,
    groundedness NUMERIC(3, 2),
    toxicity NUMERIC(3, 2),
    validation_passed BOOLEAN,
    validation_error TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    FOREIGN KEY (tenant_id) REFERENCES triage.tenants(id),
    FOREIGN KEY (tenant_id, message_id) REFERENCES triage.messages(tenant_id, id)
);

-- Autonomy policies (per-intent, per-tenant)
CREATE TABLE triage.autonomy_policies (
    tenant_id UUID PRIMARY KEY,
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    intent VARCHAR(100) NOT NULL,
    autonomy_level INTEGER NOT NULL CHECK (autonomy_level IN (0, 1, 2, 3)),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    FOREIGN KEY (tenant_id) REFERENCES triage.tenants(id),
    UNIQUE(tenant_id, intent)
);

-- Autonomy promotions (audit trail)
CREATE TABLE triage.autonomy_promotions (
    tenant_id UUID PRIMARY KEY,
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    intent VARCHAR(100) NOT NULL,
    from_level INTEGER NOT NULL,
    to_level INTEGER NOT NULL,
    accuracy NUMERIC(3, 2),
    groundedness NUMERIC(3, 2),
    sample_count INTEGER,
    admin_approved_by UUID,
    promoted_at TIMESTAMP NOT NULL DEFAULT NOW(),
    FOREIGN KEY (tenant_id) REFERENCES triage.tenants(id)
);

-- Tool executions (audit trail)
CREATE TABLE triage.tool_executions (
    tenant_id UUID PRIMARY KEY,
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL,
    tool_name VARCHAR(50) NOT NULL,
    arguments JSONB,
    result_status VARCHAR(50),
    result_data JSONB,
    error_message TEXT,
    autonomy_level INTEGER,
    executed_at TIMESTAMP NOT NULL DEFAULT NOW(),
    FOREIGN KEY (tenant_id) REFERENCES triage.tenants(id),
    FOREIGN KEY (tenant_id, customer_id) REFERENCES triage.customers(tenant_id, id)
);
CREATE INDEX idx_tool_executions_customer ON triage.tool_executions(tenant_id, customer_id);

-- Knowledge documents (S2.4)
CREATE TABLE triage.knowledge_documents (
    tenant_id UUID PRIMARY KEY,
    id BIGSERIAL PRIMARY KEY,
    title VARCHAR(255),
    url VARCHAR(255),
    content TEXT,
    source VARCHAR(50),
    last_updated TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    FOREIGN KEY (tenant_id) REFERENCES triage.tenants(id)
);

-- Knowledge chunks (embedded for RAG)
CREATE TABLE triage.knowledge_chunks (
    tenant_id UUID PRIMARY KEY,
    id BIGSERIAL PRIMARY KEY,
    doc_id BIGINT NOT NULL,
    text TEXT NOT NULL,
    embedding vector(384),
    tokens INTEGER,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    FOREIGN KEY (tenant_id) REFERENCES triage.tenants(id),
    FOREIGN KEY (tenant_id, doc_id) REFERENCES triage.knowledge_documents(tenant_id, id)
);
CREATE INDEX idx_knowledge_chunks_embedding ON triage.knowledge_chunks USING ivfflat (embedding vector_cosine_ops);

-- Routing rules (per-tenant, per-intent)
CREATE TABLE triage.routing_rules (
    tenant_id UUID PRIMARY KEY,
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    intent VARCHAR(100) NOT NULL,
    skill_required VARCHAR(100),
    priority INTEGER,
    max_wait_secs INTEGER,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    FOREIGN KEY (tenant_id) REFERENCES triage.tenants(id),
    UNIQUE(tenant_id, intent)
);

-- Agent skills (per-tenant agent)
CREATE TABLE triage.agent_skills (
    tenant_id UUID PRIMARY KEY,
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID NOT NULL,
    skill VARCHAR(100),
    proficiency_level INTEGER,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    FOREIGN KEY (tenant_id) REFERENCES triage.tenants(id),
    UNIQUE(tenant_id, agent_id, skill)
);
```

---

## Dependencies to Add

**services/api/pyproject.toml** (add to existing `dependencies`):

```toml
langgraph>=0.0.20              # Agent orchestration
sentence-transformers>=2.2     # Embedding model
scikit-learn>=1.3              # Temperature scaling, k-NN
spacy>=3.7                     # NLP preprocessing (optional, fallback)
langchain>=0.1                 # LLM integrations
langchain-community>=0.0       # Community integrations
litellm>=1.0                   # LLM abstraction (Claude, GPT-4, etc.)
asyncpg>=0.29                  # PostgreSQL async driver
pgvector>=0.2                  # pgvector Python client
redis>=5.0                     # Caching, locks
detoxify>=0.5                  # Toxicity detection
```

---

## Implementation Plan (Ordered by Dependency)

### Phase 0: Database & Model Foundations (Day 0–0.5)

- [ ] **0.1 Create Alembic migration 0004 (Sprint 2 tables)**
  - **What:** Migration adds all new tables: intent_embeddings, intent_examples, triage_runs, extracted_entities, generated_responses, autonomy_policies, autonomy_promotions, tool_executions, knowledge_documents, knowledge_chunks, routing_rules, agent_skills. All tables have tenant_id foreign key + RLS policy. Indexes on vector columns for pgvector search.
  - **Files:** `packages/py_core/alembic/versions/0004_sprint2_triage_tables.py`
  - **Verify:** Run `alembic upgrade head`. Verify in psql: `\d triage.intent_embeddings`, `\d triage.knowledge_chunks`. Indexes present: `\di triage.idx_*vector*`. Apply RLS policies: `SELECT schemaname, tablename FROM pg_tables WHERE tablename IN ('intent_embeddings', 'knowledge_chunks', ...) AND schemaname = 'triage'` returns all 11 tables.

- [ ] **0.2 Define Pydantic models for Sprint 2 data structures**
  - **What:** Create models: `Intent`, `IntentPrediction`, `TriageState` (mutable dataclass), `PolicyInput`, `ExtractedEntity`, `ToolSpec`, `RoutingRule`, `SLADeadline`. Ensure all are serializable (for DB/audit logging) and compatible with LangGraph state. `TriageState` fields include: message_id, message_text, customer_id, tenant_id, channel, intents (list), top_intent, intent_confidence, entities, customer_ial, autonomy_level, retrieved_chunks, response_text, response_valid, validation_error, action, tool_to_execute, tool_args, tool_result, reasoning (list), latency_ms.
  - **Files:** `services/api/src/triage/models/intent.py`, `services/api/src/triage/models/decision.py`, `services/api/src/triage/models/entity.py`, `services/api/src/triage/models/triage_state.py`, `services/api/src/triage/models/tool.py`, `services/api/src/triage/models/routing.py`
  - **Verify:** `pytest services/api/tests/test_models.py -v`. All models instantiate; serialization round-trips (model → dict → model); TriageState passes to LangGraph StateGraph without errors.

### Phase 1: Intent Classification (Day 1–2)

- [ ] **1.1 Implement IntentClassifier (embedding + k-NN + logistic head)**
  - **What:** Create `IntentClassifier` in `services/api/src/triage/classification/classifier.py`. Load sentence-transformers model (`all-MiniLM-L6-v2`). On init, compute intent embeddings from `intent_examples` table (average of training examples per intent). On classify: embed message, compute similarity to all intent embeddings, apply temperature scaling (default T=1.2), threshold at 0.1 confidence, return top-k intents with calibrated confidences.
  - **Files:** `services/api/src/triage/classification/classifier.py`
  - **Verify:** Unit test: classify("Where is order ORDER-123?") → intent="order_status", confidence ≥ 0.9. Test multi-label: classify("I want a refund and my account won't work") → intents=["refund", "account_issue"], both confidence ≥ 0.1. Verify confidence sum ≈ 1.0. Benchmark: `pytest --benchmark-only` shows inference time < 100ms.

- [ ] **1.2 Implement FallbackIntentClassifier (keyword/fuzzy matching)**
  - **What:** Create `FallbackIntentClassifier` in `services/api/src/triage/classification/fallback.py`. Implement keyword matching (exact substring in intent examples) and Levenshtein fuzzy matching (distance threshold ≤ 3). No external dependencies (no embeddings). Returns intent or "other" fallback. Confidence 0.5–1.0 based on match quality.
  - **Files:** `services/api/src/triage/classification/fallback.py`
  - **Verify:** Unit test: fallback("refund") matches "refund" intent, confidence=1.0. Test fuzzy: fallback("refund") with typo ("refund") still matches. Test no match: fallback("xyzabc") returns intent="other", confidence=0.5.

- [ ] **1.3 Implement TemperatureScaler (ECE calibration)**
  - **What:** Create `TemperatureScaler` in `services/api/src/triage/classification/temperature_scaler.py`. On initialization, sweep temperatures [0.5, 0.7, 1.0, 1.2, 1.5, 2.0] on validation set (e.g., last 200 intent examples). Pick T that minimizes Expected Calibration Error (ECE = average |accuracy - confidence| across bins). Store optimal T in database or config.
  - **Files:** `services/api/src/triage/classification/temperature_scaler.py`
  - **Verify:** Unit test: ECE on gold set before scaling ≥ 0.15, after scaling ≤ 0.05. Test property: ECE is non-negative and ≤ 1.0.

- [ ] **1.4 Integrate classifier into ingestion pipeline**
  - **What:** After message ingested (S1.2), trigger intent classification. Store result in `message_intents` table (intent_name, confidence). Denormalize `top_intent` in `messages` table for quick lookup. Log via structlog.
  - **Files:** Modify `services/api/src/triage/ingestion/*.py` to call `IntentClassifier.classify(message_text)` after message stored.
  - **Verify:** Integration test: ingest message → check `message_intents` table has row with correct intent + confidence. Verify denormalized `top_intent` in messages table.

- [ ] **1.5 Write unit tests for classification (≥ 90% coverage)**
  - **What:** Test cases: (1) classify with high confidence (order status), (2) low confidence (near-tie), (3) multi-label, (4) fallback on model failure, (5) confidence calibration, (6) edge cases (empty message, special chars). Use golden set examples.
  - **Files:** `services/api/tests/test_classification.py`
  - **Verify:** `pytest services/api/tests/test_classification.py -v --cov=services/api/src/triage/classification --cov-report=term-missing`. Coverage ≥ 90%. All tests pass.

### Phase 2: Decision Matrix & Autonomy (Day 2–3)

- [ ] **2.1 Implement DecisionMatrix (30+ rules, pure logic)**
  - **What:** Create `DecisionMatrix` in `services/api/src/triage/decision/matrix.py`. Implement all 30+ rules from spec (intent confidence ≥ 0.9, security flags → L0, fraud flags → L0, IAL gates, financial limits, tool-specific rules, etc.). Every rule is a pure function: PolicyInput → (autonomy_level, reason). No I/O. Return tuple (level: int, reason: str).
  - **Files:** `services/api/src/triage/decision/matrix.py`
  - **Verify:** Unit tests: 30+ test cases, one per rule, all pass. Property test: same input → same output (determinism). Edge case: message at exact thresholds (confidence = 0.9, amount = $50).

- [ ] **2.2 Implement AutonomyGate (enforcement at execution time)**
  - **What:** Create `AutonomyGate` in `services/api/src/triage/decision/autonomy.py`. Implement `execute_tool()` method: check autonomy_level against tool_required_level; block if too low; execute if allowed. Gate logic: L0 blocks all, L1 allows safe idempotent tools, L2 allows refunds < $500, L3 allows all.
  - **Files:** `services/api/src/triage/decision/autonomy.py`
  - **Verify:** Unit test: attempt refund > $500 with L2 → blocked. Attempt create_ticket with L1 → allowed. Attempt account_delete with L2 → blocked.

- [ ] **2.3 Implement AutonomyPromoter (promotion/demotion workflow)**
  - **What:** Create `AutonomyPromoter` in `services/api/src/triage/decision/promotion.py`. Implement `should_promote()`: check intent accuracy ≥ 95%, groundedness ≥ 0.95, sample_count ≥ 200, admin signed off, no demotion in last 7 days, no flips. Implement `should_demote()`: check false-resolution rate > 5%, groundedness < 0.85, injection attempts > 10/day. Both return (bool, reason).
  - **Files:** `services/api/src/triage/decision/promotion.py`
  - **Verify:** Unit test: metrics above thresholds → promotion approved. Metrics below → promotion blocked. Demotion triggers fire on degradation.

- [ ] **2.4 Write unit tests for decision matrix (Tier A, ≥ 95% coverage)**
  - **What:** 30+ test cases (one per rule), edge cases, property tests (determinism). Hypothesis-based property tests: random PolicyInput → always valid decision output.
  - **Files:** `services/api/tests/test_decision_matrix.py`
  - **Verify:** `pytest services/api/tests/test_decision_matrix.py -v --cov=services/api/src/triage/decision`. Coverage ≥ 95%. All tests pass. Hypothesis finds no counterexamples.

### Phase 3: Entity Extraction & Validation (Day 3–4)

- [ ] **3.1 Implement RuleBasedEntityExtractor (regex patterns)**
  - **What:** Create `RuleBasedEntityExtractor` in `services/api/src/triage/entity/extractor.py`. Implement regex patterns for: ORDER_ID (`ORDER-\d+`), AMOUNT (`\$\d+\.\d{2}`), EMAIL, PHONE (E.164 normalized), ACCOUNT_ID, CREDIT_CARD (masked), SSN (masked). Extract with `re.finditer()`, return list of `ExtractedEntity` with confidence=0.95 (rules are high-confidence).
  - **Files:** `services/api/src/triage/entity/extractor.py`
  - **Verify:** Unit test: extract from "I want to refund order ORDER-123 for $49.99" → [ORDER_ID, AMOUNT]. Test normalization: phone "555-1234" → E.164 format. Test PII: credit card detected and flagged.

- [ ] **3.2 Implement MLEntityExtractor (HuggingFace NER fallback)**
  - **What:** Create `MLEntityExtractor` in `services/api/src/triage/entity/ml_extractor.py`. Load model `dslim/bert-base-multilingual-cased-ner-hrl` via `transformers.pipeline("ner")`. Extract entities with `aggregation_strategy="simple"`. Map HF label tags to custom types. Confidence from model scores.
  - **Files:** `services/api/src/triage/entity/ml_extractor.py`
  - **Verify:** Unit test: extract from message with named entities. Verify confidence scores are in [0, 1].

- [ ] **3.3 Implement EntityLinker (Shopify + customer DB)**
  - **What:** Create `EntityLinker` in `services/api/src/triage/entity/linker.py`. Implement `link()` for ORDER_ID (call Shopify API, fetch order), EMAIL (query customers table), PHONE (query customers table). If found, store `linked_id`. If not found, return None (unverified entity). Async operations.
  - **Files:** `services/api/src/triage/entity/linker.py`
  - **Verify:** Integration test (with fake Shopify): extract ORDER_ID "ORDER-123" → link to Shopify order → linked_id set.

- [ ] **3.4 Implement EntityValidator (cross-tenant, injection prevention)**
  - **What:** Create `EntityValidator` in `services/api/src/triage/entity/validator.py`. Implement `validate_for_tool()`: check confidence ≥ 0.8, linked entity exists, cross-tenant isolation (order belongs to customer's tenant), amount in valid range. Return (bool, reason).
  - **Files:** `services/api/src/triage/entity/validator.py`
  - **Verify:** Unit test: attempt to bind unverified entity (confidence 0.6) → rejected. Attempt cross-tenant leak (order from other tenant) → rejected. Valid entity → accepted.

- [ ] **3.5 Implement PIIRedactingExtractor (pseudonymization)**
  - **What:** Create `PIIRedactingExtractor` in `services/api/src/triage/entity/pii_redactor.py`. On extract, detect PII entities (CREDIT_CARD, SSN, PASSWORD) and replace with vault tokens (VAULT_xyz123...). Store mapping in pii_tokens table. Return (entities, redacted_text) tuple. Redacted text safe for LLM processing.
  - **Files:** `services/api/src/triage/entity/pii_redactor.py`
  - **Verify:** Unit test: extract from "My SSN is 123-45-6789" → SSN detected, pseudonym created, text redacted to "My SSN is VAULT_xyz..."

- [ ] **3.6 Write unit tests for entity extraction (≥ 90% coverage)**
  - **What:** Test all entity types, normalization, linking, validation, PII redaction. Edge cases: malformed input, cross-tenant attempts, injection patterns.
  - **Files:** `services/api/tests/test_entity_extraction.py`
  - **Verify:** Coverage ≥ 90%. All tests pass.

### Phase 4: RAG Pipeline (Day 4–5)

- [ ] **4.1 Implement DocumentChunker (semantic splits, overlap)**
  - **What:** Create `DocumentChunker` in `services/api/src/triage/retrieval/chunker.py`. Split documents into 500-token chunks with 100-token overlap. Use sentence-level boundaries to preserve semantics. Support markdown headers and FAQ Q&A pairs as split points. Annotate chunks with doc_id, source. Return list of chunks.
  - **Files:** `services/api/src/triage/retrieval/chunker.py`
  - **Verify:** Unit test: chunk document with 1500 tokens → 3 overlapping chunks of ~500 tokens each. Verify overlap preserved (last 100 tokens of chunk 1 = first 100 of chunk 2).

- [ ] **4.2 Implement VectorSearch (pgvector lookups)**
  - **What:** Create `VectorSearch` in `services/api/src/triage/retrieval/vector_search.py`. Implement `index_chunks()` to embed chunks and store in pgvector. Implement `retrieve()` to query pgvector with cosine distance operator (`<=>`) and return top-k. Use `1 - distance` as similarity score.
  - **Files:** `services/api/src/triage/retrieval/vector_search.py`
  - **Verify:** Integration test: index 100 document chunks → query with related text → retrieve top-5 includes correct chunks.

- [ ] **4.3 Implement BM25Search (keyword matching)**
  - **What:** Create `BM25Search` in `services/api/src/triage/retrieval/bm25_search.py`. Use `rank_bm25` Python library or PostgreSQL full-text search (`tsvector`). Index chunks on ingestion. On query, rank by BM25 score, return top-k.
  - **Files:** `services/api/src/triage/retrieval/bm25_search.py`
  - **Verify:** Integration test: index chunks → search for exact keywords → top results include relevant chunks.

- [ ] **4.4 Implement HybridRetrieval (RRF fusion)**
  - **What:** Create `HybridRetrieval` in `services/api/src/triage/retrieval/hybrid.py`. Combine BM25 + semantic search via Reciprocal Rank Fusion: score = 1/(60 + rank_bm25) + 1/(60 + rank_semantic). Merge rankings, return top-k fused results.
  - **Files:** `services/api/src/triage/retrieval/hybrid.py`
  - **Verify:** Unit test: mock BM25 and semantic searches → RRF fusion combines correctly. Verify constant 60 in denominator.

- [ ] **4.5 Write unit tests for retrieval (≥ 85% coverage)**
  - **What:** Test chunking, vector indexing/search, BM25 search, fusion. Integration test: index knowledge base → query → retrieve correct documents.
  - **Files:** `services/api/tests/test_retrieval.py`
  - **Verify:** Coverage ≥ 85%. All tests pass.

### Phase 5: Response Generation & Grounding (Day 5–6)

- [ ] **5.1 Implement ResponseGenerator (LLM + context)**
  - **What:** Create `ResponseGenerator` in `services/api/src/triage/generation/generator.py`. Use LiteLLM to call Claude Opus (configurable). Build prompt with retrieved chunks as ground truth. Temperature=0.3 for consistency. Max tokens 200. Return response text.
  - **Files:** `services/api/src/triage/generation/generator.py`
  - **Verify:** Unit test (with FakeLLM): generate response with ground-truth chunks → response includes information from chunks.

- [ ] **5.2 Implement GroundednessScorer (claim extraction + matching)**
  - **What:** Create `GroundednessScorer` in `services/api/src/triage/generation/groundedness.py`. Extract factual claims from response (simple NLP or LLM-based). Check each claim against retrieved context via keyword/semantic match. Compute groundedness = 1 - (ungrounded_claims / total_claims). Return (score, ungrounded_claims).
  - **Files:** `services/api/src/triage/generation/groundedness.py`
  - **Verify:** Unit test: response "Order shipped on Oct 1" with chunk containing "Oct 1" → groundedness=1.0. Response mentioning invented fact "arrives Oct 10" without supporting context → ungrounded claim detected.

- [ ] **5.3 Implement OutputValidator (toxicity, PII, injection, IAL filters)**
  - **What:** Create `OutputValidator` in `services/api/src/triage/generation/validator.py`. Implement checks: (1) Groundedness ≥ 0.9 (block if lower), (2) Toxicity < 0.1 (use Detoxify library), (3) PII leak detection (regex for SSN/CC patterns), (4) Injection patterns (SQL, XSS, LLM prompt injection), (5) IAL-aware filters (e.g., don't discuss passwords with IAL < 2). Return (bool, reason).
  - **Files:** `services/api/src/triage/generation/validator.py`
  - **Verify:** Unit test: valid response → passes all checks. Response with hallucination → rejected. Response with toxic content → rejected. Response disclosing password to unverified customer → rejected.

- [ ] **5.4 Implement SafeResponseFallback (fallback on validation failure)**
  - **What:** Create `SafeResponseFallback` in `services/api/src/triage/generation/fallback.py`. Implement `get_safe_response()` to return templated safe responses like "I don't have enough information. Let me connect you with a specialist." based on validation failure reason.
  - **Files:** `services/api/src/triage/generation/fallback.py`
  - **Verify:** Unit test: on groundedness failure → fallback message returned.

- [ ] **5.5 Write unit tests for generation (≥ 85% coverage)**
  - **What:** Test response generation, groundedness scoring, output validation, fallback. Use golden response examples.
  - **Files:** `services/api/tests/test_generation.py`
  - **Verify:** Coverage ≥ 85%. All tests pass.

### Phase 6: Tool Integration Framework (Day 6)

- [ ] **6.1 Implement ToolRegistry & ToolSpec**
  - **What:** Create `ToolRegistry` in `services/api/src/triage/tools/registry.py`. Define `ToolSpec` with name, description, arguments, required_autonomy_level, required_ial, idempotent, compensation, estimated_cost. Pre-register 5+ tools: refund, password_reset, cancel_order, create_ticket, add_internal_note. Return tool by name or list all.
  - **Files:** `services/api/src/triage/tools/registry.py`
  - **Verify:** Unit test: get_tool("refund") returns ToolSpec; required_autonomy_level=2; arguments includes order_id, amount.

- [ ] **6.2 Implement ArgumentBinder (entity → tool args)**
  - **What:** Create `ArgumentBinder` in `services/api/src/triage/tools/argument_binder.py`. Implement `bind_arguments()` to match extracted entities to tool arguments by entity_type. Check autonomy level allows tool. Return (bound_args_dict, reason) or (None, error_reason).
  - **Files:** `services/api/src/triage/tools/argument_binder.py`
  - **Verify:** Unit test: extract entities [ORDER_ID="123", AMOUNT="50"] → bind to refund tool → bound_args={"order_id": "123", "amount": 50}. Missing required arg → error.

- [ ] **6.3 Implement ToolExecutor (execute with saga pattern)**
  - **What:** Create `ToolExecutor` in `services/api/src/triage/tools/executor.py`. Implement `execute_tool()`: autonomy gate check → execute → log → on failure, call compensation (undo). Use idempotency keys for refund operations. Return (status, result).
  - **Files:** `services/api/src/triage/tools/executor.py`
  - **Verify:** Unit test (with FakeShopify): execute refund → idempotency key prevents double-refund on retry.

- [ ] **6.4 Implement RetryPolicy (exponential backoff)**
  - **What:** Create `RetryPolicy` in `services/api/src/triage/tools/retry.py`. Implement `execute_with_retry()` with exponential backoff (2^attempt seconds), max 3 attempts. Log each retry.
  - **Files:** `services/api/src/triage/tools/retry.py`
  - **Verify:** Unit test: mock failure on first attempt, success on second → verify backoff timing.

- [ ] **6.5 Write unit tests for tools (≥ 90% coverage)**
  - **What:** Test tool registry, argument binding, execution, compensation, retry logic.
  - **Files:** `services/api/tests/test_tools.py`
  - **Verify:** Coverage ≥ 90%. All tests pass.

### Phase 7: LangGraph Agent Orchestration (Day 7)

- [ ] **7.1 Build LangGraph StateGraph with 8 nodes**
  - **What:** Create `TriageAgentGraph` in `services/api/src/triage/agent/graph.py`. Define StateGraph(TriageState). Add nodes: classify_intent, extract_entities, decide_autonomy, retrieve_context, generate_response, validate_output, execute_tool, escalate. Add edges and conditional routing. Compile graph with Postgres checkpointer for durability.
  - **Files:** `services/api/src/triage/agent/graph.py`
  - **Verify:** Unit test: graph compiles without error. Verify DAG structure: all paths end in escalate or END.

- [ ] **7.2 Implement node functions (classify, extract, decide, etc.)**
  - **What:** Create `services/api/src/triage/agent/nodes.py` with async node functions: `node_classify_intent()`, `node_extract_entities()`, `node_decide_autonomy()`, `node_retrieve_context()`, `node_generate_response()`, `node_validate_output()`, `node_execute_tool()`, `node_escalate()`. Each updates state and reasoning trail.
  - **Files:** `services/api/src/triage/agent/nodes.py`
  - **Verify:** Unit test: each node executes, updates state correctly, returns dict for graph.

- [ ] **7.3 Implement routing functions (autonomy-based, validation-based)**
  - **What:** Create routing functions in `services/api/src/triage/agent/routing.py`: `route_on_autonomy()` (L0→read_only, L2+→tool_execute, else→escalate), `route_on_validation()` (valid→END, invalid→escalate).
  - **Files:** `services/api/src/triage/agent/routing.py`
  - **Verify:** Unit test: autonomy_level=0 → route_on_autonomy()="escalate". validation_passed=False → route_on_validation()="escalate".

- [ ] **7.4 Implement GraphExecutor (run_triage_agent end-to-end)**
  - **What:** Create `GraphExecutor` in `services/api/src/triage/agent/executor.py`. Implement `run_triage_agent()`: initialize TriageState, compile graph, invoke with input, measure latency, store result in DB.
  - **Files:** `services/api/src/triage/agent/executor.py`
  - **Verify:** Integration test: run full graph → result stored in triage_runs table → latency_ms < 2000.

- [ ] **7.5 Write integration tests for graph (≥ 80% coverage)**
  - **What:** Test each node, routing logic, full end-to-end flow. Mock all downstream dependencies (LLM, Shopify, etc.).
  - **Files:** `services/api/tests/test_agent_graph.py`
  - **Verify:** Coverage ≥ 80%. All tests pass.

### Phase 8: Routing & Escalation Engine (Day 7–8)

- [ ] **8.1 Implement RoutingEngine (intent → skill → agent)**
  - **What:** Create `RoutingEngine` in `services/api/src/triage/routing/engine.py`. Implement `route()`: look up routing rule by intent, find agents with matching skill, pick agent with lowest queue size. Return agent_id.
  - **Files:** `services/api/src/triage/routing/engine.py`
  - **Verify:** Unit test: route "refund" intent → billing agents → pick agent with queue_size=1 over queue_size=3.

- [ ] **8.2 Implement LoadBalancer (queue size, rebalance, reclaim)**
  - **What:** Create `LoadBalancer` in `services/api/src/triage/routing/load_balancer.py`. Implement `get_agent_metrics()`, `rebalance()` (reclaim stale assignments > 15 min), `find_best_agent()`.
  - **Files:** `services/api/src/triage/routing/load_balancer.py`
  - **Verify:** Unit test: find_best_agent() returns agent with min queue.

- [ ] **8.3 Implement SLATracker (deadline, breach detection)**
  - **What:** Create `SLATracker` in `services/api/src/triage/routing/sla.py`. Implement `track_escalation()` to set SLA deadline. Implement `check_sla_breaches()` to find past-deadline conversations and flag them.
  - **Files:** `services/api/src/triage/routing/sla.py`
  - **Verify:** Unit test: escalate with rule max_wait_secs=300 → deadline=now+300s. Verify breach detection on past deadline.

- [ ] **8.4 Implement EscalationTrigger (should_escalate, reasons)**
  - **What:** Create `EscalationTrigger` in `services/api/src/triage/routing/escalation.py`. Check: intent_confidence < 0.8, validation_failed, autonomy_level=0, repeat customer, angry tone. Return (bool, reasons).
  - **Files:** `services/api/src/triage/routing/escalation.py`
  - **Verify:** Unit test: confidence=0.7 → should_escalate=True. All conditions passing → should_escalate=False.

- [ ] **8.5 Write unit tests for routing (≥ 85% coverage)**
  - **What:** Test routing rules, load balancing, SLA tracking, escalation triggers.
  - **Files:** `services/api/tests/test_routing.py`
  - **Verify:** Coverage ≥ 85%. All tests pass.

### Phase 9: Eval Harness & Golden Sets (Day 8–9)

- [ ] **9.1 Curate golden sets (150+ examples)**
  - **What:** Create golden datasets in `ml/evals/golden/`:
    - `intents_v1.jsonl`: 300 intent examples (diverse intents, edge cases, multi-label)
    - `entities_v1.jsonl`: 150 entity extraction examples
    - `conversations_v1.jsonl`: 20 end-to-end scenarios (J1–J3 + variants)
    - `injection_v1.jsonl`: 100 OWASP LLM Top 10 attack patterns
  - **Files:** `ml/evals/golden/intents_v1.jsonl`, `ml/evals/golden/entities_v1.jsonl`, `ml/evals/golden/conversations_v1.jsonl`, `ml/evals/golden/injection_v1.jsonl`
  - **Verify:** Load each file → parse JSONL → verify schema (text, expected_intent, etc.).

- [ ] **9.2 Implement IntentEvaluator (accuracy, macro-F1, ECE)**
  - **What:** Create `IntentEvaluator` in `ml/evals/runners/intent_runner.py`. Evaluate classifier on golden set. Compute: accuracy (top-1), macro-F1 (per-intent), ECE (calibration). Report per-intent metrics.
  - **Files:** `ml/evals/runners/intent_runner.py`
  - **Verify:** Run on golden set → accuracy ≥ 0.92, macro-F1 ≥ 0.88, ECE ≤ 0.05.

- [ ] **9.3 Implement RetrievalEvaluator (MRR, NDCG, Recall@k)**
  - **What:** Create `RetrievalEvaluator` in `ml/evals/runners/retrieval_runner.py`. Compute MRR (position of first relevant chunk), NDCG (discounted gains), Recall@5.
  - **Files:** `ml/evals/runners/retrieval_runner.py`
  - **Verify:** Run on golden set → MRR ≥ 0.8, Recall@5 ≥ 0.85.

- [ ] **9.4 Implement ResponseEvaluator (groundedness, relevance, toxicity)**
  - **What:** Create `ResponseEvaluator` in `ml/evals/runners/response_runner.py`. Evaluate responses on: groundedness ≥ 0.95, relevance (query-response similarity) ≥ 0.90, toxicity < 0.1.
  - **Files:** `ml/evals/runners/response_runner.py`
  - **Verify:** Run on golden set → all metrics pass gates.

- [ ] **9.5 Implement EvalGate (threshold gates for CI)**
  - **What:** Create `EvalGate` in `ml/evals/conftest.py`. Implement gates: intent_accuracy ≥ 0.92, macro_f1 ≥ 0.88, groundedness ≥ 0.95, relevance ≥ 0.90, toxicity ≤ 0.10. Block PR if any gate fails.
  - **Files:** `ml/evals/conftest.py`
  - **Verify:** Run pytest → gates pass on good model, fail on degraded model (e.g., random predictions).

- [ ] **9.6 Write eval tests and CI integration (S2.9)**
  - **What:** Create `ml/evals/tests/`: test_intent_classifier.py, test_retrieval_eval.py, test_response_generator.py. Add `.github/workflows/eval.yml` to run evals on every PR.
  - **Files:** `ml/evals/tests/test_intent_classifier.py`, `.github/workflows/eval.yml`
  - **Verify:** `pytest ml/evals/tests/ -v` runs all evals. GitHub Actions workflow triggers on PR. Gates block if accuracy drops.

### Phase 10: Acceptance Gate & Sign-Off (Day 9–10)

- [ ] **10.1 Implement J1 acceptance test (WISMO auto-resolve)**
  - **What:** Create `services/api/tests/acceptance/test_j1_wismo_auto_resolve.py`. Scenario: customer emails about order status → intent classified → entity extracted → autonomy L1 → response generated → auto-resolved. Assert: status=RESOLVED, latency < 2s.
  - **Files:** `services/api/tests/acceptance/test_j1_wismo_auto_resolve.py`
  - **Verify:** Test passes end-to-end.

- [ ] **10.2 Implement J2 acceptance test (chat multi-intent)**
  - **What:** Create `services/api/tests/acceptance/test_j2_chat_multi_intent.py`. Scenario: web chat, 3 messages coalesce → 2 intents → escalate to agent. Assert: conversation status=escalated, agent assigned, SLA set.
  - **Files:** `services/api/tests/acceptance/test_j2_chat_multi_intent.py`
  - **Verify:** Test passes end-to-end.

- [ ] **10.3 Implement J3 acceptance test (Zendesk refund+write-back)**
  - **What:** Create `services/api/tests/acceptance/test_j3_zendesk_refund_writeback.py`. Scenario: Zendesk ticket comment → refund tool executed → internal note written back. Assert: tool executed, write-back present.
  - **Files:** `services/api/tests/acceptance/test_j3_zendesk_refund_writeback.py`
  - **Verify:** Test passes end-to-end.

- [ ] **10.4 Measure performance (latency benchmarks)**
  - **What:** Run `pytest --benchmark-only` to measure: intent inference latency, retrieval latency, response generation latency, full triage end-to-end latency. Report p50, p95, p99.
  - **Files:** Create benchmark fixture in conftest.py.
  - **Verify:** p99 latency < 2s for full triage.

- [ ] **10.5 Verify quality gates (intent accuracy, groundedness)**
  - **What:** Run eval harness: `pytest ml/evals/tests/ -v`. Verify: intent accuracy ≥ 92%, groundedness ≥ 0.95, all gates passing.
  - **Verify:** All gates pass.

- [ ] **10.6 Collect sign-offs**
  - **What:** Create sign-off checklist in `.agents/tasks/sprint2-review.json`. Gather:
    - Product: J1–J3 scenarios working, intent taxonomy reviewed, response quality reviewed
    - Engineering: All S2.1–S2.9 implemented, code reviewed, ≥ 80% test coverage, no critical bugs, CI passing
    - QA: Acceptance tests passing, performance benchmarks met, quality gates passing, edge cases tested, no PII leaks
  - **Files:** `.agents/tasks/sprint2-review.json`
  - **Verify:** All sign-offs obtained (verdict="APPROVED").

---

## Test Strategy (All Tiers)

### Tier A: Unit Tests (≥ 80% code coverage per module)
- Intent classification: accuracy, calibration, fallback
- Decision matrix: all 30+ rules, edge cases, property tests
- Entity extraction: all entity types, normalization, validation
- Retrieval: chunking, vector search, BM25, fusion
- Response generation: prompt building, validation
- Tools: registry, argument binding, execution, retry
- Routing: load balancing, SLA tracking
- **Expected outcome:** `pytest --cov=services/api/src/triage --cov-report=term-missing` shows ≥ 80% coverage.

### Tier B: Integration Tests (100% happy path coverage)
- Message ingestion → intent classification (end-to-end)
- Intent → decision matrix → autonomy level → tool binding
- Entity extraction + linking → tool execution
- RAG pipeline: document indexing → retrieval → grounding
- Full triage agent graph execution (mocked dependencies)
- Routing: intent → agent assignment → SLA tracking
- **Expected outcome:** All integration tests pass. No data loss from ingestion to output.

### Tier C: Eval Tests (Threshold Gates)
- Intent accuracy ≥ 92% top-1 on golden set
- Macro-F1 ≥ 0.88 per intent
- ECE (calibration) ≤ 0.05
- Retrieval MRR ≥ 0.8, Recall@5 ≥ 0.85
- Response groundedness ≥ 0.95
- Response relevance ≥ 0.90
- Toxicity < 0.1
- **Expected outcome:** `pytest ml/evals/tests/ -v` all tests pass. CI gates block PRs if thresholds violated.

### Tier D: Acceptance Tests (End-to-End Scenarios)
- J1: WISMO email → auto-resolved (latency < 2s)
- J2: Chat coalescing + multi-intent → escalated
- J3: Zendesk refund + write-back (latency < 3s)
- **Expected outcome:** All 3 scenarios pass. Performance benchmarks met.

### Tier E: Security Tests
- PII leak detection: no SSN/CC in responses
- Injection attack blocking: SQL/XSS/LLM prompt injection blocked
- Cross-tenant isolation: entities linked to correct tenant
- Entity validation: unverified entities cannot bind to tools
- **Expected outcome:** All security tests pass. Zero leaks in audit.

---

## Packages to Add to pyproject.toml

**services/api/pyproject.toml** (add to `dependencies`):

```toml
# LLM & Agent Orchestration
langgraph>=0.0.20
langchain>=0.1
langchain-community>=0.0
litellm>=1.0

# Embeddings & NLP
sentence-transformers>=2.2
scikit-learn>=1.3
spacy>=3.7
transformers>=4.34
torch>=2.1

# Data & DB
pgvector>=0.2
asyncpg>=0.29

# Validation & Security
detoxify>=0.5
rank-bm25>=0.2.2
```

---

## CI/CD Integration

**New GitHub Actions workflow: `.github/workflows/eval.yml`**

```yaml
name: Eval Harness (Sprint 2)

on:
  pull_request:
    paths:
      - 'services/api/src/triage/**'
      - 'ml/evals/**'
      - '.github/workflows/eval.yml'

jobs:
  intent-eval:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      - run: pip install -e services/api -e ml/evals
      - run: pytest ml/evals/tests/test_intent_classifier.py -v
        env:
          INTENT_ACCURACY_GATE: 0.92
          MACRO_F1_GATE: 0.88

  retrieval-eval:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      - run: pip install -e services/api -e ml/evals
      - run: pytest ml/evals/tests/test_retrieval_eval.py -v
        env:
          MRR_GATE: 0.80
          RECALL_GATE: 0.85

  response-eval:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      - run: pip install -e services/api -e ml/evals
      - run: pytest ml/evals/tests/test_response_generator.py -v
        env:
          GROUNDEDNESS_GATE: 0.95
          TOXICITY_GATE: 0.10

  publish-report:
    if: always()
    needs: [intent-eval, retrieval-eval, response-eval]
    runs-on: ubuntu-latest
    steps:
      - run: echo "Eval report published"
```

---

## Acceptance Criteria (Sprint 2 Complete)

- ✅ All 10 deliverables (S2.1–S2.10) implemented per spec
- ✅ Unit test coverage ≥ 80% on core modules (classification, decision, entity, retrieval, generation, tools, agent, routing)
- ✅ Integration tests passing (all happy paths)
- ✅ Acceptance scenario J1 passing (WISMO auto-resolve, latency < 2s)
- ✅ Acceptance scenario J2 passing (chat multi-intent, escalation)
- ✅ Acceptance scenario J3 passing (Zendesk refund + write-back, latency < 3s)
- ✅ Triage latency p99 < 2s (end-to-end)
- ✅ Intent accuracy ≥ 92% on golden set
- ✅ Macro-F1 ≥ 0.88 (per-intent average)
- ✅ Response groundedness ≥ 0.95
- ✅ Response relevance ≥ 0.90
- ✅ Toxicity < 0.1
- ✅ Zero PII leaks detected
- ✅ Injection attacks blocked (SQL, XSS, LLM prompt injection)
- ✅ Cross-tenant isolation verified
- ✅ All quality gates passing (CI blocks PRs if any gate violated)
- ✅ Product sign-off obtained
- ✅ Engineering sign-off obtained
- ✅ QA sign-off obtained

---

## Success Metrics

| Metric | Target | How to Verify |
|---|---|---|
| **Intent accuracy (top-1)** | ≥ 92% | `pytest ml/evals/tests/test_intent_classifier.py -v` |
| **Intent macro-F1** | ≥ 0.88 | Per-intent F1 scores in eval report |
| **ECE (calibration)** | ≤ 0.05 | Eval metric, measured during temperature scaling |
| **Response groundedness** | ≥ 0.95 | `pytest ml/evals/tests/test_response_generator.py -v` |
| **Response relevance** | ≥ 0.90 | Embedding similarity (query vs response) |
| **Toxicity** | < 0.1 | Detoxify score on generated responses |
| **Retrieval MRR** | ≥ 0.80 | `pytest ml/evals/tests/test_retrieval_eval.py -v` |
| **Retrieval Recall@5** | ≥ 0.85 | Top-5 chunks include relevant docs |
| **Triage latency p99** | < 2000ms | `pytest --benchmark-only` (full agent graph) |
| **Triage latency p95** | < 1500ms | Benchmark percentile |
| **Acceptance J1** | PASS | `pytest services/api/tests/acceptance/test_j1_wismo_auto_resolve.py -v` |
| **Acceptance J2** | PASS | `pytest services/api/tests/acceptance/test_j2_chat_multi_intent.py -v` |
| **Acceptance J3** | PASS | `pytest services/api/tests/acceptance/test_j3_zendesk_refund_writeback.py -v` |
| **Unit test coverage** | ≥ 80% | `pytest --cov=services/api/src/triage --cov-report=term-missing` |
| **PII leak rate** | 0% | Manual audit + regex scan of output logs |
| **Injection block rate** | 100% | 100 red-team patterns → all blocked |

---

## Timeline & Effort Breakdown

| Component | Effort | Total | Owner |
|---|---|---|---|
| S2.1 Intent Classification | 2 days | 2 days | Eng 1 |
| S2.2 Decision Matrix & Autonomy | 2 days | 4 days | Eng 1 |
| S2.3 Entity Extraction | 2 days | 6 days | Eng 2 |
| S2.4 RAG Pipeline | 2 days | 8 days | Eng 2 |
| S2.5 Response Generation | 2 days | 10 days | Eng 3 |
| S2.6 Tool Framework | 1 day | 11 days | Eng 1 |
| S2.7 LangGraph Agent | 2 days | 13 days | Eng 1 |
| S2.8 Routing & Escalation | 2 days | 15 days | Eng 2 |
| S2.9 Eval Harness | 1 day | 16 days | Eng 3 |
| S2.10 Acceptance Gate | 1 day | 17 days | QA + Eng 1 |
| **Total** | **17 days** | ~2 weeks | 3 engineers + QA |

---

## Risk Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| **Intent accuracy variance by language** | Model may underperform on non-English | Use multilingual-e5, eval per-language, collect samples |
| **Hallucination in responses** | LLM invents facts not in context | Groundedness guard (≥ 0.95 gate), blocking guard prevents leakage |
| **Tool execution side effects** | Refund happens twice | Idempotency keys, saga compensation, property tests |
| **RAG retrieval gaps** | KB doesn't answer question | Fallback to escalation, collect "no answer" cases, KB expansion loop (S3) |
| **Autonomy thrashing** | Intent promoted/demoted rapidly | 7-day observation window, no flips within window |
| **Cross-tenant data leak** | Order from tenant A accessed by tenant B | Entity validation, linked_id checks, RLS policies, integration tests |
| **Performance degradation** | Latency exceeds 2s target | Caching (Redis), batch processing, async retrieval, load testing |
| **LLM cost runaway** | Token usage explodes | Rate limiting, caching, temperature=0.3, max_tokens=200 |

---

## Dependencies & Blockers

### Input from Sprint 1 (required)
- ✅ Message ingestion endpoint (S1.2)
- ✅ Message normalization (S1.1)
- ✅ Identity resolution (S1.5)
- ✅ Customer identity model
- ✅ Conversation coalescing (S1.4)
- ✅ Outbox events (S1.7)
- ✅ PII redaction vault (S1.6)

### Input from Sprint 0 (required)
- ✅ PostgreSQL + pgvector extension
- ✅ Redis
- ✅ LiteLLM gateway (for Claude/GPT-4)
- ✅ Tenant context, RLS policies
- ✅ Structured logging (py_core)
- ✅ Audit logging (S0.6)
- ✅ Eval harness scaffolding (S0.8)

### External Dependencies (to install)
- `langgraph` >= 0.0.20
- `sentence-transformers` >= 2.2
- `scikit-learn` >= 1.3
- `detoxify` >= 0.5
- `pgvector` >= 0.2
- See "Packages to Add" section above

### Blockers
- None known. All dependencies from S0 and S1 are available and tested.

---

## Phase-Out & Cleanup

After Sprint 2 is complete and approved:

1. **Merge to main branch** (via PR with all sign-offs)
2. **Deploy to staging environment** (for integration testing with real infrastructure)
3. **Run smoke tests** on staging (verify core scenarios work)
4. **Archive this plan file** (rename to `sprint2-impl-plan-COMPLETED.md` after gate passes)
5. **Begin Sprint 3 work** (enrichment layer, customer/order/billing context)

---

## Document History

| Version | Date | Author | Changes |
|---|---|---|---|
| 1.0 | Oct 2026 | Planning Agent | Initial draft from spec analysis |

---

**Status:** Ready for implementation. All 10 deliverables scoped, ordered by dependency, with concrete file paths and verification steps.

**Next Step:** Begin Phase 0 (database migrations, models, fixtures). Target: Sprint 2 complete by end of 2-week sprint with product, engineering, and QA sign-offs.
