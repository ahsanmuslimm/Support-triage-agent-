# Sprint 3 Gap-Filling Implementation Plan

## Overview
This plan addresses the 5 remaining gaps in Sprint 3 (Enrichment & Context Layers):
1. Enrichment Layer Tests (S3.1-S3.3): Customer, Order, Billing enrichers
2. Analytics Dashboard Tests (S3.9): MetricsDashboard
3. Knowledge Gap Analyzer Tests (S3.5)
4. LightGBM Model Integration (S3.4): Health scorer predict/explain
5. Acceptance Tests K1-K3: Golden dataset scenarios

---

## Gap 1: Enrichment Layer Tests (S3.1-S3.3)

### Current State
- **CustomerEnricher**: 13 existing tests (needs 2 more to reach 15)
- **OrderEnricher**: 13 existing tests (needs 2 more to reach 15)
- **BillingEnricher**: 14 existing tests (needs 2 more to reach 16, exceeds 12 target but acceptable)

All three enrichers exist in `services/api/src/triage/enrichment/` with corresponding test files in `tests/unit/enrichment/`.

### Design Decisions
- **Test approach**: Extend existing test files with focused missing scenarios rather than refactoring. Existing tests already cover the happy path, caching, timeouts, and basic error handling. Missing gaps are: cache miss edge cases with partial API failures, very specific exception handling paths, concurrent request patterns, and cache TTL boundary conditions.
- **Mock strategy**: Continue using AsyncMock/MagicMock pattern established in existing tests. No integration tests with real DBs.
- **Exception handling**: Enrichers raise `APITimeoutError` (explicit timeout), `EnrichmentError` (general failure), and fall back to DB when available. Tests should verify all three error paths.
- **Cache serialization**: All enrichers serialize context to JSON for Redis. Tests verify datetime fields are ISO-formatted and deserialization succeeds.

### Gap 1.1: Additional CustomerEnricher Tests

**Files to modify:**
- `tests/unit/enrichment/test_customer_enricher.py`

**Current count:** 13 tests | **Target:** 15+ tests | **Tests to add:** 2-3

**New test cases:**

1. `test_enrich_cache_miss_then_api_partial_failure` — When cache misses and Shopify API fails, verify fallback to DB raises EnrichmentError, not APITimeoutError. Verify tenant isolation validated before API call.

2. `test_enrich_subscription_plan_value_extraction` — Test precise extraction of Stripe subscription plan amount (in cents) conversion to USD. Verify edge case: subscriptions with no items array returns zero plan value.

3. `test_customer_context_vip_boundary_exactly_1000` — Test VIP determination at exact boundary (total_spent == 1000). Should NOT trigger VIP (test >1000 strictly). Also test just below and just above threshold.

**Verification:** `pytest tests/unit/enrichment/test_customer_enricher.py -v` — 15+ tests pass, including all existing tests.

---

### Gap 1.2: Additional OrderEnricher Tests

**Files to modify:**
- `tests/unit/enrichment/test_order_enricher.py`

**Current count:** 13 tests | **Target:** 15+ tests | **Tests to add:** 2-3

**New test cases:**

1. `test_order_enrichment_refund_partial_amount` — Test refund amount is correctly summed when partial refunds exist on single order. Verify return_rate calculation (refund_count / order_count, not refund_amount / order_value).

2. `test_risk_score_multiple_chargebacks_capped` — Test risk score caps at 1.0 when chargebacks + refunds + high-value orders all present. Verify formula: score = min(1.0, refund_penalty + chargeback_penalty + high_value_penalty).

3. `test_ordering_frequency_two_orders_interval` — Test frequency median with exactly 2 orders: interval should be days between them, not 0. Verify median([10]) = 10 for single interval.

**Verification:** `pytest tests/unit/enrichment/test_order_enricher.py -v` — 15+ tests pass.

---

### Gap 1.3: Additional BillingEnricher Tests

**Files to modify:**
- `tests/unit/enrichment/test_billing_enricher.py`

**Current count:** 14 tests | **Target:** 12+ tests | **Tests to add:** 0-2

Current count exceeds target. However, add 1-2 edge case tests for completeness:

1. `test_payment_method_type_extraction_non_card` — Test that primary_payment_type correctly identifies bank_account or other non-card types. Verify card priority if mixed types.

2. `test_card_expiry_boundary_exactly_30_days` — Test card_expiring_soon flag at exactly 30-day boundary. Should trigger (<=30), not just <30.

