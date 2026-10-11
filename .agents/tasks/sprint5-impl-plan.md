# Sprint 5 Implementation Plan: Proactive Intelligence & Optimization

**Date:** January 2026  
**Status:** PENDING  
**Goal:** Implement 10 deliverables (S5.1–S5.10) adding predictive intelligence, personalization, and cost optimization to the triage platform.

---

## Executive Summary

Sprint 5 implements 10 interconnected deliverables across 4 implementation batches:

| Batch | Deliverables | Purpose | New Modules | Files |
|-------|--------------|---------|-------------|-------|
| **B1: Lifecycle & Predictions** | S5.1, S5.2 | RFM clustering, LSTM/XGBoost/Prophet forecasting | `lifecycle/`, `predictions/` | 11 files |
| **B2: Recommendations & Optimization** | S5.3, S5.4 | Hybrid KB recommendation, campaign personalization | `recommendation/`, `campaigns/` | 10 files |
| **B3: Cost & Performance** | S5.5, S5.6, S5.7 | Micro-costing, KB optimization, team analytics | `cost/`, `knowledge_base/`, `team_analytics/` | 12 files |
| **B4: Outcomes & Intelligence** | S5.8, S5.9, S5.10 | Attribution, competitive signals, acceptance gates | `outcomes/`, `competitive_intelligence/` | 10 files |

**Total Files:** 43 Python source files + 8 test modules + 3 config/migration files = 54  
**Migrations:** 1 (0007_sprint5_intelligence_tables.py)  
**New Tables:** 8 (customer_rfm_scores, customer_lifecycle_profiles, prediction_results, cost_events, campaign_events, kb_performance, agent_kpis, competitive_signals)  
**Tests:** 65+ unit tests + 30+ E2E scenarios  
**Dependencies:** Sprints 1–4 complete (triage orchestrator, enrichment, escalation, monitoring)

---

## Dependency Map

```
S5.1 (Lifecycle)
  ├─ Depends: S3.1 (enrichment), S3.4 (health scoring)
  └─ Feeds: S5.4 (campaigns), S5.8 (outcomes)

S5.2 (Predictions)
  ├─ Depends: S3.1 (enrichment), S3.6 (sentiment)
  ├─ Feeds: S5.3 (recommendations), S5.4 (campaigns), S5.8 (outcomes)
  └─ Cross: Feature engineering (S5.2.3) used by S5.3, S5.4, S5.7

S5.3 (Recommendations)
  ├─ Depends: S2.3 (KB retrieval), S5.1 (lifecycle), S5.2 (predictions)
  └─ Feeds: S5.6 (KB optimization), S5.8 (outcomes)

S5.4 (Campaign Optimization)
  ├─ Depends: S5.1 (lifecycle), S5.2 (churn model), S5.5 (cost)
  └─ Feeds: S5.8 (outcomes)

S5.5 (Cost Analysis)
  ├─ Depends: S4.3 (escalation), S4.5 (SLA), S2.1 (routing)
  └─ Feeds: S5.4 (campaigns), S5.8 (outcomes)

S5.6 (KB Optimization)
  ├─ Depends: S2.3 (KB retrieval), S5.2 (volume forecast), S5.3 (recommendations)
  └─ Feeds: S5.8 (outcomes)

S5.7 (Team Analytics)
  ├─ Depends: S4.1 (escalation audit), S3.9 (dashboards)
  └─ Feeds: S5.8 (outcomes)

S5.8 (Outcome Tracking)
  ├─ Depends: S5.1–S5.7 (all)
  └─ Aggregates: Revenue attribution, retention analysis

S5.9 (Competitive Intelligence)
  └─ Independent; feeds S5.8

S5.10 (Acceptance Gate)
  ├─ Depends: S5.1–S5.9 (all)
  └─ Verification: Golden set (30+ E2E scenarios)
```

---

## Batch 1: Lifecycle & Predictions (S5.1, S5.2)

### S5.1 — Customer Lifecycle Stage Detection (~800 lines)

**Objective:** Classify customers into 5 stages (New, Growth, Mature, Churning, Churned) using RFM + K-means clustering.

#### Files to Create

**1.1 `services/api/src/triage/lifecycle/__init__.py`**
```python
from .detector import LifecycleDetector
from .models import CustomerRFMScore, CustomerLifecycleProfile
from .rfm import RFMCalculator
from .clustering import LifecycleClusterer

__all__ = [
    "LifecycleDetector",
    "CustomerRFMScore",
    "CustomerLifecycleProfile",
    "RFMCalculator",
    "LifecycleClusterer",
]
```

**1.2 `services/api/src/triage/lifecycle/models.py`**
- Dataclasses:
  - `RFMDimensions(BaseModel)`: recency_score, frequency_score, monetary_score (each 0–5)
  - `CustomerRFMScore(BaseModel)`: customer_id, tenant_id, rfm, calculated_at, valid_until
  - `LifecycleStage(str, Enum)`: NEW, GROWTH, MATURE, CHURNING, CHURNED
  - `CustomerLifecycleProfile(BaseModel)`: customer_id, tenant_id, stage, confidence (0–1), updated_at, stage_reasons (List[str])
- Database ORM mappings for customer_rfm_scores, customer_lifecycle_profiles tables
- Tests: serialization, validation, edge cases (confidence bounds, stage enum)

**1.3 `services/api/src/triage/lifecycle/rfm.py`**
- Class: `RFMCalculator`
- Key methods:
  - `async calculate_rfm(tenant_id: int, customer_id: int) -> RFMDimensions`
    - Recency: days since last order / last support ticket (max 365 days)
    - Frequency: count of orders + support interactions in last 365 days
    - Monetary: total spend in last 365 days (normalized to 0–5 scale; bins: 0, $100, $500, $1k, $5k+)
    - Returns 0–5 score per dimension (quantile-based or threshold-based)
  - `async batch_calculate_rfm(tenant_id: int) -> Dict[int, RFMDimensions]`
    - Query all active customers; compute RFM for each
    - Store in customer_rfm_scores table; cache in Redis (24h TTL)
- Tests: RFM calc (4 unit tests per dimension + boundary cases), batch ops (1 integration test)

**1.4 `services/api/src/triage/lifecycle/clustering.py`**
- Class: `LifecycleClusterer`
- Dependencies: scikit-learn (KMeans), numpy
- Key methods:
  - `async fit_kmeans(tenant_id: int, k: int = 5) -> None`
    - Load all RFM scores from customer_rfm_scores table
    - Build feature matrix (N × 3)
    - Train KMeans(n_clusters=5, random_state=42)
    - Validate silhouette score ≥ 0.60; log if < threshold
    - Store cluster centers in model_registry table
  - `async predict_stage(rfm: RFMDimensions) -> Tuple[LifecycleStage, float]`
    - Compute distance to each cluster center
    - Assign to nearest; return (stage, confidence as 1 - normalized_distance)
  - `async assign_stages_batch(tenant_id: int) -> None`
    - For each customer, predict stage and store in customer_lifecycle_profiles
    - Update event timestamp, track confidence distribution
- Tests: KMeans fitting (2), distance calculation (2), batch assignment (1), silhouette validation (1)

**1.5 `services/api/src/triage/lifecycle/detector.py`**
- Class: `LifecycleDetector`
- Key methods:
  - `async __init__(self)`
    - Load RFMCalculator, LifecycleClusterer
    - Load model_registry for pre-trained cluster centers per tenant
  - `async detect_customer_stage(tenant_id: int, customer_id: int) -> CustomerLifecycleProfile`
    - Fetch or compute RFM score
    - Predict stage using clustering.predict_stage()
    - Build stage_reasons (e.g., ["high frequency", "low recency", "churning trend"])
    - Return CustomerLifecycleProfile
  - `async detect_lifecycle_for_tenant(tenant_id: int) -> None`
    - Batch daily: 02:00 UTC
    - Recalculate RFM for all active customers
    - Retrain KMeans (full re-fit)
    - Assign stages to all customers
    - Emit Kafka topic: `customer.lifecycle.updated` (per customer)
  - `async on_customer_event(event: CustomerEvent) -> None`
    - Event-driven: when purchase, support ticket, or chargeback occurs
    - Recalc RFM for affected customer
    - Predict stage immediately
    - Publish lifecycle update if stage changed
    - Check for anomalies: stage dropped 2+ levels in 7 days → trigger escalation
- Tests: Stage detection (4), batch processing (2), event-driven update (2), anomaly detection (1)

**1.6 `services/api/src/triage/lifecycle/scheduler.py`**
- Async background task (APScheduler or Celery)
- Daily trigger at 02:00 UTC: call detector.detect_lifecycle_for_tenant()
- Logging and error recovery
- Tests: scheduler registration (1), trigger timing (1 via mocking)

#### Database Schema (Alembic Migration)

New tables:

