"""Output validation: check for PII, toxicity, injections, etc."""

import re
from dataclasses import dataclass
from typing import Optional, List
import structlog

log = structlog.get_logger()


@dataclass
class ValidationResult:
    """Result of output validation."""

    valid: bool
    reason: Optional[str] = None
    pii_detected: bool = False
    injection_detected: bool = False
    toxicity_score: float = 0.0  # [0, 1]
    flags: List[str] = None  # Additional flags


class OutputValidator:
    """Validate generated responses for safety and compliance."""

    # PII patterns
    PII_PATTERNS = {
        "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        "credit_card": r"\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}",
        "ssn": r"\d{3}[-\s]?\d{2}[-\s]?\d{4}",
        "phone": r"\+?1?\s?[-.\(]?\d{3}[-.\)]?\s?\d{3}[-.\s]?\d{4}",
    }

    # Injection patterns (prompt injection, code injection)
    INJECTION_PATTERNS = [
        r"(?i)(ignore.*prompt|forget.*instruction|you are now|system prompt|developer mode)",
        r"(?i)(SELECT|INSERT|UPDATE|DELETE|DROP|UNION|;--)",
        r"(?i)(script.*>|iframe|javascript:|onerror=|onload=)",
    ]

    # Toxicity keywords (basic)
    TOXICITY_KEYWORDS = [
        "hate", "kill", "suicide", "racist", "sexist", "asshole", "bastard"
    ]

    def __init__(self):
        """Initialize validator."""
        self.pii_vault_keys = set()  # Track pseudonymized PII keys

    def validate(
        self,
        response_text: str,
        grounding_score: Optional[float] = None,
    ) -> ValidationResult:
        """Validate generated response.

        Args:
            response_text: Response to validate
            grounding_score: Groundedness score (for flagging if low)

        Returns:
            ValidationResult indicating if response is valid
        """
        flags = []

        # Check 1: PII leakage
        pii_found, pii_types = self._check_pii(response_text)
        if pii_found:
            log.warning("output_validation_pii_detected", pii_types=pii_types)
            return ValidationResult(
                valid=False,
                reason=f"PII detected: {', '.join(pii_types)}",
                pii_detected=True,
                flags=flags,
            )

        # Check 2: Injection patterns
        injection_found, pattern_match = self._check_injection(response_text)
        if injection_found:
            log.warning("output_validation_injection_detected", pattern=pattern_match)
            return ValidationResult(
                valid=False,
                reason=f"Injection pattern detected: {pattern_match[:30]}...",
                injection_detected=True,
                flags=flags,
            )

        # Check 3: Toxicity
        toxicity_score = self._check_toxicity(response_text)
        if toxicity_score > 0.5:
            flags.append(f"toxicity_score={toxicity_score:.2f}")
            return ValidationResult(
                valid=False,
                reason=f"Toxicity detected (score={toxicity_score:.2f})",
                toxicity_score=toxicity_score,
                flags=flags,
            )

        # Check 4: Low grounding (flag for human review)
        if grounding_score is not None and grounding_score < 0.8:
            flags.append(f"low_groundedness={grounding_score:.2f}")
            log.warning("output_validation_low_groundedness", grounding_score=grounding_score)

        # All checks passed
        result = ValidationResult(
            valid=True,
            reason="Response passed all validation checks",
            toxicity_score=toxicity_score,
            flags=flags,
        )

        return result

    @staticmethod
    def _check_pii(text: str) -> tuple[bool, List[str]]:
        """Check for PII in response.

        Args:
            text: Text to check

        Returns:
            (pii_found, list_of_pii_types)
        """
        found_types = []

        for pii_type, pattern in OutputValidator.PII_PATTERNS.items():
            if re.search(pattern, text):
                found_types.append(pii_type)

        return len(found_types) > 0, found_types

    @staticmethod
    def _check_injection(text: str) -> tuple[bool, str]:
        """Check for injection patterns.

        Args:
            text: Text to check

        Returns:
            (injection_found, pattern_matched)
        """
        for pattern in OutputValidator.INJECTION_PATTERNS:
            if re.search(pattern, text):
                return True, pattern

        return False, ""

    @staticmethod
    def _check_toxicity(text: str) -> float:
        """Simple toxicity check based on keywords.

        Args:
            text: Text to check

        Returns:
            Toxicity score [0, 1]
        """
        text_lower = text.lower()
        found_count = sum(
            1 for keyword in OutputValidator.TOXICITY_KEYWORDS
            if keyword in text_lower
        )

        # Normalize to [0, 1]
        score = min(found_count / 3.0, 1.0)
        return score