**Verification:** `pytest tests/unit/enrichment/test_billing_enricher.py -v` — 14+ tests pass.

---

## Gap 2: Analytics Dashboard Tests (S3.9)

### Current State
- **MetricsDashboard**: Source file exists at `services/api/src/triage/analytics/metrics_dashboard.py`
- **Tests**: No test file exists yet
- **Methods to test**: `get_summary_metrics()`, `get_agent_performance()`, `get_customer_outcomes()`, `detect_anomalies()`

### Design Decisions
- **Test file location**: Create `tests/unit/analytics/test_metrics_dashboard.py`
- **Mock strategy**: All methods query materialized views (v_triage_daily_summary, v_agent_performance_daily, v_customer_outcomes_daily, v_anomalies). Mock the DB session with AsyncMock query results.
- **Error handling**: Each method returns None on DB error (not raise). Tests verify None return and error logging.
- **Fixtures**: Create reusable mocks for DB session and materialized view result objects.

### Gap 2.1: MetricsDashboard Test Suite

**Files to create:**
- `tests/unit/analytics/test_metrics_dashboard.py`

**Target:** 15+ tests covering all 4 public methods

**New test cases:**

1. `test_get_summary_metrics_success` — Mock v_triage_daily_summary query returns valid row. Assert all fields (triage_rate, escalation_pct, avg_resolution_time_sec, csat_score, cost_per_resolution, recorded_at) are returned in dict.

2. `test_get_summary_metrics_no_data` — Mock query returns None (no rows). Assert method returns None.

3. `test_get_summary_metrics_db_error` — Mock query raises Exception. Assert method returns None and logs error.

4. `test_get_agent_performance_multi_days` — Mock v_agent_performance_daily returns 3 agents with 7 days of data. Assert list of 3 dicts returned, each with agent_id, autonomy_rate, avg_resolution_time, csat_score, recorded_at.

5. `test_get_agent_performance_custom_days_param` — Call with days=30. Verify DB query uses correct cutoff (now - 30 days). Assert results filtered correctly.

6. `test_get_agent_performance_empty_result` — Mock query returns empty list. Assert method returns empty list (not None).

7. `test_get_agent_performance_db_error` — Mock query raises DB error. Assert returns None.

8. `test_get_customer_outcomes_by_segment` — Mock v_customer_outcomes_daily returns 3 segments (high-value, at-risk, new). Assert each has segment name, resolution_rate, escalation_count, churn_rate.

9. `test_get_customer_outcomes_respects_days_window` — Call with days=14. Verify query cutoff is 14 days ago. Assert results only include recent data.

10. `test_get_customer_outcomes_db_error` — Mock error. Assert returns None.

11. `test_detect_anomalies_top_10` — Mock v_anomalies returns 15 anomalies. Assert only top 10 returned, sorted by deviation_sigma DESC. Each has metric_name, current_value, expected_value, deviation_sigma.

12. `test_detect_anomalies_24h_window` — Verify query filters to last 24 hours (now - 1 day). Assert no stale anomalies included.

13. `test_detect_anomalies_empty` — Mock returns empty list. Assert empty list returned.

14. `test_detect_anomalies_db_error` — Mock error. Assert returns None.

15. `test_summary_metrics_timestamp_preservation` — Mock result includes recorded_at datetime. Assert datetime is preserved in output dict (not converted to string).

**Verification:** `pytest tests/unit/analytics/test_metrics_dashboard.py -v` — 15+ tests pass, all views correctly mocked.

---

## Gap 3: Knowledge Gap Analyzer Tests (S3.5)

### Current State
- **KnowledgeGapAnalyzer**: Source file exists at `services/api/src/triage/analysis/knowledge_gap_analyzer.py`
- **Tests**: 13 existing tests at `tests/unit/analysis/test_knowledge_gap_analyzer.py`
- **Target**: 12+ tests (already has 13, goal met)

Current test coverage is sufficient. However, verify existing tests cover all major paths:
- ✓ Basic gap analysis with classifier
- ✓ Gap score calculation (escalation rate)
- ✓ Top 10 limit
- ✓ Keyword fallback (no classifier)
- ✓ Suggested titles
- ✓ Escalation count tracking
- ✓ Empty queries
- ✓ DB errors
- ✓ Sorting by gap score
- ✓ KnowledgeGap dataclass
- ✓ Custom lookback parameter
- ✓ High resolution rate → low gap
- ✓ Gap filtering (>0.1 threshold)

