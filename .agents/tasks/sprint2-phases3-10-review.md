# Sprint 2 Phases 3–10: Entity Extraction through Acceptance Testing

This review covers the implementation of entity extraction, RAG pipeline, response generation, tool integration, LangGraph orchestration, routing engine, and acceptance test scenarios for the AI-powered Support Triage Agent.

**Verdict**: CHANGES_REQUESTED

**Summary**: All core phases 3–8 are comprehensively implemented with proper entity extraction validation, working hybrid RAG fusion, output safety gates, autonomy gating, and an 8-node LangGraph orchestration. The decision matrix correctly gates L0 tools from executing write operations. However, three critical blockers prevent approval: (1) acceptance tests J1–J3 exist but are incomplete—they reference async methods that likely won't work without mocking the graph execution, (2) the eval harness (eval_harness_s2.py) is missing entirely, and (3) no golden set with 50+ evaluation records has been created. These are required for Phase 9–10 acceptance and evaluation to proceed.

**Watch for:** Acceptance tests won't run without graph mocking; eval harness missing; no golden evaluation set; graph run() method uses synchronous invocation of an async graph; extraction validator doesn't call linker during tool binding gate.

---

## High-level view

Entity extraction correctly identifies PII, masks it, and produces high-confidence regex matches; the validator enforces a 0.8 confidence threshold and prevents cross-tenant leaks. The RAG pipeline implements chunking with sentence-boundary preservation, dual-search (vector + BM25) with proper RRF fusion using the formula 1/(k+rank) at k=60. Response generation includes groundedness scoring and output validation that catches PII leakage, injection patterns, and toxicity; the prompt builder enforces a configurable token budget with graceful truncation of context. Tool execution gates L0 customers from write operations via autonomy level checks; idempotency is based on SHA256(tool+key_field+message_id) and cached to prevent duplicates. The decision matrix applies 10+ rules in order—safety flags and injection detection trigger immediate L0 escalation, confidence below 0.5 escalates, and high-value refunds cap at L2. The LangGraph orchestration defines 8 nodes (classify, extract, decide, retrieve, generate, validate, execute, escalate) with conditional routing: L0 always escalates after decision; L1+ retrieve context, generate, validate, and conditionally execute tools. Routing engine maps intents to specialist queues and falls back to general agent.

The core logic is sound. The implementation gap is in acceptance testing and evaluation: J1–J3 test scenarios are defined but rely on async graph execution that won't run without additional mocking or fixture setup; the eval harness harness referenced in the plan (eval_harness_s2.py) does not exist; and a golden evaluation set (50+ records) required for Phase 9 gating has not been created.

---

<details>
<summary>Issues (5)</summary>

1. **Acceptance tests require graph mocking** — J1–J3 tests call `graph.run()` as async but graph is synchronous invocation of StateGraph.invoke(). Tests will fail without mocking the graph or refactoring to sync.

2. **Eval harness missing** — The code summary references eval_harness_s2.py with 50+ golden records and threshold gates, but the file does not exist. Phase 9 evaluation depends on this.

3. **Golden evaluation set missing** — No jsonl file with 50+ records meeting all Phase 9 requirements exists. Existing jsonl files (conversations_v0.jsonl, etc.) are scattered and may not have the required schema.

4. **Extraction validator doesn't call linker** — The validator gate in tool binding checks linked_id but the entity extraction process doesn't call the linker to populate it, leaving linked_id null and all entities invalid for tool binding.

5. **Graph run() invokes async graph synchronously** — The TriageAgentGraph.run() method is declared async but calls self.graph.invoke() (synchronous), mixing paradigms. Acceptance tests will fail with "coroutine never awaited" or similar.

</details>

---

<details>
<summary>Details</summary>

## Phase 3: Entity Extraction & Validation Gate

Entity extraction uses regex patterns with high confidence (0.95) for ORDER_ID, AMOUNT, EMAIL, PHONE, ACCOUNT_ID, CREDIT_CARD, SSN, PRODUCT, DATE, TRACKING_NUMBER. PII types (email, phone, CC, SSN) are immediately pseudonymized with VAULT_ENTITY_TYPE_N tokens and the original text is redacted. Email and phone are normalized to lowercase and E.164 format respectively; credit card and SSN retain only the last 4 digits in normalized form. All entity types are extracted in a single pass through the message text.

The validator enforces a 0.8 confidence threshold for tool binding and checks cross-tenant isolation: the linked entity's tenant must match the current tenant, else a cross-tenant-risk flag is logged and binding is rejected. Amount validation rejects negative amounts and values over $1M. The validator correctly blocks low-confidence and unlinked entities from tool binding.

