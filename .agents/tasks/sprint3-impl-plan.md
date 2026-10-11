# Sprint 3 Implementation Plan
## Enrichment & Context Layers

**Status:** PLANNING COMPLETE  
**Target Completion:** 10 business days (4 batches × 2.5 days average + 1 day acceptance)  
**Review Date:** TBD  

---

## Planning Context

This plan implements 10 deliverables (S3.1–S3.10) organized into 4 sequential implementation batches. Each batch builds on Sprint 2 foundations (triage graph S2.7, decision matrix S2.2, identity resolution S1.5) and leaves the codebase in a buildable, testable state.

### Key Dependencies from Sprint 2
- **TriageState model** (`services/api/src/triage/models/triage_state.py`): Base state object; S3.1–S3.7 extend with enrichment fields
- **DecisionMatrix** (`services/api/src/triage/decision/matrix.py`): Routes based on rules; S3.4 health score and S3.1 flags become new rule inputs
- **TriageAgentGraph** (`services/api/src/triage/agent/graph.py`): Orchestrates nodes; S3.7 injects dynamic prompts before LLM calls
- **EntityLinker** (S2 review confirmed): Already validates cross-tenant isolation; S3.1–S3.3 reuse isolation patterns

### Integration Risks from Sprint 2 Review
1. **Entity linker fallback:** If linker unavailable, entities remain with `linked_id=None` and validator blocks tool binding. S3.1–S3.3 enrichers must validate tenant isolation independently (not rely on linker).
2. **String-matching groundedness:** Grounding scorer uses substring + word-overlap, not semantic similarity. S3.7 prompts must avoid claims requiring semantic validation (e.g., "Customer is losing interest" vs "Customer hasn't ordered in 60 days").
3. **In-memory autonomy policies:** Decision matrix loads policies as Dict[str, int] in memory. S3.4 health score triggers (at_risk label) must be in-memory lookup; no DB query on the hot path.

### Multi-Tenancy Enforcement
- **All cache keys include tenant_id:** Format: `{cache_type}:{tenant_id}:{resource_id}`
- **All DB queries include WHERE tenant_id = $1** before WHERE clause for resource (implicit from dataclass __init__)
- **Enrichment contexts carry tenant_id** through full pipeline (S3.1 → S3.4 → S3.7 → S2.7)
- **CI linter rule:** (to add) All SQL queries and cache operations must include tenant_id scoping

### Environment Variables Required
```bash
# External APIs
SHOPIFY_API_KEY=sk_live_xxx
SHOPIFY_API_SECRET=xxx
SHOPIFY_STORE_DOMAIN=mystore.myshopify.com
STRIPE_SECRET_KEY=sk_live_xxx
STRIPE_WEBHOOK_SECRET=whsec_xxx

# Cache and Database
REDIS_URL=redis://localhost:6379/0
DATABASE_URL=postgresql://user:pass@localhost/triage_db

# Model and ML
MODEL_ARTIFACT_PATH=/models/account_health_v1.lgb
USE_TRANSFORMER_SENTIMENT=false  # Default: TextBlob; set true for DistilBERT
ML_MODELS_BUCKET=s3://ml-models-bucket  # For artifact storage

# Feature flags
ENRICHMENT_CACHE_TTL_SECONDS=3600
SENTIMENT_ANALYSIS_BATCH_SIZE=10
KNOWLEDGE_GAP_LOOKBACK_DAYS=7
HEALTH_SCORE_CHURN_THRESHOLD=0.65

# Celery and scheduling
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2
ENABLE_WEEKLY_RETRAINING=true
ENABLE_ANOMALY_DETECTION=true

# Grafana and analytics
GRAFANA_ADMIN_PASSWORD=xxx
ANALYTICS_DB_PASSWORD=xxx
```

---

## Architecture Overview

### Enrichment Data Flow

```
Customer Query (S1.5 Identity)
    ↓
[Redis Cache Check] → (hit) Cache context → (miss) Parallel Enrichment
    ↓
┌─────────────────────────────────────────────────────────────┐
│ Parallel Enrichment Layer (S3.1–S3.3, S3.6)                 │
│ • S3.1 CustomerEnricher (Shopify profile, subscription)    │
│ • S3.2 OrderAggregator (90-day orders, RFM, risk signals)  │
│ • S3.3 BillingEnricher (Stripe payment, dunning stage)     │
│ • S3.6 SentimentEnricher (NPS surveys, sentiment trend)    │
└─────────────────────────────────────────────────────────────┘
    ↓
[Context Aggregation] → EnrichmentBundle (all 4 contexts)
    ↓
[Store in Redis + DB Cache] (TTL 3600s)
    ↓
┌─────────────────────────────────────────────────────────────┐
│ Health Scoring Pipeline (S3.4)                              │
│ • Extract HealthFeatures from enrichment (15 fields)       │
│ • LightGBM predict: P(churn) ∈ [0, 1]                      │
│ • SHAP explain: top 5 drivers                              │
│ • Label: 'at_risk' if score ≥ 0.65 else 'healthy'          │
└─────────────────────────────────────────────────────────────┘
    ↓
[Decision Matrix + Routing] (S2.2 + S3.1 flags + S3.4 label)
    ↓
[Prompt Engineering] (S3.7 tone + context injection)
    ↓
[Triage Graph Execution] (S2.7 with enriched context)
    ↓
Response + Escalation Metadata
```

### File Structure (New)

