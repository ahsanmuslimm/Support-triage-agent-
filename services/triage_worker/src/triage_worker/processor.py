"""Triage pipeline: classify intent and decide autonomy for a message."""

import os

from triage.classification.fallback import FallbackIntentClassifier
from triage.decision.matrix import DecisionMatrix
from triage.models.decision import PolicyInput

from .config import DEFAULT_INTENT_KEYWORDS, TriageOutcome


def load_intent_keywords() -> dict[str, list[str]]:
    """Load intent keywords from TRIAGE_INTENT_KEYWORDS env (JSON) or defaults."""
    import json

    raw = os.getenv("TRIAGE_INTENT_KEYWORDS")
    if raw:
        return json.loads(raw)
    return DEFAULT_INTENT_KEYWORDS


def triage_text(
    text: str,
    *,
    channel: str,
    customer_tier: str = "standard",
    is_repeat_customer: bool = False,
    previous_resolution_attempts: int = 0,
    keywords: dict[str, list[str]] | None = None,
) -> TriageOutcome:
    """Classify a message and map it to an autonomy decision.

    Uses the keyword fallback classifier (no ML model required); the embedding
    k-NN classifier can replace it once examples are synced by the knowledge
    worker.
    """
    classifier = FallbackIntentClassifier()
    classifier.set_intent_keywords(keywords or load_intent_keywords())
    intent_result = classifier.classify(text)

    decision = DecisionMatrix().decide(
        PolicyInput(
            message_text=text,
            intent_name=intent_result.top_intent,
            intent_confidence=intent_result.top_confidence,
            customer_tier=customer_tier,
            channel=channel,
            is_repeat_customer=is_repeat_customer,
            previous_resolution_attempts=previous_resolution_attempts,
        )
    )

    return TriageOutcome(
        top_intent=intent_result.top_intent or "other",
        top_confidence=float(intent_result.top_confidence or 0.0),
        autonomy_level=int(decision.autonomy_level),
        action=decision.recommended_action,
        rule_triggered=decision.rule_triggered,
        reason=decision.reason,
        fallback_used=intent_result.fallback_used,
    )
