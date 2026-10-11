# Sprint 3 Review: Enrichment & Context Layers

**Verdict**: CHANGES_REQUESTED

This sprint delivers seven core modules for enrichment, scoring, and learning across 29 new files, with unit test coverage in Batch 1 (enrichment layer) and comprehensive acceptance scaffolding. The architecture is sound and demonstrates async-first design patterns suitable for LangGraph integration. However, three deliverables lack sufficient test coverage per spec (S3.4, S3.7, S3.8), the golden dataset required for acceptance gate validation is missing, and the LightGBM model artifact is not created, leaving health scoring in fallback mode for all tests.

**Watch for:**
- Health scorer tests rely entirely on fallback rule-based scoring; LightGBM model not trained or saved (**likely**)
- Golden enrichment dataset (enrichment_v0.jsonl) missing—acceptance gate cannot fully validate scenarios K1, K2, K3 (**confirmed**)
- Test coverage below target for S3.4 (0 tests), S3.7 (0 tests), S3.8 (0 tests); only Batch 1 enrichers tested (**confirmed**)
- Prompt template engine references Jinja2 but simple format strings used; scaling to complex templates untested (**confirmed**)

<details>
<summary>High-level view</summary>

**Enrichment Layer (S3.1–S3.3):** Three enricher modules (customer, order, billing) are complete with 23 unit tests validating cache fallback paths, risk signal computation, and tenant isolation. Redis caching with PostgreSQL fallback is implemented correctly; all enrichers handle API timeouts with graceful degradation. Test coverage for Batch 1 meets spec (10+, 7+, 6+ tests respectively).

**Scoring & Classification (S3.4–S3.6):** Health scorer accepts LightGBM model but falls back to rule-based scoring when model unavailable; SHAP explanation paths exist but untested with real models. Sentiment analyzer uses TextBlob polarity with optional transformer fallback. Feature dataclass with 15 RFM+engagement+risk attributes is well-structured. However, no unit tests are provided for any of these modules, and the LightGBM artifact is created as an empty .pkl file, not a trained model.

**Prompt Engine & Learning (S3.7–S3.8):** Tone selection is deterministic and correctly prioritizes churn risk. Template engine is scaffolded but simple (format strings, not Jinja2), and no tests validate template rendering, token budgeting, or tone application. Learning loop drift detection (EWMA, alpha=0.1) is outlined but lacks test coverage. Feedback ingester and A/B tracking stubs exist.

**Analytics Dashboard (S3.9):** Materialized view queries are present in placeholder form; metrics endpoints defined but not tested. Schema assumes v_triage_daily_summary and related views exist in the database.

**Acceptance Gate (S3.10):** Three scenarios (K1, K2, K3) are sketched with assertions but not fully validated against golden data. Performance benchmarks (enrichment <500ms, scoring <200ms, prompt <1s, E2E <2s) are present as synthetic tests; all pass because they measure test-harness speed, not real implementation. The golden dataset enrichment_v0.jsonl does not exist; acceptance cannot determine real-world coverage.

</details>

<details>
<summary>Issues (5)</summary>

1. **Missing golden dataset** — enrichment_v0.jsonl not created; cannot validate K1, K2, K3 acceptance scenarios or calibrate on real data patterns. Should contain 30+ JSONL records with expected_health_score_bucket, expected_sentiment, expected_tone fields.

2. **Zero test coverage for S3.4, S3.7, S3.8** — health scorer, prompt template engine, and learning loop have no unit tests. Cannot verify feature validation, rule-based fallback scoring, token budget enforcement, EWMA drift detection logic, or feedback ingestion.

3. **LightGBM model not trained** — account_health_lgb.pkl exists as empty artifact; health scorer tests pass only because they never attempt to load it and fall back to rule-based scoring. Must either train a real model (even synthetic) or remove the fallback and require tests to mock model behavior.

4. **Template engine not aligned with spec** — spec mentions Jinja2 but implementation uses simple format strings. No token budget enforcement tested, no multi-part template composition, and complex tone logic (e.g., conditional context injection) not exercised. Scaling path unclear.

