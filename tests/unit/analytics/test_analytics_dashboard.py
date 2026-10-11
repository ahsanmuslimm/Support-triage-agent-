"""Unit tests for S3.9 Analytics Dashboard."""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from services.api.src.triage.analytics.metrics_dashboard import MetricsDashboard


@pytest.fixture
def mock_db():
    """Mock database session."""
    db = MagicMock()
    db.query = MagicMock()
    return db


@pytest.fixture
def dashboard(mock_db):
    """Create dashboard with mock DB."""
    return MetricsDashboard(db_session=mock_db)


@pytest.mark.asyncio
async def test_get_summary_metrics_success(dashboard, mock_db):
    """Test successful summary metrics retrieval."""
    now = datetime.now(tz=timezone.utc)
    
    # Mock DB result
    mock_result = MagicMock()
    mock_result.triage_rate = 0.85
    mock_result.escalation_pct = 15.0
    mock_result.avg_resolution_time_sec = 120
    mock_result.csat_score = 4.2
    mock_result.cost_per_resolution = 5.50
    mock_result.recorded_at = now
    
    mock_query = MagicMock()
    mock_query.first = AsyncMock(return_value=mock_result)
    mock_db.query.return_value = mock_query
    
    result = await dashboard.get_summary_metrics(tenant_id=1)
    
    assert result is not None
    assert result["triage_rate"] == 0.85
    assert result["escalation_pct"] == 15.0
    assert result["avg_resolution_time_sec"] == 120
    assert result["csat_score"] == 4.2
    assert result["cost_per_resolution"] == 5.50


@pytest.mark.asyncio
async def test_get_summary_metrics_no_data(dashboard, mock_db):
    """Test summary metrics when no data available."""
    mock_query = MagicMock()
    mock_query.first = AsyncMock(return_value=None)
    mock_db.query.return_value = mock_query
    
    result = await dashboard.get_summary_metrics(tenant_id=1)
    
    assert result is None


@pytest.mark.asyncio
async def test_get_agent_performance_success(dashboard, mock_db):
    """Test successful agent performance retrieval."""
    now = datetime.now(tz=timezone.utc)
    
    mock_results = [
        MagicMock(
            agent_id="agent_1",
            autonomy_rate=0.75,
            avg_resolution_time=90,
            csat_score=4.5,
            recorded_at=now,
        ),
        MagicMock(
            agent_id="agent_2",
            autonomy_rate=0.68,
            avg_resolution_time=110,
            csat_score=4.1,
            recorded_at=now,
        ),
    ]
    
    mock_query = MagicMock()
    mock_query.all = AsyncMock(return_value=mock_results)
    mock_db.query.return_value = mock_query
    
    result = await dashboard.get_agent_performance(tenant_id=1, days=7)
    
    assert result is not None
    assert len(result) == 2
    assert result[0]["agent_id"] == "agent_1"
    assert result[0]["autonomy_rate"] == 0.75
    assert result[1]["autonomy_rate"] == 0.68


@pytest.mark.asyncio
async def test_get_agent_performance_empty(dashboard, mock_db):
    """Test agent performance when no data available."""
    mock_query = MagicMock()
    mock_query.all = AsyncMock(return_value=[])
    mock_db.query.return_value = mock_query
    
    result = await dashboard.get_agent_performance(tenant_id=1, days=7)
    
    assert result is not None
    assert len(result) == 0


@pytest.mark.asyncio
async def test_get_customer_outcomes_success(dashboard, mock_db):
    """Test successful customer outcomes retrieval."""
    now = datetime.now(tz=timezone.utc)
    
    mock_results = [
        MagicMock(
            segment="high_value",
            resolution_rate=0.92,
            escalation_count=5,
            churn_rate=0.02,
            recorded_at=now,
        ),
        MagicMock(
            segment="standard",
            resolution_rate=0.78,
            escalation_count=32,
            churn_rate=0.08,
            recorded_at=now,
        ),
    ]
    
    mock_query = MagicMock()
    mock_query.all = AsyncMock(return_value=mock_results)
    mock_db.query.return_value = mock_query
    
    result = await dashboard.get_customer_outcomes(tenant_id=1, days=7)
    
    assert result is not None
    assert len(result) == 2
    assert result[0]["segment"] == "high_value"
    assert result[0]["resolution_rate"] == 0.92
    assert result[1]["churn_rate"] == 0.08


@pytest.mark.asyncio
async def test_get_customer_outcomes_empty(dashboard, mock_db):
    """Test customer outcomes when no data available."""
    mock_query = MagicMock()
    mock_query.all = AsyncMock(return_value=[])
    mock_db.query.return_value = mock_query
    
    result = await dashboard.get_customer_outcomes(tenant_id=1, days=7)
    
    assert result is not None
    assert len(result) == 0


