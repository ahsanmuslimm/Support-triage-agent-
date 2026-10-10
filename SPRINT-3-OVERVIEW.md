# Sprint 3 Overview — Enrichment & Context Layers

**Sprint 3** builds the enrichment engine that transforms raw customer data into actionable signals, enabling the triage graph (S2.7) to make smarter routing and escalation decisions. By injecting customer context—account health, payment status, sentiment history, and order patterns—into every triage decision, Sprint 3 raises autonomous resolution rates and improves agent routing quality.

---

## Sprint Goals

Sprint 3 achieves three critical outcomes:

1. **Unified enrichment pipeline:** Five parallel enrichers (customer, orders, billing, sentiment, escalation) fetch and cache customer context on-demand, reducing cold-start latency to <500ms p99.

2. **Churn-risk visibility:** LightGBM health-scoring model (S3.4) with SHAP explainability detects at-risk customers in real-time, enabling proactive retention and empathetic tone injection.

3. **Decision context amplification:** Enriched context is injected into triage prompts (S3.7), decision matrix rules (S2.2), and health scores (S3.4), raising triage accuracy from ~80% to >=90% (measured by S3.10 acceptance gate).

**Link to Sprint 2:** The triage graph (S2.7) routes queries based on rules in the decision matrix (S2.2). Sprint 3 enriches both with customer context so rules become dynamic: a refund request from a loyal VIP routes to Tier 2, but the same request from a fraud-flagged customer routes to fraud investigation. Enrichment unlocks intelligent routing that Sprint 2's graph can only express statically.

---

## Sprint Summary Table

| Item | Title | Effort | Status | Key Output | Dependencies |
|------|-------|--------|--------|-----------|--------------|
| S3.1 | Customer & Account Enrichment | 2d | Complete | CustomerContext (profile, flags, VIP/at-risk signals) | S1.5, S2.7, Shopify/Stripe APIs |
| S3.2 | Order & Transaction Enrichment | 2.5d | Complete | OrderContext (RFM, 90-day history, risk signals, refund/chargeback tracking) | S1.5, S3.1, Shopify/Stripe APIs |
| S3.3 | Billing & Payment History Context | 2d | Complete | BillingContext (payment methods, dunning stage, failed payments, churn signals) | S2.2, S3.4, S3.7, Stripe API |
| S3.4 | Account Health Scoring | 3d | Complete | HealthScore (LightGBM P(churn), SHAP explanation, threshold-tuned to F-beta) | S3.1, S3.2, S3.3, S2.2, S3.8 |
| S3.5 | Knowledge Gap Analysis | 2d | Complete | KnowledgeGapReport (coverage %, top-10 gaps by escalation count, recommendations) | S2.4, S2.7, S3.8 |
| S3.6 | Customer Sentiment & NPS History | 2d | Complete | SentimentContext (NPS segment, trend, sentiment scores, risk flags) | S3.1, S3.4, S3.7 |
| S3.7 | Prompt Engineering & Context Injection | 2.5d | Complete | Dynamic prompts (4 tone templates, context injection points, 3500-token budget) | S3.1, S2.7, S2.2, S3.4 |
| S3.8 | Continuous Learning Loop | 3d | Complete | Feedback ingestion, weekly retraining, A/B testing framework, drift detection | S1.3, S3.4, S2.7, S3.1, Celery |
| S3.9 | Business Intelligence & Analytics Dashboards | 3d | Complete | Materialized views, metrics endpoints, anomaly detection, Grafana panels | S2.7, S3.1, pg_cron, PostgreSQL |
| S3.10 | Sprint 3 Acceptance Gate | 1d | Complete | 3 acceptance scenarios, E2E enrichment flow test, p99 latency <500ms, eval accuracy ≥90% | S3.1–S3.9, S2.7, pytest |

---

