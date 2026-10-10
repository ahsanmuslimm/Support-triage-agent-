# Sprint 2 - Triage & Classification Core (Overview)

## Objective
Build the **intelligent triage engine**: multi-label intent classification, decision matrix with autonomy levels, RAG-grounded response generation, tool execution, and agent orchestration via LangGraph.

## Sprint 2 Deliverables (10 Items)

| # | Deliverable | Status | Focus |
|---|---|---|---|
| **2.1** | Intent Classification & Embedding | ✅ DOCUMENTED | Multi-label classifier, embedding models, confidence calibration, deterministic fallback |
| **2.2** | Decision Matrix & Autonomy Levels | ✅ DOCUMENTED | Autonomy L0–L3, policy-driven decisions, promotion/demotion workflows |
| **2.3** | Entity Extraction & Linking | ✅ DOCUMENTED | NER, entity linking to Shopify/customers, PII redaction, validation binding |
| **2.4** | RAG Pipeline & Retrieval | ✅ DOCUMENTED | Document chunking, vector embeddings, BM25+semantic hybrid retrieval |
| **2.5** | Response Generation & Grounding | ✅ DOCUMENTED | LLM response generation, groundedness scoring, output validation guard |
| **2.6** | Tool Integration Framework | ✅ DOCUMENTED | Tool registry, argument binding, execution sagas, error handling |
| **2.7** | Triage Agent Graph (LangGraph) | ✅ DOCUMENTED | DAG orchestration, node routing, state management, async execution |
| **2.8** | Routing & Escalation Engine | ✅ DOCUMENTED | Skill-based routing, load balancing, SLA tracking, escalation triggers |
| **2.9** | Eval Harness & Golden Sets | ✅ DOCUMENTED | Classification evals, response quality metrics, threshold gates, CI integration |
| **2.10** | Sprint 2 Acceptance Gate | ✅ DOCUMENTED | End-to-end scenarios (J1–J3), performance benchmarks, sign-off process |

---

## Architecture Overview (Sprint 2)

```
Inbound Message (from S1)
    ↓
┌──────────────────────────────────────────────┐
│  TRIAGE AGENT GRAPH (LangGraph - S2.7)      │
├──────────────────────────────────────────────┤
│                                              │
│  ┌─ Intent Classifier (S2.1)               │
│  │  └─ Multi-label, confidence-calibrated  │
│  ├─ Entity Extractor (S2.3)                │
│  │  └─ NER + entity linking + PII redact   │
│  ├─ Decision Matrix (S2.2)                 │
│  │  └─ Autonomy L0–L3, policy-driven       │
│  │  └─ Promotion/demotion gates            │
│  ├─ Autonomy Gate (S2.2)                   │
│  │  └─ Block execution if L < required    │
│  ├─ RAG Retriever (S2.4)                   │
│  │  └─ Hybrid BM25+semantic search         │
│  ├─ Response Generator (S2.5)              │
│  │  └─ LLM prompt-based generation         │
│  ├─ Output Validator (S2.5)                │
│  │  └─ Groundedness, toxicity, PII, XSS   │
│  ├─ Tool Executor (S2.6)                   │
│  │  └─ Saga pattern, retry, compensation  │
│  └─ Router & Escalator (S2.8)              │
│     └─ Skill-based, load-aware, SLA       │
│                                              │
└──────────────────────────────────────────────┘
    ↓
Output: Auto-resolve, Tool execution, Escalate (with context)
```

---

## Key Components (Detailed)

### S2.1 — Intent Classification
- **Multi-label intent classifier** using embedding k-NN + temperature scaling
- **Intent embeddings** from sentence-transformers (33M params, 384-dim)
- **Confidence calibration** (ECE ≤ 0.05 target)
- **Deterministic fallback** (keyword/fuzzy matching, no ML)
- **Output:** Top-K intents with confidences

### S2.2 — Decision Matrix & Autonomy
- **4 autonomy levels:** L0=read-only, L1=low-risk write, L2=medium-risk, L3=high-risk
- **Policy input document** (intent, confidence, customer IAL, security signals, business rules)
- **Deterministic decision rules** (Tier A — strict TDD)
- **Autonomy promotion workflow** (accuracy ≥ 95%, groundedness ≥ 0.95, admin sign-off)
- **Auto-demotion** on false-resolution > 5%

