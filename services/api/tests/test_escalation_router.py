"""Tests for multi-channel escalation routing (S4.6)."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, AsyncMock

from triage.escalation.router import EscalationRouter
from triage.escalation.models import EscalationJob, HandoffContext, Priority


class TestEscalationRouter:
    """Test EscalationRouter."""

    @pytest.fixture
    def router(self):
        """Create escalation router."""
        return EscalationRouter()

    @pytest.fixture
    def sample_job(self):
        """Sample escalation job."""
        return EscalationJob(
            id=1,
            tenant_id=1,
            ticket_id="TICKET-001",
            priority=Priority.P0,
            deadline=datetime.utcnow() + timedelta(minutes=15),
            status="pending",
            created_at=datetime.utcnow(),
        )

    @pytest.fixture
    def sample_handoff(self):
        """Sample handoff context."""
        return HandoffContext(
            escalation_id=1,
            summary_text="Customer has urgent issue requiring immediate assistance.",
            customer_context={
                "health_score": 0.3,
                "is_vip": True,
                "customer_name": "John Doe",
            },
            quality_score=0.92,
        )

    @pytest.mark.asyncio
    async def test_router_initialization(self, router):
        """Test router initializes."""
        assert router.slack_webhook is None or isinstance(router.slack_webhook, str)

    @pytest.mark.asyncio
    async def test_route_escalation_success(self, router, sample_job, sample_handoff):
        """Test routing escalation."""
        with patch.object(router, '_send_slack', new_callable=AsyncMock) as mock_slack, \
             patch.object(router, '_send_pagerduty', new_callable=AsyncMock) as mock_pd, \
             patch.object(router, '_send_email', new_callable=AsyncMock) as mock_email, \
             patch.object(router, '_send_webhook', new_callable=AsyncMock) as mock_webhook:
            
            mock_slack.return_value = True
            mock_pd.return_value = True
            mock_email.return_value = False
            mock_webhook.return_value = True
            
            result = await router.route_escalation(sample_job, sample_handoff, 1)
            
            assert result["success"] is True or result.get("success", False) is not False
            assert "routed_to_channels" in result

    @pytest.mark.asyncio
    async def test_sync_oncall_rotation(self, router):
        """Test on-call rotation sync."""
        rotation = await router._sync_oncall_rotation(1)
        
        assert isinstance(rotation, dict)
        if rotation:
            assert "current_oncall" in rotation or rotation == {}

    @pytest.mark.asyncio
    async def test_check_dnd_schedule(self, router):
        """Test DND schedule check."""
        is_dnd = await router._check_dnd_schedule("agent@company.com")
        
        assert isinstance(is_dnd, bool)

    @pytest.mark.asyncio
    async def test_send_slack(self, router, sample_job, sample_handoff):
        """Test sending Slack message."""
        result = await router._send_slack(
            "agent@company.com",
            sample_job,
            sample_handoff,
        )
        
        assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_send_pagerduty(self, router, sample_job, sample_handoff):
        """Test sending PagerDuty incident."""
        result = await router._send_pagerduty(sample_job, sample_handoff)
        
        assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_send_email(self, router, sample_job, sample_handoff):
        """Test sending email."""
        result = await router._send_email(sample_job, sample_handoff)
        
        assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_send_webhook(self, router, sample_job, sample_handoff):
        """Test sending webhook."""
        result = await router._send_webhook(sample_job, sample_handoff)
        
        assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_oncall_cache_ttl(self, router):
        """Test on-call cache TTL."""
        assert router.oncall_cache_ttl == 3600  # 1 hour
