"""Fallback intent classifier using keyword and fuzzy matching."""

from difflib import SequenceMatcher
from typing import List, Dict, Optional
import structlog

from triage.models.intent import IntentPrediction, IntentClassifierResult

log = structlog.get_logger()


class FallbackIntentClassifier:
    """Keyword and fuzzy-match fallback classifier.

    Used when embedding model fails or as backup. No external dependencies.
    Confidence 0.5–1.0 based on match quality.
    """

    def __init__(self, fuzzy_threshold: float = 0.7):
        """Initialize fallback classifier.

        Args:
            fuzzy_threshold: Levenshtein similarity threshold [0, 1].
        """
        self.fuzzy_threshold = fuzzy_threshold
        self.intent_keywords: Dict[str, List[str]] = {}

    def set_intent_keywords(self, keywords: Dict[str, List[str]]) -> None:
        """Set keywords for each intent.

        Args:
            keywords: Dict mapping intent_name -> list of keywords/phrases.
        """
        self.intent_keywords = {
            intent: [kw.lower() for kw in kws] for intent, kws in keywords.items()
        }

    def classify(self, message_text: str) -> IntentClassifierResult:
        """Classify message using keyword/fuzzy matching.

        Args:
            message_text: Message to classify.

        Returns:
            IntentClassifierResult.
        """
        if not message_text.strip():
            return IntentClassifierResult(
                message_id="",
                all_intents=[
                    IntentPrediction(intent_name="other", confidence=0.5, temperature_scaled=False)
                ],
                fallback_used=True,
            )

        message_lower = message_text.lower()
        matches = {}

        # Exact keyword matches (highest priority)
        for intent, keywords in self.intent_keywords.items():
            for keyword in keywords:
                if keyword in message_lower:
                    matches[intent] = max(matches.get(intent, 0.0), 0.95)

        # Fuzzy matches (lower priority)
        for intent, keywords in self.intent_keywords.items():
            for keyword in keywords:
                ratio = SequenceMatcher(None, message_lower, keyword).ratio()
                if ratio >= self.fuzzy_threshold:
                    matches[intent] = max(matches.get(intent, 0.0), 0.7 + 0.25 * ratio)

        # Sort by confidence
        all_intents = [
            IntentPrediction(intent_name=intent, confidence=conf, temperature_scaled=False)
            for intent, conf in sorted(matches.items(), key=lambda x: x[1], reverse=True)
        ]

        # Default to "other" if no matches
        if not all_intents:
            all_intents = [
                IntentPrediction(intent_name="other", confidence=0.5, temperature_scaled=False)
            ]

        top_intent = all_intents[0].intent_name
        top_confidence = all_intents[0].confidence

        result = IntentClassifierResult(
            message_id="",
            top_intent=top_intent,
            top_confidence=top_confidence,
            all_intents=all_intents,
            fallback_used=True,
        )

        log.info("fallback_classification_complete", top_intent=top_intent)
        return result