```
services/api/src/triage/
├── enrichment/                          # BATCH 1: S3.1–S3.3
│   ├── __init__.py
│   ├── base.py                          # EnricherBase abstract class
│   ├── cache.py                         # Redis + DB cache abstraction
│   ├── customer_enricher.py             # S3.1 implementation
│   ├── order_aggregator.py              # S3.2 implementation
│   ├── billing_enricher.py              # S3.3 implementation
│   ├── models.py                        # Data classes: CustomerContext, OrderContext, BillingContext
│   └── exceptions.py                    # EnrichmentError, APITimeoutError, etc.
│
├── scoring/                             # BATCH 2: S3.4
│   ├── __init__.py
│   ├── health_scorer.py                 # LightGBM predictor + SHAP explainer
│   ├── features.py                      # HealthFeatures data class
│   ├── model_manager.py                 # Model loading, versioning, SIGHUP reload
│   └── models/                          # (External, not in repo)
│       └── account_health_v1.lgb        # Binary artifact (git-ignored)
│
├── sentiment/                           # BATCH 2: S3.6
│   ├── __init__.py
│   ├── analyzer.py                      # TextBlob + transformer fallback
│   ├── nps_aggregator.py                # NPS survey history aggregation
│   └── sentiment_enricher.py            # Sentiment context fetcher
│
├── analysis/                            # BATCH 2: S3.5
│   ├── __init__.py
│   ├── knowledge_gap_analyzer.py        # KB coverage, gap ranking
│   └── category_classifier.py           # Zero-shot query categorizer
│
├── prompting/                           # BATCH 3: S3.7
│   ├── __init__.py
│   ├── template_engine.py               # Jinja2 template loader + renderer
│   ├── tone_selector.py                 # Deterministic tone selection logic
│   ├── context_injector.py              # Context variable preparation
│   ├── templates/                       # YAML/Jinja2 prompt templates
│   │   ├── default.jinja2
│   │   ├── churn_risk.jinja2
│   │   ├── high_value.jinja2
│   │   └── enterprise.jinja2
│   └── few_shot_examples.yaml           # (tone, intent) → examples
│
├── feedback/                            # BATCH 3: S3.8
│   ├── __init__.py
│   ├── feedback_ingester.py             # HTTP endpoint + async storage
│   ├── retrainer.py                     # Weekly model retraining (Celery task)
│   ├── ab_testing.py                    # A/B test assignment + analysis
│   ├── drift_detector.py                # EWMA anomaly detection
│   └── tasks.py                         # Celery task definitions
│
├── analytics/                           # BATCH 3: S3.9
│   ├── __init__.py
│   ├── dashboards.py                    # Materialized view queries
│   ├── metrics_endpoints.py             # FastAPI endpoints (/metrics/*)
│   ├── anomaly_monitor.py               # Slack alerts on critical deviation
│   └── grafana/                         # Dashboard JSON (git-committed)
│       ├── sprint3.json
│       └── README.md
│
├── acceptance/                          # BATCH 4: S3.10
│   ├── __init__.py
│   ├── scenarios.py                     # Acceptance scenario fixtures
│   ├── e2e_test.py                      # End-to-end enrichment flow
│   └── benchmarks.py                    # Latency, cache hit rate tests

tests/unit/triage/
├── enrichment/
│   ├── test_customer_enricher.py        # S3.1 unit tests
│   ├── test_order_aggregator.py         # S3.2 unit tests
│   ├── test_billing_enricher.py         # S3.3 unit tests
│   ├── test_cache.py                    # Cache TTL, invalidation logic
│   └── fixtures.py                      # Shared mocks (Shopify, Stripe, Redis)
│
├── scoring/
│   ├── test_health_features.py          # S3.4 feature extraction
│   ├── test_health_scorer.py            # LightGBM predict + SHAP explain
│   ├── test_model_manager.py            # Model loading, versioning
│   └── fixtures.py                      # Mock LightGBM model
│
├── sentiment/
│   ├── test_sentiment_analyzer.py       # S3.6 TextBlob + transformer
│   ├── test_nps_aggregator.py
│   └── fixtures.py
│
├── analysis/
│   ├── test_knowledge_gap_analyzer.py   # S3.5 coverage, gaps
│   └── fixtures.py
│
├── prompting/
│   ├── test_template_engine.py          # S3.7 Jinja2 rendering
│   ├── test_tone_selector.py            # Determinism, priority logic
│   ├── test_context_injector.py         # Variable preparation
│   └── test_token_budget.py             # Budget enforcement
│
├── feedback/
│   ├── test_feedback_ingester.py        # S3.8 HTTP endpoint
│   ├── test_ab_testing.py               # Deterministic assignment
│   ├── test_drift_detector.py           # EWMA control limits
│   └── fixtures.py
│
├── analytics/
│   ├── test_metrics_endpoints.py        # S3.9 endpoint schemas
│   ├── test_anomaly_monitor.py
│   └── fixtures.py

tests/integration/triage/
├── test_enrichment_pipeline.py          # All 5 enrichers + cache fallback
├── test_health_scoring_with_enrichment.py  # S3.4 full pipeline
├── test_prompt_injection.py             # S3.7 prompt building
├── test_e2e_enrichment_triage.py        # S3.10 E2E scenarios

packages/py_core/alembic/versions/
├── 0005_sprint3_enrichment_tables.py    # Create 10 new tables + indices
└── 0006_sprint3_materialized_views.py   # Create 4 views + pg_cron jobs

ml/models/
├── training/
│   ├── train_health_model.py            # LightGBM trainer (weekly job)
│   ├── feature_engineering.py           # HealthFeatures extraction pipeline
│   └── eval.py                          # Model validation (AUC, F-beta)
└── .gitignore                           # Ignore .lgb artifacts
```