**Action for Gap 3:** No additional tests needed. Existing 13 tests exceed target of 12. Verify during implementation that all existing tests pass.

**Verification:** `pytest tests/unit/analysis/test_knowledge_gap_analyzer.py -v` — 13 tests pass, gap_score calculation correct, filtering works.

---

## Gap 4: LightGBM Model Integration (S3.4)

### Current State
- **HealthScorer**: Source file `services/api/src/triage/scoring/health_scorer.py`
- **Tests**: 13 existing tests at `tests/unit/scoring/test_health_scorer.py`
- **Model artifact**: `ml/models/account_health_lgb.pkl` (exists, trained on 1000 samples)
- **Current behavior**: predict() and explain() use heuristic fallback when self.model is None

### Design Decisions
- **Model loading**: Constructor accepts `model_path` parameter. If provided, load model via `_load_model()` (already implemented). Support .pkl (pickle) and .lgb (LightGBM format).
- **Integration scope**: Wire actual LightGBM predictions into predict() method. When model is loaded, use model.predict(X) instead of fallback heuristic. SHAP explanations should use actual SHAP values when model is available.
- **Fallback preservation**: Keep fallback scoring for tests without model. Tests should work both with and without model.
- **Test strategy**: Existing tests use model=None (fallback). Add 2-3 tests that load the actual model and verify predict/explain use it.

### Gap 4.1: Wire LightGBM into AccountHealthScorer

**Files to modify:**
- `services/api/src/triage/scoring/health_scorer.py`

**Changes required:**

1. **Line ~50-60 (predict method):** Modify to call actual model.predict(X) when self.model is not None. Currently implemented but verify it returns proper prediction (0-1 range).
   - Add check: `if self.model: return model-based prediction`
   - Ensure numpy array conversion: `X = np.array([features.to_array()])`
   - Bound prediction to [0, 1]: `churn_risk_score = max(0.0, min(1.0, prediction))`

2. **Line ~70-100 (explain method):** Modify to compute actual SHAP explanations when model is loaded.
   - Add check: `if self.model: use shap.TreeExplainer`
   - Verify SHAP values shape (binary classifier returns list of 2 arrays, take index 1 for positive class)
   - Extract top 3 drivers by |SHAP value|
   - Return driver list with feature name, impact (SHAP value), direction (positive/negative)

3. **Verify _load_model():** Already implemented. Test it can load .pkl file via pickle.load() and .lgb via lgb.Booster().

**Tests to add to test_health_scorer.py:**

1. `test_predict_with_actual_model_loaded` — Load model from `ml/models/account_health_lgb.pkl`. Call predict() with healthy features. Verify returns 0.0-1.0 score and "healthy" or "at_risk" label.

2. `test_explain_with_actual_model_shap` — Load model. Call explain() with features. Verify returns list of 3 dicts with {feature, impact, direction}. Impact should be float (SHAP value), direction should be "positive" or "negative".

3. `test_model_loading_invalid_path` — Try to load from non-existent path. Verify error is raised and logged.

**Verification:**
- Run: `pytest tests/unit/scoring/test_health_scorer.py::test_predict_with_actual_model_loaded -v`
- Run: `pytest tests/unit/scoring/test_health_scorer.py::test_explain_with_actual_model_shap -v`
- Existing fallback tests should still pass
- Full suite: `pytest tests/unit/scoring/test_health_scorer.py -v` — 16+ tests pass

---

## Gap 5: Acceptance Tests K1-K3

### Current State
- **Test file**: `tests/acceptance/sprint3_acceptance_test.py`
- **Golden dataset**: `ml/evals/golden/enrichment_v0.jsonl` (exists, contains customer/tenant/expected outcomes)
- **Current structure**: Basic K1 test started but incomplete

### Design Decisions
- **Golden dataset usage**: Load enrichment_v0.jsonl to get test fixtures (customer_id, tenant_id, expected_health_score_bucket, expected_tone, expected_gap_topics).
- **Test pattern**: Each acceptance test (K1, K2, K3) uses one golden record. K1 focuses on customer enrichment + health scoring for VIP. K2 focuses on order + billing enrichment. K3 focuses on health scoring with all enrichment context.
- **Mocking**: Mock Shopify, Stripe, and DB clients to return data matching golden expectations. Do NOT skip on fixture failure — all tests must load golden data or fail explicitly.
- **Assertions**: Verify tone selection, enrichment accuracy, and health score buckets match expected values from golden dataset.

### Gap 5.1: Complete Acceptance Test K1 (Customer Enrichment + Health Score)

