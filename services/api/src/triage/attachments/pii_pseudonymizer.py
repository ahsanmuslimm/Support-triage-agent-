"""PII pseudonymization for extracted text using Presidio."""

import uuid
from dataclasses import dataclass
from enum import Enum

import structlog

log = structlog.get_logger()


class PIIEntityType(str, Enum):
    """PII entity types that can be detected."""

    EMAIL = "EMAIL_ADDRESS"
    PHONE = "PHONE_NUMBER"
    CREDIT_CARD = "CREDIT_CARD"
    SSN = "US_SSN"
    PERSON = "PERSON"
    LOCATION = "LOCATION"
    DATE_TIME = "DATE_TIME"
    IP_ADDRESS = "IP_ADDRESS"


@dataclass
class PIIEntity:
    """Detected PII entity."""

    entity_type: PIIEntityType
    """Type of PII."""

    value: str
    """Original value."""

    token: str
    """Replacement token."""

    confidence: float
    """Confidence score (0-1)."""


class PIIPseudonymizer:
    """Pseudonymize PII in text using Presidio."""

    def __init__(self, min_confidence: float = 0.5) -> None:
        """Initialize pseudonymizer.

        Args:
            min_confidence: Minimum confidence threshold for PII detection.
        """
        self.min_confidence = min_confidence
        self.token_map: dict[str, str] = {}  # original_value -> token
        self.reverse_map: dict[str, str] = {}  # token -> original_value
        self.entities: list[PIIEntity] = []

    async def pseudonymize(self, text: str) -> tuple[str, list[PIIEntity]]:
        """Pseudonymize PII in text.

        Args:
            text: Input text potentially containing PII.

        Returns:
            Tuple[str, List[PIIEntity]]: Pseudonymized text and detected entities.
        """
        try:
            from presidio_analyzer import AnalyzerEngine

            log.info("pseudonymization_start", text_chars=len(text))

            # Create analyzer
            analyzer = AnalyzerEngine()

            # Analyze text
            results = analyzer.analyze(
                text,
                language="en",
                score_threshold=self.min_confidence,
            )

            # Sort by position (reverse order for replacement)
            results = sorted(results, key=lambda x: x.start, reverse=True)

            pseudonymized_text = text
            self.entities = []

            # Replace each PII entity
            for result in results:
                entity_type = PIIEntityType(result.entity_type)
                original_value = text[result.start : result.end]

                # Create or reuse token
                if original_value in self.token_map:
                    token = self.token_map[original_value]
                else:
                    token = self._generate_token(entity_type)
                    self.token_map[original_value] = token
                    self.reverse_map[token] = original_value

                # Replace in text
                pseudonymized_text = (
                    pseudonymized_text[: result.start]
                    + token
                    + pseudonymized_text[result.end :]
                )

                # Record entity
                self.entities.append(
                    PIIEntity(
                        entity_type=entity_type,
                        value=original_value,
                        token=token,
                        confidence=result.score,
                    )
                )

            log.info(
                "pseudonymization_complete",
                entities_count=len(self.entities),
                text_chars=len(pseudonymized_text),
            )

            return pseudonymized_text, self.entities

        except Exception as e:
            log.error("pseudonymization_error", error=str(e))
            # Fallback: return original text
            return text, []

    def _generate_token(self, entity_type: PIIEntityType) -> str:
        """Generate replacement token for PII entity.

        Args:
            entity_type: Type of PII entity.

        Returns:
            str: Replacement token.
        """
        short_id = str(uuid.uuid4())[:8].upper()

        token_map = {
            PIIEntityType.EMAIL: f"[EMAIL_{short_id}]",
            PIIEntityType.PHONE: f"[PHONE_{short_id}]",
            PIIEntityType.CREDIT_CARD: f"[CARD_{short_id}]",
            PIIEntityType.SSN: f"[SSN_{short_id}]",
            PIIEntityType.PERSON: f"[PERSON_{short_id}]",
            PIIEntityType.LOCATION: f"[LOCATION_{short_id}]",
            PIIEntityType.DATE_TIME: f"[DATE_{short_id}]",
            PIIEntityType.IP_ADDRESS: f"[IP_{short_id}]",
        }

        return token_map.get(entity_type, f"[PII_{short_id}]")

    def restore_pii(self, pseudonymized_text: str) -> str:
        """Restore original PII from pseudonymized text.

        Note: This should be restricted to authorized users only.

        Args:
            pseudonymized_text: Text with PII tokens.

        Returns:
            str: Text with original PII restored.
        """
        restored = pseudonymized_text
        for token, original_value in self.reverse_map.items():
            restored = restored.replace(token, original_value)
        return restored

    def get_entities_summary(self) -> dict[str, int]:
        """Get summary of detected PII entities by type.

        Returns:
            Dict[str, int]: Count of entities by type.
        """
        summary: dict[str, int] = {}
        for entity in self.entities:
            entity_type = entity.entity_type.value
            summary[entity_type] = summary.get(entity_type, 0) + 1
        return summary
