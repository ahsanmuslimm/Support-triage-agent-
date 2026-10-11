"""Unit tests for S3.4 Account Health Scorer."""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from services.api.src.triage.scoring.health_scorer import AccountHealthScorer, HealthScore
from services.api.src.triage.scoring.features import HealthFeatures


@pytest.fixture
def health_features_healthy():
    """Fixture for healthy customer features."""
    return HealthFeatures(
        recency_days=5,
        frequency=10,
        monetary_value=5000.0,
        support_contact_count=1,
        avg_resolution_days=1.0,
        failed_payments_90d=0,
        chargeback_count=0,
        subscription_age_days=365,
        subscription_status_active=True,
        plan_value_usd=99.0,
        account_age_days=365,
        total_order_count=10,
        high_value_order_count=2,
        return_rate=0.05,
        sentiment_negative_ratio=0.1,
    )


@pytest.fixture
def health_features_at_risk():
    """Fixture for at-risk customer features."""
    return HealthFeatures(
        recency_days=120,
        frequency=1,
        monetary_value=0.0,
        support_contact_count=10,
        avg_resolution_days=5.0,
        failed_payments_90d=3,
        chargeback_count=1,
        subscription_age_days=30,
        subscription_status_active=False,
        plan_value_usd=0.0,
        account_age_days=60,
        total_order_count=2,
        high_value_order_count=0,
        return_rate=0.5,
        sentiment_negative_ratio=0.8,
    )


@pytest.fixture
def scorer():
    """Create health scorer without model (uses fallback)."""
    return AccountHealthScorer()


def test_scorer_initialization(scorer):
    """Test health scorer initializes without model."""
    assert scorer.model is None
    assert scorer.threshold == 0.65


def test_predict_healthy_customer(scorer, health_features_healthy):
    """Test predicting healthy customer using fallback scoring."""
    score, label = scorer.predict(health_features_healthy)
    
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0
    assert label in ["healthy", "at_risk"]
    # Healthy features should result in low risk score
    assert score < 0.65


def test_predict_at_risk_customer(scorer, health_features_at_risk):
    """Test predicting at-risk customer using fallback scoring."""
    score, label = scorer.predict(health_features_at_risk)
    
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0
    assert label in ["healthy", "at_risk"]
    # At-risk features should result in high risk score
    assert score >= 0.65


def test_fallback_scoring_recency(scorer):
    """Test fallback scoring heavily weights recency."""
    features_recent = HealthFeatures(
        recency_days=5,
        frequency=1,
        monetary_value=100.0,
        support_contact_count=0,
        avg_resolution_days=1.0,
        failed_payments_90d=0,
        chargeback_count=0,
        subscription_age_days=100,
        subscription_status_active=True,
        plan_value_usd=29.0,
        account_age_days=100,
        total_order_count=1,
        high_value_order_count=0,
        return_rate=0.0,
        sentiment_negative_ratio=0.0,
    )
    
    features_stale = HealthFeatures(
        recency_days=120,
        frequency=1,
        monetary_value=100.0,
        support_contact_count=0,
        avg_resolution_days=1.0,
        failed_payments_90d=0,
        chargeback_count=0,
        subscription_age_days=100,
        subscription_status_active=True,
        plan_value_usd=29.0,
        account_age_days=100,
        total_order_count=1,
        high_value_order_count=0,
        return_rate=0.0,
        sentiment_negative_ratio=0.0,
    )
    
    score_recent, _ = scorer.predict(features_recent)
    score_stale, _ = scorer.predict(features_stale)
    
    # Stale recency should increase risk
    assert score_stale > score_recent