@pytest.mark.asyncio
async def test_detect_anomalies_success(dashboard, mock_db):
    """Test successful anomaly detection."""
    now = datetime.now(tz=timezone.utc)
    
    mock_results = [
        MagicMock(
            metric_name="escalation_rate",
            current_value=0.35,
            expected_value=0.15,
            deviation_sigma=2.5,
        ),
        MagicMock(
            metric_name="csat_score",
            current_value=3.2,
            expected_value=4.1,
            deviation_sigma=2.1,
        ),
    ]
    
    mock_query = MagicMock()
    mock_query.all = AsyncMock(return_value=mock_results)
    mock_db.query.return_value = mock_query
    
    result = await dashboard.detect_anomalies(tenant_id=1)
    
    assert result is not None
    assert len(result) == 2
    assert result[0]["metric_name"] == "escalation_rate"
    assert result[0]["deviation_sigma"] == 2.5


@pytest.mark.asyncio
async def test_detect_anomalies_no_anomalies(dashboard, mock_db):
    """Test anomaly detection when no anomalies found."""
    mock_query = MagicMock()
    mock_query.all = AsyncMock(return_value=[])
    mock_db.query.return_value = mock_query
    
    result = await dashboard.detect_anomalies(tenant_id=1)
    
    assert result is not None
    assert len(result) == 0


@pytest.mark.asyncio
async def test_db_error_in_summary_metrics(dashboard, mock_db):
    """Test error handling in summary metrics."""
    mock_query = MagicMock()
    mock_query.first = AsyncMock(side_effect=Exception("DB error"))
    mock_db.query.return_value = mock_query
    
    result = await dashboard.get_summary_metrics(tenant_id=1)
    
    assert result is None


@pytest.mark.asyncio
async def test_db_error_in_agent_performance(dashboard, mock_db):
    """Test error handling in agent performance."""
    mock_query = MagicMock()
    mock_query.all = AsyncMock(side_effect=Exception("DB error"))
    mock_db.query.return_value = mock_query
    
    result = await dashboard.get_agent_performance(tenant_id=1, days=7)
    
    assert result is None


@pytest.mark.asyncio
async def test_db_error_in_customer_outcomes(dashboard, mock_db):
    """Test error handling in customer outcomes."""
    mock_query = MagicMock()
    mock_query.all = AsyncMock(side_effect=Exception("DB error"))
    mock_db.query.return_value = mock_query
    
    result = await dashboard.get_customer_outcomes(tenant_id=1, days=7)
    
    assert result is None


@pytest.mark.asyncio
async def test_db_error_in_anomaly_detection(dashboard, mock_db):
    """Test error handling in anomaly detection."""
    mock_query = MagicMock()
    mock_query.all = AsyncMock(side_effect=Exception("DB error"))
    mock_db.query.return_value = mock_query
    
    result = await dashboard.detect_anomalies(tenant_id=1)
    
    assert result is None


@pytest.mark.asyncio
async def test_agent_performance_custom_days(dashboard, mock_db):
    """Test agent performance with custom lookback days."""
    mock_query = MagicMock()
    mock_query.all = AsyncMock(return_value=[])
    mock_db.query.return_value = mock_query
    
    # Call with 30 days
    result = await dashboard.get_agent_performance(tenant_id=1, days=30)
    
    # Verify query was called
    assert mock_db.query.called


@pytest.mark.asyncio
async def test_customer_outcomes_custom_days(dashboard, mock_db):
    """Test customer outcomes with custom lookback days."""
    mock_query = MagicMock()
    mock_query.all = AsyncMock(return_value=[])
    mock_db.query.return_value = mock_query
    
    # Call with 14 days
    result = await dashboard.get_customer_outcomes(tenant_id=1, days=14)
    
    # Verify query was called
    assert mock_db.query.called


@pytest.mark.asyncio
async def test_dashboard_no_db_summary(dashboard):
    """Test summary metrics with no DB session."""
    dashboard_no_db = MetricsDashboard(db_session=None)
    
    result = await dashboard_no_db.get_summary_metrics(tenant_id=1)
    
    assert result is None


@pytest.mark.asyncio
async def test_dashboard_no_db_performance(dashboard):
    """Test agent performance with no DB session."""
    dashboard_no_db = MetricsDashboard(db_session=None)
    
    result = await dashboard_no_db.get_agent_performance(tenant_id=1)
    
    assert result is None


