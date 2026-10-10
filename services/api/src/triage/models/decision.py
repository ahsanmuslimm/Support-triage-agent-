"""Decision matrix and autonomy models for Sprint 2."""

from pydantic import BaseModel, Field
from enum import IntEnum
from typing import Optional, List


class AutonomyLevel(IntEnum):
    """Autonomy levels for decision matrix."""

    L0_READ_ONLY = 0
    """No automation; route to human."""

    L1_SUGGEST = 1
    """Suggest action (show draft to agent)."""

    L2_CONFIRM = 2
    """Execute with confirmation required."""

    L3_AUTO = 3
    """Auto-execute (highest autonomy)."""


class SafetyFlag(str):
    """Safety triggers that mandate L0 routing."""

    CHARGEBACK = "chargeback"
    LEGAL_THREAT = "legal_threat"
    BREACH_REPORT = "breach_report"
    REGULATOR_MENTION = "regulator_mention"
    EXECUTIVE_ESCALATION = "executive_escalation"
    INJECTION_ATTEMPT = "injection_attempt"


class PolicyInput(BaseModel):
    """Input to the decision matrix."""

    message_text: str
    intent_name: Optional[str] = Field(default=None)
    intent_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    customer_tier: str = Field(default="standard")  # standard, premium, enterprise
    customer_ial: int = Field(default=0, ge=0, le=3)  # Identity Assurance Level
    safety_flags: List[SafetyFlag] = Field(default_factory=list)
    extracted_amount: Optional[float] = Field(default=None)
    channel: str = Field(default="email")  # email, chat, sms, etc.
    is_repeat_customer: bool = Field(default=False)
    previous_resolution_attempts: int = Field(default=0)

    class Config:
        json_schema_extra = {
            "example": {
                "message_text": "I want to refund order ORDER-123",
                "intent_name": "refund",
                "intent_confidence": 0.87,
                "customer_tier": "standard",
                "customer_ial": 2,
                "safety_flags": [],
                "extracted_amount": 49.99,
                "channel": "email",
                "is_repeat_customer": False,
                "previous_resolution_attempts": 0,
            }
        }


class DecisionResult(BaseModel):
    """Output of decision matrix."""

    autonomy_level: AutonomyLevel
    reason: str
    rule_triggered: Optional[str] = Field(default=None, description="Which rule was matched")
    recommended_action: str = Field(default="escalate")  # escalate, compose_draft, execute_tools, hold_for_agent
    fallback_required: bool = Field(default=False)

    class Config:
        json_schema_extra = {
            "example": {
                "autonomy_level": 2,
                "reason": "Refund < $500 and customer verified",
                "rule_triggered": "rule_7_low_risk_refund",
                "recommended_action": "execute_tools",
                "fallback_required": False,
            }
        }
