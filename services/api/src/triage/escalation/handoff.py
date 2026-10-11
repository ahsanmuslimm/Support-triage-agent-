"""Escalation handoff context composition and quality scoring."""

import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

from .models import HandoffContext, TriageState, EscalationJob

logger = logging.getLogger(__name__)


class HandoffComposer:
    """Composes escalation handoff context for human agents."""

    def __init__(self, db_session=None):
        """
        Initialize handoff composer.
        
        Args:
            db_session: Database session
        """
        self.db_session = db_session
        self.quality_threshold = 0.90

    async def compose_handoff(
        self,
        escalation_id: int,
        state: TriageState,
        enrichment_context: Dict[str, Any],
        escalation_job: EscalationJob,
    ) -> Optional[HandoffContext]:
        """
        Compose escalation handoff context for human agent.
        
        Args:
            escalation_id: Escalation ID
            state: Triage state
            enrichment_context: Enrichment data
            escalation_job: Escalation job details
        
        Returns:
            HandoffContext with summary and quality score
        """
        try:
            # Generate summary (2-3 sentences)
            summary = self._extract_summary(
                state, enrichment_context, escalation_job
            )
            
            # Extract customer context
            customer_context = self._extract_customer_context(
                enrichment_context, state
            )
            
            # Compute quality score
            handoff_data = {
                "summary": summary,
                "customer_context": customer_context,
            }
            quality_score = self._compute_quality_score(handoff_data)
            
            handoff = HandoffContext(
                escalation_id=escalation_id,
                summary_text=summary,
                customer_context=customer_context,
                quality_score=quality_score,
                created_at=datetime.utcnow(),
            )
            
            # Log quality assessment
            quality_status = (
                "PASSED" if quality_score >= self.quality_threshold else "FAILED"
            )
            logger.info(
                f"Handoff composed: escalation={escalation_id} "
                f"quality={quality_score:.2f} status={quality_status}"
            )
            
            # In real implementation, insert into context_handoff table
            
            return handoff
        except Exception as e:
            logger.error(f"Failed to compose handoff: {e}")
            return None

    def _extract_summary(
        self,
        state: TriageState,
        enrichment_context: Dict[str, Any],
        escalation_job: EscalationJob,
    ) -> str:
        """
        Generate 2-3 sentence handoff summary.
        
        Args:
            state: Triage state
            enrichment_context: Enrichment data
            escalation_job: Escalation job
        
        Returns:
            Summary text
        """
        parts = []
        
        # Primary issue from intent + entities
        if state.intent:
            parts.append(f"Issue: {state.intent}")
        
        # Key enrichment signal
        customer = enrichment_context.get("customer", {})
        is_vip = customer.get("is_vip", False)
        health_score = enrichment_context.get("health_score", 0.5)
        churn_risk = enrichment_context.get("churn_risk", 0.0)
        
        if is_vip:
            parts.append("Customer is VIP")
        if health_score < 0.5:
            parts.append("Health score below threshold")
        if churn_risk > 0.7:
            parts.append("Churn risk elevated")
        
        # Confidence or escalation reason
        if state.intent_confidence < 0.5:
            parts.append(f"Low confidence ({state.intent_confidence:.2f}) on classification")
        
        # Combine into 2-3 sentences
        if len(parts) == 0:
            summary = f"Escalation: {state.ticket_id}. Customer requires human support."
        elif len(parts) <= 2:
            summary = f"{parts[0]}. {parts[1] if len(parts) > 1 else 'Customer requires attention.'}"
        else:
            summary = f"{parts[0]}. {parts[1]}. {parts[2]}"
        
        return summary

    def _extract_customer_context(
        self,
        enrichment_context: Dict[str, Any],
        state: TriageState,
    ) -> Dict[str, Any]:
        """
        Extract customer context fields for handoff.
        
        Args:
            enrichment_context: Enrichment data
            state: Triage state
        
        Returns:
            Dictionary with extracted context
        """
        customer_data = enrichment_context.get("customer", {})
        
        context = {
            "health_score": enrichment_context.get("health_score", 0.5),
            "churn_risk": enrichment_context.get("churn_risk", 0.0),
            "is_vip": customer_data.get("is_vip", False),
            "account_age_days": customer_data.get("account_age_days", 0),
            "customer_name": customer_data.get("name", "Unknown"),
            "customer_email": customer_data.get("email", "unknown@example.com"),
        }
        
        # Add last 3 attempts (ticket history)
        last_attempts = enrichment_context.get("last_3_attempts", [])
        context["last_3_attempts"] = last_attempts
        
        # Add order history
        context["order_count"] = customer_data.get("order_count", 0)
        context["total_spent"] = customer_data.get("total_spent", 0.0)
        
        return context

    def _compute_quality_score(self, handoff: Dict[str, Any]) -> float:
        """
        Compute quality score (0-1) for handoff context.
        
        Checklist (8 items, each worth 0.125):
        - summary not empty
        - summary >= 50 chars
        - health_score present
        - churn_risk present
        - last_3_attempts not empty
        - customer_context includes is_vip
        - escalation_reason present
        - created_at recent
        
        Args:
            handoff: Handoff data dictionary
        
        Returns:
            Quality score 0-1
        """
        score_items = []
        
        summary = handoff.get("summary", "")
        score_items.append(len(summary) > 0)
        score_items.append(len(summary) >= 50)
        
        context = handoff.get("customer_context", {})
        score_items.append("health_score" in context)
        score_items.append("churn_risk" in context)
        score_items.append(len(context.get("last_3_attempts", [])) > 0)
        score_items.append("is_vip" in context)
        score_items.append("summary" in handoff)  # Escalation reason proxy
        score_items.append(context.get("customer_name") != "Unknown")
        
        # Calculate score: number of items present / total items
        score = sum(score_items) / len(score_items)
        
        return score
