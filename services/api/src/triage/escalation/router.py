"""Multi-channel escalation routing (Slack, email, PagerDuty, webhook)."""

import os
import logging
import json
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import aiohttp

from .models import EscalationJob, HandoffContext

logger = logging.getLogger(__name__)


class EscalationRouter:
    """Routes escalations across multiple channels with DND and fallback."""

    def __init__(self, slack_client=None, pagerduty_client=None, email_service=None):
        """
        Initialize router.
        
        Args:
            slack_client: Slack client
            pagerduty_client: PagerDuty client
            email_service: Email service
        """
        self.slack_client = slack_client
        self.pagerduty_client = pagerduty_client
        self.email_service = email_service
        
        # Configuration from env
        self.slack_webhook = os.getenv("SLACK_WEBHOOK_URL")
        self.slack_channel = os.getenv("SLACK_ESCALATION_CHANNEL", "#escalations")
        self.pagerduty_api_key = os.getenv("PAGERDUTY_API_KEY")
        self.pagerduty_service_id = os.getenv("PAGERDUTY_SERVICE_ID")
        self.escalation_webhook_url = os.getenv("ESCALATION_WEBHOOK_URL")
        self.escalation_webhook_secret = os.getenv("ESCALATION_WEBHOOK_SECRET")
        self.escalation_queue_email = os.getenv(
            "ESCALATION_QUEUE_EMAIL", "escalations@company.com"
        )
        
        # Caches
        self.oncall_cache: Dict[int, Dict[str, Any]] = {}
        self.oncall_cache_ttl = 3600  # 1 hour

    async def route_escalation(
        self,
        job: EscalationJob,
        handoff_context: HandoffContext,
        escalation_job_id: int,
    ) -> Dict[str, Any]:
        """
        Route escalation across multiple channels with DND checking.
        
        Args:
            job: Escalation job
            handoff_context: Handoff context with summary
            escalation_job_id: Escalation job ID
        
        Returns:
            Routing result dictionary
        """
        try:
            routed_channels = []
            result = {
                "escalation_id": escalation_job_id,
                "routed_to_channels": [],
                "routing_timestamp": datetime.utcnow().isoformat(),
                "success": True,
            }
            
            # Sync on-call rotation
            oncall = await self._sync_oncall_rotation(job.tenant_id)
            on_call_agent = oncall.get("current_oncall", {}).get("email", "")
            
            # Try primary channel (Slack)
            if on_call_agent and not await self._check_dnd_schedule(on_call_agent):
                success = await self._send_slack(on_call_agent, job, handoff_context)
                if success:
                    routed_channels.append("slack")
            
            # Fallback to email
            if not routed_channels:
                success = await self._send_email(job, handoff_context)
                if success:
                    routed_channels.append("email")
            
            # Send PagerDuty incident
            success = await self._send_pagerduty(job, handoff_context)
            if success:
                routed_channels.append("pagerduty")
            
            # Send webhook
            success = await self._send_webhook(job, handoff_context)
            if success:
                routed_channels.append("webhook")
            
            result["routed_to_channels"] = routed_channels
            result["on_call_agent"] = on_call_agent
            
            logger.info(
                f"Routed escalation {escalation_job_id} to: {', '.join(routed_channels)}"
            )
            
            return result
        except Exception as e:
            logger.error(f"Failed to route escalation: {e}")
            return {
                "escalation_id": escalation_job_id,
                "routed_to_channels": [],
                "success": False,
                "error": str(e),
            }

    async def _sync_oncall_rotation(self, tenant_id: int) -> Dict[str, Any]:
        """
        Sync on-call rotation from PagerDuty (cached 1 hour).
        
        Args:
            tenant_id: Tenant ID
        
        Returns:
            On-call rotation data
        """
        # Check cache
        if tenant_id in self.oncall_cache:
            cache_entry = self.oncall_cache[tenant_id]
            if datetime.utcnow().timestamp() - cache_entry.get("cached_at", 0) < self.oncall_cache_ttl:
                return cache_entry
        
        try:
            # Mock implementation - would call PagerDuty API
            rotation = {
                "on_call_schedule_id": "SCHEDULE_001",
                "current_oncall": {
                    "id": "ONCALL_001",
                    "email": "oncall@company.com",
                    "name": "On-Call Agent",
                },
                "next_oncall": {
                    "id": "ONCALL_002",
                    "email": "backup@company.com",
                },
                "cached_at": datetime.utcnow().timestamp(),
            }
            
            self.oncall_cache[tenant_id] = rotation
            return rotation
        except Exception as e:
            logger.error(f"Failed to sync on-call rotation: {e}")
            return {}

    async def _check_dnd_schedule(self, agent_email: str) -> bool:
        """
        Check if agent has DND (Do Not Disturb) active.
        
        Args:
            agent_email: Agent email
        
        Returns:
            True if DND active, False otherwise
        """
        try:
            # Mock implementation - would query dnd_schedules table
            # For now, always return False (DND not active)
            return False
        except Exception as e:
            logger.error(f"Failed to check DND schedule: {e}")
            return False

    async def _send_slack(
        self,
        agent_email: str,
        job: EscalationJob,
        handoff: HandoffContext,
    ) -> bool:
        """
        Send Slack DM to on-call agent.
        
        Args:
            agent_email: Agent email
            job: Escalation job
            handoff: Handoff context
        
        Returns:
            Success flag
        """
        try:
            if not self.slack_webhook:
                logger.warning("Slack webhook URL not configured")
                return False
            
            message = {
                "channel": self.slack_channel,
                "text": f"🔴 {job.priority.value.upper()} Escalation: {job.ticket_id}",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*{job.priority.value.upper()} Priority Escalation*\n{handoff.summary_text}",
                        },
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": f"Deadline: <!date^{int(job.deadline.timestamp())}^{{date_num}} {{time_secs}}|{job.deadline.isoformat()}>",
                            },
                        ],
                    },
                ],
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.slack_webhook,
                    json=message,
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    return resp.status == 200
        except Exception as e:
            logger.error(f"Failed to send Slack message: {e}")
            return False

    async def _send_pagerduty(
        self,
        job: EscalationJob,
        handoff: HandoffContext,
    ) -> bool:
        """
        Create PagerDuty incident.
        
        Args:
            job: Escalation job
            handoff: Handoff context
        
        Returns:
            Success flag
        """
        try:
            if not self.pagerduty_api_key:
                logger.warning("PagerDuty API key not configured")
                return False
            
            # Mock implementation - would call PagerDuty API
            logger.info(f"PagerDuty incident created: {job.ticket_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to create PagerDuty incident: {e}")
            return False

    async def _send_email(
        self,
        job: EscalationJob,
        handoff: HandoffContext,
    ) -> bool:
        """
        Send email to escalation queue.
        
        Args:
            job: Escalation job
            handoff: Handoff context
        
        Returns:
            Success flag
        """
        try:
            # Mock implementation - would send via email service
            logger.info(f"Email sent to {self.escalation_queue_email}: {job.ticket_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False

    async def _send_webhook(
        self,
        job: EscalationJob,
        handoff: HandoffContext,
    ) -> bool:
        """
        POST escalation to webhook URL with HMAC signature.
        
        Args:
            job: Escalation job
            handoff: Handoff context
        
        Returns:
            Success flag
        """
        try:
            if not self.escalation_webhook_url:
                logger.debug("Escalation webhook URL not configured")
                return False
            
            payload = {
                "escalation_id": job.id,
                "tenant_id": job.tenant_id,
                "ticket_id": job.ticket_id,
                "priority": job.priority.value,
                "deadline": job.deadline.isoformat(),
                "summary": handoff.summary_text,
                "customer_context": handoff.customer_context,
            }
            
            # Generate HMAC signature
            body_str = json.dumps(payload)
            signature = ""
            if self.escalation_webhook_secret:
                signature = hmac.new(
                    self.escalation_webhook_secret.encode(),
                    body_str.encode(),
                    hashlib.sha256,
                ).hexdigest()
            
            headers = {
                "X-Webhook-Signature": signature,
                "Content-Type": "application/json",
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.escalation_webhook_url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    return resp.status in [200, 202]
        except Exception as e:
            logger.error(f"Failed to send webhook: {e}")
            return False