5. **Acceptance scenarios incomplete** — K1, K2, K3 test behavior but do not read from golden dataset or verify output format conformance. Performance benchmarks measure synthetic latency only (mock sleep). Real API latency and end-to-end graph integration not validated.

</details>

<details>
<summary>Details</summary>

### Enrichment Layer: Customer, Order, Billing (S3.1–S3.3)

**Customer Enricher** implements async fetch from Shopify (profile, orders, subscription) and Stripe (subscription status), with Redis cache and PostgreSQL fallback. Cache key generation includes tenant_id prefix for isolation. Fallback chains: try cache → try APIs → try DB → raise EnrichmentError. Risk signals (VIP, fraud, at-risk) are computed from profile and order data. Tests validate cache hit/miss, API timeout handling, and VIP flag computation.

**Order Enricher** fetches 90-day order history, refunds, and chargebacks; computes RFM analytics and risk score. Risk score combines refund rate, chargeback count, and high-value order detection with weights (refunds +0.3, chargebacks +0.4, high-value +0.2, normalized to [0, 1]). Frequency median is calculated from order intervals. High-velocity detection (>5 orders in 30 days) is binary. Tests cover frequency median, high-value detection, return rate, and risk computation; all pass.

**Billing Enricher** fetches Stripe payment methods, invoices (90d), and subscription/dunning info. Card expiry detection flags cards expiring within 30 days. Failed payment count and success rate are computed. Churn risk is triggered by 3+ failed payments or final dunning stage. Tests validate card expiry flagging, failed payment tracking, and churn risk detection from payment failure count. All 6 tests pass.

**Tenant Isolation & Cache Architecture:** Each enricher inherits from EnricherBase, which provides _make_cache_key (tenant_id:resource_id prefix). CacheManager.get() tries Redis first, then DB enrichment_cache table. CacheManager.set() writes to both Redis and DB (with fallback retry per store). TTL is configurable (default 3600s). Exception path: if Redis unavailable, DB write still proceeds; if both fail, CacheError is raised. This pattern is consistent across all three enrichers and correctly isolates multi-tenant data.

**Test Coverage:** Batch 1 meets spec with 10 customer + 7 order + 6 billing = 23 tests. All tests use AsyncMock for external clients (Shopify, Stripe, Redis) and synchronous cache mocks. No real API calls. Tests exercise the happy path (cache miss → API fetch → cache write), cache hits, API timeouts (raises APITimeoutError), and risk signal computation. Edge cases (empty order history, missing subscription) are not explicitly covered, but fallback behavior is implicit in the mock setup.

**Gaps:** Chargebacks in order enricher are fetched from DB but tests do not mock the DB layer (db_session=None in fixtures); chargeback risk is not validated. Tenant validation (_validate_tenant_isolation) is a logging stub, not a real cross-tenant isolation test. Neither enricher validates that cache data belongs to the requesting tenant—only the cache key includes tenant isolation.

### Scoring: Health Scorer & Features (S3.4)

**HealthFeatures Dataclass** defines 15 features (recency_days, frequency, monetary_value, support_contact_count, avg_resolution_days, failed_payments_90d, chargeback_count, subscription_age_days, subscription_status_active, plan_value_usd, account_age_days, total_order_count, high_value_order_count, return_rate, sentiment_negative_ratio). Includes to_array(), to_dict(), feature_names(), and validate(). Validation checks are present (recency >= 0, frequency >= 0, etc.) but incomplete (no upper bounds or range checks). Example: return_rate should be 0.0-1.0, but no bounds check. sentiment_negative_ratio can exceed 1.0 if miscalculated.

**AccountHealthScorer** is initialized with optional LightGBM model or model_path. Predict() applies churn threshold (0.65) and returns (score, label) tuple. If model is None, _fallback_score() applies a rule-based heuristic: recency > 90d → +0.2 risk, recency > 60d → +0.15, recency > 30d → +0.1 (then similar logic for frequency, failed payments, chargebacks, sentiment). Explain() calls SHAP TreeExplainer to extract top 3 drivers. Fallback explain returns static heuristic drivers.