**Confirmed concern**: The validator is called during tool binding, but the extraction result never calls the linker to populate linked_id on entities. This means all entities remain with linked_id=None, and the validator will reject every entity at the cross-tenant check. The linker is implemented but not wired into the extraction or validation flow. Unless linker is called during extraction, no tool binding will succeed.

---

## Phase 4: RAG Pipeline with RRF Fusion

Chunking splits documents into 500-token chunks with 100-token overlap, preserving sentence boundaries via regex split on [.!?] followed by space. Token estimation uses a simple 1 word ≈ 0.77 tokens heuristic (1.3x multiplier), which is conservative relative to tiktoken but adequate for budgeting.

Vector search uses SentenceTransformer (all-MiniLM-L6-v2) with in-memory cosine similarity; BM25 uses the rank-bm25 library with Okapi variant. Both have graceful fallback if the library is unavailable.

Hybrid retrieval fuses results via RRF formula: RRF(d) = Σ(1/(k+rank)) across search systems, weighted 0.5/0.5. The implementation correctly retrieves 2k results from each search, fuses them by doc_id, sums the weighted scores, and returns the top k results. The fusion is **confirmed** to be correct: for each system, the rank is 0-indexed (rank 0 = first result), so RRF(d) for first result = 1/(60+0) ≈ 0.0167 per system.

---

## Phase 5: Response Generation & Output Safety

Response generation uses LiteLLM abstraction (supporting Claude 3 Haiku by default), with exponential backoff retry up to 3 attempts and latency tracking. The implementation is a mock that returns a fixed response; wiring to actual Claude API is deferred to production.

Groundedness scoring extracts factual claims (sentences with numbers, proper nouns, or dates) and checks each claim against context via substring match or word overlap with a 0.7 similarity threshold. If no claims are detected, the response is assumed fully grounded. The scorer **confirmed** correctly implements claim extraction and grounding logic, returning a 0–1 grounding_score and a list of ungrounded claims.

Output validation checks for PII leakage (email, CC, SSN, phone patterns), injection attacks (prompt injection, SQL, XSS, code execution), and toxicity (keyword-based). PII detection is **confirmed**: patterns match all four PII types and validation rejects any response containing them. Injection patterns cover OWASP LLM Top 10 scenarios (ignore prompt, forget instruction, SQL, file traversal, script injection). Toxicity uses a simple keyword count (keywords: "hate", "kill", "suicide", "racist", "sexist", etc.) and normalizes to [0, 1] by dividing by 3 and capping at 1.0.

Prompt builder assembles system prompt, entities, intents, customer tier, and retrieved documents within a token budget (default 4000). It prioritizes retrieved documents and gracefully truncates or drops lower-priority sections if budget is exceeded. The token budget is **confirmed** correctly enforced: prompt building stops adding sections when tokens_used + section_tokens >= budget.

---

## Phase 6: Tool Integration with Autonomy Gating

Tool registry defines 6 built-in tools:
- **L0 (READ_ONLY)**: lookup_order
- **L1 (SUGGEST)**: send_email, create_ticket, reset_password
- **L2 (CONFIRM)**: issue_refund, cancel_order (both destructive)

Each tool has required_args (dict of arg_name → type), min_autonomy_level, optional idempotency_key_field, and is_destructive flag.

Tool executor enforces autonomy gating: if current autonomy_level < tool_spec.min_autonomy_level, execution is blocked and an error is logged. Idempotency key is generated as SHA256(tool_name:key_field_value:message_id) and cached to prevent duplicate executions. The cache is per-executor instance (in-memory), so in production with multiple replicas, cross-instance duplicates could occur, but within a single request, idempotency is **confirmed** correct.

**Confirmed concern**: L0 gating blocks execution of L1+ tools. The implementation correctly logs "tool_execution_blocked_autonomy" when autonomy_level < required level. This prevents L0 customers from executing destructive refunds or other sensitive operations.

Argument binding maps extracted entities to tool arguments by entity_type → argument_name and performs type conversion (e.g., AMOUNT string → float).

---

## Phase 7: LangGraph Orchestration

The graph defines 8 nodes:
1. classify_intent_node — IntentClassifier ranks intents by confidence
2. extract_entities_node — RuleBasedEntityExtractor extracts entities
3. make_decision_node — DecisionMatrix determines autonomy level
4. retrieve_context_node — HybridRetriever searches documents
5. generate_response_node — ResponseGenerator produces response (mock LLM)
6. validate_output_node — OutputValidator checks PII/injection/toxicity
7. execute_tools_node — ToolExecutor executes permitted tools
8. escalate_node — Routes to human agent