## Architecture Diagram (ASCII)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        CUSTOMER SUPPORT TRIAGE AGENT                    │
│                         Sprint 3 Enrichment Pipeline                    │
└─────────────────────────────────────────────────────────────────────────┘

                         ┌─────────────────────┐
                         │  Incoming Query     │
                         │  (S1.5 Identity)    │
                         └────────────┬────────┘
                                      │
                    ┌─────────────────▼────────────────┐
                    │  Cache Layer (Redis)             │
                    │  TTL: 3600s per enricher         │
                    │  Key: enrichment:{tenant}:{id}   │
                    └────────────────┬───────────────┬─┘
                                     │               │
                    ┌────────────────▼─┐         (miss)
                    │   (cache hit)     │             │
                    │   Return cached   │             │
                    │   context         │    ┌────────▼──────────────────────┐
                    │                   │    │ Parallel Enrichers (S3.1–S3.3) │
                    │                   │    └────────┬─────────┬─────────┬───┘
                    │                   │             │         │         │
                    │                   │   ┌─────────▼──┐  ┌───▼────┐  ┌──▼──────┐
                    │                   │   │ Customer   │  │ Orders │  │ Billing │
                    │                   │   │ Enricher   │  │Agg     │  │Enricher │
                    │                   │   │(Shopify    │  │(Shopify│  │(Stripe) │
                    │                   │   │ Profile)   │  │ Orders)│  │         │
                    │                   │   └─────────┬──┘  └───┬────┘  └──┬──────┘
                    │                   │             │         │         │
                    │       ┌───────────┘             │         │         │
                    │       │                ┌────────▼────┐   │         │
                    │       │                │ Sentiment   │   │         │
                    │       │                │ Enricher    │   │         │
                    │       │                │ (NLP Sent,  │   │         │
                    │       │                │  NPS Agg)   │   │         │
                    │       │                └────────┬────┘   │         │
                    │       │                         │        │         │
        ┌───────────▼───────▼──────────┬──────────────▼────────▼─────────▼────┐
        │  Context Aggregation Layer    │ (All enrichers return in parallel)   │
        │  • CustomerContext (S3.1)     │ • Merge into EnrichmentBundle       │
        │  • OrderContext (S3.2)        │ • Store in Redis (TTL 3600s)        │
        │  • BillingContext (S3.3)      │ • On miss: DB fallback              │
        │  • SentimentContext (S3.6)    └──────────────┬──────────────────────┘
        └───────────┬────────────────────────────────────┬─────────────────────┘
                    │                                    │
        ┌───────────▼────────────────────────────────────▼─────────────────┐
        │         Health Scoring Pipeline (S3.4)                           │
        │  • Build HealthFeatures from contexts                            │
        │  • LightGBM predict: P(churn) ∈ [0, 1]                          │
        │  • SHAP explain: top 5 drivers                                   │
        │  • Label: 'at_risk' if score >= 0.65 else 'healthy'             │
        │  • Log to audit_entries (S1.8)                                   │
        └───────────┬────────────────────────────────────────────────────┬─┘
                    │                                                   │
        ┌───────────▼────────────────┐      ┌──────────────────────────▼──┐
        │ Prompt Template Engine     │      │ Decision Matrix (S2.2)      │
        │ (S3.7)                     │      │ • Route based on health     │
        │ • Select tone (4 options)  │      │ • Apply enrichment rules    │
        │ • Inject context into      │      │ • Compute escalation tier   │
        │   4 base templates         │      │ • Set customer tone (4 TBD) │
        │ • Enforce 3500-token       │      │ • Determine priority        │
        │   budget                   │      └───────────┬─────────────────┘
        │ • Return dynamic prompt    │                  │
        └─────────┬──────────────────┘                  │
                  │         ┌─────────────────────────┘
                  │         │
        ┌─────────▼─────────▼──────────────────────────┐
        │     Triage Graph (S2.7) with Context        │
        │  • Receives enriched TriageState            │
        │  • Executes with injected prompt            │
        │  • Makes routing decision based on:         │
        │    - Health score + label                   │
        │    - Enrichment flags (fraud, abuse, VIP)   │
        │    - Order & billing risk signals           │
        │    - Sentiment and NPS context              │
        │  • Computes escalation_reason + metadata    │
        └─────────┬────────────────────────────────────┘
                  │
        ┌─────────▼──────────────────────┐
        │    Final Decision + Escalation │
        │  • triage_decision (handle/    │
        │    escalate/refer)             │
        │  • tone (urgency/empathy/      │
        │    formal/neutral)             │
        │  • escalation_team (if needed) │
        │  • tier (1/2/human)            │
        │  • metadata (reasoning,        │
        │    health_score, drivers)      │
        └──────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│ Supporting Infrastructure                                                │
├──────────────────────────────────────────────────────────────────────────┤
│ • Redis: Enrichment cache (per-enricher TTL 3600s)                       │
│   Key format: enrichment:{tenant_id}:{customer_id}                       │
│   Key format: sentiment:{tenant_id}:{customer_id}                        │
│   Key format: billing:{tenant_id}:{customer_id}                          │
│   Fallback: PostgreSQL cache tables (billing_enrichment_cache, etc.)    │
│                                                                          │
│ • PostgreSQL:                                                            │
│   - customer_enrichment_cache (S3.1)                                     │
│   - order_enrichment_cache (S3.2)                                        │
│   - billing_enrichment_cache (S3.3)                                      │
│   - model_versions (S3.4, S3.8)                                          │
│   - nps_surveys (S3.6)                                                   │
│   - feedback_events (S3.8)                                               │
│   - ab_tests, ab_test_outcomes (S3.8)                                    │
│   - anomaly_events (S3.9)                                                │
│   - audit_entries (S1.8, extended in S3.4)                              │
│                                                                          │
│ • LightGBM Model Artifacts (S3.4):                                       │
│   - models/account_health_v1.lgb (trained by S3.8 weekly)               │
│   - Versioning: model_versions table tracks all versions                 │
│   - Reload on SIGHUP (S3.8 deploys new version)                         │
│                                                                          │
│ • Celery (async jobs):                                                   │
│   - Weekly retraining job (S3.8)                                         │
│   - Anomaly detection monitoring (S3.9)                                  │
│   - Analytics refresh (S3.9 materialized views via pg_cron)             │
│                                                                          │
│ • Grafana/Metabase (S3.9):                                               │
│   - Materialized views (v_triage_daily, v_intent_accuracy, etc.)        │
│   - Real-time metrics endpoints                                          │
│   - Dashboards: Triage rate, escalation rate, agent accuracy, anomalies │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Component Deep-Dives

### S3.1 — Customer & Account Enrichment

**Purpose:** Fetch and cache customer profile, account age, order history, subscription status, and account flags (fraud, abuse, VIP, at-risk).

**Key Technical Decisions:**
- **Parallel fetching:** Use `asyncio.gather()` to fetch Shopify and Stripe concurrently (reduces latency vs. sequential)
- **Cache first:** Redis with 3600s TTL; DB fallback on Stripe/Shopify timeout
- **Flag-based signals:** Binary flags (fraud_flag, abuse_flag, vip, at_risk) allow decision matrix rules to be simple and predictable
- **Account age signal:** Computed at enrichment time; accounts <30 days old are flagged for abuse monitoring

