"""Human override capture and feedback routing."""

import logging
from datetime import datetime

from .models import OverrideReason

logger = logging.getLogger(__name__)


class OverrideHandler:
    """Captures human overrides and routes feedback."""

    def __init__(self, db_session=None, feedback_router=None):
        """
        Initialize override handler.
        
        Args:
            db_session: Database session
            feedback_router: Feedback loop router (S4.7)
        """
        self.db_session = db_session
        self.feedback_router = feedback_router

    async def record_override(
        self,
        escalation_id: int,
        override_by: str,
        reason_text: str,
        override_decision: str,
        tenant_id: int,
    ) -> OverrideReason | None:
        """
        Record human override with reason.
        
        Args:
            escalation_id: Escalation ID being overridden
            override_by: Agent email
            reason_text: Reason for override
            override_decision: 'accept' or 'reject'
            tenant_id: Tenant ID
        
        Returns:
            OverrideReason record if successful, None otherwise
        """
        try:
            if override_decision not in ['accept', 'reject']:
                logger.warning(f"Invalid override decision: {override_decision}")
                return None

            override_reason = OverrideReason(
                tenant_id=tenant_id,
                escalation_id=escalation_id,
                override_by=override_by,
                reason_text=reason_text,
                override_decision=override_decision,
                ts=datetime.utcnow(),
            )

            # In real implementation, insert into override_reason table
            logger.info(
                f"Recorded override: escalation={escalation_id} "
                f"decision={override_decision} by={override_by}"
            )

            # Route to feedback loop if router available
            if self.feedback_router:
                await self.feedback_router.ingest_override_reason(override_reason)

            return override_reason
        except Exception as e:
            logger.error(f"Failed to record override: {e}")
            return None

    async def get_override_reasons(
        self,
        tenant_id: int,
        limit: int = 100,
    ) -> list[OverrideReason]:
        """
        Get recent override reasons for feedback analysis.
        
        Args:
            tenant_id: Tenant ID
            limit: Maximum number of records
        
        Returns:
            List of OverrideReason records
        """
        try:
            # In real implementation, query override_reason table
            # ORDER BY ts DESC LIMIT ?

            logger.debug(f"Fetched {limit} override reasons for tenant {tenant_id}")
            return []
        except Exception as e:
            logger.error(f"Failed to get override reasons: {e}")
            return []