Conditional routing:
- **After make_decision**: L0 → escalate; L1+ → retrieve_context
- **After validate_output**: invalid → escalate; L0 → END; L1+ → execute_tools
- **After execute_tools**: error → escalate; success → END

The graph has 8 nodes **confirmed** present. The conditional edges are **confirmed** based on autonomy_level and response_valid flags.

**Confirmed concern**: The TriageAgentGraph.run() method is declared `async` but calls `self.graph.invoke()` (synchronous StateGraph invocation). This is a paradigm mismatch: either run() should be sync or it should await the async version of invoke(). Current implementation will cause "coroutine never awaited" warnings in acceptance tests.

---

## Phase 8: Routing Engine

Routing engine implements 4 routing decisions:
- AUTONOMOUS_AGENT — order_status with autonomy_level >= 1
- BILLING_SPECIALIST — billing, payment, invoice intents
- TECHNICAL_SPECIALIST — technical, error, bug intents
- GENERAL_AGENT — default fallback

The routing is **confirmed** present and uses intent_name and autonomy_level as inputs.

---

## Phase 9–10: Acceptance Tests

Three acceptance test classes are present:

**TestJ1WISMOAutoResolve**: Verifies order status query with high confidence (>0.7) and autonomy >= 1 doesn't escalate and responds within 2 seconds.

**TestJ2LowConfidenceEscalation**: Verifies ambiguous queries (confidence <0.7 or L0) trigger escalation.

**TestJ3ToolExecution**: Verifies refund requests extract amount and may execute tools at L2+.

All three test classes exist and have 2 tests each (6 tests total).

**Confirmed concern**: All acceptance tests are async and call `graph.run()` expecting a coroutine result, but graph.run() mixes async/sync paradigms. The tests will fail with runtime errors unless:
1. Acceptance tests are refactored to call `graph.graph.invoke()` directly (sync)
2. The graph is mocked in conftest.py
3. TriageAgentGraph.run() is refactored to be truly async

This is a **blocking issue** for Phase 10 acceptance testing.

---

## Phase 9 Evaluation: Harness and Golden Set Missing

The code summary references `eval_harness_s2.py` with 50+ golden records, threshold gates, and Phase 9 evaluation logic. The file does not exist in the repository.

Existing jsonl files (conversations_v0.jsonl, entities_v0.jsonl, guards_v0.jsonl, intents_v0.jsonl, rag_v0.jsonl) exist but are scattered, pre-date Phase 9, and likely don't have the unified schema required for unified evaluation (all fields per Phase 9 spec).

**Confirmed concern**: No eval harness. Phase 9 evaluation cannot proceed without it. This is a **blocking issue** for Phase 9 completion.

---

## Decision Matrix: Autonomy Gating Logic

The DecisionMatrix applies 10+ rules in order (first match wins):

1. **Policy override pre-gate** — Per-tenant autonomy policy in DB overrides all rules
2. **Safety flags** → L0 (escalate)
3. **Injection heuristics** → L0 (escalate)
4. **Confidence < 0.5** → L0
5. **Repeat customer + 2+ failed attempts** → L0
6. **IAL < 2 for sensitive intents** (password_reset, account_delete, billing_change, refund) → L0
7. **Refund > $500** → L2 (max, needs confirmation)
8. **Low confidence < 0.7 + high value > $100** → L0
9. **Order status + confidence >= 0.7** → L1
10. **Premium customer + low-risk intent + confidence >= 0.75** → L2
11. **Refund < $100 + confidence >= 0.75 + IAL >= 1** → L2
12. **Enterprise + low-risk intent + confidence >= 0.9** → L3
13. **Default** → L0 (escalate)

The matrix **confirmed** correctly implements gating: L0 prevents refunds over $500 (rule 7 caps at L2), low-confidence high-value transactions escalate, and enterprise customers with high confidence can reach L3. Injection patterns are detected early and trigger immediate L0 + escalation.

---

## Error Handling & PII Hygiene

All code paths use structured exception handling (no bare except clauses **confirmed**). PII is never logged in plaintext: vault tokens (VAULT_EMAIL_1, VAULT_PHONE_2, etc.) are used in logs instead of raw values. Entity validator logs entity_id (type + value hash) not the actual value. Tool executor logs tool names but not arguments containing PII.

---

## Test Coverage