```sql
CREATE TABLE triage.customer_rfm_scores (
    id BIGSERIAL PRIMARY KEY,
    tenant_id INT NOT NULL,
    customer_id INT NOT NULL,
    recency_score INT NOT NULL CHECK (recency_score >= 0 AND recency_score <= 5),
    frequency_score INT NOT NULL CHECK (frequency_score >= 0 AND frequency_score <= 5),
    monetary_score INT NOT NULL CHECK (monetary_score >= 0 AND monetary_score <= 5),
    calculated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    valid_until TIMESTAMP NOT NULL DEFAULT (NOW() + INTERVAL '24 hours'),
    UNIQUE(tenant_id, customer_id),
    FOREIGN KEY (tenant_id) REFERENCES triage.tenants(id)
);
CREATE INDEX idx_rfm_tenant_calculated ON triage.customer_rfm_scores(tenant_id, calculated_at DESC);

CREATE TABLE triage.customer_lifecycle_profiles (
    id BIGSERIAL PRIMARY KEY,
    tenant_id INT NOT NULL,
    customer_id INT NOT NULL,
    stage VARCHAR(20) NOT NULL CHECK (stage IN ('NEW', 'GROWTH', 'MATURE', 'CHURNING', 'CHURNED')),
    confidence NUMERIC(3, 2) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    stage_reasons TEXT[] NOT NULL DEFAULT '{}',
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE(tenant_id, customer_id),
    FOREIGN KEY (tenant_id) REFERENCES triage.tenants(id)
);
CREATE INDEX idx_lifecycle_tenant_stage ON triage.customer_lifecycle_profiles(tenant_id, stage);
CREATE INDEX idx_lifecycle_tenant_updated ON triage.customer_lifecycle_profiles(tenant_id, updated_at DESC);
```

#### Verification

```bash
# Unit tests
pytest services/api/tests/test_lifecycle_rfm.py -v

# Integration tests
pytest services/api/tests/test_lifecycle_detector.py -v

# Expected: 18+ unit tests, all pass
```

---

### S5.2 — Predictive Insights & Forecasting (~900 lines)

**Objective:** Implement 4 ML models (LSTM, XGBoost, Prophet, feature engineering) for next-issue prediction, 72h churn forecast, and volume forecasting.

#### Files to Create

**2.1 `services/api/src/triage/predictions/__init__.py`**
```python
from .lstm_model import LSTMNextIssuePreditor
from .churn_xgb import ChurnXGBoostModel
from .volume_prophet import VolumeForecaster
from .feature_engineering import FeatureEngineer
from .cache import PredictionCache

__all__ = [
    "LSTMNextIssuePreditor",
    "ChurnXGBoostModel",
    "VolumeForecaster",
    "FeatureEngineer",
    "PredictionCache",
]
```

**2.2 `services/api/src/triage/predictions/feature_engineering.py`**
- Class: `FeatureEngineer`
- Key methods:
  - `async extract_features(customer_id: int, tenant_id: int, lookback_days: int = 30) -> Dict[str, float]`
    - Extract 8–12 features per customer:
      1. Customer lifecycle stage (from S5.1)
      2. Days since last issue
      3. Issue frequency (past 30 days)
      4. Avg time-to-resolution (past 30 days)
      5. Escalation ratio (past 30 days)
      6. Account age (days)
      7. Total lifetime spend
      8. Support sentiment (avg from S3.6)
      9. Health score (from S3.4)
      10. Account status (active/paused/churned)
      11. Subscription plan value
      12. Chargeback count (past 90 days)
    - Normalize features to [0, 1] using MinMaxScaler (fitted on historical data)
    - Return Dict[str, float]
  - `async batch_extract_features(tenant_id: int) -> Dict[int, Dict[str, float]]`
    - For all active customers
    - Use Redis cache for unchanged customers (1h TTL)
- Tests: Feature extraction (4), normalization (2), batch ops (1), cache behavior (1)

**2.3 `services/api/src/triage/predictions/lstm_model.py`**
- Class: `LSTMNextIssuePreditor`
- Dependencies: tensorflow/torch (LSTM), numpy
- Key methods:
  - `async __init__(self, sequence_length: int = 30, embedding_dim: int = 64)`
    - Load pre-trained LSTM model from model_registry
    - Initialize encoder (intent label → embedding)
    - Output: top-3 predicted intents with probabilities
  - `async train(training_data: List[Tuple[sequence, label]], epochs: int = 10) -> None`
    - Input: [(history of 30 intents, target_intent), ...]
    - Architecture: Embedding → LSTM(64) → Dense(128) → Dropout(0.2) → Dense(num_intents) → Softmax
    - Validation split: 0.2
    - Early stopping if val_loss plateau for 3 epochs
    - Save model to model_registry with metadata: date, accuracy, val_loss
  - `async predict_next_issue(customer_id: int, tenant_id: int) -> List[Tuple[str, float]]`
    - Fetch customer's last 30 issues (intent, date)
    - Build sequence of intent embeddings
    - Forward pass through LSTM
    - Return top-3 intents with probabilities (≥ 0.15 threshold)
    - Cache result (1h TTL)
- Key Metric: Top-3 accuracy ≥ 85% (evaluated on holdout test set)
- Tests: Model training (2), prediction (3), top-3 accuracy eval (1), sequence handling (1)

**2.4 `services/api/src/triage/predictions/churn_xgb.py`**
- Class: `ChurnXGBoostModel`
- Dependencies: xgboost, sklearn
- Key methods:
  - `async __init__(self)`
    - Load pre-trained XGBoost model from model_registry
    - Load feature scaler (fitted during training)
  - `async train(training_data: List[Tuple[features, label]], test_data: Optional[List] = None) -> None`
    - Input: features (12D from FeatureEngineer), label (1 if churned in next 72h, 0 otherwise)
    - Split: 80/20 train/test
    - XGBoost params: max_depth=6, learning_rate=0.1, n_estimators=100, tree_method='hist'
    - Train on training set; evaluate on test set
    - Compute precision, recall, AUC-ROC
    - Requirement: precision ≥ 85%, recall ≥ 80%
    - Save model + metadata (precision, recall, AUC, feature_importance)
  - `async predict_churn_72h(customer_id: int, tenant_id: int) -> Tuple[float, Dict[str, float]]`
    - Fetch customer features (via FeatureEngineer.extract_features)
    - Forward pass through XGBoost
    - Return (churn_probability, feature_importance_dict)
    - Cache result (1h TTL)
  - `async evaluate_model(test_data) -> Dict[str, float]`
    - Return precision, recall, AUC-ROC, F1
- Tests: Model training (2), prediction (2), metric eval (2), feature importance (1)