### S2.3 — Entity Extraction & Linking
- **Rule-based NER** (ORDER_ID, AMOUNT, EMAIL, PHONE patterns)
- **ML-based NER fallback** (dslim/bert-base-multilingual-cased-ner)
- **Entity linking** (order → Shopify, email → customer identity)
- **PII redaction during extraction** (SSN, credit card → vault tokens)
- **Entity validation** (cross-tenant isolation, amount bounds)

### S2.4 — RAG Pipeline
- **Document chunking** (500-token chunks, 100-token overlap)
- **Embedding indexing** (pgvector, 384-dim vectors)
- **Hybrid retrieval** (BM25 + semantic via RRF fusion)
- **Retrieval ranking** (cosine similarity, chunk relevance)
- **Metrics:** MRR ≥ 0.8, Recall@5 ≥ 0.85

### S2.5 — Response Generation & Grounding
- **LLM response generation** (Claude 3.5, temperature=0.3)
- **Groundedness scorer** (claims extracted, matched to context, target ≥ 0.95)
- **Output validators** (toxicity < 0.1, no PII, no injection, IAL-aware)
- **Fallback responses** (on validation failure, safe escalation)

### S2.6 — Tool Framework
- **Tool registry** (refund, password_reset, cancel_order, create_ticket, etc.)
- **Argument binding** (extracted entities → tool args)
- **Autonomy gates** (enforce L level before execution)
- **Saga pattern** (undo/compensation on failure)
- **Retry logic** (exponential backoff, max 3 attempts)

### S2.7 — Triage Agent Graph (LangGraph)
- **DAG with 8 nodes:** classify → extract → decide → gate → retrieve → generate → validate → escalate/tool
- **Conditional routing** (autonomy-based, validation-based)
- **State machine** (TriageState carries context through nodes)
- **Reasoning trail** (audit log of decisions)
- **Async execution** (all nodes run concurrently where possible)

### S2.8 — Routing & Escalation
- **Routing rules** (intent → skill required → matching agent)
- **Load balancing** (assign to agent with lowest queue)
- **SLA tracking** (deadline per routing rule, breach detection)
- **Stale assignment reclaim** (reassign if no activity > 15 min)
- **Escalation triggers** (low confidence, validation fail, autonomy L0, etc.)

### S2.9 — Eval Harness
- **Golden sets** (150+ curated examples: 100 intent, 50 retrieval, 50 response)
- **Evaluators** (intent accuracy, macro-F1, groundedness, relevance, toxicity)
- **Threshold gates** (accuracy ≥ 92%, groundedness ≥ 0.95, relevance ≥ 0.90)
- **CI integration** (pytest + pytest-bdd + GitHub Actions)

### S2.10 — Acceptance Gate
- **J1 Scenario:** WISMO auto-resolution (email → intent → auto-resolve)
- **J2 Scenario:** Chat coalescing + multi-intent (3 messages → 2 intents → escalate)
- **J3 Scenario:** Zendesk refund + write-back (webhook → refund tool → internal note)
- **Performance targets:** Latency p99 < 2s, p95 < 1.5s
- **Quality targets:** Intent accuracy ≥ 92%, groundedness ≥ 0.95

---

## Effort Estimate

| Item | Effort | Total |
|---|---|---|
| S2.1 | 2 days | 2 days |
| S2.2 | 2 days | 4 days |
| S2.3 | 2 days | 6 days |
| S2.4 | 2 days | 8 days |
| S2.5 | 2 days | 10 days |
| S2.6 | 1 day | 11 days |
| S2.7 | 2 days | 13 days |
| S2.8 | 2 days | 15 days |
| S2.9 | 1 day | 16 days |
| S2.10 | 1 day | 17 days |
| **Total** | **17 days** | ~2 weeks (2-week sprint) |

---

## Documentation Output

