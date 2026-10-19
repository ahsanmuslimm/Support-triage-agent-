"""Default intent keywords and outcome model for the triage pipeline."""

from dataclasses import dataclass

DEFAULT_INTENT_KEYWORDS: dict[str, list[str]] = {
    "refund": ["refund", "money back", "return my order", "charged twice", "reimburse"],
    "billing": ["invoice", "payment failed", "billing", "subscription", "charge"],
    "shipping": ["shipping", "delivery", "track my order", "package", "parcel", "arrived"],
    "technical_issue": ["error", "bug", "not working", "crash", "broken", "500", "timeout"],
    "account": ["login", "log in", "password", "sign in", "account locked", "2fa"],
    "cancellation": ["cancel", "stop my subscription", "close my account"],
    "complaint": ["unacceptable", "terrible", "worst", "complaint", "escalate this"],
    "question": ["how do i", "how can i", "where is", "when will", "can i"],
}


@dataclass
class TriageOutcome:
    """Result of the triage pipeline for one message."""

    top_intent: str
    top_confidence: float
    autonomy_level: int
    action: str
    rule_triggered: str | None
    reason: str
    fallback_used: bool