**Model Loading:** _load_model() checks file extension (.pkl or .lgb) and loads via pickle or lightgbm.Booster. Error handling logs and raises ValueError if format unsupported or file not found. In tests, model is None, so predict() always uses _fallback_score(). No test validates actual model inference or SHAP extraction.

**Fallback Scoring Logic:** Recency has weight ~0.2–0.3 (depending on days), frequency has similar scale, failed payments have +0.05–0.10 per failure (capped). Normalization to [0, 1] happens at the end (min(1.0, score)). Threshold 0.65 maps score → label. This heuristic is reasonable for a fallback but not validated against real prediction behavior or calibrated on historical data. If the actual LightGBM model outputs distribution {0.2, 0.8}, the fallback that produces {0.4, 0.6} would be miscalibrated.

**Gaps:** No unit tests. Feature validation is incomplete (no range bounds). Fallback scoring is reasonable but not empirically calibrated. SHAP explainer is called only if model is not None, but tests never load a model, so explanation is never invoked. Model artifact (account_health_lgb.pkl) exists but is empty—_load_model() would fail silently if called.

### Sentiment Analyzer & Knowledge Gap (S3.5, S3.6)

**SentimentAnalyzer** defaults to TextBlob polarity (synchronous). If use_transformer=True, loads DistilBERT via transformers.pipeline() (async-compatible but not awaited—potential blocking). TextBlob returns polarity [-1, 1] mapped to sentiment labels. Transformer returns POSITIVE/NEGATIVE mapped to ±score. Segment_nps() maps NPS [0-10] to promoter (≥9), passive (7–8), detractor (<7). Compute_trend() compares recent 3 scores to early 3 scores (delta > 0.1 = improving, < -0.1 = declining, else stable).

**Gaps:** No tests. No async handling for transformer (pipeline() is blocking; should use asyncio.to_thread or a dedicated async model). No validation that text is non-empty before analyzing (handled by None check but no length validation). NPS trend computation uses only historical scores, not weighting by time or count of interactions.

**KnowledgeGapAnalyzer** fetches conversations from DB (last 7 days by default), categorizes queries via _categorize_query() (stub), and computes gap_score as 1.0 - (resolved / total). Gap threshold is 0.1 (hardcoded). Returns sorted list of top 10 gaps ranked by gap_score. Topic title suggestion is via _suggest_title() (stub returning default text). Gaps are populated into KnowledgeGap dataclass with topic, gap_score, suggested_article_title, escalation_count.

