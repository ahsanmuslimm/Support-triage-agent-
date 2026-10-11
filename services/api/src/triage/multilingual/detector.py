"""Language detection for messages and KB articles."""

from dataclasses import dataclass
from typing import Dict, List, Optional
import structlog

log = structlog.get_logger()


@dataclass
class LanguageDetectionResult:
    """Language detection result."""

    language: str
    """ISO 639-1 language code (e.g., 'en', 'es', 'fr')."""

    confidence: float
    """Confidence score (0-1)."""

    alternatives: List[tuple[str, float]] = None
    """Alternative languages with scores."""

    def __post_init__(self):
        if self.alternatives is None:
            self.alternatives = []


class LanguageDetector:
    """Detect language of text using langdetect or TextBlob."""

    # Top 10 languages for per-language eval slices
    TOP_LANGUAGES = ["en", "es", "fr", "de", "it", "pt", "ja", "zh", "ko", "ar"]

    async def detect_language(self, text: str) -> LanguageDetectionResult:
        """Detect language of text.

        Args:
            text: Input text.

        Returns:
            LanguageDetectionResult: Detected language and confidence.
        """
        try:
            from langdetect import detect_langs

            log.info("language_detection_start", text_chars=len(text))

            # Detect language with probabilities
            detections = detect_langs(text)

            if not detections:
                return LanguageDetectionResult(language="en", confidence=0.5)

            # Primary language
            primary = detections[0]
            language = primary.lang
            confidence = primary.prob

            # Alternatives
            alternatives = [(d.lang, d.prob) for d in detections[1:]]

            result = LanguageDetectionResult(
                language=language,
                confidence=confidence,
                alternatives=alternatives,
            )

            log.info(
                "language_detected",
                language=language,
                confidence=confidence,
            )

            return result

        except Exception as e:
            log.error("language_detection_error", error=str(e))
            # Default to English
            return LanguageDetectionResult(language="en", confidence=0.5)

    def is_supported_language(self, language_code: str) -> bool:
        """Check if language is in supported set for per-language evals.

        Args:
            language_code: ISO 639-1 language code.

        Returns:
            bool: True if language is in top 10 supported languages.
        """
        return language_code in self.TOP_LANGUAGES

    def get_supported_languages(self) -> List[str]:
        """Get list of supported languages for per-language eval slices.

        Returns:
            List[str]: ISO 639-1 language codes.
        """
        return self.TOP_LANGUAGES.copy()

    def get_language_name(self, language_code: str) -> str:
        """Get human-readable language name.

        Args:
            language_code: ISO 639-1 code.

        Returns:
            str: Language name.
        """
        language_names = {
            "en": "English",
            "es": "Spanish",
            "fr": "French",
            "de": "German",
            "it": "Italian",
            "pt": "Portuguese",
            "ja": "Japanese",
            "zh": "Chinese",
            "ko": "Korean",
            "ar": "Arabic",
        }
        return language_names.get(language_code, language_code.upper())
