# Sprint 5 Planning Summary

**Plan Location:** `.agents/tasks/sprint5-impl-plan.md`  
**Status:** Complete and ready for implementation  
**Date Created:** 2026-10-11

---

## Overview

Sprint 5 "Proactive Intelligence & Optimization" adds predictive ML capabilities, personalization, cost optimization, and business intelligence to the Support Triage platform. The sprint spans **10 deliverables (S5.1–S5.10)** organized into **4 implementation batches** with **strict dependency ordering**.

---

## Key Deliverables

| Deliverable | Purpose | Files | Lines | Status |
|-------------|---------|-------|-------|--------|
| **S5.1** | Customer Lifecycle Stage Detection (RFM + K-means) | 6 | 800 | Planned |
| **S5.2** | Predictive Insights (LSTM, XGBoost, Prophet) | 8 | 900 | Planned |
| **S5.3** | Recommendation Engine (TF-IDF + semantic + collaborative) | 7 | 750 | Planned |
| **S5.4** | Campaign Optimization (personalization, budget, send-time) | 8 | 850 | Planned |
| **S5.5** | Cost Analysis & ROI (micro-costing, profitability) | 6 | 700 | Planned |
| **S5.6** | KB Optimization (placement, gap analysis, performance) | 6 | 650 | Planned |
| **S5.7** | Team Efficiency (KPIs, skill gaps, benchmarking) | 6 | 700 | Planned |
| **S5.8** | Customer Outcome Tracking (attribution, retention, revenue lift) | 6 | 800 | Planned |
| **S5.9** | Market Intelligence (competitive signals, churn reasons) | 6 | 650 | Planned |
| **S5.10** | Acceptance Gate (E2E tests, CI gate, monitoring) | 30 E2E | 900 | Planned |

**Total:** 43 source files + 8 test modules + 3 config files = 54 files  
**Total Lines:** ~8,000 lines of production code + ~2,000 lines of tests  
**Database:** 8 new tables + migration script  
**Tests:** 65+ unit tests + 30+ E2E scenarios

---

## Implementation Batches & Dependencies

### Batch 1: Lifecycle & Predictions (Week 1)
- **S5.1:** RFM scoring → customer segmentation (5 lifecycle stages)
- **S5.2:** LSTM/XGBoost/Prophet models → next-issue/churn/volume forecasting
- Feeds: Campaigns (S5.4), outcomes (S5.8), all downstream modules
- Files: 14 files, ~1,700 lines

### Batch 2: Recommendations & Optimization (Week 1.5)
- **S5.3:** Hybrid KB recommendation (TF-IDF + semantic + collaborative)
- **S5.4:** Campaign personalization (incentives, budget, send-time, channels)
- Depends on: S5.1 (lifecycle), S5.2 (predictions), S5.5 (cost for budget checks)
- Feeds: Outcomes (S5.8), KB optimization (S5.6)
- Files: 15 files, ~1,600 lines

### Batch 3: Cost & Performance (Week 2)
- **S5.5:** Micro-costing, ROI, profitability, anomaly detection
- **S5.6:** KB placement, gap analysis, performance tracking
- **S5.7:** Agent KPIs, skill gaps, peer benchmarking, training recommendations
- Depends on: S5.4 (campaigns for cost), S2.3 (KB retrieval)
- Feeds: Outcomes (S5.8), team dashboards
- Files: 18 files, ~2,050 lines

### Batch 4: Outcomes & Intelligence (Week 2.5)
- **S5.8:** Customer outcome attribution, retention analysis, revenue lift, cohort analysis
- **S5.9:** Competitive mention tracking, feature request aggregation, churn reason analysis
- Depends on: S5.1–S5.7 (all prior modules)
- Feeds: Dashboards, executive reporting
- Files: 12 files, ~1,450 lines

### Batch 5: Integration & Acceptance (Week 3)
- **S5.10:** E2E scenarios, CI gate, monitoring, staged rollout plan
- Depends on: S5.1–S5.9 (all)
- Deliverable: 30+ passing E2E tests, dashboards, documentation
- Files: 3 config files, 30+ E2E tests

---

## Database Schema

**8 New Tables:**

1. **customer_rfm_scores** — RFM dimensions per customer (Recency, Frequency, Monetary; 0–5 scale each)
2. **customer_lifecycle_profiles** — Lifecycle stage + confidence per customer (NEW, GROWTH, MATURE, CHURNING, CHURNED)
3. **prediction_results** — Model predictions (LSTM next-issue, XGBoost churn 72h, Prophet volume)
4. **model_registry** — Model versioning, metadata, and binary storage
5. **campaign_events** — Campaign performance (sent, viewed, clicked, converted)
6. **cost_events** — Micro-cost events (escalation, automation, agent time, channels, KB updates)
7. **kb_article_interactions** — Article performance (views, clicks, resolves, dwell time)
8. **agent_kpis** — Rolled-up agent metrics (MTTR, resolution rate, CSAT, escalation rate)