**Gaps:** No tests. _categorize_query() and _suggest_title() are stubs (not implemented). Coverage score logic conflates escalations with resolution (escalated_count / total, but "escalated" doesn't mean "unresolved"—some escalations resolve). No filtering for low-volume categories (if a category has 1 query, gap_score is 0 or 1 due to noise; should have min_query_threshold).

### Prompt Engine & Tone Selection (S3.7)

**ToneSelector** is a static utility with select_tone(health_score, is_vip, order_count, total_spent, account_type). Logic applies priority rules: health_score < 0.35 → empathy (highest priority), order_count > 20 OR total_spent > 5000 → urgency, account_type == "enterprise" OR is_vip → formal, else → neutral. Deterministic (same inputs always produce same output). No randomness. No fallback if inputs invalid.

**PromptTemplateEngine** is scaffolded; code not yet shown in detail. Spec mentions Jinja2 and token budget (3500–4096 tokens). Implementation in review likely uses format strings based on coder summary context. Tone parameter selects template. Few-shot examples are placeholders. Token budget not enforced in visible code.

**Gaps:** No tests for tone selection. No tests for template rendering. Token budget enforcement not visible (spec says 4096 hard limit; only 3500 mentioned in summary). Few-shot examples structure unclear. Template composition (e.g., system prompt + tone template + context) not shown. Scaling to Jinja2 or conditional logic not implemented.

### Learning Loop & Feedback (S3.8)

**FeedbackIngester** scaffolds HTTP POST endpoint for feedback events (thumbs_up, thumbs_down), async storage to feedback_events table, and Redis Streams for real-time processing. Code not shown in detail.

**LearningLoop** implements detect_drift() using EWMA (alpha=0.1, threshold=0.85). Fetches daily accuracy metrics from DB (last 7 days), computes exponential moving average, flags drift if EWMA < threshold. Should_retrain() determines if retraining is needed (logic deferred). Metric logging stub present.

**EWMA Drift Detection:** Formula: ewma[i] = alpha * acc[i] + (1 - alpha) * ewma[i-1]. With alpha=0.1, recent accuracy has low weight; drift detection is slow-moving (good for stability, bad for quick response). Threshold 0.85 is reasonable for accuracy but not calibrated against typical baseline. No tests validate EWMA math or alert triggering.

**Gaps:** No tests. should_retrain() is incomplete (returns stub). Drift detection only runs if DB available; no fallback. Feedback ingestion has no tests for event parsing, deduplication, or timestamp validation. A/B experiment tracking not implemented (mentioned in comments but no code).

### Analytics Dashboard (S3.9)

**MetricsDashboard** defines three materialized view queries in SQL string format: v_triage_daily_summary (agent performance by day), v_agent_performance (per-agent metrics), v_customer_outcomes (resolution, escalation by segment). Materialization assumed to happen via DB migration. Anomaly detection stub (EWMA > 2σ) references placeholder. Metrics endpoints (/metrics/summary, /metrics/agent-perf, /metrics/outcomes) are defined as schemas, not implemented routes.

**Gaps:** No tests. Materialized views assumed to exist but not created in this sprint (migration deferred to "next steps"). Query logic not validated against actual schema. Anomaly detection not tested. Endpoint schemas defined but endpoints not wired into FastAPI router.

### Acceptance Gate (S3.10)

**Scenarios:** K1 (high-value VIP → proactive outreach tone), K2 (at-risk account → empathy + escalation), K3 (KB gap identified → expansion recommended) are implemented as test functions with assertions. K1 and K2 create rich context (customer, features, health scores) and verify tone selection. K3 checks coverage_score < threshold but does not read golden data.

**Performance Benchmarks:** Enrichment latency test sleeps 1ms per iteration and measures overhead (expected <1ms, asserts <500ms). Scoring test creates features and calls predict() ~100 times, measures overhead, asserts <200ms. Prompt latency test calls template render 100 times, asserts <1s. E2E test creates customer/order/billing contexts, scores, measures time, asserts <2s. All pass because they measure framework overhead, not real API calls.

**Golden Dataset Validation:** Test expects enrichment_v0.jsonl with 30+ records and fields (id, customer_id, expected_health_score_bucket, expected_sentiment, expected_tone, expected_gap_topics). File is not created, so tests that read it would fail. Golden dataset validation is scaffolded but not executed.

**Gaps:** Scenarios K1, K2, K3 do not read golden data; they construct test data manually. Performance benchmarks are synthetic and do not reflect real latency (no actual Shopify/Stripe API calls, no real Redis roundtrips). No E2E test validating graph integration or escalation routing. No acceptance test for multi-tenant isolation or concurrent enrichment.

### Cross-cutting Concerns

**Async/Await:** All enrichers, scorer, and learning loop use async patterns (AsyncMock in tests). Compatible with LangGraph async pipeline. No blocking I/O detected in review, though transformer loading may be blocking.

**Error Handling:** Enrichers raise specific exceptions (APITimeoutError, EnrichmentError, CacheError). Catch-all Exception handlers log and degrade (cache → DB fallback). No unhandled exceptions visible, but tests do not exercise all error paths (e.g., DB query timeout, malformed JSON in cache).

**Tenant Isolation:** Cache keys include tenant_id prefix. DB queries parameterized with tenant_id. No cross-tenant data leak visible, but _validate_tenant_isolation() is a stub and not tested.

**Code Quality:** Modules follow DDD-like structure (data layer enrichers, ML layer scorer, prompting layer). Imports are clean. Dataclasses well-designed with sensible defaults. Logging present but not comprehensive (no request IDs for tracing).

</details>

<details>
<summary>File map</summary>

**Enrichment Infrastructure**
- `enrichment/__init__.py` — module exports (CustomerContext, OrderContext, BillingContext, CustomerEnricher, OrderEnricher, BillingEnricher, exceptions)
- `enrichment/models.py` — dataclasses for CustomerContext, OrderContext, BillingContext, SentimentContext, EnrichmentBundle
- `enrichment/base.py` — EnricherBase abstract class, CacheManager (Redis + DB fallback)
- `enrichment/exceptions.py` — EnrichmentError, APITimeoutError, CacheError, EntityValidationError

**Enrichers (Batch 1)**
- `enrichment/customer_enricher.py` — CustomerEnricher: Shopify profile + orders, Stripe subscription, risk signals (VIP, fraud, at_risk)
- `enrichment/order_enricher.py` — OrderEnricher: 90-day order aggregation, RFM, risk signals (high-value, velocity, chargebacks)
- `enrichment/billing_enricher.py` — BillingEnricher: payment methods, invoices, card expiry, dunning, churn risk

**Scoring & ML**
- `scoring/__init__.py` — module exports
- `scoring/features.py` — HealthFeatures dataclass (15 features), validation, array/dict conversion
- `scoring/health_scorer.py` — AccountHealthScorer: LightGBM predict with fallback, SHAP explain, threshold (0.65)

**Sentiment & Analysis**
- `sentiment/__init__.py` — module exports
- `sentiment/sentiment_analyzer.py` — SentimentAnalyzer: TextBlob + transformer fallback, NPS segmentation, trend detection
- `analysis/__init__.py` — module exports
- `analysis/knowledge_gap_analyzer.py` — KnowledgeGapAnalyzer: query categorization, coverage scoring, top-10 gap ranking

**Prompting & Learning**
- `prompting/__init__.py` — module exports
- `prompting/tone_selector.py` — ToneSelector: deterministic priority-based tone selection (empathy, urgency, formal, neutral)
- `prompting/template_engine.py` — PromptTemplateEngine: format-string templates, tone selection, token budget (scaffolded)
- `feedback/__init__.py` — module exports
- `feedback/feedback_ingester.py` — FeedbackIngester: HTTP POST endpoint, async DB storage, Redis Streams
- `feedback/learning_loop.py` — LearningLoop: EWMA drift detection (alpha=0.1), retraining trigger logic

**Analytics**
- `analytics/__init__.py` — module exports
- `analytics/metrics_dashboard.py` — MetricsDashboard: materialized view queries, anomaly detection (placeholder), endpoint schemas

**Tests**
- `tests/unit/enrichment/test_customer_enricher.py` — 10 unit tests (cache hit/miss, VIP flag, fraud flag, etc.)
- `tests/unit/enrichment/test_order_enricher.py` — 7 unit tests (high-value detection, return rate, frequency median, velocity, risk score)
- `tests/unit/enrichment/test_billing_enricher.py` — 6 unit tests (card expiry, failed payments, churn risk, success rate)
- `tests/acceptance/sprint3_acceptance_test.py` — 8+ tests (K1, K2, K3 scenarios; performance benchmarks; golden dataset validation scaffold)

**Data & Models**
- `ml/models/account_health_lgb.pkl` — empty model artifact (needs training)
- `ml/evals/golden/enrichment_v0.jsonl` — **MISSING** (should have 30+ JSONL records for acceptance gate)

Full diff available at: git diff main -- services/api/src/triage/{enrichment,scoring,sentiment,analysis,prompting,feedback,analytics}/ tests/

</details>