**Testing Approach:**
- Unit tests: Flag logic, VIP thresholds (total_spent > $1000), age calculation
- Integration tests: Mock Shopify/Stripe API responses (using `responses` library or httpx mocks); verify cache TTL
- Contract tests: Validate Shopify and Stripe response schemas

**Adjacent Components:**
- **Upstream (S1.5):** Receives customer_id from identity resolution
- **Downstream (S2.2, S3.7, S3.4):** Context injected into decision matrix, prompt templates, health scoring

---

### S3.2 — Order & Transaction Enrichment

**Purpose:** Aggregate order history, compute RFM metrics, track refunds/chargebacks, and identify velocity spikes or high-value order risk.

**Key Technical Decisions:**
- **90-day lookback:** Focuses on recent behavior (more predictive of churn than all-time)
- **Risk scoring:** Weighted sum of signals (chargebacks: 0.40, multiple refunds: 0.25, frequent returner: 0.20, velocity spike: 0.10)
- **Frequency as median:** Uses median days-between-orders (resistant to outliers) rather than mean
- **Parallel fetching:** Shopify orders, Stripe refunds, and Stripe chargebacks fetched concurrently

**Testing Approach:**
- Unit tests: Risk signal detection (chargeback flag, refund threshold), frequency median computation, seasonal pattern grouping
- Integration tests: Cache miss → API fetch → cache write; API failure → DB fallback
- Contract tests: Shopify order schema (id, created_at, total_price, status); Stripe refund schema

**Adjacent Components:**
- **Upstream (S1.5, S3.1):** Enrichment chaining; orders enrich S3.1 customer context
- **Downstream (S2.2, S3.4):** RFM features feed health scoring; risk signals trigger routing rules

---

### S3.3 — Billing & Payment History Context

**Purpose:** Surface payment health, dunning stage, failed payments, card expiry, and churn risk from billing platform (Stripe).

**Key Technical Decisions:**
- **Dunning escalation:** Map Stripe state (none → warning → final → suspended) to internal dunning_stage enum; 'final' or 'suspended' = churn risk
- **Stripe webhook invalidation:** Payment events immediately invalidate cache, ensuring real-time accuracy
- **Churn signal computation:** Combined flag (dunning_stage in ['final', 'suspended'] OR failed_payments_90d >= 3)
- **Card expiry as 30-day threshold:** Flag cards expiring within 30 days to enable proactive outreach

**Testing Approach:**
- Unit tests: Dunning stage computation (rules: canceled sub → suspended, retry≥3 + failure≥2 → final, etc.); card expiry logic
- Integration tests: Mock Stripe API; webhook signature validation; cache invalidation on payment_failed event
- Contract tests: Stripe Invoice schema (status, attempt_count, next_payment_attempt); Customer schema (payment methods, address, phone)

**Adjacent Components:**
- **Upstream (Stripe API, S1.5):** Payment data source
- **Downstream (S2.2, S3.4, S3.7):** Dunning stage drives retention routing; failed payments are features in health model

---

### S3.4 — Account Health Scoring

**Purpose:** Train and deploy a LightGBM binary classifier predicting P(churn); compute SHAP explanations for transparency; tune threshold to maximize F-2 (recall-weighted).

**Key Technical Decisions:**
- **15-feature vector:** RFM, payment health, support engagement, sentiment, NPS, plan tier (all numeric or ordinal)
- **LightGBM:** Fast training (200 estimators, <30s), deterministic predictions, native SHAP integration
- **F-beta threshold tuning:** Beta=2 emphasizes recall (catching churners) over precision (false alarms); threshold ~0.65 achieves 70% recall
- **SHAP TreeExplainer:** <5ms per prediction (vs. KernelExplainer ~500ms); provides audit trail of decision drivers
- **Model versioning:** All versions stored in model_versions table; active version reloaded on SIGHUP

**Testing Approach:**
- Unit tests: Feature extraction (dunning_stage string → ordinal), risk signal thresholds, SHAP top-5 filtering
- Integration tests: Full pipeline (mock enrichment → predict → explain); audit log written to audit_entries
- Model validation: Load production model, run on golden test set, measure AUC ≥ 0.75 and accuracy ≥ 0.80

**Adjacent Components:**
- **Upstream (S3.1, S3.2, S3.3, S3.6):** Enrichment contexts are feature sources
- **Downstream (S2.2, S3.7, S3.8):** Health score and label drive routing rules, tone selection, and retraining feedback

---

### S3.5 — Knowledge Gap Analysis

**Purpose:** Analyze escalations to identify KB coverage gaps, rank by frequency, and generate actionable expansion recommendations.

**Key Technical Decisions:**
- **Query categorizer:** Zero-shot classification using sentence-transformers (fallback to keyword matching)
- **Coverage metric:** (queries resolved by KB) / (total queries per category); 0–1 scale
- **Gap ranking:** Sort by escalation_count descending; assign priority (high: >50/week, medium: 20–50, low: <20)
- **Nightly job:** Scheduled at 02:00 UTC; 7-day lookback window; results cached in Redis (24h TTL)

**Testing Approach:**
- Unit tests: Categorizer (billing text → 'billing' category), coverage calculation, gap ranking, recommendation template filling
- Integration tests: Query mock data, run pipeline, verify coverage_score and top_missing_areas in report
- Mock KB: Stub KB lookup to verify coverage calculation with known data

