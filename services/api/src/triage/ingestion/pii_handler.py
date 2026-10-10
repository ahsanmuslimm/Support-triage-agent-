"""PII detection and pseudonymization."""

import re
import hashlib
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class PiiEntity:
    """Detected PII entity."""

    entity_type: str  # "EMAIL", "PHONE", "CREDIT_CARD", "SSN", "PERSON"
    value: str
    start: int
    end: int
    token: str


class PiiHandler:
    """Detects PII in text and replaces with tokens."""

    # PII detection patterns
    EMAIL_PATTERN = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
    PHONE_PATTERN = r"\(?(\d{3})\)?[-.\s]?(\d{3})[-.\s]?(\d{4})"
    CREDIT_CARD_PATTERN = r"\b(?:\d{4}[-\s]?){3}\d{4}\b"
    SSN_PATTERN = r"\b\d{3}-\d{2}-\d{4}\b"

    def __init__(self):
        """Initialize PII patterns."""
        self.patterns = {
            "EMAIL": re.compile(self.EMAIL_PATTERN),
            "PHONE": re.compile(self.PHONE_PATTERN),
            "CREDIT_CARD": re.compile(self.CREDIT_CARD_PATTERN),
            "SSN": re.compile(self.SSN_PATTERN),
        }

    def detect(self, text: str) -> List[PiiEntity]:
        """Detect PII entities in text.

        Args:
            text: Text to scan for PII

        Returns:
            List of detected PII entities
        """
        entities: List[PiiEntity] = []

        for pii_type, pattern in self.patterns.items():
            for match in pattern.finditer(text):
                token = self._generate_token(pii_type, match.group())
                entity = PiiEntity(
                    entity_type=pii_type,
                    value=match.group(),
                    start=match.start(),
                    end=match.end(),
                    token=token,
                )
                entities.append(entity)

        # Sort by start position (for replacement)
        entities.sort(key=lambda e: e.start)
        return entities

    def redact(self, text: str) -> Tuple[str, List[PiiEntity], Dict[str, str]]:
        """Redact PII from text, returning vault tokens.

        Args:
            text: Text to redact

        Returns:
            (redacted_text, entities_list, vault_mapping)
        """
        entities = self.detect(text)
        vault: Dict[str, str] = {}
        offset = 0

        for entity in entities:
            # Replace with token in text
            start = entity.start + offset
            end = entity.end + offset
            replacement = f"[PII_{entity.entity_type}_{entity.token[:8]}]"
            text = text[:start] + replacement + text[end:]
            offset += len(replacement) - (entity.end - entity.start)

            # Store in vault
            vault[entity.token] = entity.value

        return text, entities, vault

    def re_hydrate(
        self,
        redacted_text: str,
        vault: Dict[str, str],
    ) -> str:
        """Re-hydrate redacted text from vault.

        Args:
            redacted_text: Text with PII tokens
            vault: Token → plaintext mapping

        Returns:
            Original text with PII restored
        """
        text = redacted_text
        for token, value in vault.items():
            # Replace all token variants
            pattern = f"\\[PII_\\w+_{token[:8]}\\]"
            text = re.sub(pattern, value, text)
        return text

    @staticmethod
    def _generate_token(pii_type: str, value: str) -> str:
        """Generate deterministic token for PII value.

        Args:
            pii_type: Type of PII (EMAIL, PHONE, etc.)
            value: PII value

        Returns:
            Unique token
        """
        # Hash: deterministic, but not reversible
        hash_bytes = hashlib.sha256(f"{pii_type}:{value}".encode()).digest()
        return hash_bytes.hex()[:16]