**Files to modify:**
- `tests/acceptance/sprint3_acceptance_test.py`

**Test K1:**

Name: `test_k1_customer_enrichment_health_score_vip`

Scenario: High-value VIP customer (order_count > 20, total_spent > $5000). Expected health label: "healthy" (low churn risk).

Steps:
1. Load golden dataset, find record with expected_health_score_bucket == "high"
2. Mock CustomerEnricher to return wealthy customer context (25 orders, $15K spent, no failed payments)
3. Mock OrderEnricher to return active recent orders (order_count_90d=10, high_value_orders=3, risk_score=0.2)
4. Mock BillingEnricher to return good payment health (successful_payments_90d=12, payment_success_rate=1.0, not churn_risk)
5. Create HealthFeatures from enriched data
6. Call AccountHealthScorer.predict()
7. Assert health_score < 0.65 (healthy, not at_risk)
8. Call ToneSelector.select_tone(health_score, is_vip=True)
9. Assert tone in ["appreciative", "professional"] (VIP + healthy = professional or appreciative)

**File locations:**
- Enricher classes: `services/api/src/triage/enrichment/{customer,order,billing}_enricher.py`
- Scorer: `services/api/src/triage/scoring/health_scorer.py`
- Tone selector: `services/api/src/triage/prompting/tone_selector.py` (may need to verify exists)

**Verification:** `pytest tests/acceptance/sprint3_acceptance_test.py::TestAcceptanceScenarios::test_k1_customer_enrichment_health_score_vip -v`

---

### Gap 5.2: New Acceptance Test K2 (Order + Billing Enrichment)

**Test K2:**

Name: `test_k2_order_billing_enrichment_risk_detection`

Scenario: Customer with problematic order/billing pattern (>3 refunds, failed payments, high-velocity orders). Expected health label: "at_risk" (high churn risk).

Steps:
1. Load golden dataset, find record with expected_health_score_bucket == "low"
2. Mock OrderEnricher to return risky pattern: order_count_90d=8, high_value_orders=2, refund_count_90d=4, return_rate=0.5, risk_score=0.7, is_high_velocity=True
3. Mock BillingEnricher to return billing problems: failed_payments_90d=3, payment_success_rate=0.6, is_churn_risk=True, card_expiring_soon=True
4. Create HealthFeatures from enriched data (high failed_payments, high return_rate, high support_contact_count)
5. Call AccountHealthScorer.predict()
6. Assert health_score >= 0.65 (at_risk)
7. Call ToneSelector.select_tone(health_score, is_vip=False)
8. Assert tone in ["empathy", "reassurance"] (at_risk = empathetic approach)

**File locations:** Same as K1

**Verification:** `pytest tests/acceptance/sprint3_acceptance_test.py::TestAcceptanceScenarios::test_k2_order_billing_enrichment_risk_detection -v`

---

### Gap 5.3: New Acceptance Test K3 (Health Scoring with Full Enrichment Context)

**Test K3:**

Name: `test_k3_health_scoring_full_enrichment_context`

Scenario: Complete end-to-end: enrich customer from all layers (customer, order, billing), compute health score, generate explanation drivers.

Steps:
1. Load golden dataset, pick any record
2. Mock all three enrichers to return realistic data per golden customer profile
3. Aggregate HealthFeatures from all enrichment layers:
   - From CustomerEnricher: account_age_days, is_vip, total_spent
   - From OrderEnricher: order_count_90d, high_value_order_count, return_rate, risk_score
   - From BillingEnricher: failed_payments_90d, payment_success_rate, subscription_status_active
4. Call AccountHealthScorer.predict(features)
5. Assert health_score and health_label are consistent (score >= 0.65 → "at_risk", else "healthy")
6. Call AccountHealthScorer.explain(features)
7. Assert 3 drivers returned, each with feature name, impact, direction
8. Assert at least one driver is one of: recency_days, failed_payments_90d, return_rate, chargeback_count, sentiment_negative_ratio

**File locations:** Same as K1 + likely analytics dashboard usage

**Verification:** `pytest tests/acceptance/sprint3_acceptance_test.py::TestAcceptanceScenarios::test_k3_health_scoring_full_enrichment_context -v`

---

### Gap 5.4: Acceptance Test Structure

**Files to modify:**
- `tests/acceptance/sprint3_acceptance_test.py`