**Adjacent Components:**
- **Upstream (S2.4, S2.7):** Reads conversations and escalation_events tables
- **Downstream (S3.8, Analytics):** Gap recommendations feed continuous learning; coverage trends displayed in dashboards

---

### S3.6 — Customer Sentiment & NPS History

**Purpose:** Aggregate historical sentiment from support tickets and NPS survey responses; compute trend; flag risk (avg_sentiment < -0.3 or nps_score < 6).

**Key Technical Decisions:**
- **TextBlob for sentiment:** Lightweight (<100ms), synchronous, good for internal use
- **Transformer fallback:** DistilBERT via HuggingFace (if `USE_TRANSFORMER_SENTIMENT=true`)
- **NPS aggregation:** Average of last 3 surveys; segment logic (≥9: promoter, 7–8: passive, <7: detractor)
- **Trend via linear regression:** Slope thresholds (>0.05: improving, <-0.05: declining, else: stable)

**Testing Approach:**
- Unit tests: TextBlob sentiment on positive/negative text, NPS segmentation logic, trend computation
- Integration tests: Enrich with mock interactions and surveys, verify cache hit/miss
- Transformer validation: Confirm fallback works if transformer unavailable

**Adjacent Components:**
- **Upstream (S3.1, conversations table, nps_surveys table):** Data source
- **Downstream (S3.4, S3.7):** Sentiment score is health model feature; risk_flag triggers empathy tone and health penalties

---

### S3.7 — Prompt Engineering & Context Injection

**Purpose:** Build dynamic LLM prompts that inject enriched customer context (tone, examples, decision rationale) before each triage turn; enforce 3500-token budget.

**Key Technical Decisions:**
- **4 tone templates:** Default, Churn Risk (empathy), High-Value (urgency), Enterprise (formal) — selected by deterministic rules
- **Injection points:** System intro, decision rationale, escalation justification blocks
- **Token budget enforcement:** Target 3500 tokens; truncate few-shot examples first, then context if needed; hard max 4096
- **Few-shot examples:** YAML-based, stored in git, 2 examples per (tone, intent) pair for zero-shot learning
- **No LLM for tone:** Deterministic priority-based selection (churn risk → empathy, VIP+high_value → urgency, enterprise → formal, else → neutral)

**Testing Approach:**
- Unit tests: Tone selector determinism, variable injection completeness (no remaining `{{` in output), token budget enforcement
- Integration tests: Build full prompt with EnrichmentBundle, verify tone keywords in output (empathy prompt contains empathy keywords, etc.)
- Tone validation: Sample 50 prompts, classify by keyword match, target ≥90% accuracy

**Adjacent Components:**
- **Upstream (S3.1, S3.4, S2.2):** Context source
- **Downstream (S2.7):** Triage graph executes with injected prompt; improves LLM decision quality

---

### S3.8 — Continuous Learning Loop

**Purpose:** Ingest human feedback (thumbs up/down, escalation judgments), retrain models weekly, run A/B tests, and detect drift in real-time.

**Key Technical Decisions:**
- **Feedback ingestion:** HTTP POST endpoint, async storage to feedback_events table + Redis Streams for processing
- **Weekly retraining:** Celery Beat job; trains intent classifier (S1.3) and health model (S3.4) on labeled feedback; validates against performance gates (AUC ≥ 0.75)
- **A/B testing:** Deterministic assignment (hash-based); chi-square significance test; support multiple concurrent tests
- **Drift detection:** EWMA baseline + ±3σ control limits; triggers alerts on critical deviation

**Testing Approach:**
- Unit tests: Feedback event validation, dunning stage computation, F-beta threshold tuning
- Integration tests: Ingest mock feedback, trigger retraining job, verify model artifact upload and version recording
- A/B testing: Deterministic assignment validation, significance test computation, winner detection

**Adjacent Components:**
- **Upstream (S3.1–S3.6):** Model retraining depends on enrichment feature quality
- **Downstream (S2.7, S3.4, S3.9):** Retraining results feed triage graph updates, analytics monitoring

---

### S3.9 — Business Intelligence & Analytics Dashboards

**Purpose:** Provide real-time and historical visibility into triage performance, agent effectiveness, customer outcomes, and system anomalies.

**Key Technical Decisions:**
- **Materialized views:** Four views (v_triage_daily, v_intent_accuracy, v_agent_tool_usage, v_customer_outcomes) refreshed every 15–30 min via pg_cron
- **Metrics endpoints:** FastAPI endpoints for summary, agent performance, customer outcomes, anomalies
- **Anomaly detection:** EWMA baseline with ±3σ control limits; Slack webhook alerts on critical deviations
- **Grafana dashboards:** Time series (triage rate), gauge (escalation rate <20%), histogram (resolution time), heatmap (intent accuracy)

**Testing Approach:**
- Unit tests: Triage rate calculation (80 autonomous + 20 escalated → 0.80), anomaly detection (value outside bounds → alert), cost calculation
- Integration tests: Insert mock data, refresh materialized view, query metrics endpoints, verify schemas
- Dashboard rendering: Docker Compose spin-up, import dashboard JSON, render panels (E2E smoke test)

**Adjacent Components:**
- **Upstream (S2.7, S3.1):** Metrics source (conversations, enrichment)
- **Downstream (Ops/Analytics teams):** Dashboards consumed by support managers and product team

---

### S3.10 — Sprint 3 Acceptance Gate