---

## Implementation Batches

### BATCH 1: Enrichment Data Fetching Layer (S3.1–S3.3)
**Duration:** ~2.5 days  
**Dependencies:** S1.5, Shopify API, Stripe API, Redis, PostgreSQL  
**Gate:** Unit tests (A), integration tests (B), contract tests (C) pass

#### 1.1 Create cache abstraction and base enricher class
**What:** Build EnricherBase abstract class and CacheManager (Redis + DB fallback). Establish patterns for all enrichers: fetch → cache/update → return.  
**Files:**  
- `services/api/src/triage/enrichment/__init__.py`
- `services/api/src/triage/enrichment/base.py` (EnricherBase, EnrichmentError)
- `services/api/src/triage/enrichment/cache.py` (CacheManager, Redis + PostgreSQL fallback)
- `services/api/src/triage/enrichment/exceptions.py`

**Verify:**  
```bash
cd services/api
python -m pytest tests/unit/triage/enrichment/test_cache.py -v
# Expected: test_cache_hit, test_cache_miss_with_fallback, test_invalidation_on_webhook pass
```

#### 1.2 Implement S3.1 Customer & Account Enrichment
**What:** Build CustomerEnricher to fetch profile (Shopify), account age, subscription status, and flags (fraud/abuse/VIP); cache with TTL 3600s; implement DB fallback.  
**Files:**  
- `services/api/src/triage/enrichment/models.py` (CustomerContext, PaymentMethodInfo, BillingContext, OrderContext, SentimentContext)
- `services/api/src/triage/enrichment/customer_enricher.py` (async enrich(), _fetch_profile, _fetch_orders, _fetch_subscription, _fetch_flags)
- `tests/unit/triage/enrichment/test_customer_enricher.py` (~50 tests: flag logic, VIP threshold >$1000, account age calculation, cache TTL)
- `tests/integration/triage/test_enrichment_pipeline.py` (mock Shopify/Redis, verify cache hit/miss, DB fallback)

**Verify:**  
```bash
cd services/api
python -m pytest tests/unit/triage/enrichment/test_customer_enricher.py -v --cov=triage.enrichment.customer_enricher
# Expected: ≥85% coverage, all flag logic and cache tests pass
python -m pytest tests/integration/triage/test_enrichment_pipeline.py::test_customer_enrichment_cache_miss -v
# Expected: E2E call to mock Shopify, cache miss → Redis store, TTL 3600s
```

#### 1.3 Implement S3.2 Order & Transaction Enrichment
**What:** Build OrderAggregator to fetch 90-day order history (Shopify), compute RFM, detect risk signals (chargebacks, refunds, velocity spikes); risk score 0–1 weighted sum.  
**Files:**  
- `services/api/src/triage/enrichment/order_aggregator.py` (async aggregate(), _frequency_median, _seasonal_pattern, compute_risk_signals, risk scoring logic)
- `tests/unit/triage/enrichment/test_order_aggregator.py` (~40 tests: RFM calculation, frequency median on edge cases, risk signal detection, seasonal grouping)
- `tests/integration/triage/test_enrichment_pipeline.py` (parallel fetch of orders + refunds + chargebacks, verify risk score ∈ [0, 1])

**Dependencies:** S3.1 (CustomerContext is enriched with order signals)

**Verify:**  
```bash
cd services/api
python -m pytest tests/unit/triage/enrichment/test_order_aggregator.py -v --cov=triage.enrichment.order_aggregator
# Expected: ≥85% coverage, median frequency and risk scoring tests pass
python -m pytest tests/integration/triage/test_enrichment_pipeline.py::test_order_enrichment_risk_signals -v
# Expected: Mock refund/chargeback flags trigger in risk_score, score in [0, 1]
```

#### 1.4 Implement S3.3 Billing & Payment History Context
**What:** Build BillingEnricher to fetch payment methods, dunning stage, failed payments (Stripe), detect churn risk (dunning_stage='final'/'suspended' OR failed_payments_90d ≥ 3); implement Stripe webhook handler for cache invalidation.  
**Files:**  
- `services/api/src/triage/enrichment/billing_enricher.py` (async enrich(), _fetch_payment_methods, _fetch_invoices_90d, _fetch_subscription, dunning computation, churn risk logic)
- `services/api/src/triage/api/endpoints/webhooks.py` (extend with Stripe webhook handler; on invoice.payment_failed/succeeded → invalidate billing cache key)
- `tests/unit/triage/enrichment/test_billing_enricher.py` (~40 tests: dunning stage mapping, card expiry flag, churn risk logic, failed payment count)
- `tests/integration/triage/test_enrichment_pipeline.py` (mock Stripe API, verify webhook signature validation and cache invalidation)

**Verify:**  
```bash
cd services/api
python -m pytest tests/unit/triage/enrichment/test_billing_enricher.py -v --cov=triage.enrichment.billing_enricher
# Expected: ≥85% coverage, dunning stage and churn risk tests pass
python -m pytest tests/integration/triage/test_enrichment_pipeline.py::test_billing_webhook_invalidation -v
# Expected: Stripe webhook with valid signature invalidates Redis key, DB fallback returns fresh data
```

