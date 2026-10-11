# Sprint 3 Review: Enrichment & Context Layers

## Summary

Sprint 3 implements the enrichment pipeline (customer/order/billing context), scoring engine (LightGBM-based health scorer), prompt templating (Jinja2), learning loop (drift detection), sentiment analysis, and analytics dashboards. The core implementations are solid and well-structured: models have proper dataclass definitions, enrichers follow a consistent pattern with cache/fallback strategies, and S3.4, S3.7, S3.8 have strong test coverage (22-30 tests each). However, test coverage is critically incomplete for S3.1-S3.3 (enrichment layer) and S3.9 (analytics), and the analytics dashboard endpoints lack corresponding integration tests. The golden dataset (33 records) and trained model exist, but analytics endpoints are not tested.

**Verdict**: NEEDS_CHANGES

<details>
<summary>Details</summary>

## High-level view

The enrichment layer (S3.1–S3.3) is implemented with Redis caching and PostgreSQL fallback, risk signals computed correctly (fraud flags, chargebacks, refund patterns), and proper tenant isolation. However, unit tests exist only for customer enricher (2 tests), with order and billing enrichers untested. The health scorer (S3.4) falls back to rule-based scoring when the LightGBM model is unavailable, with 12 unit tests validating thresholds and drivers; the model is trained and pickled but not loaded or tested in inference paths. The prompt engine (S3.7) uses Jinja2 templates with token budget enforcement (3500 token hard limit) and all 22 tests pass. Learning loop (S3.8) implements EWMA drift detection and feedback ingestion with 30 comprehensive tests. Sentiment analysis (S3.6) has 26 tests covering TextBlob polarity and NPS segmentation. Analytics dashboards (S3.9) query materialized views for summary metrics, agent performance, and customer outcomes, but lack dedicated unit tests. Knowledge gap analyzer (S3.5) implements zero-shot intent classification with category coverage scoring but has no dedicated tests. Acceptance tests (S3.10) are comprehensive: 12 tests validate K1/K2/K3 scenarios against golden data and performance benchmarks (500ms enrichment, 200ms scoring, 1s prompting, 2s E2E).

## Issues (5)

1. **Incomplete enrichment layer testing (HIGH)** — Customer enricher has only 2 tests; order and billing enrichers have 0 tests. S3.1, S3.2, S3.3 specify 15+, 12+, 10+ tests respectively but these are untested. Error paths (API timeout, cache failures, tenant isolation) lack coverage.

2. **Missing analytics dashboard unit tests (MEDIUM)** — MetricsDashboard (S3.9) has 4 async methods (get_summary_metrics, get_agent_performance, get_customer_outcomes, detect_anomalies) but zero unit tests. Database queries to materialized views are untested, and anomaly detection logic is not validated.

3. **Knowledge gap analyzer tests not implemented (MEDIUM)** — KnowledgeGapAnalyzer (S3.5) has no dedicated tests. Intent classification, gap scoring, and keyword fallback paths are untested.

4. **Health scorer model integration incomplete (MEDIUM)** — LightGBM model is trained and saved as account_health_lgb.pkl but is never loaded or used in predict() / explain() — scoring falls back to heuristic rule-based approach. SHAP explainability path uses fallback heuristics rather than actual model drivers.

5. **Acceptance test coverage incomplete (LOW)** — K1/K2/K3 scenarios skip when golden_dataset fixture fails; performance benchmarks measure synthetic latency only (not E2E with actual enrichment APIs). End-to-end flow is not tested against real enrichment layers.

</details>

## File map

- `services/api/src/triage/enrichment/models.py` — CustomerContext, OrderContext, BillingContext, SentimentContext dataclasses
- `services/api/src/triage/enrichment/customer_enricher.py` — S3.1 customer profile enrichment with cache/fallback
- `services/api/src/triage/enrichment/order_enricher.py` — S3.2 order history and risk signals (last 90d)
- `services/api/src/triage/enrichment/billing_enricher.py` — S3.3 payment and billing context
- `services/api/src/triage/scoring/health_scorer.py` — S3.4 LightGBM-based churn risk scoring with SHAP (uses fallback heuristics)
- `services/api/src/triage/analysis/knowledge_gap_analyzer.py` — S3.5 category coverage analysis
- `services/api/src/triage/sentiment/sentiment_analyzer.py` — S3.6 TextBlob + transformer sentiment classification
- `services/api/src/triage/prompting/template_engine.py` — S3.7 Jinja2 prompt templates with tone selection and token budget
- `services/api/src/triage/feedback/learning_loop.py` — S3.8 EWMA drift detection and feedback ingestion
- `services/api/src/triage/analytics/metrics_dashboard.py` — S3.9 analytics dashboard for summary metrics and anomaly detection
- `ml/models/account_health_lgb.pkl` — Trained LightGBM model (binary churn predictor, 15 features, 1000 training samples)
- `ml/models/account_health_lgb_v1.0.0.json` — Model version metadata
- `ml/evals/golden/enrichment_v0.jsonl` — 33 JSONL records for acceptance validation
- `tests/unit/enrichment/test_customer_enricher.py` — 2 tests (S3.1)
- `tests/unit/enrichment/test_order_enricher.py` — 0 tests (S3.2)
- `tests/unit/enrichment/test_billing_enricher.py` — 0 tests (S3.3)
- `tests/unit/scoring/test_health_scorer.py` — 12 tests (S3.4)
- `tests/unit/sentiment/test_sentiment_analyzer.py` — 26 tests (S3.6)
- `tests/unit/prompting/test_prompt_engine.py` — 22 tests (S3.7)
- `tests/unit/feedback/test_learning_loop.py` — 30 tests (S3.8)
- `tests/acceptance/sprint3_acceptance_test.py` — 12 tests (S3.10)
- `packages/py_core/alembic/versions/0005_sprint3_enrichment_tables.py` — Migration for cache tables
- `packages/py_core/alembic/versions/0006_sprint3_materialized_views.py` — Migration for analytics materialized views