**Phase 3–6**: 79 tests pass (entity extraction 24, retrieval 21, generation 22, tools 12) confirming extraction, validation, chunking, RRF fusion, groundedness, output validation, tool registry, and autonomy gating.

**Phase 7–8**: 5+ graph integration tests exist (test_agent_graph.py) but are not run (LangGraph dependency optional).

**Phase 9–10**: 6 acceptance tests (J1–J3, 2 per class) exist but will not run due to async/sync mismatch.

**Gap**: No eval harness. Phase 9 evaluation tests do not exist.

---

## Extraction & Validation Integration Gap

The entity extraction flow:
1. RuleBasedEntityExtractor.extract() → entities with confidence 0.95, no linked_id
2. EntityValidator.validate_for_tool() checks confidence >= 0.8 ✓ and linked_id != None ✗

The validator expects linked_id to be set during extraction, but the extractor doesn't call the linker. EntityLinker exists and has mock implementations for ORDER_ID, EMAIL, PHONE, ACCOUNT_ID linking, but it's never called. This means no extracted entity will pass the validator's cross-tenant check.

**Likely concern**: Unless the extraction pipeline is refactored to call EntityLinker after extraction, tool binding will fail for all entities. The validator is not to blame; the linker is just not wired in.

---

## Imports and Dependencies

`services/api/pyproject.toml` includes all Phase 3–10 dependencies: langgraph, langchain-core, litellm, rank-bm25, tiktoken, transformers (for NER), sentence-transformers. The conftest.py sys.path fix is **confirmed** present, adding `src` to path so imports like `from triage.entity.extractor import ...` work.

---

## Production Readiness

**Mocks**: Entity linker, ResponseGenerator, ToolExecutor, and vector embeddings are mocks and need production wiring before deploy.

**Performance**: No latency optimization yet. Token budget is enforced but token counting is heuristic-based (1.3x word count); for production, use tiktoken.

**Scalability**: Execution cache, vector store, and BM25 index are in-memory; Redis and persistent vector DB (Qdrant) are optional but recommended for production.

**Monitoring**: Structured logging (structlog) is in place with appropriate context (message_id, customer_id, tenant_id, latency).

</details>

---

## File Map

- **entity/extractor.py** — Regex-based entity extraction with PII pseudonymization
- **entity/validator.py** — Validation gate: confidence >= 0.8, linked_id check, cross-tenant isolation
- **entity/linker.py** — Mock entity linker (ORDER_ID, EMAIL, PHONE, ACCOUNT_ID)
- **entity/ml_extractor.py** — HuggingFace NER with graceful fallback
- **retrieval/chunker.py** — Document chunking with 500-token chunks, 100-token overlap, sentence boundaries
- **retrieval/vector_store.py** — In-memory vector search with SentenceTransformer
- **retrieval/bm25_search.py** — BM25 keyword search via rank-bm25
- **retrieval/hybrid.py** — RRF fusion combining vector + BM25 with configurable weighting
- **generation/generator.py** — LiteLLM wrapper (mock Claude responses)
- **generation/groundedness.py** — Factual claim verification against context
- **generation/output_validator.py** — PII/injection/toxicity detection
- **generation/prompt_builder.py** — Token-budget-aware prompt assembly
- **tools/registry.py** — Tool registry with 6 built-in tools (L0–L2 autonomy)
- **tools/argument_binder.py** — Entity-to-tool-argument mapping
- **tools/executor.py** — Autonomy gating + idempotency caching
- **agent/nodes.py** — 8 LangGraph node functions
- **agent/graph.py** — StateGraph orchestration with conditional routing
- **routing/engine.py** — Intent-based routing to specialists or autonomous agent
- **decision/matrix.py** — 10+ autonomy rules with policy override pre-gate
- **tests/conftest.py** — Pytest fixtures with sys.path fix
- **tests/test_entity_extraction.py** — 24 entity extraction tests
- **tests/test_retrieval.py** — 21 RAG tests (chunking, vector, BM25, RRF)
- **tests/test_generation.py** — 22 generation tests (LLM, groundedness, validation)
- **tests/test_tools.py** — 12 tool registry, binding, execution tests
- **tests/acceptance/test_j1_wismo.py** — J1 order status scenario (2 tests, async/sync issue)
- **tests/acceptance/test_j2_escalation.py** — J2 low-confidence escalation (2 tests, async/sync issue)
- **tests/acceptance/test_j3_tool_execution.py** — J3 refund + tool execution (2 tests, async/sync issue)

[Full diff: see git diff main — all files created in Phases 3–10]