#### 1.5 Verify Batch 1 contract tests and performance
**What:** Validate Shopify and Stripe response schemas; measure enrichment latency p99 <500ms with warm cache.  
**Files:**  
- `tests/unit/triage/enrichment/test_contract_schemas.py` (validate Shopify order schema, Stripe invoice schema)
- `tests/integration/triage/test_enrichment_pipeline.py::test_enrichment_latency_warm_cache`

**Verify:**  
```bash
cd services/api
python -m pytest tests/unit/triage/enrichment/test_contract_schemas.py -v
# Expected: All schema validation tests pass
python -m pytest tests/integration/triage/test_enrichment_pipeline.py::test_enrichment_latency_warm_cache -v
# Expected: p99 latency < 500ms, cache hit rate > 80% over 1000 iterations
```

---

### BATCH 2: ML Scoring & Classification Layer (S3.4, S3.5, S3.6)
**Duration:** ~2.5 days  
**Dependencies:** BATCH 1 (enrichment contexts), LightGBM, sentence-transformers, TextBlob  
**Gate:** Eval harness accuracy ≥90%, model validation AUC ≥0.75

#### 2.1 Create health scoring feature extraction and model manager
**What:** Build HealthFeatures dataclass (15 fields: RFM, payment health, sentiment, NPS, support engagement, plan tier); implement ModelManager to load LightGBM artifact, handle versioning, SIGHUP reload signal.  
**Files:**  
- `services/api/src/triage/scoring/features.py` (HealthFeatures dataclass, to_array(), feature validation)
- `services/api/src/triage/scoring/model_manager.py` (load_model, reload_on_sighup, get_active_version, version tracking)
- `packages/py_core/alembic/versions/0005_sprint3_enrichment_tables.py` (model_versions table)
- `tests/unit/triage/scoring/test_health_features.py` (~25 tests: RFM encoding, ordinal encoding, missing value imputation)

**Verify:**  
```bash
cd services/api
python -m pytest tests/unit/triage/scoring/test_health_features.py -v --cov=triage.scoring.features
# Expected: ≥85% coverage, feature encoding and edge case tests pass
```

#### 2.2 Implement S3.4 Account Health Scoring
**What:** Build HealthScorer to extract HealthFeatures from enrichment contexts, call LightGBM predict (P(churn) ∈ [0, 1]), compute SHAP explanations (top 5 drivers), apply threshold (0.65 → at_risk label); log to audit_entries with SHAP JSON.  
**Files:**  
- `services/api/src/triage/scoring/health_scorer.py` (predict(), explain_with_shap(), _apply_threshold, audit logging)
- `services/api/src/triage/scoring/__init__.py`
- `tests/unit/triage/scoring/test_health_scorer.py` (~35 tests: feature extraction, threshold logic, SHAP filtering, audit logging)
- `tests/integration/triage/test_health_scoring_with_enrichment.py` (mock enrichment contexts → predict → explain, verify SHAP drivers in audit log)
- `ml/models/fixtures.py` (mock LightGBM model artifact for testing)

**Verify:**  
```bash
cd services/api
python -m pytest tests/unit/triage/scoring/test_health_scorer.py -v --cov=triage.scoring.health_scorer
# Expected: ≥85% coverage, threshold and SHAP tests pass
python -m pytest tests/integration/triage/test_health_scoring_with_enrichment.py -v
# Expected: E2E enrichment → health scoring → audit log with SHAP JSON
```

#### 2.3 Implement S3.6 Customer Sentiment & NPS History
**What:** Build SentimentAnalyzer (TextBlob synchronous default + DistilBERT transformer fallback if USE_TRANSFORMER_SENTIMENT=true); aggregate NPS surveys (average last 3, segment logic: ≥9 promoter, 7–8 passive, <7 detractor); compute sentiment trend via linear regression (improving/declining/stable); enrich with risk flags.  
**Files:**  
- `services/api/src/triage/sentiment/analyzer.py` (TextBlob + transformer fallback, sentiment on text)
- `services/api/src/triage/sentiment/nps_aggregator.py` (aggregate NPS surveys, segment, trend)
- `services/api/src/triage/sentiment/sentiment_enricher.py` (async enrich(), fetch surveys + conversations, compute sentiment + NPS context)
- `packages/py_core/alembic/versions/0005_sprint3_enrichment_tables.py` (nps_surveys table)
- `tests/unit/triage/sentiment/test_sentiment_analyzer.py` (~25 tests: TextBlob on positive/negative text, transformer fallback, NPS segmentation)
- `tests/integration/triage/test_enrichment_pipeline.py` (mock NPS data, verify sentiment enrichment)

**Verify:**  
```bash
cd services/api
python -m pytest tests/unit/triage/sentiment/test_sentiment_analyzer.py -v --cov=triage.sentiment
# Expected: ≥85% coverage, sentiment and NPS aggregation tests pass
python -m pytest tests/integration/triage/test_enrichment_pipeline.py::test_sentiment_enrichment -v
# Expected: E2E sentiment context with trend and NPS segment
```