def test_fallback_scoring_failed_payments(scorer):
    """Test fallback scoring penalizes failed payments."""
    features_good = HealthFeatures(
        recency_days=10,
        frequency=5,
        monetary_value=1000.0,
        support_contact_count=1,
        avg_resolution_days=1.0,
        failed_payments_90d=0,
        chargeback_count=0,
        subscription_age_days=200,
        subscription_status_active=True,
        plan_value_usd=49.0,
        account_age_days=200,
        total_order_count=5,
        high_value_order_count=0,
        return_rate=0.0,
        sentiment_negative_ratio=0.0,
    )
    
    features_bad = HealthFeatures(
        recency_days=10,
        frequency=5,
        monetary_value=1000.0,
        support_contact_count=1,
        avg_resolution_days=1.0,
        failed_payments_90d=3,
        chargeback_count=0,
        subscription_age_days=200,
        subscription_status_active=True,
        plan_value_usd=49.0,
        account_age_days=200,
        total_order_count=5,
        high_value_order_count=0,
        return_rate=0.0,
        sentiment_negative_ratio=0.0,
    )
    
    score_good, _ = scorer.predict(features_good)
    score_bad, _ = scorer.predict(features_bad)
    
    # Failed payments should increase risk
    assert score_bad > score_good


def test_fallback_explain(scorer, health_features_at_risk):
    """Test fallback explanation generation."""
    drivers = scorer.explain(health_features_at_risk)
    
    assert isinstance(drivers, list)
    assert len(drivers) <= 3
    for driver in drivers:
        assert "feature" in driver
        assert "impact" in driver
        assert "direction" in driver
        assert driver["direction"] in ["positive", "negative"]


def test_predict_threshold_application(scorer):
    """Test that threshold is applied correctly."""
    # Create features that result in exactly 0.65 risk
    features = HealthFeatures(
        recency_days=45,
        frequency=1,
        monetary_value=100.0,
        support_contact_count=0,
        avg_resolution_days=1.0,
        failed_payments_90d=0,
        chargeback_count=0,
        subscription_age_days=100,
        subscription_status_active=True,
        plan_value_usd=29.0,
        account_age_days=100,
        total_order_count=1,
        high_value_order_count=0,
        return_rate=0.0,
        sentiment_negative_ratio=0.0,
    )
    
    score, label = scorer.predict(features)
    
    if score >= 0.65:
        assert label == "at_risk"
    else:
        assert label == "healthy"


def test_inactive_subscription_increases_risk(scorer):
    """Test that inactive subscriptions increase risk."""
    features_active = HealthFeatures(
        recency_days=10,
        frequency=5,
        monetary_value=1000.0,
        support_contact_count=1,
        avg_resolution_days=1.0,
        failed_payments_90d=0,
        chargeback_count=0,
        subscription_age_days=200,
        subscription_status_active=True,
        plan_value_usd=49.0,
        account_age_days=200,
        total_order_count=5,
        high_value_order_count=0,
        return_rate=0.0,
        sentiment_negative_ratio=0.0,
    )
    
    features_inactive = HealthFeatures(
        recency_days=10,
        frequency=5,
        monetary_value=1000.0,
        support_contact_count=1,
        avg_resolution_days=1.0,
        failed_payments_90d=0,
        chargeback_count=0,
        subscription_age_days=200,
        subscription_status_active=False,
        plan_value_usd=0.0,
        account_age_days=200,
        total_order_count=5,
        high_value_order_count=0,
        return_rate=0.0,
        sentiment_negative_ratio=0.0,
    )
    
    score_active, _ = scorer.predict(features_active)
    score_inactive, _ = scorer.predict(features_inactive)
    
    assert score_inactive > score_active