**Indexes:** Optimized for tenant_id + timestamp queries; composite keys for fast lookups.

---

## Key Architecture Decisions

### 1. Lifecycle Detection: K-means Clustering with 5 Stages
- **Rationale:** RFM is interpretable, K-means fits 5 natural segments, ensemble with rules provides fallback
- **Confidence:** 0.60–1.0; silhouette score ≥ 0.60 validates cluster quality
- **Event-Driven:** On purchase/support ticket, recalc RFM + predict stage immediately; batch retrain daily 02:00 UTC

### 2. Predictions: Ensemble of 3 Models
- **LSTM:** Next-issue category (30-day seq, Embedding→LSTM→Dense, top-3 acc ≥85%)
- **XGBoost:** Churn 72h forecast (12-D feature vector, precision ≥85%, recall ≥80%)
- **Prophet:** Volume forecasting (daily tickets, trend + seasonality, MAPE ≤15%)
- **Rationale:** Each model specialized for its domain; stacking ensemble would over-engineer; cache (1h TTL) for efficiency
- **Feature Engineering:** 8–12 normalized features; shared across recommendations and campaigns

### 3. Recommendations: TF-IDF + Semantic + Collaborative
- **TF-IDF:** 10k features, ngrams (1,2), fast baseline
- **Semantic:** Sentence-Transformers re-ranking for semantic relevance
- **Collaborative:** ALS (50 latent factors) for personalization
- **Blending:** 0.3 × TF-IDF + 0.7 × semantic for hybrid ranking
- **Rationale:** Covers content-based (TF-IDF), semantic (transformers), and user-based (ALS) approaches; 35–45% self-service target

### 4. Campaigns: LTV × Churn Risk Matrix
- **Offer Tiers:** Personal call | 20% off | 10% off | Free shipping
- **Mapping:** 4 LTV quartiles × 3 churn risk levels → 12 offer combinations
- **Budget:** LTV-weighted allocation per segment
- **Send-Time:** Hourly engagement rate optimization
- **Channels:** Email 15%, SMS 30% (2x/week cap), Push 25%
- **Auto-Pause:** CTR <1% or conversion <0.5%
- **Rationale:** Data-driven personalization balances cost and targeting; A/B testing validates effectiveness

### 5. Cost Analysis: Micro-Costing with Event Tracking
- **Cost Matrix:** Escalation $4.50, automation $0.08, agent $0.65/min, email $0.002, SMS $0.012, chat $0.05, KB update $1.20
- **ROI:** (value_delivered - cost_incurred) / cost_incurred × 100%
- **Tracking:** Per-conversation cost roll-up; daily materialized view for reporting
- **Rationale:** Enables ROI accountability per initiative; cost anomaly detection flags unusual patterns

### 6. Team Analytics: Rolling 30-Day KPI Trends
- **KPIs:** MTTR, resolution rate, CSAT, escalation rate, avg handling time
- **Skill Gaps:** Per-category success rate vs. team average (flags weakness if <1σ below mean)
- **Benchmarking:** Percentile ranking vs. peers
- **Training:** Category weakness → KB module recommendation
- **Rationale:** Actionable insights for manager coaching; peer pressure drives improvement

### 7. Outcomes: Multi-Touch Attribution
- **Support:** Tracks resolution impact on LTV (lower churn risk, higher retention)
- **Campaigns:** Tracks conversion and revenue lift
- **Attribution:** Proportional credit allocation if multiple touchpoints in window
- **Cohorts:** Lifecycle × vertical × region analysis; NPS/CSAT correlation
- **Rationale:** Connects support actions to business outcomes; informs resource allocation

### 8. Competitive Intelligence: Ticket Mining + NLP
- **Mentions:** Regex + NER to detect competitor names in tickets/feedback
- **Features:** NLP extraction of "need", "would like", "request" patterns
- **Churn Reasons:** Categorize exit surveys (price | feature | support | competitor | other)
- **Rationale:** Proactive market awareness; informs product roadmap

### 9. AB Testing: Deterministic Customer Segmentation
- **Assignment:** hash(customer_id + test_name) % 3 → variant (Control | Personalized | Collaborative)
- **Tracking:** Event-level logging; daily metric aggregation
- **Significance:** Chi-square or t-test for statistical validation
- **Rationale:** Reproducible, no state management; efficient per-request decision

