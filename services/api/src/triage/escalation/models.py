"""Escalation and manual override models."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel


class Priority(str, Enum):
    """Escalation priority levels with SLA."""

    P0 = "p0"  # 15 min
    P1 = "p1"  # 1 hour
    P2 = "p2"  # 4 hours
    P3 = "p3"  # 24 hours


class EscalationRule(BaseModel):
    """Escalation trigger rule."""

    rule_id: str
    trigger_type: str  # confidence_low, safety_flag, entity_extraction_fail, anomaly, override_request
    priority: Priority
    description: str

    class Config:
        use_enum_values = False


class EscalationJob(BaseModel):
    """Escalation queue item."""

    id: int | None = None
    tenant_id: int
    ticket_id: str
    priority: Priority
    deadline: datetime
    assigned_agent: str | None = None
    status: str  # pending, assigned, in_progress, resolved, sla_breached
    created_at: datetime
    escalated_at: datetime | None = None
    resolved_at: datetime | None = None
    resolution_time_sec: float | None = None

    class Config:
        use_enum_values = False


class OverrideReason(BaseModel):
    """Human override record."""

    id: int | None = None
    tenant_id: int
    escalation_id: int
    override_by: str  # agent email
    reason_text: str
    override_decision: str  # accept or reject
    ts: datetime = field(default_factory=datetime.utcnow)

    class Config:
        use_enum_values = False


class HandoffContext(BaseModel):
    """Context for handing off to human agent."""

    escalation_id: int
    summary_text: str  # 2-3 sentences
    customer_context: dict[str, Any]  # health_score, churn_risk, last_3_attempts, etc.
    quality_score: float  # 0-1
    created_at: datetime = field(default_factory=datetime.utcnow)

    class Config:
        use_enum_values = False


@dataclass
class TriageState:
    """Current triage state for evaluation."""

    tenant_id: int
    ticket_id: str
    customer_id: int

    # Classification
    intent: str
    intent_confidence: float

    # Entities
    entities: dict[str, Any]
    entity_extraction_error: str | None = None

    # Safety
    safety_flags: list[str] = field(default_factory=list)

    # Enrichment context
    enrichment_context: dict[str, Any] = field(default_factory=dict)

    # Escalation history
    escalation_count: int = 0