@pytest.mark.asyncio
async def test_dashboard_no_db_outcomes(dashboard):
    """Test customer outcomes with no DB session."""
    dashboard_no_db = MetricsDashboard(db_session=None)
    
    result = await dashboard_no_db.get_customer_outcomes(tenant_id=1)
    
    assert result is None


@pytest.mark.asyncio
async def test_dashboard_no_db_anomalies(dashboard):
    """Test anomaly detection with no DB session."""
    dashboard_no_db = MetricsDashboard(db_session=None)
    
    result = await dashboard_no_db.detect_anomalies(tenant_id=1)
    
    assert result is None


@pytest.mark.asyncio
async def test_anomalies_sorted_by_deviation(dashboard, mock_db):
    """Test anomalies are sorted by deviation sigma descending."""
    mock_results = [
        MagicMock(metric_name="metric_1", current_value=1, expected_value=1, deviation_sigma=1.5),
        MagicMock(metric_name="metric_2", current_value=2, expected_value=2, deviation_sigma=3.2),
        MagicMock(metric_name="metric_3", current_value=3, expected_value=3, deviation_sigma=2.1),
    ]
    
    mock_query = MagicMock()
    mock_query.all = AsyncMock(return_value=mock_results)
    mock_db.query.return_value = mock_query
    
    result = await dashboard.detect_anomalies(tenant_id=1)
    
    # Top anomaly should be metric_2 (3.2 sigma)
    assert result[0]["metric_name"] == "metric_2"
    assert result[0]["deviation_sigma"] == 3.2


@pytest.mark.asyncio
async def test_summary_metrics_structure(dashboard, mock_db):
    """Test summary metrics return all required fields."""
    now = datetime.now(tz=timezone.utc)
    
    mock_result = MagicMock()
    mock_result.triage_rate = 0.80
    mock_result.escalation_pct = 20.0
    mock_result.avg_resolution_time_sec = 150
    mock_result.csat_score = 4.0
    mock_result.cost_per_resolution = 6.0
    mock_result.recorded_at = now
    
    mock_query = MagicMock()
    mock_query.first = AsyncMock(return_value=mock_result)
    mock_db.query.return_value = mock_query
    
    result = await dashboard.get_summary_metrics(tenant_id=1)
    
    required_fields = ["triage_rate", "escalation_pct", "avg_resolution_time_sec", "csat_score", "cost_per_resolution", "recorded_at"]
    for field in required_fields:
        assert field in result


@pytest.mark.asyncio
async def test_agent_performance_structure(dashboard, mock_db):
    """Test agent performance return all required fields."""
    now = datetime.now(tz=timezone.utc)
    
    mock_result = MagicMock()
    mock_result.agent_id = "agent_1"
    mock_result.autonomy_rate = 0.70
    mock_result.avg_resolution_time = 100
    mock_result.csat_score = 4.0
    mock_result.recorded_at = now
    
    mock_query = MagicMock()
    mock_query.all = AsyncMock(return_value=[mock_result])
    mock_db.query.return_value = mock_query
    
    result = await dashboard.get_agent_performance(tenant_id=1)
    
    required_fields = ["agent_id", "autonomy_rate", "avg_resolution_time", "csat_score", "recorded_at"]
    for field in required_fields:
        assert field in result[0]


@pytest.mark.asyncio
async def test_customer_outcomes_structure(dashboard, mock_db):
    """Test customer outcomes return all required fields."""
    now = datetime.now(tz=timezone.utc)
    
    mock_result = MagicMock()
    mock_result.segment = "vip"
    mock_result.resolution_rate = 0.95
    mock_result.escalation_count = 2
    mock_result.churn_rate = 0.01
    mock_result.recorded_at = now
    
    mock_query = MagicMock()
    mock_query.all = AsyncMock(return_value=[mock_result])
    mock_db.query.return_value = mock_query
    
    result = await dashboard.get_customer_outcomes(tenant_id=1)
    
    required_fields = ["segment", "resolution_rate", "escalation_count", "churn_rate", "recorded_at"]
    for field in required_fields:
        assert field in result[0]


@pytest.mark.asyncio
async def test_anomalies_structure(dashboard, mock_db):
    """Test anomalies return all required fields."""
    mock_result = MagicMock()
    mock_result.metric_name = "escalation_rate"
    mock_result.current_value = 0.30
    mock_result.expected_value = 0.15
    mock_result.deviation_sigma = 2.5
    
    mock_query = MagicMock()
    mock_query.all = AsyncMock(return_value=[mock_result])
    mock_db.query.return_value = mock_query
    
    result = await dashboard.detect_anomalies(tenant_id=1)
    
    required_fields = ["metric_name", "current_value", "expected_value", "deviation_sigma"]
    for field in required_fields:
        assert field in result[0]