### 10. Model Versioning & Monitoring
- **Registry:** Binary model storage + metadata (accuracy, precision, recall, MAPE)
- **Retraining:** Daily at 03:00 UTC; validate metrics before activation
- **Cache:** Redis 1h TTL for predictions; invalidate on customer event
- **Alerts:** Prometheus + Grafana dashboards for inference latency, error rates, metric drift
- **Rationale:** Auditable model lineage; automated safeguards against stale models

---

## Testing Strategy

| Tier | Focus | Count | Coverage |
|------|-------|-------|----------|
| A (Strict TDD) | RFM, clustering, feature eng | 18 tests | ≥90% |
| B (Behavioral) | ML models, APIs | 47 tests | ≥80% |
| C (Eval/Probe) | Model metrics gates | 5 checks | accuracy, precision, recall, MAPE |
| D (BDD/Scenario) | E2E journeys | 30 tests | Full workflows |
| **Total** | — | **65+ tests** | **≥85% coverage** |

**Performance Gates:**
- LSTM inference: <100ms p99
- Recommendations: <200ms p99
- API responses: <500ms p99

**Model Metrics Gates:**
- LSTM top-3 accuracy: ≥85%
- XGBoost precision: ≥85%, recall: ≥80%
- Prophet MAPE: ≤15%

---

## Staged Rollout Plan

**Phase 1: Canary (5%, Week 1)**
- Features: LSTM predictions, churn model
- Success: No errors, <100ms p99 latency
- Rollback: Disable feature flag `s5_predictions`

**Phase 2: Early Adopters (25%, Week 2)**
- Features: Add recommendations + campaigns
- Success: Self-service >35%, CTR >1%
- Rollback: Pause campaigns, revert to CONTROL variant

**Phase 3: General Availability (100%, Week 3)**
- Features: Full rollout
- Success: CSAT +10, churn -8–12%, cost -25–30%
- Monitor: Anomalies, model drift, performance

---

## Business Outcomes (Expected)

- **Churn Reduction:** 8–12% via proactive interventions
- **CSAT Improvement:** +10–15 points via better routing + team training
- **Cost Efficiency:** 25–30% reduction via automation + SKU consolidation
- **Self-Service Rate:** 35–45% via recommendations + KB placement
- **ROI:** Positive within 2 weeks (campaign + prediction payoff)

---

## File Organization

**Source:** `services/api/src/triage/`
- `lifecycle/` (6 files) — RFM, clustering, detection
- `predictions/` (8 files) — LSTM, XGBoost, Prophet, feature eng
- `recommendation/` (7 files) — TF-IDF, semantic, collaborative, AB testing
- `campaigns/` (8 files) — Incentives, budget, send-time, channel, performance
- `cost/` (6 files) — Events, ROI, profitability, anomaly
- `knowledge_base/` (6 files) — Placement, gaps, performance
- `team_analytics/` (6 files) — KPIs, skill gaps, benchmarking, training
- `outcomes/` (6 files) — Attribution, retention, revenue lift, cohort
- `competitive_intelligence/` (6 files) — Mentions, features, reasons, benchmarking

**Tests:** `services/api/tests/`
- `test_lifecycle_*.py` (4 files)
- `test_predictions_*.py` (4 files)
- `test_recommendation_*.py` (4 files)
- `test_campaigns_*.py` (5 files)
- `test_cost_*.py` (4 files)
- `test_kb_*.py` (3 files)
- `test_team_*.py` (4 files)
- `test_outcomes_*.py` (4 files)
- `test_competitive_*.py` (4 files)
- `acceptance/test_s5_scenarios.py` (30+ E2E)

**Config & Migration:**
- `packages/py_core/alembic/versions/0007_sprint5_intelligence_tables.py`
- `.github/workflows/sprint5-gate.yml`
- Updated `.env.example`

---

## Constraints & Assumptions

1. **Historical Data:** Assumes 2+ years of transaction/ticket history; synthetic data fallback if unavailable
2. **Enrichment:** Depends on S3 completion (customer profiles, payment history); uses fallback features if gaps
3. **Redis:** Required for caching (1h TTL); cluster mode for multi-tenancy
4. **Time Zones:** Uses customer account TZ for send-time; falls back to tenant/UTC
5. **Model Storage:** Binary blobs in DB; alternative S3 if storage constraints
6. **External Integrations:** Competitive mention tracking is internal (no vendor API calls)

---

## Next Steps

1. **Review & Approval:** Stakeholder review of architecture, feature set, rollout plan
2. **Sprint Planning:** Break plan into sprints (5–7 days each); assign team members
3. **Environment Setup:** Provision Redis, PostgreSQL, model training hardware
4. **Dependency Installation:** Add fbprophet, implicit, TensorFlow/torch, xgboost to pyproject.toml
5. **Kick-Off:** Start Batch 1 (Lifecycle & Predictions) in Week 1

---

**End of Sprint 5 Planning Summary**