**Purpose:** Define and execute mandatory exit criteria for Sprint 3 completion (3 acceptance scenarios, E2E enrichment flow, performance benchmarks, eval harness accuracy).

**Key Technical Decisions:**
- **3 acceptance scenarios:** High-value (triage_decision=handle), Churn Risk (escalate w/ retention), Fraud Flagged (escalate w/ fraud team)
- **E2E enrichment flow:** Call all 5 enrichers in sequence, measure p99 latency <500ms
- **Performance benchmark:** 1000 iterations with warm Redis cache; assert p99 <500ms and hit rate >80%
- **Eval harness:** Run triage on golden JSONL records; assert accuracy ≥90%

**Testing Approach:**
- Scenario tests: Mock enrichment contexts, assert triage decisions match expected (e.g., scenario A → handle, scenario B → escalate)
- Latency tests: Measure wall-clock time; use `time.perf_counter()` for precision
- Cache statistics: `redis.info()` for keyspace_hits and keyspace_misses
- Eval tests: Load golden records, compute accuracy, abort deployment if <90%

**Adjacent Components:**
- **Upstream (S3.1–S3.9):** All sprint items tested
- **Downstream (Sprint 4):** Acceptance gate passes before Sprint 4 begins; enriched context is ready for agent decision refinement

---

## Data Flow

This sequence traces a single customer query through the entire enrichment pipeline to final triage decision:

1. **Incoming Query (S1.5 Identity Resolution)**
   - Customer ID resolved from email or session
   - Tenant ID extracted from request context
   - Query intent detected (S1.3 classifier)

2. **Cache Check (Redis)**
   - Enrichment engine checks Redis for cached context
   - Key format: `enrichment:{tenant_id}:{customer_id}` (TTL 3600s)
   - If hit: skip to step 7 (Health Scoring)
   - If miss: proceed to step 3

3. **Parallel Enrichment Fetches (S3.1–S3.3, S3.6)**
   - **S3.1 Customer Enricher:** Fetch Shopify customer profile, account age, subscription status
   - **S3.2 Order Aggregator:** Fetch Shopify orders (90d), compute RFM, detect risk signals
   - **S3.3 Billing Enricher:** Fetch Stripe payment methods, invoices, dunning stage
   - **S3.6 Sentiment Enricher:** Fetch recent conversations, NPS surveys; compute sentiment trend
   - All four fetch concurrently (asyncio.gather); latency = max(enricher latencies)
   - On API failure: fall back to DB cache tables

4. **Context Aggregation**
   - Merge CustomerContext, OrderContext, BillingContext, SentimentContext into EnrichmentBundle
   - Store bundle in Redis (3600s TTL)
   - On cache miss: store in DB fallback tables (with gzip compression)

5. **Health Scoring (S3.4)**
   - Extract HealthFeatures from enrichment bundle (15 numeric/ordinal fields)
   - LightGBM predict: P(churn) ∈ [0, 1]
   - SHAP explain: compute top 5 feature drivers
   - Apply threshold (0.65): label = 'at_risk' if score ≥ 0.65 else 'healthy'
   - Log to audit_entries (S1.8) with SHAP JSON

6. **Decision Matrix Evaluation (S2.2)**
   - Apply routing rules based on enrichment signals:
     - If fraud_flag OR abuse_flag: escalate to fraud/abuse team
     - Else if health_label='at_risk' AND dunning_stage='final': escalate to retention (empathy tone)
     - Else if is_vip AND high_value_order: route to senior agent (urgency tone)
     - Else if escalation_rate > 0.3: escalate to specialist (formal tone)
     - Else: tier 1 or self-service (neutral tone)
   - Compute escalation_tier, escalation_team, tone

7. **Prompt Engineering (S3.7)**
   - Select tone template based on signals:
     - health_label='at_risk' OR churn_risk_signal → empathy
     - is_vip AND high_value_order → urgency
     - subscription_plan='enterprise' → formal
     - else → neutral
   - Inject enrichment context into selected template:
     - System intro: acknowledge customer status (VIP, at-risk, enterprise)
     - Decision rationale: insert intent, health score label, top SHAP driver
     - Escalation block: specify escalation conditions and team
     - Few-shot examples: 2 (tone, intent) -specific examples from YAML
   - Enforce 3500-token budget (truncate few-shot first, then context if needed)

8. **Triage Graph Execution (S2.7)**
   - Execute triage graph with enriched TriageState:
     - Nodes: enrich_context (already done), classify_intent, apply_rules, decide, escalate
     - Each node receives enriched context (avoid re-fetching)
     - LLM calls use injected dynamic prompts (not generic system prompts)
   - Output: triage_decision, tone, health_label, escalation_team, metadata

9. **Escalation & Response**
   - If triage_decision='escalate': route to escalation_team queue with health score, drivers, and enrichment snapshot
   - If triage_decision='handle': return routing recommendation + self-service URL or tier-1 queue
   - If triage_decision='refer': route to knowledge base or FAQ

10. **Feedback & Continuous Learning (S3.8)**
    - Human reviewer provides feedback (thumbs up/down, manual intent tag, escalation judgment)
    - Feedback stored in feedback_events table + Redis Streams
    - Weekly retraining job (Celery Beat) consumes feedback, retrains models, validates against performance gates
    - A/B testing framework assigns variant and records outcome
    - Drift detector monitors metrics, triggers Slack alerts on critical deviations

---

## Shared Infrastructure

### Redis: Caching Strategy

Redis serves as L1 cache across all enrichers. Fallback is PostgreSQL cache tables (L2).