def test_high_return_rate_increases_risk(scorer):
    """Test that high return rates increase risk."""
    features_low_returns = HealthFeatures(
        recency_days=10,
        frequency=5,
        monetary_value=1000.0,
        support_contact_count=1,
        avg_resolution_days=1.0,
        failed_payments_90d=0,
        chargeback_count=0,
        subscription_age_days=200,
        subscription_status_active=True,
        plan_value_usd=49.0,
        account_age_days=200,
        total_order_count=5,
        high_value_order_count=0,
        return_rate=0.05,
        sentiment_negative_ratio=0.0,
    )
    
    features_high_returns = HealthFeatures(
        recency_days=10,
        frequency=5,
        monetary_value=1000.0,
        support_contact_count=1,
        avg_resolution_days=1.0,
        failed_payments_90d=0,
        chargeback_count=0,
        subscription_age_days=200,
        subscription_status_active=True,
        plan_value_usd=49.0,
        account_age_days=200,
        total_order_count=5,
        high_value_order_count=0,
        return_rate=0.5,
        sentiment_negative_ratio=0.0,
    )
    
    score_low, _ = scorer.predict(features_low_returns)
    score_high, _ = scorer.predict(features_high_returns)
    
    assert score_high > score_low


def test_negative_sentiment_increases_risk(scorer):
    """Test that negative sentiment increases risk."""
    features_positive = HealthFeatures(
        recency_days=10,
        frequency=5,
        monetary_value=1000.0,
        support_contact_count=1,
        avg_resolution_days=1.0,
        failed_payments_90d=0,
        chargeback_count=0,
        subscription_age_days=200,
        subscription_status_active=True,
        plan_value_usd=49.0,
        account_age_days=200,
        total_order_count=5,
        high_value_order_count=0,
        return_rate=0.0,
        sentiment_negative_ratio=0.1,
    )
    
    features_negative = HealthFeatures(
        recency_days=10,
        frequency=5,
        monetary_value=1000.0,
        support_contact_count=1,
        avg_resolution_days=1.0,
        failed_payments_90d=0,
        chargeback_count=0,
        subscription_age_days=200,
        subscription_status_active=True,
        plan_value_usd=49.0,
        account_age_days=200,
        total_order_count=5,
        high_value_order_count=0,
        return_rate=0.0,
        sentiment_negative_ratio=0.8,
    )
    
    score_positive, _ = scorer.predict(features_positive)
    score_negative, _ = scorer.predict(features_negative)
    
    assert score_negative > score_positive


def test_chargebacks_increase_risk(scorer):
    """Test that chargebacks significantly increase risk."""
    features_no_chargeback = HealthFeatures(
        recency_days=10,
        frequency=5,
        monetary_value=1000.0,
        support_contact_count=1,
        avg_resolution_days=1.0,
        failed_payments_90d=0,
        chargeback_count=0,
        subscription_age_days=200,
        subscription_status_active=True,
        plan_value_usd=49.0,
        account_age_days=200,
        total_order_count=5,
        high_value_order_count=0,
        return_rate=0.0,
        sentiment_negative_ratio=0.0,
    )
    
    features_with_chargeback = HealthFeatures(
        recency_days=10,
        frequency=5,
        monetary_value=1000.0,
        support_contact_count=1,
        avg_resolution_days=1.0,
        failed_payments_90d=0,
        chargeback_count=2,
        subscription_age_days=200,
        subscription_status_active=True,
        plan_value_usd=49.0,
        account_age_days=200,
        total_order_count=5,
        high_value_order_count=0,
        return_rate=0.0,
        sentiment_negative_ratio=0.0,
    )
    
    score_no_cb, _ = scorer.predict(features_no_chargeback)
    score_with_cb, _ = scorer.predict(features_with_chargeback)
    
    assert score_with_cb > score_no_cb


@pytest.mark.asyncio
async def test_predict_invalid_features(scorer):
    """Test prediction with invalid features raises error."""
    # Create invalid features
    invalid_features = HealthFeatures(
        recency_days=-10,  # Invalid negative
        frequency=5,
        monetary_value=1000.0,
        support_contact_count=1,
        avg_resolution_days=1.0,
        failed_payments_90d=0,
        chargeback_count=0,
        subscription_age_days=200,
        subscription_status_active=True,
        plan_value_usd=49.0,
        account_age_days=200,
        total_order_count=5,
        high_value_order_count=0,
        return_rate=0.0,
        sentiment_negative_ratio=0.0,
    )
    
    with pytest.raises((ValueError, AssertionError)):
        scorer.predict(invalid_features)


