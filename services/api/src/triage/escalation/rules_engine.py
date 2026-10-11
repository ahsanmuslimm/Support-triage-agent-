"""Escalation rules engine for determining escalation priority."""

import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple, List

from .models import EscalationJob, Priority, TriageState

logger = logging.getLogger(__name__)


class EscalationRulesEngine:
    """Evaluates triage state against escalation rules."""

    def __init__(self, db_session=None):
        """
        Initialize rules engine.
        
        Args:
            db_session: Database session
        """
        self.db_session = db_session
        self.confidence_threshold = 0.50
        self.anomaly_priority_map = {
            "churn_spike": Priority.P1,
            "fraud_pattern": Priority.P0,
            "complaint_surge": Priority.P1,
            "response_delay": Priority.P2,
            "volume_spike": Priority.P2,
            "api_error_rate": Priority.P0,
        }

    async def evaluate(self, state: TriageState) -> Optional[EscalationJob]:
        """
        Evaluate triage state and determine if escalation needed.
        
        Args:
            state: TriageState to evaluate
        
        Returns:
            EscalationJob if escalation needed, None otherwise
        """
        # Check primary rule: confidence < 0.50
        should_escalate, priority = await self._check_confidence_rule(state)
        if should_escalate:
            return await self._create_escalation_job(state, priority, "confidence < 0.50")
        
        # Check secondary rules
        should_escalate, priority = await self._check_safety_flags(state)
        if should_escalate:
            return await self._create_escalation_job(state, priority, "safety_flags present")
        
        # Check entity extraction failure
        should_escalate, priority = await self._check_entity_extraction_failure(state)
        if should_escalate:
            return await self._create_escalation_job(state, priority, "entity_extraction_failure")
        
        # Check repeat escalation
        should_escalate, priority = await self._check_repeat_escalation(state)
        if should_escalate:
            return await self._create_escalation_job(state, priority, "repeat_escalation (>=2)")
        
        # Check for anomaly signals
        should_escalate, priority = await self._check_anomaly_signals(state)
        if should_escalate:
            return await self._create_escalation_job(state, priority, "anomaly_detected")
        
        return None

    async def _check_confidence_rule(self, state: TriageState) -> Tuple[bool, Priority]:
        """
        PRIMARY RULE: Check if intent_confidence < 0.50.
        
        Returns:
            Tuple of (should_escalate, priority)
        """
        if state.intent_confidence < self.confidence_threshold:
            logger.info(
                f"Confidence rule triggered: {state.intent_confidence} < {self.confidence_threshold}"
            )
            return True, Priority.P1
        return False, Priority.P3

    async def _check_safety_flags(self, state: TriageState) -> Tuple[bool, Priority]:
        """
        SECONDARY RULE: Check for safety flags (chargeback, legal_threat, etc.).
        
        Returns:
            Tuple of (should_escalate, priority)
        """
        safety_flags = {
            "chargeback": Priority.P0,
            "legal_threat": Priority.P0,
            "fraud_suspected": Priority.P0,
            "account_compromised": Priority.P0,
            "data_breach": Priority.P0,
        }
        
        for flag in state.safety_flags:
            if flag.lower() in safety_flags:
                priority = safety_flags[flag.lower()]
                logger.info(f"Safety flag rule triggered: {flag}")
                return True, priority
        
        return False, Priority.P3

    async def _check_entity_extraction_failure(self, state: TriageState) -> Tuple[bool, Priority]:
        """
        SECONDARY RULE: Check if entity extraction failed.
        
        Returns:
            Tuple of (should_escalate, priority)
        """
        if state.entity_extraction_error or not state.entities:
            logger.info("Entity extraction failure rule triggered")
            return True, Priority.P1
        
        return False, Priority.P3

    async def _check_anomaly_signals(self, state: TriageState) -> Tuple[bool, Priority]:
        """
        SECONDARY RULE: Check for anomaly signals from detector.
        
        Returns:
            Tuple of (should_escalate, priority)
        """
        # In real implementation, would query anomaly queue
        # For now, check if anomaly metadata in enrichment context
        if "anomaly_signal" in state.enrichment_context:
            signal_type = state.enrichment_context["anomaly_signal"].get("type", "unknown")
            priority = self.anomaly_priority_map.get(signal_type, Priority.P2)
            logger.info(f"Anomaly signal rule triggered: {signal_type}")
            return True, priority
        
        return False, Priority.P3

    async def _check_repeat_escalation(self, state: TriageState) -> Tuple[bool, Priority]:
        """
        SECONDARY RULE: Check if ticket already escalated 2+ times.
        
        Returns:
            Tuple of (should_escalate, priority)
        """
        if state.escalation_count >= 2:
            logger.info(f"Repeat escalation rule triggered: {state.escalation_count} escalations")
            return True, Priority.P0
        
        return False, Priority.P3

    async def _create_escalation_job(
        self,
        state: TriageState,
        priority: Priority,
        trigger_reason: str,
    ) -> EscalationJob:
        """
        Create escalation job with deadline based on priority.
        
        Args:
            state: Triage state
            priority: Escalation priority
            trigger_reason: Human-readable reason
        
        Returns:
            EscalationJob instance
        """
        sla_minutes_map = {
            Priority.P0: 15,
            Priority.P1: 60,
            Priority.P2: 240,
            Priority.P3: 1440,
        }
        
        sla_minutes = sla_minutes_map.get(priority, 1440)
        deadline = datetime.utcnow() + timedelta(minutes=sla_minutes)
        
        job = EscalationJob(
            tenant_id=state.tenant_id,
            ticket_id=state.ticket_id,
            priority=priority,
            deadline=deadline,
            status="pending",
            created_at=datetime.utcnow(),
        )
        
        logger.info(
            f"Created escalation job: {job.ticket_id} "
            f"priority={priority.value} sla={sla_minutes}min reason={trigger_reason}"
        )
        
        return job