#### 2.4 Implement S3.5 Knowledge Gap Analysis
**What:** Build KnowledgeGapAnalyzer to categorize queries (zero-shot with sentence-transformers, fallback to keyword matching), compute coverage (resolved/total per category), rank gaps by escalation count, generate recommendations; run nightly via Celery, cache results 24h in Redis.  
**Files:**  
- `services/api/src/triage/analysis/category_classifier.py` (zero-shot query categorizer)
- `services/api/src/triage/analysis/knowledge_gap_analyzer.py` (coverage calculation, gap ranking, recommendation generation)
- `services/api/src/triage/feedback/tasks.py` (add gap_analysis_nightly Celery task)
- `tests/unit/triage/analysis/test_knowledge_gap_analyzer.py` (~30 tests: categorizer, coverage metric, gap ranking, recommendation logic)

**Verify:**  
```bash
cd services/api
python -m pytest tests/unit/triage/analysis/test_knowledge_gap_analyzer.py -v --cov=triage.analysis
# Expected: ≥85% coverage, gap ranking and recommendations pass
```

#### 2.5 Verify Batch 2 model validation
**What:** Run eval harness on golden test set; assert model accuracy ≥90%, AUC ≥0.75.  
**Files:**  
- `tests/integration/triage/test_e2e_enrichment_triage.py::test_eval_harness_accuracy`
- `ml/models/eval.py` (model validation script)

**Verify:**  
```bash
cd services/api
python -m pytest tests/integration/triage/test_e2e_enrichment_triage.py::test_eval_harness_accuracy -v
# Expected: Accuracy ≥90%, model ready for deployment
cd ml
python eval.py --model-path models/account_health_v1.lgb --golden-set golden_set.jsonl
# Expected: AUC ≥0.75, F-beta metric meets threshold
```

---

### BATCH 3: Prompt Engineering, Learning Loop, Analytics (S3.7, S3.8, S3.9)
**Duration:** ~2.5 days  
**Dependencies:** BATCH 1–2, Jinja2, Celery, pg_cron, Grafana  
**Gate:** Prompt determinism verified, retraining job runs, dashboards load

#### 3.1 Create prompt template engine and tone selector
**What:** Build TemplateEngine (Jinja2 loader + renderer) with 4 base templates (DEFAULT, CHURN_RISK, HIGH_VALUE, ENTERPRISE); implement ToneSelector (deterministic priority: churn_risk → empathy, VIP+high_value → urgency, enterprise → formal, else → neutral); enforce 3500-token budget (truncate few-shot first, preserve system + escalation).  
**Files:**  
- `services/api/src/triage/prompting/__init__.py`
- `services/api/src/triage/prompting/template_engine.py` (load_template, render with context)
- `services/api/src/triage/prompting/tone_selector.py` (select_tone deterministically)
- `services/api/src/triage/prompting/context_injector.py` (prepare context variables for injection)
- `services/api/src/triage/prompting/templates/default.jinja2` (4 templates with system intro, customer context, decision rationale, escalation block, few-shot examples)
- `services/api/src/triage/prompting/few_shot_examples.yaml` (YAML: (tone, intent) → 2 examples)
- `tests/unit/triage/prompting/test_template_engine.py` (~20 tests: Jinja2 rendering, variable interpolation)
- `tests/unit/triage/prompting/test_tone_selector.py` (~15 tests: priority order, determinism)
- `tests/unit/triage/prompting/test_token_budget.py` (~10 tests: token counting, truncation priority)

**Verify:**  
```bash
cd services/api
python -m pytest tests/unit/triage/prompting/ -v --cov=triage.prompting
# Expected: ≥85% coverage, tone selector determinism, token budget enforcement pass
# Determinism check: run tone_selector 100x on same input, all outputs identical
```

#### 3.2 Integrate S3.7 prompts into triage graph
**What:** Modify TriageAgentGraph to call PromptTemplateEngine before LLM node; inject enrichment context (CustomerContext, BillingContext, HealthScore, top SHAP driver); select tone deterministically based on enrichment signals; pass dynamic prompt to LLM (not generic system prompt).  
**Files:**  
- `services/api/src/triage/agent/nodes.py` (extend generate_response node to inject prompts before LLM call)
- `services/api/src/triage/models/triage_state.py` (extend TriageState with enrichment fields: customer_context, billing_context, health_score, health_label, tone)
- `tests/integration/triage/test_prompt_injection.py` (verify prompt injection, tone selection, token budget on E2E)

**Dependencies:** BATCH 2 (health scores, SHAP drivers)

**Verify:**  
```bash
cd services/api
python -m pytest tests/integration/triage/test_prompt_injection.py -v
# Expected: Prompts injected with tone, context, token budget enforced
# Inspect sample prompts: empathy keywords in churn-risk prompts, urgency in high-value, formal in enterprise
```