**2.5 `services/api/src/triage/predictions/volume_prophet.py`**
- Class: `VolumeForecaster`
- Dependencies: fbprophet (Facebook's Prophet)
- Key methods:
  - `async __init__(self)`
    - Load pre-trained Prophet model from model_registry (per tenant)
  - `async train(daily_volumes: List[Tuple[date, count]], forecast_days: int = 90) -> None`
    - Input: daily ticket counts (last 2 years or available)
    - Prophet params: yearly_seasonality=True, weekly_seasonality=True, daily_seasonality=False
    - Fit to historical data
    - Forecast forward forecast_days
    - Compute MAPE on holdout test (last 30 days)
    - Requirement: MAPE ≤ 15%
    - Save model + metadata
  - `async forecast(days_ahead: int = 30) -> List[Tuple[date, float, float, float]]`
    - Return [(date, point_forecast, lower_95_ci, upper_95_ci), ...] for days_ahead
    - Use Prophet's intervals
    - Cache result (1h TTL)
  - `async detect_anomalies(lookback_days: int = 7) -> List[Tuple[date, float, str]]`
    - Compare actual vs. forecast for last lookback_days
    - Flag outliers (actual > upper_95_ci or actual < lower_95_ci)
    - Return [(date, deviation_pct, direction), ...]
- Tests: Model training (2), forecast generation (2), anomaly detection (1), MAPE eval (1)

**2.6 `services/api/src/triage/predictions/cache.py`**
- Class: `PredictionCache`
- Methods:
  - `async set_prediction(prediction_type: str, customer_id: int, tenant_id: int, data: Dict, ttl_seconds: int = 3600) -> None`
    - Store in Redis: key = f"prediction:{prediction_type}:{tenant_id}:{customer_id}"
    - TTL: 1 hour (default)
  - `async get_prediction(prediction_type: str, customer_id: int, tenant_id: int) -> Optional[Dict]`
    - Fetch from Redis; return None if expired
  - `async invalidate_prediction(customer_id: int, tenant_id: int) -> None`
    - Delete all prediction entries for customer (triggered on lifecycle change, new issue, etc.)
- Tests: Cache get/set (2), TTL expiry (1), invalidation (1)

**2.7 `services/api/src/triage/predictions/orchestrator.py`**
- Class: `PredictionOrchestrator`
- Methods:
  - `async predict_for_customer(customer_id: int, tenant_id: int) -> Dict[str, Any]`
    - Call LSTM next-issue predictor
    - Call XGBoost churn model
    - Return {next_issues: [...], churn_72h: (prob, features), ...}
  - `async daily_retrain() -> None`
    - Runs daily at 03:00 UTC
    - Fetch training data for each model (past 2 years or available)
    - Retrain LSTM, XGBoost, Prophet
    - Validate metrics (accuracy ≥ 85%, precision ≥ 85%, MAPE ≤ 15%)
    - Save models if metrics pass; log warnings if not
  - `async scheduler_task()` — APScheduler trigger
- Tests: Orchestration (2), daily retrain (2), error handling (1)

#### Database Schema (Alembic Migration)

New tables:

```sql
CREATE TABLE triage.prediction_results (
    id BIGSERIAL PRIMARY KEY,
    tenant_id INT NOT NULL,
    customer_id INT NOT NULL,
    prediction_type VARCHAR(50) NOT NULL CHECK (prediction_type IN ('next_issue', 'churn_72h', 'volume_forecast')),
    predicted_at TIMESTAMP NOT NULL DEFAULT NOW(),
    valid_until TIMESTAMP NOT NULL,
    prediction_data JSONB NOT NULL,
    confidence NUMERIC(3, 2),
    actual_outcome JSONB,
    evaluated_at TIMESTAMP,
    FOREIGN KEY (tenant_id) REFERENCES triage.tenants(id)
);
CREATE INDEX idx_predictions_tenant_type_date ON triage.prediction_results(tenant_id, prediction_type, predicted_at DESC);

CREATE TABLE triage.model_registry (
    id BIGSERIAL PRIMARY KEY,
    tenant_id INT NOT NULL,
    model_name VARCHAR(50) NOT NULL,
    model_version INT NOT NULL DEFAULT 1,
    trained_at TIMESTAMP NOT NULL DEFAULT NOW(),
    metrics JSONB NOT NULL,
    model_blob BYTEA NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE(tenant_id, model_name, model_version),
    FOREIGN KEY (tenant_id) REFERENCES triage.tenants(id)
);
CREATE INDEX idx_model_registry_active ON triage.model_registry(tenant_id, model_name, is_active);
```

#### Verification

```bash
# Unit tests
pytest services/api/tests/test_predictions_lstm.py -v
pytest services/api/tests/test_predictions_churn.py -v
pytest services/api/tests/test_predictions_volume.py -v
pytest services/api/tests/test_predictions_features.py -v

# Expected: 25+ unit tests, all pass
# Metric gates: LSTM accuracy ≥ 85%, XGBoost precision ≥ 85%, recall ≥ 80%, Prophet MAPE ≤ 15%
```

---

## Batch 2: Recommendations & Optimization (S5.3, S5.4)

### S5.3 — Recommendation Engine (~750 lines)

**Objective:** Hybrid KB recommendation engine combining TF-IDF, semantic search, and collaborative filtering. Target: 35–45% self-service resolution.

#### Files to Create

**3.1 `services/api/src/triage/recommendation/__init__.py`**
```python
from .engine import RecommendationEngine
from .tfidf_vectorizer import TFIDFVectorizer
from .semantic_ranker import SemanticRanker
from .collaborative import CollaborativeFilteringModel
from .ab_testing import ABTestingFramework

__all__ = [
    "RecommendationEngine",
    "TFIDFVectorizer",
    "SemanticRanker",
    "CollaborativeFilteringModel",
    "ABTestingFramework",
]
```

**3.2 `services/api/src/triage/recommendation/models.py`**
- Dataclasses:
  - `KBArticle(BaseModel)`: article_id, title, content, category, created_at, views, resolution_count, ctr, dwell_time_sec
  - `RecommendationResult(BaseModel)`: article_id, title, rank, score (0–1), reason (e.g., "semantic match", "collaborative"), method_used
  - `ABTestVariant(str, Enum)`: CONTROL, PERSONALIZED, COLLABORATIVE
- Tests: Model serialization, validation

**3.3 `services/api/src/triage/recommendation/tfidf_vectorizer.py`**
- Class: `TFIDFVectorizer`
- Dependencies: scikit-learn TfidfVectorizer
- Key methods:
  - `async __init__(self, max_features: int = 10000, ngram_range: Tuple[int, int] = (1, 2))`
    - Load pre-trained TF-IDF vectorizer from cache/disk
    - ngram_range: (1, 2) for unigrams + bigrams
    - max_features: 10k features
  - `async fit_vectorizer(kb_articles: List[KBArticle]) -> None`
    - Build TF-IDF matrix from articles (title + content)
    - Store vectorizer and feature names
  - `async search_articles(query: str, top_k: int = 5) -> List[Tuple[int, float]]`
    - Vectorize query (using fitted vectorizer)
    - Compute cosine similarity to all articles
    - Return top_k (article_id, similarity_score)
- Tests: Vectorizer training (2), search (2), edge cases (1)

**3.4 `services/api/src/triage/recommendation/semantic_ranker.py`**
- Class: `SemanticRanker`
- Dependencies: sentence-transformers (all-MiniLM-L6-v2)
- Key methods:
  - `async __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2")`
    - Load pre-trained sentence transformer model
  - `async rank_articles(query: str, candidates: List[KBArticle], top_k: int = 3) -> List[Tuple[int, float]]`
    - Embed query and article titles/summaries using sentence transformer
    - Compute cosine similarity
    - Return top_k (article_id, similarity_score)
  - `async rerank_tfidf_results(query: str, tfidf_results: List[Tuple[int, float]]) -> List[Tuple[int, float]]`
    - Take TF-IDF top results (e.g., top 20)
    - Re-rank using semantic similarity
    - Blend scores: 0.3 * tfidf_score + 0.7 * semantic_score
    - Return top_k
- Tests: Embedding (1), similarity (1), re-ranking (2), edge cases (1)

**3.5 `services/api/src/triage/recommendation/collaborative.py`**
- Class: `CollaborativeFilteringModel`
- Dependencies: implicit (ALS), numpy
- Key methods:
  - `async __init__(self, latent_factors: int = 50)`
    - Load pre-trained ALS model from cache
    - latent_factors: 50
  - `async train(user_article_interactions: List[Tuple[customer_id, article_id, feedback]]) -> None`
    - Input: (customer_id, article_id, feedback_signal) where feedback ∈ {click, resolve, helpful}
    - Build sparse user-item interaction matrix
    - Train ALS model
    - Save model
  - `async recommend_for_customer(customer_id: int, top_k: int = 5) -> List[Tuple[int, float]]`
    - Look up customer latent factors
    - Compute score with all article factors
    - Return top_k (article_id, score)
- Tests: ALS training (1), recommendation (2), interaction matrix (1), edge cases (1)

**3.6 `services/api/src/triage/recommendation/engine.py`**
- Class: `RecommendationEngine`
- Key methods:
  - `async __init__(self, ab_test_framework)`
    - Initialize TFIDFVectorizer, SemanticRanker, CollaborativeFilteringModel
    - Initialize AB testing framework
  - `async recommend_articles(customer_id: int, tenant_id: int, issue: Issue, variant: ABTestVariant = None) -> List[RecommendationResult]`
    - Determine AB variant for customer (or passed variant)
    - If CONTROL: TF-IDF only (top 5)
    - If PERSONALIZED: TF-IDF + semantic re-ranking + lifecycle stage weighting (e.g., New customers get beginner articles)
    - If COLLABORATIVE: TF-IDF + collaborative filtering (articles similar to what cohort resolved)
    - Score blending: weighted sum of methods
    - Rank articles by final score
    - Return top 5 RecommendationResult objects with reason
    - Log to AB test tracking
- Tests: Recommendation variants (3), blending logic (2), ranking (1)

**3.7 `services/api/src/triage/recommendation/ab_testing.py`**
- Class: `ABTestingFramework`
- Key methods:
  - `async get_variant_for_customer(customer_id: int, test_name: str) -> ABTestVariant`
    - Deterministic assignment: hash(customer_id + test_name) % 3 → variant
    - Log assignment
    - Return variant
  - `async log_recommendation_event(customer_id: int, tenant_id: int, article_id: int, variant: ABTestVariant, action: str) -> None`
    - action ∈ {viewed, clicked, resolved, dismissed}
    - Store in ab_test_events table
  - `async compute_test_metrics(test_name: str, days: int = 7) -> Dict[str, Dict[str, float]]`
    - Compute per-variant metrics: click_rate, resolution_rate, avg_time_to_resolution
    - Return {variant: {metric: value, ...}, ...}
    - Statistical significance test (Chi-square or t-test)
- Tests: Variant assignment (2), event logging (1), metric computation (1)

#### Verification

```bash
# Unit tests
pytest services/api/tests/test_recommendation_tfidf.py -v
pytest services/api/tests/test_recommendation_semantic.py -v
pytest services/api/tests/test_recommendation_collaborative.py -v
pytest services/api/tests/test_recommendation_ab_testing.py -v

# Expected: 20+ unit tests
# Target: Self-service resolution 35–45%
```

---

### S5.4 — Campaign Optimization & Personalization (~850 lines)

**Objective:** Dynamic offer generation, budget allocation, send-time optimization, channel selection, and performance auto-pause.

#### Files to Create

**4.1 `services/api/src/triage/campaigns/__init__.py`**
```python
from .optimizer import CampaignOptimizer
from .incentive import IncentiveMatrixGenerator
from .budget import BudgetAllocator
from .send_time import SendTimeOptimizer
from .channel import ChannelSelector
from .performance import PerformanceMonitor

__all__ = [
    "CampaignOptimizer",
    "IncentiveMatrixGenerator",
    "BudgetAllocator",
    "SendTimeOptimizer",
    "ChannelSelector",
    "PerformanceMonitor",
]
```

**4.2 `services/api/src/triage/campaigns/models.py`**
- Dataclasses:
  - `IncentiveOffer(BaseModel)`: offer_id, offer_type, discount_pct, offer_description
  - `OfferTier(str, Enum)`: PERSONAL_CALL, DISCOUNT_20PCT, DISCOUNT_10PCT, FREE_SHIPPING
  - `CampaignSegment(BaseModel)`: segment_id, ltv_quartile, churn_risk_level, size
  - `ChannelConfig(BaseModel)`: channel, capacity_pct, frequency_cap
- Tests: Model serialization

**4.3 `services/api/src/triage/campaigns/incentive.py`**
- Class: `IncentiveMatrixGenerator`
- Key methods:
  - `async build_incentive_matrix() -> Dict[Tuple[str, str], OfferTier]`
    - LTV quartiles: Q1 (0–25th), Q2 (25–50th), Q3 (50–75th), Q4 (75–100th)
    - Churn risk: LOW, MEDIUM, HIGH (from S5.2 churn model)
    - Matrix (4 × 3):
      ```
      Churn Risk:   LOW              MEDIUM            HIGH
      LTV Q4:       FREE_SHIPPING    DISCOUNT_10PCT    DISCOUNT_20PCT
      LTV Q3:       FREE_SHIPPING    DISCOUNT_10PCT    DISCOUNT_20PCT
      LTV Q2:       DISCOUNT_10PCT   DISCOUNT_20PCT    PERSONAL_CALL
      LTV Q1:       DISCOUNT_10PCT   DISCOUNT_20PCT    PERSONAL_CALL
      ```
    - Return matrix as dict
  - `async select_offer(customer_ltv: float, churn_prob: float) -> OfferTier`
    - Map customer to LTV quartile, churn_prob to risk level
    - Lookup matrix
    - Return offer type
- Tests: Matrix generation (1), offer selection (2), edge cases (1)

**4.4 `services/api/src/triage/campaigns/budget.py`**
- Class: `BudgetAllocator`
- Key methods:
  - `async allocate_budget(total_budget: float, segments: List[CampaignSegment]) -> Dict[str, float]`
    - LTV-weighted allocation: segment_budget = total_budget * (segment_ltv_sum / total_ltv)
    - Return {segment_id: allocated_budget, ...}
  - `async track_spend(segment_id: str, amount: float) -> None`
    - Decrement segment budget in Redis (key: f"campaign_budget:{segment_id}")
    - Log to campaign_events table
  - `async check_budget_available(segment_id: str, amount: float) -> bool`
    - Fetch current budget from Redis
    - Return True if amount ≤ budget, else False
- Tests: Budget allocation (2), spend tracking (1), availability check (1)

**4.5 `services/api/src/triage/campaigns/send_time.py`**
- Class: `SendTimeOptimizer`
- Key methods:
  - `async build_engagement_schedule(tenant_id: int, customer_id: int) -> Dict[int, float]`
    - Query last 60 days of customer engagement events (email opens, clicks, SMS reads)
    - Bin by hour-of-day (0–23)
    - Compute engagement rate per hour
    - Smooth with rolling average (3-hour window)
    - Return {hour: engagement_rate, ...}
  - `async recommend_send_time(customer_id: int, tenant_id: int) -> int`
    - Fetch engagement schedule
    - Return hour with highest engagement rate
    - If no history, return customer timezone's 10:00 AM
- Tests: Schedule building (2), recommendation (1), no-history edge case (1)

**4.6 `services/api/src/triage/campaigns/channel.py`**
- Class: `ChannelSelector`
- Constants:
  ```python
  CHANNEL_CAPACITY = {
      "email": 0.15,      # 15% of campaigns
      "sms": 0.30,        # 30% of campaigns
      "push": 0.25,       # 25% of campaigns
  }
  SMS_FREQUENCY_CAP = 2  # max 2x per week
  ```
- Key methods:
  - `async select_channel(customer_id: int, tenant_id: int) -> str`
    - Fetch customer preferences and opt-in status
    - Fetch recent SMS sends (last 7 days)
    - If SMS sends < SMS_FREQUENCY_CAP and rand() < 0.30: return "sms"
    - Elif email opted in and rand() < 0.15: return "email"
    - Elif push opted in and rand() < 0.25: return "push"
    - Else return None (do not send)
  - `async is_channel_available(customer_id: int, channel: str) -> bool`
    - Check customer opt-in and frequency caps
- Tests: Channel selection (2), frequency cap (1), edge cases (1)

**4.7 `services/api/src/triage/campaigns/performance.py`**
- Class: `PerformanceMonitor`
- Key methods:
  - `async track_campaign_event(campaign_id: str, customer_id: int, event_type: str) -> None`
    - event_type ∈ {sent, viewed, clicked, converted}
    - Store in campaign_events table
    - Update Redis metrics (5min TTL): {campaign_metrics:{campaign_id}:{event_type}: count}
  - `async compute_metrics(campaign_id: str) -> Dict[str, float]`
    - Fetch recent events from Redis + database
    - Compute CTR = clicked / sent, conversion = converted / sent
    - Return {ctr, conversion_rate, sent_count, ...}
  - `async check_auto_pause(campaign_id: str) -> bool`
    - Fetch metrics
    - If CTR < 0.01 or conversion < 0.005: return True (pause)
    - Else return False
  - `async pause_campaign(campaign_id: str) -> None`
    - Set campaign status to PAUSED in database
  - `async rollup_to_database() -> None`
    - Runs hourly: aggregate Redis metrics (5min) to campaign_events table (daily rollup)
- Tests: Event tracking (2), metric computation (1), auto-pause logic (1)

**4.8 `services/api/src/triage/campaigns/optimizer.py`**
- Class: `CampaignOptimizer`
- Key methods:
  - `async generate_campaign(customer_id: int, tenant_id: int) -> Campaign`
    - Fetch customer: lifecycle_stage, ltv, churn_prob (from S5.1, S5.2)
    - Call IncentiveMatrixGenerator.select_offer()
    - Call SendTimeOptimizer.recommend_send_time()
    - Call ChannelSelector.select_channel()
    - Call BudgetAllocator.check_budget_available()
    - If all checks pass: create Campaign object; return
    - Else: return None
  - `async execute_campaign(campaign: Campaign) -> None`
    - Send offer via selected channel at optimal time
    - Log to PerformanceMonitor
- Tests: Campaign generation (2), execution (1)

#### Verification

```bash
# Unit tests
pytest services/api/tests/test_campaigns_incentive.py -v
pytest services/api/tests/test_campaigns_budget.py -v
pytest services/api/tests/test_campaigns_send_time.py -v
pytest services/api/tests/test_campaigns_channel.py -v
pytest services/api/tests/test_campaigns_performance.py -v

# Expected: 20+ unit tests
```

---

## Batch 3: Cost & Performance (S5.5, S5.6, S5.7)

### S5.5 — Cost Analysis & ROI Tracking (~700 lines)

**Objective:** Micro-costing, ROI calculation, per-segment profitability, anomaly detection.

#### Files to Create

**5.1 `services/api/src/triage/cost/__init__.py`**
```python
from .events import CostEventTracker
from .roi import ROICalculator
from .profitability import ProfitabilityAnalyzer
from .anomaly import CostAnomalyDetector

__all__ = [
    "CostEventTracker",
    "ROICalculator",
    "ProfitabilityAnalyzer",
    "CostAnomalyDetector",
]
```

**5.2 `services/api/src/triage/cost/events.py`**
- Class: `CostEventTracker`
- Constants:
  ```python
  COST_MATRIX = {
      "escalation": 4.50,        # per escalation
      "automation": 0.08,        # per automated decision
      "agent": 0.65,             # per minute of agent handling
      "email": 0.002,            # per email
      "sms": 0.012,              # per SMS
      "chat": 0.05,              # per chat message
      "kb_update": 1.20,         # per article added/updated
  }
  ```
- Key methods:
  - `async log_cost_event(event_type: str, tenant_id: int, conversation_id: int, cost_amount: float, metadata: Dict) -> None`
    - Validate event_type
    - Calculate cost from metadata (e.g., if event_type == "agent", cost = COST_MATRIX["agent"] * duration_minutes)
    - Store in cost_events table
    - Update Redis running total (5min TTL)
  - `async calculate_resolution_cost(conversation_id: int) -> float`
    - Query conversation events (routing, classification, escalation, agent time, etc.)
    - Sum costs
    - Return total
  - `async get_daily_costs(tenant_id: int, date: date) -> Dict[str, float]`
    - Query cost_events for date
    - Group by event_type
    - Return {event_type: total_cost, ...}
- Tests: Event logging (2), cost calculation (2), daily aggregation (1)

**5.3 `services/api/src/triage/cost/roi.py`**
- Class: `ROICalculator`
- Key methods:
  - `async calculate_roi(initiative_id: str, cost_incurred: float, value_delivered: float) -> float`
    - ROI % = ((value_delivered - cost_incurred) / cost_incurred) × 100
    - Return ROI%
    - Log to database
  - `async track_initiative_costs(initiative_id: str, cost_type: str, amount: float) -> None`
    - initiative_id ∈ {S5.1_lifecycle, S5.2_prediction, S5.3_recommendation, ...}
    - Aggregate costs per initiative
  - `async estimate_value_delivered(initiative_id: str, metric: str) -> float`
    - S5.1 (lifecycle): value = (churn_prevented_count × avg_ltv)
    - S5.2 (prediction): value = (proactive_interventions × success_rate × avg_ltv_retained)
    - S5.3 (recommendation): value = (self_service_resolutions × cost_saved_per_resolution)
    - S5.4 (campaigns): value = (revenue_from_campaign - campaign_cost)
    - Return float
- Tests: ROI calculation (2), initiative tracking (1), value estimation (2)

**5.4 `services/api/src/triage/cost/profitability.py`**
- Class: `ProfitabilityAnalyzer`
- Key methods:
  - `async compute_segment_profitability(segment_name: str, tenant_id: int, date_range: Tuple[date, date]) -> Dict[str, float]`
    - Segment ∈ {lifecycle_stage, ltv_quartile, vertical, region}
    - Query revenue (from triage.orders or revenue table)
    - Query CAC (customer acquisition cost from marketing)
    - Query support costs (from cost_events)
    - Calculate: LTV-to-CAC, cost-per-resolution, margin
    - Return {segment_value: {ltv: float, cac: float, ltv_cac_ratio: float, margin_pct: float, ...}, ...}
  - `async track_ltv_to_cac_ratio(segment: str) -> float`
    - Return LTV / CAC for segment
  - `async identify_underperforming_segments(threshold: float = 1.5) -> List[str]`
    - Segments with LTV-to-CAC ratio < threshold
    - Flag for review
    - Return list
- Tests: Segment profitability (2), LTV-to-CAC (1), underperforming segments (1)

**5.5 `services/api/src/triage/cost/anomaly.py`**
- Class: `CostAnomalyDetector`
- Key methods:
  - `async detect_cost_spike(event_type: str, tenant_id: int, lookback_hours: int = 24) -> Tuple[bool, Dict]`
    - Query cost events for last lookback_hours
    - Compute mean and std of hourly costs
    - If latest hour > mean + 2σ: flag anomaly
    - Return (is_anomaly, {current_cost, mean, threshold, ...})
  - `async log_anomaly(event: Dict) -> None`
    - Store in cost_anomalies table
    - Alert if spike > 50% above baseline
- Tests: Anomaly detection (2), threshold validation (1)

#### Verification

```bash
# Unit tests
pytest services/api/tests/test_cost_events.py -v
pytest services/api/tests/test_cost_roi.py -v
pytest services/api/tests/test_cost_profitability.py -v
pytest services/api/tests/test_cost_anomaly.py -v

# Expected: 15+ unit tests
```

---

### S5.6 — Knowledge Base Optimization & Updates (~650 lines)

**Objective:** Proactive KB article placement, content gap identification, per-article performance tracking.

#### Files to Create

**6.1 `services/api/src/triage/knowledge_base/__init__.py`**
```python
from .optimizer import KBOptimizer
from .placement import PlacementEngine
from .gap_analysis import GapAnalyzer
from .performance_tracker import PerformanceTracker

__all__ = [
    "KBOptimizer",
    "PlacementEngine",
    "GapAnalyzer",
    "PerformanceTracker",
]
```

**6.2 `services/api/src/triage/knowledge_base/models.py`**
- Dataclasses:
  - `KBArticlePerformance(BaseModel)`: article_id, views, clicks, resolutions, dwell_time_sec, ctr, resolution_rate
  - `ContentGap(BaseModel)`: category, gap_score (0–1), ticket_volume, kb_articles_count, recommendation
- Tests: Model serialization

**6.3 `services/api/src/triage/knowledge_base/placement.py`**
- Class: `PlacementEngine`
- Key methods:
  - `async calculate_placement_confidence(issue: Issue, article_id: int) -> float`
    - Estimate confidence that article will resolve issue
    - Use recommendation engine (S5.3) semantic similarity + historical resolution rate
    - Requirement: confidence ≥ 0.8 to place
  - `async place_article(issue: Issue, article_id: int, placement_type: str) -> bool`
    - placement_type ∈ {proactive_email, in_app_prompt, chat_suggestion}
    - Check confidence ≥ 0.8
    - Schedule placement (via campaigns module if email/in_app)
    - Log to kb_placement_events table
    - Return success
  - `async self_service_decision_tree(issue: Issue) -> Optional[int]`
    - Order: KB search → FAQ → escalate
    - Execute KB search (S2.3 retrieval)
    - If top result confidence ≥ 0.8: return article_id
    - Else if FAQ match: return faq_id
    - Else: return None (escalate)
- Tests: Placement confidence (2), placement execution (2), decision tree (1)

**6.4 `services/api/src/triage/knowledge_base/gap_analysis.py`**
- Class: `GapAnalyzer`
- Key methods:
  - `async identify_content_gaps(tenant_id: int) -> List[ContentGap]`
    - Query ticket categories from last 90 days
    - For each category: count tickets, count KB articles
    - Compute gap_score = tickets_without_resolution / total_tickets
    - Threshold: flag if gap_score > 0.3 (30% of tickets lack KB coverage)
    - Return sorted by gap_score descending
  - `async recommend_articles(gap: ContentGap) -> List[str]`
    - Extract common themes from unresolved tickets in gap category
    - Suggest article titles/outline
    - Return recommendations
- Tests: Gap identification (2), recommendation generation (1)

**6.5 `services/api/src/triage/knowledge_base/performance_tracker.py`**
- Class: `PerformanceTracker`
- Key methods:
  - `async log_article_interaction(article_id: int, action: str, duration_sec: int) -> None`
    - action ∈ {viewed, clicked, resolved, dismissed}
    - duration_sec: time spent reading
    - Store in kb_article_interactions table
    - Update Redis metrics
  - `async compute_article_metrics(article_id: int, days: int = 30) -> KBArticlePerformance`
    - Query interactions for last days
    - Compute: views, clicks, resolutions, dwell_time, CTR, resolution_rate
    - Return KBArticlePerformance
  - `async identify_underperforming_articles(threshold_ctr: float = 0.10) -> List[int]`
    - CTR < threshold
    - Flag for review/update
    - Return article_ids
- Tests: Interaction logging (1), metric computation (2), underperforming detection (1)

**6.6 `services/api/src/triage/knowledge_base/optimizer.py`**
- Class: `KBOptimizer`
- Key methods:
  - `async optimize_kb(tenant_id: int) -> Dict[str, Any]`
    - Call gap analyzer
    - Call performance tracker
    - Return {gaps: [...], underperformers: [...], recommendations: [...]}
- Tests: Full optimization workflow (1)

#### Verification

```bash
# Unit tests
pytest services/api/tests/test_kb_placement.py -v
pytest services/api/tests/test_kb_gap_analysis.py -v
pytest services/api/tests/test_kb_performance.py -v

# Expected: 12+ unit tests
```

---

### S5.7 — Team Efficiency & Skill Development (~700 lines)

**Objective:** Per-agent KPIs, skill gap detection, peer benchmarking, training recommendations.

#### Files to Create

**7.1 `services/api/src/triage/team_analytics/__init__.py`**
```python
from .kpi import KPICalculator
from .skill_gap import SkillGapDetector
from .benchmarking import PeerBenchmarker
from .training import TrainingRecommender

__all__ = [
    "KPICalculator",
    "SkillGapDetector",
    "PeerBenchmarker",
    "TrainingRecommender",
]
```

**7.2 `services/api/src/triage/team_analytics/models.py`**
- Dataclasses:
  - `AgentKPI(BaseModel)`: agent_id, mttr, resolution_rate, csat, escalation_rate, avg_handling_time, period
  - `SkillGap(BaseModel)`: agent_id, issue_category, weak_in_percentage (0–1), recommended_training
  - `PeerBenchmark(BaseModel)`: agent_id, metric, value, team_average, percentile
- Tests: Model serialization

**7.3 `services/api/src/triage/team_analytics/kpi.py`**
- Class: `KPICalculator`
- Key methods:
  - `async calculate_agent_kpis(agent_id: int, period: Tuple[date, date]) -> AgentKPI`
    - Query conversations handled by agent in period
    - MTTR: Mean time-to-resolution (seconds)
    - Resolution rate: (resolved / total) %
    - CSAT: avg CSAT score from feedback (S4.7)
    - Escalation rate: (escalations / total) %
    - Avg handling time: avg time per conversation
    - Return AgentKPI
  - `async batch_calculate_team_kpis(team_id: int, period: Tuple[date, date]) -> Dict[int, AgentKPI]`
    - For all agents in team
- Tests: Single agent KPI (2), batch calculation (1), edge cases (1)

**7.4 `services/api/src/triage/team_analytics/skill_gap.py`**
- Class: `SkillGapDetector`
- Key methods:
  - `async detect_skill_gaps(agent_id: int) -> List[SkillGap]`
    - Query agent's handled conversations by category (last 90 days)
    - For each category: compute success_rate = (resolved / total)
    - Team average per category
    - If agent success < team_avg - 1σ: flag as weakness
    - Return gaps sorted by weakness level
  - `async identify_category_weakness(agent_id: int, category: str) -> float`
    - Return weakness_percentage (0–1)
- Tests: Gap detection (2), category weakness (1)

**7.5 `services/api/src/triage/team_analytics/benchmarking.py`**
- Class: `PeerBenchmarker`
- Key methods:
  - `async benchmark_agent(agent_id: int, metric: str, team_id: int) -> PeerBenchmark`
    - Calculate agent metric value (via KPICalculator)
    - Query team average and distribution
    - Compute percentile
    - Return PeerBenchmark
  - `async rank_agents(team_id: int, metric: str) -> List[Tuple[int, float]]`
    - Rank all team agents by metric (descending)
    - Return [(agent_id, metric_value), ...]
- Tests: Benchmarking (2), ranking (1)

**7.6 `services/api/src/triage/team_analytics/training.py`**
- Class: `TrainingRecommender`
- Key methods:
  - `async recommend_training(agent_id: int) -> List[Dict[str, str]]`
    - Detect skill gaps (via SkillGapDetector)
    - For each gap: map category → KB module / training material
    - Return [{category, training_module, urgency}, ...]
  - `async track_training_completion(agent_id: int, module_id: str) -> None`
    - Log completion to agent_training_records table
  - `async compute_rolling_trend(agent_id: int, metric: str, days: int = 30) -> List[Tuple[date, float]]`
    - Return daily metric values (30-day rolling window)
- Tests: Training recommendations (2), completion tracking (1), rolling trends (1)

#### Verification

```bash
# Unit tests
pytest services/api/tests/test_team_kpi.py -v
pytest services/api/tests/test_team_skill_gap.py -v
pytest services/api/tests/test_team_benchmarking.py -v
pytest services/api/tests/test_team_training.py -v

# Expected: 15+ unit tests
```

---

## Batch 4: Outcomes & Intelligence (S5.8, S5.9, S5.10)

### S5.8 — Customer Outcome Tracking & Impact (~800 lines)

**Objective:** Attribution of support + campaigns to LTV changes, retention event tracking, revenue lift, cohort analysis, NPS/CSAT correlation.

#### Files to Create

**8.1 `services/api/src/triage/outcomes/__init__.py`**
```python
from .attribution import AttributionModel
from .retention import RetentionAnalyzer
from .revenue_lift import RevenueLiftCalculator
from .cohort import CohortAnalyzer

__all__ = [
    "AttributionModel",
    "RetentionAnalyzer",
    "RevenueLiftCalculator",
    "CohortAnalyzer",
]
```

**8.2 `services/api/src/triage/outcomes/models.py`**
- Dataclasses:
  - `AttributionEvent(BaseModel)`: customer_id, event_type (support_resolved | campaign_delivered), impact_on_ltv, attributed_at
  - `RetentionEvent(BaseModel)`: customer_id, intervention_date, churn_date, days_to_churn_before, days_to_churn_after, retained
  - `RevenueLiftAnalysis(BaseModel)`: campaign_id, treatment_group_revenue, control_group_revenue, lift_pct, significance
- Tests: Model serialization

**8.3 `services/api/src/triage/outcomes/attribution.py`**
- Class: `AttributionModel`
- Key methods:
  - `async attribute_ltv_change(customer_id: int, tenant_id: int, lookback_days: int = 90) -> Dict[str, float]`
    - Query customer LTV before/after period
    - Query support resolutions + campaigns in period
    - Multi-touch attribution: assign credit proportionally
    - Return {support_credit: %, campaign_credit: %, other: %}
  - `async track_support_impact(conversation_id: int, customer_id: int) -> None`
    - On successful resolution: estimate impact (lower churn risk, higher LTV)
    - Log to outcomes_attribution table
  - `async track_campaign_impact(campaign_id: str, customer_id: int, conversion: bool) -> None`
    - Log to outcomes_attribution table
- Tests: LTV attribution (2), support impact (1), campaign impact (1)

**8.4 `services/api/src/triage/outcomes/retention.py`**
- Class: `RetentionAnalyzer`
- Key methods:
  - `async analyze_retention_event(customer_id: int, intervention: Dict) -> RetentionEvent`
    - Track: intervention_date, subsequent churn_date
    - Compute: days_to_churn_before (from S5.2), days_to_churn_after (actual if churned, else null)
    - Retained = (churn_date is None or days_to_churn_after > threshold)
    - Return RetentionEvent
  - `async compute_retention_rate(segment: str, intervention_type: str, period: Tuple[date, date]) -> float`
    - Query retention events filtered by segment + intervention type
    - Compute: retained_count / total_interventions
    - Return rate
- Tests: Retention event analysis (2), retention rate (1)

**8.5 `services/api/src/triage/outcomes/revenue_lift.py`**
- Class: `RevenueLiftCalculator`
- Key methods:
  - `async calculate_revenue_lift(treatment_customers: List[int], control_customers: List[int], period: Tuple[date, date]) -> RevenueLiftAnalysis`
    - Query revenue for treatment + control groups in period
    - Compute mean revenue per group
    - Lift % = ((treatment_mean - control_mean) / control_mean) × 100
    - Statistical test: t-test for significance
    - Return RevenueLiftAnalysis
  - `async ab_test_revenue_comparison(campaign_id: str, period: Tuple[date, date]) -> Dict[str, Any]`
    - Fetch AB test variant assignments (from S5.3)
    - Compute revenue per variant
    - Return comparison
- Tests: Revenue lift calc (2), AB test comparison (1), statistical test (1)

**8.6 `services/api/src/triage/outcomes/cohort.py`**
- Class: `CohortAnalyzer`
- Key methods:
  - `async create_cohort(name: str, filters: Dict) -> str`
    - filters: {lifecycle_stage, ltv_quartile, vertical, region, ...}
    - Query customers matching filters
    - Store cohort definition
    - Return cohort_id
  - `async analyze_cohort_outcome(cohort_id: str, metric: str, period: Tuple[date, date]) -> Dict[str, float]`
    - Query cohort members
    - Compute metric (e.g., avg_ltv, churn_rate, nps)
    - Return {metric_name: value, cohort_size, ...}
  - `async compute_nps_csat_correlation(cohort_id: str, metric: str) -> float`
    - Query NPS/CSAT scores from feedback table
    - Correlate with support outcomes (resolution rate, escalation rate)
    - Return correlation coefficient
- Tests: Cohort creation (1), outcome analysis (2), NPS/CSAT correlation (1)

#### Verification

```bash
# Unit tests
pytest services/api/tests/test_outcomes_attribution.py -v
pytest services/api/tests/test_outcomes_retention.py -v
pytest services/api/tests/test_outcomes_revenue_lift.py -v
pytest services/api/tests/test_outcomes_cohort.py -v

# Expected: 18+ unit tests
```

---

### S5.9 — Market Intelligence & Competitive Analysis (~650 lines)

**Objective:** Competitive mention tracking, feature request aggregation, churn reason analysis, market signal detection.

#### Files to Create

**9.1 `services/api/src/triage/competitive_intelligence/__init__.py`**
```python
from .mentions import MentionTracker
from .feature_requests import FeatureRequestAnalyzer
from .churn_reasons import ChurnReasonAnalyzer
from .benchmarking import CompetitiveBenchmarker

__all__ = [
    "MentionTracker",
    "FeatureRequestAnalyzer",
    "ChurnReasonAnalyzer",
    "CompetitiveBenchmarker",
]
```

**9.2 `services/api/src/triage/competitive_intelligence/models.py`**
- Dataclasses:
  - `CompetitiveMention(BaseModel)`: competitor_name, mention_context, sentiment, source (ticket | social | feedback), mentioned_at
  - `FeatureRequest(BaseModel)`: feature_name, request_count, user_impact_score, priority_rank
  - `ChurnReason(BaseModel)`: reason, count, severity (low | medium | high)
- Tests: Model serialization

**9.3 `services/api/src/triage/competitive_intelligence/mentions.py`**
- Class: `MentionTracker`
- Key methods:
  - `async extract_mentions(text: str) -> List[CompetitiveMention]`
    - Parse text for competitor names (regex + NER)
    - Sentiment analysis (per mention)
    - Return mentions
  - `async track_ticket_mentions(conversation_id: int, customer_id: int, transcript: str) -> None`
    - Extract mentions from transcript
    - Store in competitive_mentions table
  - `async monthly_mention_report(tenant_id: int, month: date) -> Dict[str, Any]`
    - Count mentions per competitor
    - Sentiment distribution
    - Return report
- Tests: Mention extraction (2), tracking (1), reporting (1)

**9.4 `services/api/src/triage/competitive_intelligence/feature_requests.py`**
- Class: `FeatureRequestAnalyzer`
- Key methods:
  - `async extract_feature_requests(text: str) -> List[str]`
    - NLP: detect "requests", "would like", "need", "feature" patterns
    - Extract feature descriptions
    - Return list
  - `async aggregate_requests(tenant_id: int, days: int = 90) -> List[FeatureRequest]`
    - Query customer conversations for last days
    - Extract + deduplicate feature requests
    - Rank by request_count
    - Compute impact_score (based on customer LTV + frequency)
    - Return sorted
  - `async prioritize_features(requests: List[FeatureRequest]) -> List[FeatureRequest]`
    - Rank by impact_score × request_count
    - Return prioritized list
- Tests: Feature extraction (2), aggregation (1), prioritization (1)

**9.5 `services/api/src/triage/competitive_intelligence/churn_reasons.py`**
- Class: `ChurnReasonAnalyzer`
- Key methods:
  - `async extract_churn_reasons(exit_survey_response: str) -> List[str]`
    - Parse reasons from structured/open-text survey
    - Categorize: (price | feature | support | competitor | other)
    - Return list
  - `async analyze_churn_patterns(tenant_id: int, days: int = 90) -> Dict[str, Dict]`
    - Query churned customers + exit surveys
    - Aggregate reasons by category + severity
    - Return {reason: {count, severity, examples}, ...}
  - `async flag_critical_reasons(threshold_count: int = 10) -> List[ChurnReason]`
    - Reasons with count > threshold
    - Flag for executive review
    - Return list
- Tests: Reason extraction (2), pattern analysis (1), critical flagging (1)

**9.6 `services/api/src/triage/competitive_intelligence/benchmarking.py`**
- Class: `CompetitiveBenchmarker`
- Key methods:
  - `async compare_support_metrics(tenant_id: int, benchmark_data: Dict) -> Dict[str, float]`
    - Query internal metrics: CSAT, response_time, resolution_rate
    - Compare to industry benchmarks (provided by user or from external source)
    - Return {metric: percentile_vs_benchmark, ...}
  - `async identify_gaps(tenant_id: int, competitive_report: Dict) -> List[str]`
    - Identify where support metrics lag competitors
    - Return gaps
- Tests: Benchmark comparison (1), gap identification (1)

#### Verification

```bash
# Unit tests
pytest services/api/tests/test_competitive_mentions.py -v
pytest services/api/tests/test_competitive_feature_requests.py -v
pytest services/api/tests/test_competitive_churn_reasons.py -v
pytest services/api/tests/test_competitive_benchmarking.py -v

# Expected: 14+ unit tests
```

---

### S5.10 — Acceptance Gate & Production Readiness (~900 lines)

**Objective:** Define acceptance criteria, create golden set (30+ E2E scenarios), CI gate, staged rollout plan, monitoring.

#### Files to Create

**10.1 Acceptance Criteria**

Functional Completeness:
- All S5.1–S5.9 modules deployed and tested
- Triage orchestrator integrated with lifecycle, predictions, recommendations
- Campaign system functional with AB testing
- Cost analysis dashboard active
- Team analytics KPIs generating

Performance Targets:
- LSTM inference: <100ms p99
- Recommendation engine: <200ms p99
- Prediction cache hit rate: >80%
- API response time: <500ms p99

Data Quality & Reliability:
- Customer RFM update: 99.5% uptime
- ML model availability: 99.9%
- Prediction freshness: <1h stale (cached)
- Cost event capture: 99.95% (no missing events)

Security & Compliance:
- PII masking in logs and dashboards
- Model training data: only de-identified features
- RBAC: teams see only their segment data
- Audit trail: all cost adjustments logged

Documentation:
- API docs (OpenAPI/Swagger) for all endpoints
- Runbook: model retraining failure recovery
- Dashboard guide: KPI interpretation
- Migration guide: A/B test rollout

**10.2 `services/api/tests/acceptance/test_s5_scenarios.py`**

30+ E2E scenarios covering:

```python
# Lifecycle Detection (3 scenarios)
test_e2e_lifecycle_new_customer_to_growth()
test_e2e_lifecycle_mature_customer_churn_detection()
test_e2e_lifecycle_event_driven_stage_change()

# Predictions (4 scenarios)
test_e2e_lstm_next_issue_recommendation()
test_e2e_churn_xgb_72h_forecast()
test_e2e_prophet_volume_forecast()
test_e2e_feature_engineering_consistency()

# Recommendations (4 scenarios)
test_e2e_tfidf_kb_search()
test_e2e_semantic_reranking()
test_e2e_collaborative_filtering()
test_e2e_ab_test_variant_assignment()

# Campaigns (5 scenarios)
test_e2e_incentive_selection_by_ltv_churn()
test_e2e_budget_allocation_per_segment()
test_e2e_send_time_optimization()
test_e2e_channel_selection_frequency_cap()
test_e2e_campaign_auto_pause_low_ctr()

# Cost & ROI (3 scenarios)
test_e2e_resolution_cost_calculation()
test_e2e_roi_per_initiative()
test_e2e_segment_profitability_analysis()

# KB Optimization (2 scenarios)
test_e2e_content_gap_identification()
test_e2e_article_performance_tracking()

# Team Analytics (3 scenarios)
test_e2e_agent_kpi_calculation()
test_e2e_skill_gap_detection()
test_e2e_peer_benchmarking()

# Outcomes & Attribution (4 scenarios)
test_e2e_ltv_attribution_multi_touch()
test_e2e_retention_event_analysis()
test_e2e_revenue_lift_ab_test()
test_e2e_cohort_nps_correlation()

# Competitive Intelligence (3 scenarios)
test_e2e_mention_tracking()
test_e2e_feature_request_aggregation()
test_e2e_churn_reason_analysis()

# Cross-System (1 scenario)
test_e2e_end_to_end_customer_journey()
```

Each scenario:
- Setup: create test data (customers, tickets, campaigns, models)
- Execute: call workflow
- Assert: verify outputs, metrics, side effects
- Teardown: clean up

**10.3 CI Gate Configuration**

```yaml
# .github/workflows/sprint5-gate.yml
name: Sprint 5 Acceptance Gate
on: [pull_request, push]
jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run unit tests
        run: pytest services/api/tests -v --cov=src/triage --cov-report=xml
      - name: Coverage threshold
        run: |
          coverage report --fail-under=85
  integration-tests:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
      redis:
        image: redis:7
    steps:
      - uses: actions/checkout@v3
      - name: Run integration tests
        run: pytest services/api/tests -m integration -v
  acceptance-tests:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
      redis:
        image: redis:7
    steps:
      - uses: actions/checkout@v3
      - name: Run E2E acceptance tests
        run: pytest services/api/tests/acceptance/test_s5_scenarios.py -v
      - name: Performance gate
        run: |
          # Check inference times < 100ms, recommendations < 200ms, etc.
  model-metrics:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Validate model performance
        run: |
          python scripts/validate_models.py
          # LSTM top-3 acc ≥ 85%, XGBoost precision ≥ 85%, recall ≥ 80%, Prophet MAPE ≤ 15%
```

**10.4 Staged Rollout Plan**

Phase 1: Canary (5% of customers)
- Week 1: Monitor LSTM predictions, churn model
- Success criteria: No errors, inference time < 100ms p99
- Rollback: Disable feature flag s5_predictions

Phase 2: Early Adopters (25% of customers)
- Week 2: Add recommendations + campaigns
- Success criteria: Self-service resolution > 35%, CTR > 1%
- Rollback: Pause campaigns, revert recommendation variant to CONTROL

Phase 3: General Availability (100% of customers)
- Week 3: Full rollout
- Success criteria: All metrics passing, CSAT +10 points
- Monitor: Cost anomalies, model drift, performance

**10.5 Monitoring & Alerting**

Prometheus metrics:
```python
# lifecycle_stage_detection.py
s5_lifecycle_stage_distribution = Gauge('s5_lifecycle_stage_distribution', 'Customers per lifecycle stage', ['stage'])
s5_lifecycle_update_duration_seconds = Histogram('s5_lifecycle_update_duration_seconds', 'RFM + clustering duration')

# predictions
s5_lstm_inference_time_ms = Histogram('s5_lstm_inference_time_ms', 'LSTM inference latency')
s5_churn_model_prediction_count = Counter('s5_churn_model_prediction_count', 'Predictions made')

# recommendations
s5_recommendation_latency_ms = Histogram('s5_recommendation_latency_ms', 'Recommendation engine latency')

# campaigns
s5_campaign_ctr = Gauge('s5_campaign_ctr', 'Campaign click-through rate')
s5_campaign_conversion = Gauge('s5_campaign_conversion', 'Campaign conversion rate')

# cost
s5_cost_per_resolution_usd = Gauge('s5_cost_per_resolution_usd', 'Average cost per resolved ticket')
s5_roi_percentage = Gauge('s5_roi_percentage', 'ROI percentage per initiative', ['initiative'])

# team
s5_agent_mttr_seconds = Gauge('s5_agent_mttr_seconds', 'Mean time-to-resolution per agent', ['agent_id'])
s5_agent_resolution_rate = Gauge('s5_agent_resolution_rate', 'Resolution rate per agent', ['agent_id'])
```

Grafana dashboards (4 total):
1. **Lifecycle & Predictions** — RFM distribution, lifecycle stage distribution, LSTM confidence, churn predictions
2. **Recommendations & Campaigns** — Top articles recommended, self-service resolution rate, campaign CTR/conversion by variant
3. **Cost & ROI** — Daily cost breakdown, cost per resolution, ROI per initiative, segment profitability
4. **Team & Outcomes** — Agent KPIs (MTTR, resolution rate, CSAT), skill gaps, customer cohort LTV trends

#### Verification

```bash
# Run all acceptance tests
pytest services/api/tests/acceptance/test_s5_scenarios.py -v

# Expected: 30+ E2E tests, all pass
# Run performance profiler
python services/api/tests/acceptance/profiler.py

# Expected: LSTM <100ms p99, recommendations <200ms p99, API <500ms p99

# Model metrics validation
python scripts/validate_models.py
# Expected: LSTM top-3 acc ≥ 85%, XGBoost precision ≥ 85%, recall ≥ 80%, Prophet MAPE ≤ 15%
```

---

## Database Schema (Alembic Migration 0007)

**Migration File:** `packages/py_core/alembic/versions/0007_sprint5_intelligence_tables.py`

New tables (8 total):
1. `customer_rfm_scores` — RFM dimensions per customer
2. `customer_lifecycle_profiles` — Lifecycle stage assignments
3. `prediction_results` — LSTM/XGBoost/Prophet predictions
4. `model_registry` — Model versioning and metadata
5. `campaign_events` — Campaign performance tracking
6. `cost_events` — Per-event micro-costing
7. `kb_article_interactions` — Article view/click/resolve tracking
8. `agent_kpis` — Rolled-up agent performance metrics

Indexes and materialized views (updates to S3 views):
- Add indices on tenant_id + timestamp for fast queries
- Add view refresh triggers (pg_cron or application scheduler)

---

## Implementation Sequence

1. **Week 1: Lifecycle & Predictions (S5.1, S5.2)**
   - Create lifecycle module (S5.1): RFM + K-means
   - Create predictions module (S5.2): LSTM, XGBoost, Prophet, feature engineering
   - Database migration
   - Unit tests (40+ tests)

2. **Week 1.5: Recommendations & Campaigns (S5.3, S5.4)**
   - Create recommendation module (S5.3): TF-IDF + semantic + collaborative + AB testing
   - Create campaigns module (S5.4): incentives, budget, send-time, channel, performance
   - Unit tests (35+ tests)

3. **Week 2: Cost, KB, Team Analytics (S5.5, S5.6, S5.7)**
   - Create cost module (S5.5): micro-costing, ROI, profitability, anomaly detection
   - Create knowledge_base module (S5.6): placement, gap analysis, performance tracking
   - Create team_analytics module (S5.7): KPIs, skill gaps, benchmarking, training
   - Unit tests (40+ tests)

4. **Week 2.5: Outcomes & Intelligence (S5.8, S5.9)**
   - Create outcomes module (S5.8): attribution, retention, revenue lift, cohort analysis
   - Create competitive_intelligence module (S5.9): mentions, feature requests, churn reasons, benchmarking
   - Unit tests (32+ tests)

5. **Week 3: Integration & Acceptance (S5.10)**
   - Integration with triage orchestrator
   - E2E acceptance tests (30+ scenarios)
   - Performance profiling and tuning
   - Grafana dashboards
   - Documentation
   - Staged rollout plan

---

## Testing Strategy

| Tier | Module | Coverage Target | Count |
|------|--------|-----------------|-------|
| A (Strict TDD) | RFM, clustering, feature engineering | ≥90% | 18 tests |
| B (Behavioral) | LSTM, XGBoost, Prophet | ≥80% | 20 tests |
| B (Behavioral) | Recommendations, campaigns | ≥80% | 30 tests |
| B (Behavioral) | Cost, KB, team, outcomes, competitive | ≥80% | 40 tests |
| C (Eval/Probe) | Model metrics (accuracy, precision, recall, MAPE) | Metric gates | 5 checks |
| D (Scenario/BDD) | E2E acceptance | 30+ scenarios | 30 tests |

**Total:** 65+ unit tests + 30+ E2E scenarios

---

## File Inventory

### Source Files (43 files)

**Lifecycle & Predictions (11 files)**
- `lifecycle/__init__.py`, `lifecycle/models.py`, `lifecycle/rfm.py`, `lifecycle/clustering.py`, `lifecycle/detector.py`, `lifecycle/scheduler.py`
- `predictions/__init__.py`, `predictions/models.py`, `predictions/feature_engineering.py`, `predictions/lstm_model.py`, `predictions/churn_xgb.py`, `predictions/volume_prophet.py`, `predictions/cache.py`, `predictions/orchestrator.py`

**Recommendations & Campaigns (10 files)**
- `recommendation/__init__.py`, `recommendation/models.py`, `recommendation/tfidf_vectorizer.py`, `recommendation/semantic_ranker.py`, `recommendation/collaborative.py`, `recommendation/engine.py`, `recommendation/ab_testing.py`
- `campaigns/__init__.py`, `campaigns/models.py`, `campaigns/incentive.py`, `campaigns/budget.py`, `campaigns/send_time.py`, `campaigns/channel.py`, `campaigns/performance.py`, `campaigns/optimizer.py`

**Cost, KB, Team (12 files)**
- `cost/__init__.py`, `cost/models.py`, `cost/events.py`, `cost/roi.py`, `cost/profitability.py`, `cost/anomaly.py`
- `knowledge_base/__init__.py`, `knowledge_base/models.py`, `knowledge_base/placement.py`, `knowledge_base/gap_analysis.py`, `knowledge_base/performance_tracker.py`, `knowledge_base/optimizer.py`
- `team_analytics/__init__.py`, `team_analytics/models.py`, `team_analytics/kpi.py`, `team_analytics/skill_gap.py`, `team_analytics/benchmarking.py`, `team_analytics/training.py`

**Outcomes & Intelligence (10 files)**
- `outcomes/__init__.py`, `outcomes/models.py`, `outcomes/attribution.py`, `outcomes/retention.py`, `outcomes/revenue_lift.py`, `outcomes/cohort.py`
- `competitive_intelligence/__init__.py`, `competitive_intelligence/models.py`, `competitive_intelligence/mentions.py`, `competitive_intelligence/feature_requests.py`, `competitive_intelligence/churn_reasons.py`, `competitive_intelligence/benchmarking.py`

### Test Files (8 modules)

- `tests/test_lifecycle_*.py` (4 files covering RFM, clustering, detector, scheduler)
- `tests/test_predictions_*.py` (4 files covering LSTM, XGBoost, volume, features)
- `tests/test_recommendation_*.py` (4 files covering TF-IDF, semantic, collaborative, AB testing)
- `tests/test_campaigns_*.py` (5 files covering incentives, budget, send-time, channel, performance)
- `tests/test_cost_*.py` (4 files covering events, ROI, profitability, anomaly)
- `tests/test_kb_*.py` (3 files covering placement, gaps, performance)
- `tests/test_team_*.py` (4 files covering KPI, skill gap, benchmarking, training)
- `tests/test_outcomes_*.py` (4 files covering attribution, retention, revenue lift, cohort)
- `tests/test_competitive_*.py` (4 files covering mentions, features, reasons, benchmarking)
- `tests/acceptance/test_s5_scenarios.py` (30+ E2E scenarios)

### Configuration & Migration Files (3 files)

- `packages/py_core/alembic/versions/0007_sprint5_intelligence_tables.py` — Database schema
- `.github/workflows/sprint5-gate.yml` — CI gate
- Updated `.env.example` — New configuration variables

---

## Dependencies & Imports

**New External Dependencies** (add to `services/api/pyproject.toml`):
- `fbprophet>=0.7.10` — Prophet time-series forecasting
- `implicit>=0.6.0` — ALS collaborative filtering
- `tensorflow>=2.13.0` OR `torch>=2.0.0` — LSTM model (choose one)
- `xgboost>=2.0.0` — Gradient boosting for churn
- `scikit-learn>=1.3.0` — KMeans, TF-IDF, metrics (already present)
- `sentence-transformers>=2.2.0` — Semantic embeddings (already present)

**Internal Imports** (from completed sprints):
- From S3: `triage.enrichment`, `triage.scoring` (account health)
- From S4: `triage.escalation`, `triage.feedback`, `triage.monitoring`
- From S2: `triage.decision`, `triage.retrieval` (KB search), `triage.routing`
- From S1: `triage.classification` (intent detection), `triage.models` (ORM)

---

## Known Constraints & Assumptions

1. **Model Training:** Assumes 2+ years of historical data per tenant. If unavailable, use synthetic data + simulated feedback for initial training.
2. **Feature Availability:** Assumes S3 enrichment (customer profiles, transaction history) is complete and accessible. If gaps exist, use fallback features.
3. **Redis Caching:** All predictions cached with 1h TTL. Requires Redis cluster for multi-tenancy.
4. **Database Size:** RFM + lifecycle tables grow with customer base. Ensure indexes on tenant_id + customer_id for performance.
5. **ML Model Deployment:** Models stored as binary blobs in model_registry. Alternative: serialize to S3 / model store (MLflow).
6. **Time Zone Handling:** Send-time optimizer uses customer account time zone. If unavailable, fall back to tenant time zone or UTC.

---

## Success Criteria

**Functional:**
- [x] All S5.1–S5.9 modules deployed and tested
- [x] Triage orchestrator receives lifecycle, predictions, recommendations
- [x] Campaign system sends offers with A/B testing
- [x] Cost dashboard calculates ROI per initiative
- [x] Team analytics generates KPIs and training recommendations

**Performance:**
- [x] LSTM inference <100ms p99
- [x] Recommendation engine <200ms p99
- [x] Prediction cache hit rate >80%

**Quality:**
- [x] Unit test coverage ≥85%
- [x] 30+ E2E acceptance scenarios pass
- [x] LSTM top-3 accuracy ≥85%
- [x] XGBoost precision ≥85%, recall ≥80%
- [x] Prophet MAPE ≤15%

**Business:**
- [x] Self-service resolution rate 35–45%
- [x] Customer churn reduced by 8–12%
- [x] CSAT improved by +10–15 points
- [x] Cost-to-serve reduced by 25–30%

---

**End of Sprint 5 Implementation Plan**