**TTL per Enricher:**
- S3.1 Customer: 3600s (1 hour) — account profile changes rarely
- S3.2 Orders: 3600s — order history updated on new order (Shopify webhook)
- S3.3 Billing: 3600s (but invalidated on Stripe webhook) — payment status critical
- S3.6 Sentiment: 3600s — sentiment recalculated nightly (S3.8)
- S3.4 Health Score: not cached (computed on-demand, <100ms with warm cache)

**Key Naming Convention:**
```
enrichment:{tenant_id}:{customer_id}                 # Generic (S3.1)
customer:{tenant_id}:{customer_id}                   # Customer-specific
order:{tenant_id}:{customer_id}                      # Orders
billing:{tenant_id}:{customer_id}                    # Billing (invalidated on webhook)
sentiment:{tenant_id}:{customer_id}                  # Sentiment
knowledge_gaps:{tenant_id}:{date}                    # KB gaps (S3.5, 24h TTL)
health_model:active_version                          # LightGBM model metadata
ab_test:{test_id}:assignments                        # A/B test assignments
```

**Invalidation Strategy:**
- S3.3 Billing: Stripe webhooks (`invoice.payment_failed`, `invoice.payment_succeeded`, `subscription.deleted`) immediately DELETE cache key
- S3.5 Knowledge gaps: TTL-based (24h); no explicit invalidation
- S3.4 Health model: SIGHUP signal reloads from disk

### PostgreSQL: New Tables

All tables added in Sprint 3 migrations (Alembic):

| Table | Purpose | Columns |
|-------|---------|---------|
| `customer_enrichment_cache` | L2 fallback for S3.1 | tenant_id, customer_id, name, account_age_days, order_count, total_spent, subscription_status, flags[], is_vip, is_at_risk, is_fraud_flagged, fetched_at, expires_at |
| `customer_flags` | Account flags (fraud, abuse, VIP) | tenant_id, customer_id, flag_name, flagged_at, flagged_by_user_id, reason, is_active |
| `order_enrichment_cache` | L2 fallback for S3.2 | tenant_id, customer_id, payload (JSONB: orders, RFM, risk_signals, risk_score) |
| `billing_enrichment_cache` | L2 fallback for S3.3 | tenant_id, customer_id, payload (JSONB: payment_methods, dunning_stage, failed_payments_90d, churn_risk_signal) |
| `nps_surveys` | NPS survey responses (S3.6) | tenant_id, customer_id, score (0–10), comment, survey_date |
| `model_versions` | LightGBM artifact versioning (S3.4, S3.8) | tenant_id, name ('account_health'), version, artifact_path (S3 URI), metrics (JSONB: {auc, f_beta, precision, recall}), config (JSONB), trained_at, deployed_at, is_active |
| `feedback_events` | Human feedback for retraining (S3.8) | tenant_id, session_id, customer_id, agent_decision, human_feedback (enum), tag, feedback_at, agent_version |
| `ab_tests` | A/B test configurations (S3.8) | test_id, name, variant_a, variant_b, traffic_split, status, tenant_id, created_at, ended_at |
| `ab_test_outcomes` | A/B test result recordings (S3.8) | test_id, session_id, variant, outcome ('converted'/'escalated'/'churned'), tenant_id, recorded_at |
| `anomaly_events` | Drift detection alerts (S3.9) | tenant_id, metric_name, value, expected_low, expected_high, severity ('warning'/'critical'), detected_at, acknowledged_at, acknowledged_by_user_id |
| `metric_history` | Metric baselines for anomaly detection (S3.9) | tenant_id, metric_name, value, recorded_at |

**Indices:**
- `idx_customer_flags_active` on (tenant_id, customer_id) WHERE is_active=TRUE
- `idx_enrichment_expires` on (expires_at) — for cleanup job
- `idx_order_enrichment_updated` on (updated_at DESC)
- `idx_nps_surveys_customer` on (tenant_id, customer_id, survey_date DESC)
- `idx_model_versions_active` on (tenant_id, is_active=TRUE)
- `idx_anomaly_events_severity` on (severity) WHERE acknowledged_at IS NULL

### LightGBM + SHAP: Model Artifact Management

**Training & Deployment Flow:**
1. S3.8 (Continuous Learning) trains model weekly on feedback + enrichment data
2. Model serialized to `models/account_health_v{timestamp}.lgb`
3. Artifact uploaded to S3: `s3://ml-models-bucket/account_health_v{timestamp}.lgb`
4. Version record inserted into `model_versions` table (name, version, artifact_path, metrics, is_active=FALSE)
5. If performance gates pass (AUC ≥ 0.75): `UPDATE model_versions SET is_active=TRUE WHERE version=new_version`
6. Process sends SIGHUP to app; handler calls `reload_health_model()` → loads new model from disk

**SIGHUP Reload Pattern (Linux/Unix):**
```python
import signal
import logging

logger = logging.getLogger(__name__)

def handle_sighup(signum, frame):
    """Reload model on SIGHUP (signal 1)."""
    logger.info("SIGHUP received, reloading health model...")
    reload_health_model()
    logger.info("Health model reloaded successfully")

signal.signal(signal.SIGHUP, handle_sighup)
```

**Deployment on K8s:**
- Model artifact stored in ConfigMap or etcd
- App Pod has init container that downloads latest model from S3
- `SIGHUP` sent via `kubectl exec` or webhook after model training completes

### Celery: Task Queues

Celery Beat schedules and executes async tasks:

