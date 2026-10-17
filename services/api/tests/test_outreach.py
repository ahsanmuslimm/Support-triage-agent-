"""Tests for proactive outreach campaigns (S4.2)."""

from datetime import datetime, timedelta

import pytest
from triage.outreach.ab_testing import ABTestFramework
from triage.outreach.campaigns import CampaignEngine
from triage.outreach.models import CampaignContext, CampaignType


class TestCampaignEngine:
    """Test CampaignEngine."""

    @pytest.fixture
    def engine(self):
        """Create campaign engine."""
        return CampaignEngine()

    @pytest.fixture
    def sample_context(self):
        """Sample customer context."""
        return CampaignContext(
            customer_id=1,
            tenant_id=1,
            health_score=0.7,
            is_active=True,
            last_support_contact=datetime.utcnow() - timedelta(days=30),
            is_vip=False,
            payment_failed_count=0,
            churn_risk=0.2,
            order_count=5,
            last_order_date=datetime.utcnow() - timedelta(days=10),
        )

    @pytest.mark.asyncio
    async def test_campaign_engine_initialization(self, engine):
        """Test engine initializes with default templates."""
        assert engine.template_store is not None
        assert len(engine.template_store) > 0

    @pytest.mark.asyncio
    async def test_trigger_health_check_campaign(self, engine, sample_context):
        """Test health check campaign trigger."""
        # Health score in range (0.35 - 0.65) should trigger
        sample_context.health_score = 0.5

        campaigns = await engine.trigger_campaigns(1, 1, sample_context)
        health_campaigns = [c for c in campaigns if c.campaign_type == CampaignType.HEALTH_CHECK]
        assert len(health_campaigns) == 1
        assert health_campaigns[0].variant in ['A', 'B']

    @pytest.mark.asyncio
    async def test_no_health_check_healthy_customer(self, engine, sample_context):
        """Test no health check for healthy customers."""
        # Health score > 0.8 should not trigger
        sample_context.health_score = 0.85

        campaigns = await engine.trigger_campaigns(1, 1, sample_context)
        health_campaigns = [c for c in campaigns if c.campaign_type == CampaignType.HEALTH_CHECK]
        assert len(health_campaigns) == 0

    @pytest.mark.asyncio
    async def test_trigger_engagement_campaign(self, engine, sample_context):
        """Test engagement campaign trigger."""
        # No contact for 60+ days should trigger
        sample_context.last_support_contact = datetime.utcnow() - timedelta(days=90)

        campaigns = await engine.trigger_campaigns(1, 1, sample_context)
        engagement_campaigns = [c for c in campaigns if c.campaign_type == CampaignType.ENGAGEMENT]
        assert len(engagement_campaigns) == 1

    @pytest.mark.asyncio
    async def test_no_engagement_recent_contact(self, engine, sample_context):
        """Test no engagement if recent contact."""
        # Contact within 60 days - no trigger
        sample_context.last_support_contact = datetime.utcnow() - timedelta(days=30)

        campaigns = await engine.trigger_campaigns(1, 1, sample_context)
        engagement_campaigns = [c for c in campaigns if c.campaign_type == CampaignType.ENGAGEMENT]
        assert len(engagement_campaigns) == 0

    @pytest.mark.asyncio
    async def test_trigger_billing_winback_campaign(self, engine, sample_context):
        """Test billing winback campaign trigger."""
        # Payment failures + high churn risk should trigger
        sample_context.payment_failed_count = 2
        sample_context.churn_risk = 0.8

        campaigns = await engine.trigger_campaigns(1, 1, sample_context)
        billing_campaigns = [c for c in campaigns if c.campaign_type == CampaignType.BILLING_WINBACK]
        assert len(billing_campaigns) == 1

    @pytest.mark.asyncio
    async def test_no_billing_winback_no_failures(self, engine, sample_context):
        """Test no billing winback without payment failures."""
        sample_context.payment_failed_count = 0
        sample_context.churn_risk = 0.9

        campaigns = await engine.trigger_campaigns(1, 1, sample_context)
        billing_campaigns = [c for c in campaigns if c.campaign_type == CampaignType.BILLING_WINBACK]
        assert len(billing_campaigns) == 0

    @pytest.mark.asyncio
    async def test_trigger_loyalty_reward_campaign(self, engine, sample_context):
        """Test loyalty reward campaign trigger."""
        # Loyal customer (>10 orders) with high health, not VIP
        sample_context.order_count = 15
        sample_context.health_score = 0.9
        sample_context.is_vip = False

        campaigns = await engine.trigger_campaigns(1, 1, sample_context)
        loyalty_campaigns = [c for c in campaigns if c.campaign_type == CampaignType.LOYALTY_REWARD]
        assert len(loyalty_campaigns) == 1

    @pytest.mark.asyncio
    async def test_no_loyalty_vip_customer(self, engine, sample_context):
        """Test no loyalty reward for VIP customers."""
        sample_context.order_count = 15
        sample_context.health_score = 0.9
        sample_context.is_vip = True

        campaigns = await engine.trigger_campaigns(1, 1, sample_context)
        loyalty_campaigns = [c for c in campaigns if c.campaign_type == CampaignType.LOYALTY_REWARD]
        assert len(loyalty_campaigns) == 0

    @pytest.mark.asyncio
    async def test_ab_randomization_distribution(self, engine):
        """Test A/B variant randomization."""
        variants = []
        for _ in range(100):
            variant = engine._random_ab_variant()
            variants.append(variant)
            assert variant in ['A', 'B']

        # Should have roughly 50/50 distribution
        a_count = variants.count('A')
        b_count = variants.count('B')
        assert 30 < a_count < 70  # Allow 30-70 split in 100 samples
        assert 30 < b_count < 70

    @pytest.mark.asyncio
    async def test_template_rendering(self, engine):
        """Test Jinja2 template rendering."""
        templates_list = list(engine.template_store.values())
        if templates_list:
            template = templates_list[0]
            context = {"customer_name": "John Doe"}
            rendered = engine.render_template(template, context)
            assert "John Doe" in rendered or "customer_name" not in template.body_template

    @pytest.mark.asyncio
    async def test_multiple_campaigns_per_customer(self, engine):
        """Test multiple campaigns can trigger for one customer."""
        context = CampaignContext(
            customer_id=1,
            tenant_id=1,
            health_score=0.5,  # Triggers health check
            is_active=True,
            last_support_contact=datetime.utcnow() - timedelta(days=90),  # Triggers engagement
            is_vip=False,
            payment_failed_count=1,
            churn_risk=0.8,  # Triggers billing winback
            order_count=15,  # Triggers loyalty
        )

        campaigns = await engine.trigger_campaigns(1, 1, context)
        assert len(campaigns) >= 3  # At least 3 campaigns should trigger


class TestABTestFramework:
    """Test ABTestFramework."""

    @pytest.fixture
    def framework(self):
        """Create A/B test framework."""
        return ABTestFramework(min_sample_size=100)

    @pytest.mark.asyncio
    async def test_framework_initialization(self, framework):
        """Test framework initializes."""
        assert framework.min_sample_size == 100

    @pytest.mark.asyncio
    async def test_record_event_success(self, framework):
        """Test recording campaign event."""
        result = await framework.record_event(1, 'opened')
        assert result is True

    @pytest.mark.asyncio
    async def test_record_event_valid_types(self, framework):
        """Test valid event types."""
        for event_type in ['opened', 'clicked', 'converted']:
            result = await framework.record_event(1, event_type)
            assert result is True

    @pytest.mark.asyncio
    async def test_record_event_invalid_type(self, framework):
        """Test invalid event type."""
        result = await framework.record_event(1, 'invalid_event')
        assert result is False

    @pytest.mark.asyncio
    async def test_compute_results_no_data(self, framework):
        """Test computing results with no data."""
        results = await framework.compute_results(1, CampaignType.HEALTH_CHECK)
        assert results is None