**Files Created:**
- ✅ S2.1-Intent-Classification-and-Embedding-Model.md (450 lines)
- ✅ S2.2-Decision-Matrix-and-Autonomy-Levels.md (400 lines)
- ✅ S2.3-Entity-Extraction-and-Linking.md (350 lines)
- ✅ S2.4-RAG-Pipeline-and-Retrieval.md (350 lines)
- ✅ S2.5-Response-Generation-and-Grounding.md (400 lines)
- ✅ S2.6-Tool-Integration-Framework.md (300 lines)
- ✅ S2.7-Triage-Agent-Graph-LangGraph.md (400 lines)
- ✅ S2.8-Routing-and-Escalation-Engine.md (300 lines)
- ✅ S2.9-Eval-Harness-and-Golden-Sets.md (350 lines)
- ✅ S2.10-Sprint-2-Acceptance-Gate.md (400 lines)
- ✅ SPRINT-2-OVERVIEW.md (this file)

**Total:** ~3,500 lines of implementation specifications + code examples

---

## Testing Strategy by Tier

| Tier | Target | Coverage |
|---|---|---|
| **A (Unit)** | ≥ 80% code coverage | Decision matrix, entity validation, routing rules, eval gates |
| **B (Integration)** | 100% happy path | E2E graph execution, tool framework, retrieval ranking |
| **C (Eval-Driven)** | Golden set thresholds | Intent accuracy ≥ 92%, groundedness ≥ 0.95 |
| **D (ATDD)** | 3/3 scenarios passing | J1–J3 acceptance scenarios |
| **E (Smoke)** | UI/dashboard | Routing dashboard, audit logs |

---

## Acceptance Criteria (Sprint 2 Complete)

- ✓ All 10 deliverables implemented per spec
- ✓ Unit test coverage ≥ 80%
- ✓ Integration tests passing (all happy paths)
- ✓ Acceptance scenario J1 passing (WISMO auto-resolve)
- ✓ Acceptance scenario J2 passing (chat multi-intent)
- ✓ Acceptance scenario J3 passing (Zendesk refund)
- ✓ Performance target met (triage latency p99 < 2s)
- ✓ Quality gates passing (intent accuracy ≥ 92%, groundedness ≥ 0.95)
- ✓ Intent accuracy on golden set ≥ 92%
- ✓ Response groundedness ≥ 0.95
- ✓ Product sign-off obtained
- ✓ Engineering sign-off obtained
- ✓ QA sign-off obtained

---

## Success Metrics

| Metric | Target | Verification |
|---|---|---|
| **Intent accuracy** | ≥ 92% top-1 | Golden set eval (100+ examples) |
| **Intent macro-F1** | ≥ 0.88 | Per-intent F1 scores |
| **Response groundedness** | ≥ 0.95 | Claim extraction + matching |
| **Response relevance** | ≥ 0.90 | Embedding similarity to question |
| **Toxicity** | < 0.1 | Detoxify score |
| **Triage latency p99** | < 2000ms | k6 load test (100 msg/s) |
| **Latency p95** | < 1500ms | k6 load test |
| **False positive rate** | < 1% | Manual audit of escalations |
| **PII leak rate** | 0% | Regex + manual audit |
| **Tool execution success** | ≥ 99% | Idempotency test + saga tests |

---

## Dependencies & Integrations

### Input from Sprint 1
- ✅ Message ingestion endpoint (S1.2)
- ✅ Message normalization (S1.1)
- ✅ Identity resolution (S1.5)
- ✅ Customer identity (S1.5)
- ✅ Conversation model (S1.9)
- ✅ Coalescing (S1.4) — ensures single triage job

### Dependencies on Sprint 0
- ✅ PostgreSQL + pgvector (vector search)
- ✅ Redis (caching, locks)
- ✅ LiteLLM gateway (LLM abstraction)
- ✅ Eval harness (S0.8)
- ✅ Audit logging (S0.6)

### Output to Sprint 3+
- 📋 Outbox events (message triage completed)
- 📋 Enrichment hooks (S3 — add context)
- 📋 Proactive triggers (S4 — outreach)
- 📋 Learning loop (weekly retraining)

---

## Known Challenges & Mitigations