**Key requirements:**
1. **Golden data loading**: Use `load_golden_dataset()` helper to load enrichment_v0.jsonl
2. **No skip on fixture failure**: If golden dataset cannot load, raise pytest.fail() (don't pytest.skip()). This ensures production readiness.
3. **Mocking pattern**: Use AsyncMock for all enricher methods; return realistic dictionaries that will deserialize to Context objects
4. **Assertions per scenario**: Reference expected values from golden record (expected_health_score_bucket, expected_tone, expected_gap_topics)

**Verification:** 
- All three acceptance tests (K1, K2, K3) run without skip
- Golden dataset loaded successfully
- All enrichers mocked correctly
- Health scores in valid range [0, 1]
- Tone selections are sensible for health/VIP context

---

## Summary Table

| Gap | Component | Current State | Target | Changes |
|-----|-----------|---------------|--------|---------|
| 1.1 | CustomerEnricher Tests | 13 tests | 15+ tests | Add 2-3 tests: cache edge case, subscription plan extraction, VIP boundary |
| 1.2 | OrderEnricher Tests | 13 tests | 15+ tests | Add 2-3 tests: partial refund calculation, risk score capping, frequency interval |
| 1.3 | BillingEnricher Tests | 14 tests | 12+ tests | Add 0-2 tests: payment type extraction, card expiry boundary |
| 2 | MetricsDashboard Tests | 0 tests | 15+ tests | Create `tests/unit/analytics/test_metrics_dashboard.py` with 15 tests |
| 3 | KnowledgeGapAnalyzer Tests | 13 tests | 12+ tests | No changes needed, existing tests exceed target |
| 4 | Health Scorer LightGBM Integration | Heuristic fallback | Model + SHAP | Wire model.predict(), SHAP explain(), add 2-3 model-based tests |
| 5 | Acceptance Tests K1-K3 | Partial K1 | 3 complete | Complete K1, add K2 (risk detection), add K3 (full context) |

---

## Testing & Verification Strategy

### Unit Tests
Run per module:
```bash
pytest tests/unit/enrichment/ -v  # CustomerEnricher, OrderEnricher, BillingEnricher
pytest tests/unit/analytics/test_metrics_dashboard.py -v  # MetricsDashboard (new)
pytest tests/unit/analysis/test_knowledge_gap_analyzer.py -v  # KnowledgeGapAnalyzer (existing)
pytest tests/unit/scoring/test_health_scorer.py -v  # HealthScorer (+ LightGBM tests)
```

### Acceptance Tests
```bash
pytest tests/acceptance/sprint3_acceptance_test.py::TestAcceptanceScenarios -v -k "k1 or k2 or k3"
```

### Coverage Check
Ensure all new tests follow existing patterns:
- Use pytest fixtures for mocks (AsyncMock, MagicMock)
- Test happy path, error cases, edge cases, and boundary conditions
- All datetime fields properly serialized (ISO format for JSON)
- Verify cache behaviors and fallback paths
- Tenant isolation checked before API calls

### Integration Check
- All enrichers can be imported and instantiated with mocks
- Health scorer can load model from `ml/models/account_health_lgb.pkl`
- Golden dataset (enrichment_v0.jsonl) loads and deserializes correctly
- Acceptance tests run to completion without skips

---

## Implementation Order

1. **Gaps 1.1-1.3 (Enricher tests)**: Add 4-7 tests to existing enricher test files. Low risk, extends existing fixtures.
2. **Gap 2 (Analytics tests)**: Create new test file `tests/unit/analytics/test_metrics_dashboard.py` with 15 tests. Medium effort, all DB queries mocked.
3. **Gap 3 (KnowledgeGapAnalyzer)**: Verify existing tests pass. No new tests needed.
4. **Gap 4 (LightGBM integration)**: Modify `health_scorer.py` to use model.predict() and SHAP when loaded. Add 2-3 tests. Medium risk — must verify model loads and makes valid predictions.
5. **Gap 5 (Acceptance tests)**: Complete K1, add K2, add K3 in `sprint3_acceptance_test.py`. High confidence — uses established enricher and scorer APIs.

---

## Notes

- **No breaking changes**: All changes are additive (new tests, new test file, model wiring).
- **Backward compatible**: Fallback heuristic scoring remains for tests and scenarios without model.
- **Golden dataset mandatory**: Acceptance tests MUST load enrichment_v0.jsonl; failure to load is test failure, not skip.
- **Datetime handling**: All enricher tests verify ISO format datetime serialization for Redis caching.
- **Model artifact integrity**: Assume `ml/models/account_health_lgb.pkl` is valid and tested during training. No retraining in this phase.
