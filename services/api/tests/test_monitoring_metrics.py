"""Tests for monitoring and metrics (S4.9, S4.4)."""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from triage.monitoring.metrics import MetricsCollector
from triage.monitoring.dashboard import DashboardServer


class TestMetricsCollector:
    """Test MetricsCollector."""

    @pytest.mark.asyncio
    async def test_record_escalation(self):
        """Test recording escalation metric."""
        result = await MetricsCollector.record_escalation("tenant1", "p1")
        # Should not raise exception
        assert result is None

    @pytest.mark.asyncio
    async def test_record_resolution(self):
        """Test recording resolution time metric."""
        result = await MetricsCollector.record_resolution(245.0, 3)
        assert result is None

    @pytest.mark.asyncio
    async def test_record_cost(self):
        """Test recording cost metric."""
        result = await MetricsCollector.record_cost("tenant1", 15.50)
        assert result is None

    @pytest.mark.asyncio
    async def test_record_sla_breach(self):
        """Test recording SLA breach metric."""
        result = await MetricsCollector.record_sla_breach("tenant1", "p1")
        assert result is None

    @pytest.mark.asyncio
    async def test_record_anomaly_detection(self):
        """Test recording anomaly detection latency."""
        result = await MetricsCollector.record_anomaly_detection("churn_spike", 1500.0)
        assert result is None

    @pytest.mark.asyncio
    async def test_record_routing(self):
        """Test recording routing latency."""
        result = await MetricsCollector.record_routing("slack", 250.0)
        assert result is None

    @pytest.mark.asyncio
    async def test_record_context_quality(self):
        """Test recording context quality."""
        result = await MetricsCollector.record_context_quality("tenant1", 0.92)
        assert result is None


class TestDashboardServer:
    """Test DashboardServer."""

    @pytest.fixture
    def server(self):
        """Create dashboard server."""
        return DashboardServer()

    @pytest.mark.asyncio
    async def test_server_initialization(self, server):
        """Test server initializes."""
        assert server.db_session is None

    @pytest.mark.asyncio
    async def test_get_dashboard_data(self, server):
        """Test getting dashboard data."""
        data = await server.get_dashboard_data(1)
        
        assert "agent_performance" in data
        assert "anomaly_alerts" in data
        assert "override_queue" in data
        assert "workload_balancing" in data
        assert "refreshed_at" in data

    @pytest.mark.asyncio
    async def test_dashboard_agent_performance_panel(self, server):
        """Test agent performance panel."""
        panel = await server._get_agent_performance_panel(1)
        
        assert "kpis" in panel
        assert len(panel["kpis"]) > 0
        assert "current_vs_baseline" in panel

    @pytest.mark.asyncio
    async def test_dashboard_anomaly_alerts_panel(self, server):
        """Test anomaly alerts panel."""
        panel = await server._get_anomaly_alerts_panel(1)
        
        assert isinstance(panel, list)

    @pytest.mark.asyncio
    async def test_dashboard_override_queue_panel(self, server):
        """Test override queue panel."""
        panel = await server._get_override_queue_panel(1)
        
        assert "pending_count" in panel
        assert "recent_overrides" in panel

    @pytest.mark.asyncio
    async def test_dashboard_workload_balancing_panel(self, server):
        """Test workload balancing panel."""
        panel = await server._get_workload_balancing_panel(1)
        
        assert "queue_depth" in panel
        assert "oncall_utilization" in panel
        assert "sla_forecast" in panel