#### 3.3 Implement S3.8 Continuous Learning Loop
**What:** Build FeedbackIngester (HTTP POST endpoint, async storage to feedback_events + Redis Streams); implement Retrainer (weekly Celery task, trains intent classifier S1.3 + health model S3.4 on feedback, validates gates AUC ≥0.75, deploys if passes); implement ABTesting (deterministic hash-based assignment, chi-square significance test); implement DriftDetector (EWMA baseline + ±3σ control limits, alerts on critical deviation).  
**Files:**  
- `services/api/src/triage/feedback/feedback_ingester.py` (HTTP POST endpoint, async storage)
- `services/api/src/triage/feedback/retrainer.py` (train_models, validate_gates, deploy_if_passes)
- `services/api/src/triage/feedback/ab_testing.py` (assign_variant deterministically, chi_square_test, detect_winner)
- `services/api/src/triage/feedback/drift_detector.py` (EWMA baseline, detect_anomaly, alert_on_critical)
- `services/api/src/triage/feedback/tasks.py` (Celery Beat schedule: retrain_all_tenants weekly, detect_anomalies every 5 min)
- `services/api/src/triage/api/endpoints/conversations.py` (extend with feedback POST handler)
- `packages/py_core/alembic/versions/0005_sprint3_enrichment_tables.py` (feedback_events, ab_tests, ab_test_outcomes, anomaly_events, metric_history tables)
- `tests/unit/triage/feedback/test_feedback_ingester.py` (~20 tests: endpoint validation, async storage)
- `tests/unit/triage/feedback/test_ab_testing.py` (~15 tests: deterministic assignment, significance test)
- `tests/unit/triage/feedback/test_drift_detector.py` (~15 tests: EWMA baseline, control limits, alerting)
- `tests/integration/triage/test_e2e_enrichment_triage.py::test_retraining_job` (mock feedback, run retrainer, verify model saved)

**Verify:**  
```bash
cd services/api
python -m pytest tests/unit/triage/feedback/ -v --cov=triage.feedback
# Expected: ≥85% coverage, A/B test assignment determinism, drift detection pass
python -m pytest tests/integration/triage/test_e2e_enrichment_triage.py::test_retraining_job -v
# Expected: Weekly retraining job executes, new model version recorded in DB
```