def test_explain_drivers_are_valid(scorer, health_features_at_risk):
    """Test that explanation drivers have valid structure."""
    drivers = scorer.explain(health_features_at_risk)
    
    assert isinstance(drivers, list)
    for driver in drivers:
        assert isinstance(driver, dict)
        assert "feature" in driver
        assert "impact" in driver
        assert "direction" in driver
        assert isinstance(driver["feature"], str)
        assert isinstance(driver["impact"], float)
        assert driver["direction"] in ["positive", "negative"]


# Tests for LightGBM model integration

@pytest.fixture
def model_path():
    """Path to the trained LightGBM model."""
    from pathlib import Path
    return Path(__file__).parent.parent.parent.parent / "ml" / "models" / "account_health_lgb.pkl"


def test_predict_with_actual_model_loaded(health_features_healthy, model_path):
    """Test prediction using loaded LightGBM model."""
    if not model_path.exists():
        pytest.skip(f"Model file not found at {model_path}")
    
    scorer = AccountHealthScorer(model_path=str(model_path))
    
    assert scorer.model is not None
    
    score, label = scorer.predict(health_features_healthy)
    
    # Verify valid prediction
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0
    assert label in ["healthy", "at_risk"]


def test_predict_model_vs_fallback_consistency(health_features_healthy, model_path):
    """Test that model-based predictions return valid scores."""
    if not model_path.exists():
        pytest.skip(f"Model file not found at {model_path}")
    
    scorer_model = AccountHealthScorer(model_path=str(model_path))
    scorer_fallback = AccountHealthScorer()
    
    score_model, label_model = scorer_model.predict(health_features_healthy)
    score_fallback, label_fallback = scorer_fallback.predict(health_features_healthy)
    
    # Both should produce valid outputs
    assert 0.0 <= score_model <= 1.0
    assert 0.0 <= score_fallback <= 1.0
    assert label_model in ["healthy", "at_risk"]
    assert label_fallback in ["healthy", "at_risk"]


def test_explain_with_actual_model_shap(health_features_at_risk, model_path):
    """Test SHAP-based explanation using loaded model."""
    if not model_path.exists():
        pytest.skip(f"Model file not found at {model_path}")
    
    try:
        import shap  # noqa: F401
    except ImportError:
        pytest.skip("SHAP not installed")
    
    scorer = AccountHealthScorer(model_path=str(model_path))
    drivers = scorer.explain(health_features_at_risk)
    
    # Verify valid explanation
    assert isinstance(drivers, list)
    assert len(drivers) <= 3
    
    for driver in drivers:
        assert "feature" in driver
        assert "impact" in driver
        assert "direction" in driver
        assert isinstance(driver["feature"], str)
        assert isinstance(driver["impact"], float)
        assert driver["direction"] in ["positive", "negative"]


def test_model_loading_invalid_path():
    """Test that invalid model path raises error."""
    with pytest.raises(Exception):
        AccountHealthScorer(model_path="/nonexistent/path/model.pkl")


def test_predict_fallback_when_model_none(health_features_healthy):
    """Test that prediction falls back to heuristic when model is None."""
    scorer = AccountHealthScorer(model=None)
    
    assert scorer.model is None
    
    score, label = scorer.predict(health_features_healthy)
    
    # Fallback should still work
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0
    assert label in ["healthy", "at_risk"]


def test_explain_fallback_when_shap_unavailable(health_features_at_risk):
    """Test that explanation falls back gracefully when SHAP unavailable."""
    scorer = AccountHealthScorer()
    
    # Even without SHAP, explain should work with fallback
    drivers = scorer.explain(health_features_at_risk)
    
    assert isinstance(drivers, list)
    assert len(drivers) <= 3
    for driver in drivers:
        assert "feature" in driver
        assert "impact" in driver
        assert "direction" in driver