| Task | Schedule | Purpose | Dependency |
|------|----------|---------|------------|
| `retrain_all_tenants` | Weekly, Sunday 03:00 UTC | Train intent + health models on feedback (S3.8) | S1.3, S3.4, S3.8 |
| `run_gap_analysis_job` | Nightly, 02:00 UTC | Analyze KB coverage gaps (S3.5) | S2.4, S3.5 |
| `refresh_materialized_views` | Every 15 min | Update triage_daily, intent_accuracy views (S3.9) | pg_cron (alternative: Celery) |
| `detect_anomalies` | Every 5 min | Monitor metrics for drift, alert on critical deviation (S3.9) | S3.9 |

Celery configuration (celery_config.py):
```python
from celery.schedules import crontab

app.conf.beat_schedule = {
    'retrain-weekly': {
        'task': 'tasks.retrain_all_tenants',
        'schedule': crontab(day_of_week=6, hour=3, minute=0),
    },
    'gap-analysis-nightly': {
        'task': 'tasks.run_gap_analysis_job',
        'schedule': crontab(hour=2, minute=0),
    },
    'detect-anomalies': {
        'task': 'tasks.detect_anomalies',
        'schedule': 300.0,  # Every 5 minutes
    },
}
```

---

## Testing Strategy

### TDD Tier Summary

| Tier | Name | Description | Sprint 3 Test Count |
|------|------|-------------|-------------------|
| **A** | Unit Tests | Pure functions, no I/O (cache logic, feature extraction, calculations). Fast (<1s each). | ~120 |
| **B** | Integration Tests | Mock external APIs (Shopify, Stripe), test cache miss/hit, DB fallback, webhook handlers. <5s each. | ~60 |
| **C** | Contract Tests | Validate external API schemas (Shopify order, Stripe invoice). Stub-based. | ~20 |
| **D** | Golden Set / Eval Tests | Run triage on recorded golden conversations; measure accuracy ≥90%. <30s total. | ~50 |
| **E** | Dashboard Smoke Tests | Docker spin-up Grafana, import dashboards, verify panels render. <60s. | ~5 |

**Coverage Targets:**
- Unit test coverage >= 85% for all new modules (S3.1–S3.9)
- Integration test coverage >= 70% for enrichment pipelines
- All acceptance scenarios (S3.10) pass
- Eval harness accuracy >= 90% on golden set

---

## Deployment Checklist

Before bringing Sprint 3 live, complete these steps:

1. **Database Migrations**
   - [ ] Run Alembic migrations for all 10 new tables
   - [ ] Verify indices created and query plans optimized
   - [ ] Test rollback procedure on staging

2. **Environment Variables**
   - [ ] Set `SHOPIFY_API_KEY`, `SHOPIFY_API_SECRET`, `SHOPIFY_STORE_DOMAIN`
   - [ ] Set `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`
   - [ ] Set `REDIS_URL` (cluster or standalone)
   - [ ] Set `USE_TRANSFORMER_SENTIMENT=false` (TextBlob default)
   - [ ] Set `MODEL_ARTIFACT_PATH` (local path or S3 URI)
   - [ ] Set `GRAFANA_ADMIN_PASSWORD`, `ANALYTICS_DB_PASSWORD`

3. **Redis Configuration**
   - [ ] Verify Redis maxmemory policy (recommend `allkeys-lru` for cache eviction)
   - [ ] Configure persistence (RDB or AOF) if data durability required
   - [ ] Test failover / replica sync (if HA setup)

4. **PostgreSQL Setup**
   - [ ] Enable `pg_cron` extension (`CREATE EXTENSION IF NOT EXISTS pg_cron;`)
   - [ ] Create `analytics_read` user with read-only role (for Grafana)
   - [ ] Schedule materialized view refresh jobs via pg_cron
   - [ ] Set up maintenance window for index optimization (VACUUM, ANALYZE)

5. **Model Artifact Deployment**
   - [ ] Download `account_health_v1.lgb` from training pipeline
   - [ ] Upload to S3 or artifact registry
   - [ ] Record version metadata in `model_versions` table
   - [ ] Test model loading and SIGHUP reload

6. **Celery Worker Setup**
   - [ ] Deploy Celery Beat scheduler (runs beat schedule)
   - [ ] Deploy Celery worker(s) (consume tasks from queue)
   - [ ] Verify broker (RabbitMQ or Redis) connectivity
   - [ ] Test sample task (retrain_all_tenants) in dry-run mode

7. **Stripe Webhook Registration**
   - [ ] Register webhook endpoint at Stripe dashboard
   - [ ] Configure events: `invoice.payment_failed`, `invoice.payment_succeeded`, `customer.subscription.deleted`
   - [ ] Store webhook secret in `STRIPE_WEBHOOK_SECRET` env var
   - [ ] Test webhook delivery with Stripe CLI

8. **CI/CD Acceptance Gate**
   - [ ] Add `.github/workflows/sprint3-acceptance.yml` (pytest S3.10 tests)
   - [ ] Ensure gate passes (all 3 scenarios + E2E + benchmarks + eval)
   - [ ] Gate must pass before Sprint 4 PR merge

9. **Grafana Provisioning**
   - [ ] Import dashboard JSON (`grafana/dashboards/sprint3.json`)
   - [ ] Configure datasource pointing to read-replica
   - [ ] Create alerts for anomalies (severity='critical')
   - [ ] Test dashboard panels load (time series, gauge, histogram, heatmap)