| Challenge | Risk | Mitigation |
|---|---|---|
| **Intent accuracy variance by language** | Intent classifier may underperform on non-English | Use multilingual embeddings (multilingual-e5), eval per language, collect samples |
| **Hallucination risk** | LLM may invent facts not in context | Groundedness scorer with blocking guard (target 0.95) |
| **Tool execution side effects** | Refund happens twice if retry logic fails | Idempotency keys, saga pattern, compensation |
| **RAG retrieval gaps** | KB doesn't answer customer question | Fallback to escalation, collect "no answer" cases for KB improvement |
| **Autonomy level thrashing** | Intent promoted/demoted rapidly | Gate on 7-day observation window, no flips within window |

---

## File Structure After Sprint 2

```
packages/api/src/triage/
├── models/
│   ├── message.py              # S1.1 (from Sprint 1)
│   ├── conversation.py         # S1.9 (from Sprint 1)
│   └── intent.py               # S2.1
├── classification/
│   ├── classifier.py           # S2.1
│   └── fallback_classifier.py  # S2.1
├── decision/
│   ├── matrix.py               # S2.2
│   ├── autonomy.py             # S2.2
│   └── promotion.py            # S2.2
├── entity/
│   ├── extractor.py            # S2.3
│   ├── validator.py            # S2.3
│   └── linker.py               # S2.3
├── retrieval/
│   ├── chunker.py              # S2.4
│   ├── vector_search.py        # S2.4
│   └── hybrid.py               # S2.4
├── generation/
│   ├── generator.py            # S2.5
│   ├── groundedness.py         # S2.5
│   └── validator.py            # S2.5
├── tools/
│   ├── registry.py             # S2.6
│   ├── executor.py             # S2.6
│   └── retry.py                # S2.6
├── agent/
│   ├── graph.py                # S2.7
│   ├── state.py                # S2.7
│   └── nodes.py                # S2.7
├── routing/
│   ├── engine.py               # S2.8
│   ├── sla.py                  # S2.8
│   └── escalation.py           # S2.8
└── tests/
    ├── test_classification.py
    ├── test_decision_matrix.py
    ├── test_entity_extraction.py
    ├── test_retrieval.py
    ├── test_generation.py
    ├── test_tools.py
    ├── test_agent_graph.py
    ├── test_routing.py
    ├── evals/
    │   ├── test_intent_classifier.py
    │   ├── test_retrieval_eval.py
    │   └── test_response_generator.py
    └── scenarios/
        ├── test_j1_wismo.py
        ├── test_j2_coalescing.py
        └── test_j3_zendesk.py
```

---

## Integration with Sprint 0 & 1

**Sprint 0** provides the foundation:
- ✅ PostgreSQL (persistent storage)
- ✅ pgvector (vector search)
- ✅ Redis (caching, locking)
- ✅ LiteLLM gateway (LLM abstraction)
- ✅ Audit logging (S0.6)
- ✅ Eval harness (S0.8)

**Sprint 1** provides the ingestion:
- ✅ Message ingestion (S1.2 endpoint)
- ✅ Message normalization (S1.1)
- ✅ Identity resolution (S1.5)
- ✅ Coalescing (S1.4)
- ✅ Encryption/PII (S1.6)
- ✅ Conversation model (S1.9)

**Sprint 2** provides the intelligence:
- 🔄 Triage classification & routing
- 🔄 Autonomy & decision-making
- 🔄 Tool execution
- 🔄 Response generation

**Sprint 3** (future) will use Sprint 2 output:
- 📋 Enrichment layer (add customer/order context)
- 📋 Proactive triggers
- 📋 Continuous learning loop

---

## Status

**Sprint 2 documentation:** ✅ **COMPLETE**  
**All 10 deliverables:** ✅ **DOCUMENTED**  
**Total lines:** ~3,500 (specifications + code examples)  
**Next:** Push to GitHub, begin implementation

---

## Timeline

- **Weeks 1–2:** Implement S2.1–S2.5 (classification, decision, entity, retrieval, generation)
- **Week 2:** Implement S2.6–S2.8 (tools, graph, routing)
- **Week 2–3:** Implement S2.9–S2.10 (eval, acceptance gate)
- **Week 3:** Integration, testing, sign-off

**Total:** ~2 weeks (2-week sprint)

---

**Status:** Sprint 2 documentation **COMPLETE** and committed to GitHub.  
**Next:** Continue with Sprint 3 (Enrichment & Context), or begin implementation.