#### 3.4 Implement S3.9 Business Intelligence & Analytics Dashboards
**What:** Create 4 materialized views (v_triage_daily: triage rate, escalation count, autonomy level distribution; v_intent_accuracy: intent classification accuracy per intent; v_agent_tool_usage: tool execution success rate; v_customer_outcomes: resolution time, escalation count, churn rate by customer segment); schedule refresh every 15 min via pg_cron; build metrics endpoints (/metrics/summary, /metrics/agent_performance, /metrics/customer_outcomes, /metrics/anomalies); implement anomaly detection (EWMA + control limits, Slack webhook alerts).  
**Files:**  
- `packages/py_core/alembic/versions/0006_sprint3_materialized_views.py` (CREATE MATERIALIZED VIEW statements + pg_cron refresh schedule)
- `services/api/src/triage/analytics/dashboards.py` (materialized view query functions)
- `services/api/src/triage/analytics/metrics_endpoints.py` (FastAPI endpoints /metrics/*)
- `services/api/src/triage/analytics/anomaly_monitor.py` (EWMA baseline, Slack alerting)
- `services/api/src/triage/analytics/grafana/sprint3.json` (Grafana dashboard JSON: time series, gauge, histogram, heatmap)
- `tests/unit/triage/analytics/test_metrics_endpoints.py` (~20 tests: endpoint schemas, response validation)
- `tests/integration/triage/test_e2e_enrichment_triage.py::test_dashboards_render` (Docker Compose spin-up Grafana, import dashboard, verify panels load)

**Verify:**  
```bash
cd services/api
python -m pytest tests/unit/triage/analytics/ -v --cov=triage.analytics
# Expected: ≥85% coverage, metrics endpoint schemas pass
python -m pytest tests/integration/triage/test_e2e_enrichment_triage.py::test_dashboards_render -v
# Expected: Grafana dashboard imported and renders without errors (smoke test)
```

#### 3.5 Verify Batch 3 integration
**What:** End-to-end test: enrichment → health scoring → prompt injection → triage execution with learning feedback.  
**Files:**  
- `tests/integration/triage/test_e2e_enrichment_triage.py` (full E2E scenario)

**Verify:**  
```bash
cd services/api
python -m pytest tests/integration/triage/test_e2e_enrichment_triage.py -v
# Expected: All E2E scenarios pass, latency p99 <500ms, eval accuracy ≥90%
```

---

### BATCH 4: Acceptance Gate & Deployment (S3.10)
**Duration:** ~1 day  
**Dependencies:** BATCH 1–3 complete, all tests passing  
**Gate:** All 3 acceptance scenarios pass, E2E latency <500ms, eval accuracy ≥90%

#### 4.1 Implement S3.10 acceptance scenarios
**What:** Define 3 acceptance scenarios and verify triage decisions are correct:
1. **High-Value Customer (Scenario A):** VIP flag + high recent order → triage_decision='handle', tone='urgency'
2. **Churn Risk (Scenario B):** health_label='at_risk' + dunning_stage='final' → triage_decision='escalate', tone='empathy', escalation_team='retention'
3. **Fraud Flagged (Scenario C):** fraud_flag=true → triage_decision='escalate', escalation_team='fraud_investigation'

**Files:**  
- `services/api/src/triage/acceptance/scenarios.py` (3 scenario fixtures with mocked enrichment contexts)
- `tests/integration/triage/test_acceptance_gate.py` (3 scenario tests verifying decisions)

**Verify:**  
```bash
cd services/api
python -m pytest tests/integration/triage/test_acceptance_gate.py -v
# Expected: All 3 scenarios pass, decisions match acceptance criteria
```

#### 4.2 Implement E2E enrichment flow benchmark
**What:** Measure p99 latency <500ms over 1000 iterations with warm Redis cache; report cache hit rate >80%; measure health scoring latency <50ms.  
**Files:**  
- `services/api/src/triage/acceptance/benchmarks.py` (latency benchmark, cache stats)
- `tests/integration/triage/test_acceptance_gate.py::test_enrichment_latency_benchmark`

**Verify:**  
```bash
cd services/api
python -m pytest tests/integration/triage/test_acceptance_gate.py::test_enrichment_latency_benchmark -v
# Expected: p99 latency <500ms, cache hit rate >80%, health scoring <50ms
```

#### 4.3 Verify eval harness accuracy ≥90%
**What:** Run triage on golden JSONL records; compute intent accuracy, route accuracy, entity F1; assert all ≥90%.  
**Files:**  
- `tests/integration/triage/test_acceptance_gate.py::test_eval_harness_accuracy`
- `tests/integration/triage/fixtures/golden_set.jsonl` (55 records: J1 WISMO 20, J2 escalation 20, J3 tool execution 15)

**Verify:**  
```bash
cd services/api
python -m pytest tests/integration/triage/test_acceptance_gate.py::test_eval_harness_accuracy -v
# Expected: Accuracy ≥90%, all metrics pass, deployment gate opens
```

#### 4.4 Database migration verification
**What:** Run Alembic migrations (0005, 0006) on staging DB; verify all tables, indices, materialized views created; test rollback.  
**Files:**  
- `packages/py_core/alembic/versions/0005_sprint3_enrichment_tables.py` (10 new tables + 6 indices)
- `packages/py_core/alembic/versions/0006_sprint3_materialized_views.py` (4 materialized views + pg_cron jobs)

**Verify:**  
```bash
cd packages/py_core
alembic upgrade head  # Apply migrations
alembic downgrade base  # Test rollback
alembic upgrade head  # Re-apply
# Expected: All migrations apply cleanly, rollback succeeds
python -c "from sqlalchemy import inspect; # Verify tables/indices/views exist"
```

#### 4.5 Environment setup and deployment checklist
**What:** Verify all environment variables set, Redis cluster configured, PostgreSQL extensions enabled (pg_cron), Stripe webhooks registered, model artifact downloaded.  
**Checklist:**
- [ ] Shopify API credentials in env vars
- [ ] Stripe API credentials + webhook secret
- [ ] Redis cluster reachable (test PING)
- [ ] PostgreSQL pg_cron extension enabled
- [ ] LightGBM model artifact downloaded to MODEL_ARTIFACT_PATH
- [ ] Celery workers running (test with sample task)
- [ ] Grafana datasource pointing to read-replica
- [ ] Slack webhook URL for anomaly alerts (if enabled)

**Verify:**  
```bash
# Test connectivity
redis-cli ping  # Expected: PONG
psql -c "CREATE EXTENSION IF NOT EXISTS pg_cron; SELECT * FROM cron.job;" # Expected: extension exists
curl -X POST https://api.stripe.com/v1/webhook_endpoints -H "Authorization: Bearer $STRIPE_SECRET_KEY" # Verify webhook registered

# Test model loading
python -c "from triage.scoring.model_manager import ModelManager; m = ModelManager(); print('Model loaded:', m.get_active_version())"
# Expected: Model version printed
```

#### 4.6 Create CI/CD acceptance gate workflow
**What:** Add GitHub Actions workflow `.github/workflows/sprint3-acceptance.yml` that runs all S3.10 tests before merge; must pass before Sprint 4 begins.  
**Files:**  
- `.github/workflows/sprint3-acceptance.yml`

**Verify:**  
```bash
git push origin feature/sprint3  # Trigger workflow
# Expected: Workflow runs, all S3.10 tests pass, PR mergeable
```

---

## Cross-Batch Integration Points

### Data Flow Verification
- **S3.1 → S3.4:** CustomerContext flags + order stats → HealthFeatures
- **S3.2 → S3.4:** OrderContext RFM → HealthFeatures
- **S3.3 → S3.4:** BillingContext dunning stage + failed payments → HealthFeatures
- **S3.6 → S3.4:** SentimentContext sentiment + NPS → HealthFeatures
- **S3.4 → S2.2:** HealthScore label (at_risk) + SHAP drivers → Decision matrix rules
- **S3.1 + S3.4 + S3.5 + S3.6 → S3.7:** Enrichment contexts → Prompt template variables
- **S3.7 → S2.7:** Dynamic prompt → Triage graph LLM call
- **S2.7 → S3.8:** Triage decision → Feedback ingestion + retraining

### Tenant Isolation Verification
- [ ] All cache keys formatted `{type}:{tenant_id}:{resource_id}`
- [ ] All DB queries include `WHERE tenant_id = $1` as first filter
- [ ] Enrichment contexts carry `tenant_id` field
- [ ] CI linter enforces tenant_id in SQL queries and cache ops

### Performance Validation
- [ ] Enrichment p99 latency <500ms (warm cache): 1000 iterations
- [ ] Health scoring latency <50ms: mock enrichment input
- [ ] Prompt rendering latency <100ms: 100 iterations
- [ ] Materialized view refresh <30s: pg_cron every 15 min
- [ ] Weekly retraining <5 min: mock 10k training samples

### Multi-API Rate Limiting
- [ ] Shopify rate limit (2 req/sec): exponential backoff, max 3 retries
- [ ] Stripe rate limit (100 req/sec): batching by customer, connection pooling
- [ ] All API failures fall back to Redis cache (TTL-based stale data acceptable)

---

## Test Coverage Summary

| Module | Unit (Tier A) | Integration (Tier B) | Contract (Tier C) | Golden Set (Tier D) | Target |
|--------|---------------|----------------------|-------------------|-------------------|---------|
| S3.1 Customer | 50 | 10 | 5 | — | ≥85% |
| S3.2 Orders | 40 | 10 | 5 | — | ≥85% |
| S3.3 Billing | 40 | 10 | 5 | — | ≥85% |
| S3.4 Health | 35 | 10 | — | 15 | ≥85% |
| S3.5 Knowledge | 30 | 5 | — | — | ≥85% |
| S3.6 Sentiment | 25 | 5 | — | — | ≥85% |
| S3.7 Prompting | 45 | 10 | — | 20 | ≥85% |
| S3.8 Feedback | 40 | 10 | — | — | ≥85% |
| S3.9 Analytics | 30 | 10 | — | — | ≥85% |
| **Total** | **335** | **70** | **15** | **35** | **≥85% avg** |

**Eval Harness (S3.10):** 55 golden records (J1: 20, J2: 20, J3: 15) → ≥90% accuracy required for gate pass

---

## Risks & Mitigations

### Risk 1: Shopify/Stripe API Timeouts
**Impact:** Enrichment fetch fails, cold-start latency spike  
**Mitigation:**  
- Exponential backoff (2^attempt, max 3 retries)
- Redis cache + DB fallback returns stale data on timeout
- Monitor rate limit headers; alert ops if approaching limit

### Risk 2: LightGBM Model Staleness
**Impact:** Model drift, predictions become unreliable  
**Mitigation:**  
- Weekly retraining job with performance gates (AUC ≥0.75)
- Drift detector monitors prediction metrics; alerts if AUC drops >5%
- Rollback procedure: revert model_versions.is_active to previous version

### Risk 3: Redis Cache Stampede
**Impact:** On cache expiry (3600s), all requests for same key hit external APIs  
**Mitigation:**  
- Probabilistic early refresh (10% chance to refresh at 90% TTL)
- Batch customer fetches (prefetch for high-volume customers)
- Use Redis lock to prevent duplicate fetches

### Risk 4: Multi-Tenant Data Leakage
**Impact:** Customer data visible to wrong tenant  
**Mitigation:**  
- All cache keys and DB queries include tenant_id
- CI linter enforces tenant_id in new code
- Audit logging on all data access (S1.8)

### Risk 5: Prompt Injection via Context
**Impact:** Malicious customer name or context variable injects LLM instructions  
**Mitigation:**  
- Sanitize context variables (no Jinja2 syntax in input)
- Template escaping in Jinja2 default
- LLM guard rails on output (injection pattern detection)

### Risk 6: Feature Decay in Health Model
**Impact:** Enrichment API schema change breaks HealthFeatures extraction  
**Mitigation:**  
- Contract tests validate Shopify/Stripe response schemas weekly
- Feature importance monitoring (SHAP) alerts if top driver becomes unavailable
- Fallback for missing enrichment fields (imputation strategy)

---

## Known Limitations & Deferred Work

### Limitations Inherited from Sprint 2
1. **Groundedness scorer uses substring + word overlap, not semantic similarity** — May falsely flag grounded claims as ungrounded if wording differs. Acceptable for MVP; future sprint can add semantic similarity (cross-encoder model).
2. **Entity linker falls back gracefully** — Does not prevent tool binding on unlinked entities; validator catches this. Future sprint can make linker failure hard-stop.
3. **In-memory autonomy policies** — Loaded as Dict[str, int]; no live DB reload. Future sprint can add hot-reload from policy_overrides table.

### Deferred to Sprint 4 / Beyond
1. **Multi-turn reasoning loops:** S3 provides single-turn enrichment; S4 will add clarifying questions, mid-conversation context updates.
2. **Tool integration:** S3 provides context; S4 will wire tools (send email, create tickets, offer retention incentives).
3. **Advanced prompt optimization:** S3 uses 4 templates; future work: per-agent prompt tuning, dynamic few-shot selection.
4. **Real-time personalization:** S3 enrichment is per-customer snapshot; future work: session-level context (recent interactions) and dynamic tone adjustment.
5. **Explainability UI:** S3 computes SHAP drivers; future work: agent dashboard showing drivers, audit trail visualization.

---

## Summary

Sprint 3 implements 10 deliverables across 4 sequential batches:

- **Batch 1 (S3.1–S3.3):** Enrichment data fetching layer (customer, order, billing) with Redis caching and DB fallback.
- **Batch 2 (S3.4–S3.6):** ML scoring and classification (health scoring with SHAP, sentiment analysis, knowledge gap analysis).
- **Batch 3 (S3.7–S3.9):** Prompt engineering, learning loop, and analytics dashboards.
- **Batch 4 (S3.10):** Acceptance gate, deployment verification, CI/CD integration.

All components integrate into the Sprint 2 triage graph (S2.7) via enriched TriageState, dynamic prompts (S3.7), and decision matrix enhancements (S3.1 flags + S3.4 health label). Testing includes 335 unit tests, 70 integration tests, 15 contract tests, and 35 eval harness records, targeting ≥85% coverage per module and ≥90% eval accuracy. Performance targets: enrichment p99 <500ms, cache hit >80%, health scoring <50ms.

Deployment is blocked until all acceptance tests pass (S3.10), model validation clears (AUC ≥0.75), and environment setup checklist is complete. Sprint 4 builds on enriched context for agent decision refinement and tool integration.

---

*Plan finalized: Sprint 3 ready for implementation.*

