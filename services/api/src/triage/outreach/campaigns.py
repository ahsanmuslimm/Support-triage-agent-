"""Campaign engine for proactive outreach triggers."""

import logging
import random
from datetime import datetime
from typing import Any

from jinja2 import Template

from .models import Campaign, CampaignContext, CampaignTemplate, CampaignType

logger = logging.getLogger(__name__)


class CampaignEngine:
    """Engine for triggering proactive outreach campaigns."""

    def __init__(self, template_store: dict[str, CampaignTemplate] | None = None):
        """
        Initialize campaign engine.
        
        Args:
            template_store: Dictionary of campaign templates
        """
        self.template_store = template_store or self._init_default_templates()

    def _init_default_templates(self) -> dict[str, CampaignTemplate]:
        """Initialize default campaign templates."""
        return {
            "health_check_a": CampaignTemplate(
                template_id="health_check_a",
                campaign_type=CampaignType.HEALTH_CHECK,
                channels=["email", "in_app"],
                subject_line="We've noticed changes in your account",
                body_template="Hi {{ customer_name }}, we noticed some changes in your account recently. Everything okay?",
                cta_text="Let us know",
            ),
            "health_check_b": CampaignTemplate(
                template_id="health_check_b",
                campaign_type=CampaignType.HEALTH_CHECK,
                channels=["email"],
                subject_line="Quick question about your experience",
                body_template="Hi {{ customer_name }}, we'd love your feedback. Everything going smoothly?",
                cta_text="Share feedback",
            ),
            "engagement_a": CampaignTemplate(
                template_id="engagement_a",
                campaign_type=CampaignType.ENGAGEMENT,
                channels=["email"],
                subject_line="We miss you!",
                body_template="Hi {{ customer_name }}, it's been a while. Check out what's new.",
                cta_text="See what's new",
            ),
            "engagement_b": CampaignTemplate(
                template_id="engagement_b",
                campaign_type=CampaignType.ENGAGEMENT,
                channels=["in_app"],
                subject_line="Exclusive offer inside",
                body_template="Hi {{ customer_name }}, we have something special for returning customers.",
                cta_text="View offer",
            ),
            "billing_winback_a": CampaignTemplate(
                template_id="billing_winback_a",
                campaign_type=CampaignType.BILLING_WINBACK,
                channels=["email"],
                subject_line="We can help fix your payment",
                body_template="Hi {{ customer_name }}, we noticed a payment issue. Let's get it resolved.",
                cta_text="Update payment",
            ),
            "billing_winback_b": CampaignTemplate(
                template_id="billing_winback_b",
                campaign_type=CampaignType.BILLING_WINBACK,
                channels=["email", "in_app"],
                subject_line="Complete your subscription",
                body_template="Hi {{ customer_name }}, your subscription is waiting for you.",
                cta_text="Complete setup",
            ),
            "loyalty_reward_a": CampaignTemplate(
                template_id="loyalty_reward_a",
                campaign_type=CampaignType.LOYALTY_REWARD,
                channels=["email"],
                subject_line="You're a valued customer - exclusive offer inside",
                body_template="Hi {{ customer_name }}, thank you for your loyalty. Here's 20% off.",
                cta_text="Claim offer",
            ),
            "loyalty_reward_b": CampaignTemplate(
                template_id="loyalty_reward_b",
                campaign_type=CampaignType.LOYALTY_REWARD,
                channels=["in_app"],
                subject_line="Special VIP access unlocked",
                body_template="Hi {{ customer_name }}, you've unlocked early access to new features.",
                cta_text="Explore",
            ),
        }

    async def trigger_campaigns(
        self,
        tenant_id: int,
        customer_id: int,
        context: CampaignContext,
    ) -> list[Campaign]:
        """
        Trigger campaigns based on customer context.
        
        Args:
            tenant_id: Tenant ID
            customer_id: Customer ID
            context: Customer context with enrichment signals
        
        Returns:
            List of triggered campaigns (ready to send)
        """
        campaigns: list[Campaign] = []

        # Check each trigger condition
        if await self._should_trigger_health_check(context):
            campaign = await self._create_campaign(
                tenant_id, customer_id, CampaignType.HEALTH_CHECK
            )
            if campaign:
                campaigns.append(campaign)

        if await self._should_trigger_engagement(context):
            campaign = await self._create_campaign(
                tenant_id, customer_id, CampaignType.ENGAGEMENT
            )
            if campaign:
                campaigns.append(campaign)

        if await self._should_trigger_billing_winback(context):
            campaign = await self._create_campaign(
                tenant_id, customer_id, CampaignType.BILLING_WINBACK
            )
            if campaign:
                campaigns.append(campaign)

        if await self._should_trigger_loyalty_reward(context):
            campaign = await self._create_campaign(
                tenant_id, customer_id, CampaignType.LOYALTY_REWARD
            )
            if campaign:
                campaigns.append(campaign)

        return campaigns

    async def _should_trigger_health_check(self, context: CampaignContext) -> bool:
        """Check if health check campaign should trigger."""
        # Trigger if health_score in middle range (0.35 - 0.65)
        return 0.35 < context.health_score < 0.65

    async def _should_trigger_engagement(self, context: CampaignContext) -> bool:
        """Check if engagement campaign should trigger."""
        if not context.is_active:
            return False

        if context.last_support_contact is None:
            return False

        # Trigger if no contact in last 60 days
        days_since_contact = (datetime.utcnow() - context.last_support_contact).days
        return days_since_contact > 60

    async def _should_trigger_billing_winback(self, context: CampaignContext) -> bool:
        """Check if billing winback campaign should trigger."""
        # Trigger if payment failures AND high churn risk
        return context.payment_failed_count >= 1 and context.churn_risk > 0.7

    async def _should_trigger_loyalty_reward(self, context: CampaignContext) -> bool:
        """Check if loyalty reward campaign should trigger."""
        # Trigger if loyal customer (>10 orders), healthy, but not VIP yet
        if context.order_count <= 10:
            return False
        if context.health_score <= 0.8:
            return False
        if context.is_vip:
            return False

        return True

    async def _create_campaign(
        self,
        tenant_id: int,
        customer_id: int,
        campaign_type: CampaignType,
    ) -> Campaign | None:
        """
        Create a campaign instance with A/B variant.
        
        Args:
            tenant_id: Tenant ID
            customer_id: Customer ID
            campaign_type: Type of campaign
        
        Returns:
            Campaign instance or None if templates not found
        """
        # Find templates for this campaign type
        templates_for_type = [
            t for t in self.template_store.values()
            if t.campaign_type == campaign_type
        ]

        if not templates_for_type:
            logger.warning(f"No templates found for {campaign_type.value}")
            return None

        # Random A/B assignment
        variant = self._random_ab_variant()

        # Filter to variant (assume naming convention: type_a, type_b)
        variant_templates = [
            t for t in templates_for_type
            if t.template_id.endswith(f"_{variant.lower()}")
        ]

        if not variant_templates:
            # Fallback to any template if variant not found
            variant_templates = templates_for_type

        template = variant_templates[0]

        return Campaign(
            tenant_id=tenant_id,
            customer_id=customer_id,
            template_id=template.template_id,
            campaign_type=campaign_type,
            variant=variant,
            created_at=datetime.utcnow(),
        )

    def _random_ab_variant(self) -> str:
        """
        Return random A/B variant.
        
        Returns:
            'A' or 'B' with 50/50 probability
        """
        return random.choice(['A', 'B'])

    def render_template(self, template: CampaignTemplate, context: dict[str, Any]) -> str:
        """
        Render Jinja2 template with context.
        
        Args:
            template: Campaign template
            context: Variables for template
        
        Returns:
            Rendered body text
        """
        jinja_template = Template(template.body_template)
        return jinja_template.render(**context)