10. **Documentation & Runbooks**
    - [ ] Update README with enrichment architecture diagram
    - [ ] Document environment variables and configuration
    - [ ] Write runbook for model retraining failure recovery
    - [ ] Create troubleshooting guide (high latency, cache misses, webhook failures)

---

## Performance Targets

| Metric | Target | Measurement |
|--------|--------|-------------|
| Enrichment p99 latency (warm cache) | <500ms | `time.perf_counter()` over 1000 iterations |
| Cache hit rate | >80% | Redis `keyspace_hits / (keyspace_hits + keyspace_misses)` |
| Health scoring latency | <50ms | LightGBM predict + SHAP explain time |
| Triage autonomous rate | >70% | (triage_decision='handle') / total tickets |
| Escalation rate | <20% | (triage_decision='escalate') / total tickets |
| Eval harness accuracy | ≥90% | Passed predictions / golden set size |
| Model retraining time | <5 min | Time to train 200 estimators on 10k samples |
| Prompt token budget | <3500 avg | Token count measured by tiktoken |
| Database query latency (enrichment cache lookups) | <20ms p95 | PostgreSQL EXPLAIN ANALYZE |

---

## Known Risks & Mitigations

1. **Shopify API Rate Limits**
   - **Risk:** Shopify rate limit (2 req/sec) → API timeout → enrichment failure
   - **Mitigation:** Exponential backoff (2^attempt), retry max 3 times. Fall back to DB cache if Stripe unavailable. Monitor rate limit headers.

2. **LightGBM Model Staleness**
   - **Risk:** If weekly retraining fails, model drifts; stale predictions harm routing
   - **Mitigation:** Retrain job alerts on failure. Drift detection (S3.9) monitors model performance; if AUC drops >5%, alert ops team.

3. **Redis Cache Stampede**
   - **Risk:** On cache expiry (3600s), all requests for same key hit Shopify API simultaneously
   - **Mitigation:** Use cache-aside with probabilistic early expiry (e.g., 10% chance to refresh at 90% TTL), reducing thundering herd.

4. **Stripe Webhook Replay Attacks**
   - **Risk:** Attacker replays old webhook events (e.g., payment_failed) → incorrect billing state
   - **Mitigation:** Verify webhook signature (HMAC-SHA256). Webhook handler is idempotent (cache invalidation is safe to repeat).

5. **Enrichment Feature Decay**
   - **Risk:** If enrichment APIs (Shopify, Stripe) change schema or fail over time, model predictions degrade
   - **Mitigation:** Contract tests validate API schemas weekly. Feature importance monitoring (SHAP) alerts if top drivers become unavailable.

6. **Multi-Tenant Isolation Failures**
   - **Risk:** Cache key collision or SQL WHERE clause omission → customer data leakage between tenants
   - **Mitigation:** All cache keys include tenant_id. All DB queries have `WHERE tenant_id = $1`. CI linter checks for tenant isolation patterns. Audit logging on data access.

---

## Sprint 4 Handoff

Sprint 3 delivers to Sprint 4:

**From Sprint 3:**
- Enriched TriageState with customer context (account health, billing status, sentiment history)
- LightGBM health score (P(churn)) with SHAP explanations for every customer
- Dynamic prompts with tone injection and context insertion
- CI acceptance gate (S3.10) validating >=90% eval accuracy

**Sprint 4 Builds On Top:**
- **Agent Decision Refinement:** Use health scores + SHAP explanations to improve agent routing logic (adjust thresholds, add new routing rules)
- **Advanced Orchestration:** Implement multi-turn reasoning loops (agent asks clarifying questions, updates context mid-conversation)
- **Tool Integration:** Wire escalation tools (send email to account manager, open Zendesk ticket, trigger retention offer)
- **Performance Optimization:** Batch enrichment fetches, prefetch for high-volume customers, optimize LLM prompt latency

**Dependency for Sprint 4:**
- All enrichment APIs (Shopify, Stripe) must be stable and reachable
- PostgreSQL and Redis uptime >= 99.9%
- Model artifact registry accessible (S3 or local)
- Celery workers running for weekly retraining + monitoring

---

## Summary

Sprint 3 transforms the triage agent from a static rule-based system into a data-driven, context-aware platform. By enriching every decision with customer account health, billing status, sentiment, and order history—and backing those decisions with explainable LightGBM models—Sprint 3 enables intelligent routing that respects customer lifetime value, churn risk, and business objectives.

The five parallel enrichers (S3.1–S3.3, S3.6) deliver <500ms p99 latency with Redis caching. Health scoring (S3.4) with SHAP explains the "why" behind every churn prediction. Prompt engineering (S3.7) injects tone and context, improving LLM decision quality. Continuous learning (S3.8) closes the feedback loop, retraining models weekly on human judgment. Analytics dashboards (S3.9) surface performance metrics and anomalies to the ops team. The acceptance gate (S3.10) validates that enrichment improves triage accuracy to ≥90% before Sprint 4 begins.

All infrastructure is shared (Redis, PostgreSQL, Celery, LightGBM artifacts), enabling seamless integration with existing systems (S1–S2). Multi-tenant isolation is enforced throughout, ensuring security and data privacy.

Sprint 3 is complete when:
- [ ] All 10 components fully tested (Tier A ≥85%, Tier B ≥70%)
- [ ] Acceptance gate passes in CI
- [ ] Performance targets met (p99 <500ms, cache hit rate >80%, eval accuracy ≥90%)
- [ ] Deployment checklist items completed
- [ ] Documentation and runbooks finalized

---

*End of Sprint 3 Overview*
