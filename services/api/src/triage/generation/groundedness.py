"""Groundedness scoring: verify response claims are supported by context."""

from dataclasses import dataclass
from typing import List
import re
import structlog

log = structlog.get_logger()


@dataclass
class GroundednessResult:
    """Result of groundedness evaluation."""

    grounding_score: float  # [0, 1] fraction of claims grounded
    supported_claims: int
    unsupported_claims: int
    ungrounded_claims: List[str]  # Claims not supported by context


class GroundednessScorer:
    """Score groundedness of generated response against context."""

    # Simple patterns for factual claims (contain numbers, names, dates)
    CLAIM_PATTERNS = [
        r"\b\d+\b",  # Numbers
        r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*",  # Proper nouns
        r"\d{1,4}[-/]\d{1,2}[-/]\d{1,4}",  # Dates
    ]

    MIN_CLAIM_LENGTH = 5  # Minimum words in a claim

    def __init__(self, similarity_threshold: float = 0.7):
        """Initialize scorer.

        Args:
            similarity_threshold: Minimum similarity for a claim to be considered grounded
        """
        self.similarity_threshold = similarity_threshold

    def score(self, response_text: str, context_text: str) -> GroundednessResult:
        """Score groundedness of response.

        Args:
            response_text: Generated response text
            context_text: Context documents

        Returns:
            GroundednessResult with scores and ungrounded claims
        """
        # Extract factual claims from response
        claims = self._extract_claims(response_text)

        if not claims:
            # No factual claims detected; assume fully grounded
            return GroundednessResult(
                grounding_score=1.0,
                supported_claims=0,
                unsupported_claims=0,
                ungrounded_claims=[],
            )

        # Check each claim against context
        supported = 0
        ungrounded = []

        for claim in claims:
            if self._is_claim_grounded(claim, context_text):
                supported += 1
            else:
                ungrounded.append(claim)

        grounding_score = supported / len(claims) if claims else 1.0

        log.info(
            "groundedness_scored",
            total_claims=len(claims),
            supported=supported,
            grounding_score=grounding_score,
        )

        return GroundednessResult(
            grounding_score=grounding_score,
            supported_claims=supported,
            unsupported_claims=len(ungrounded),
            ungrounded_claims=ungrounded,
        )

    @staticmethod
    def _extract_claims(text: str) -> List[str]:
        """Extract factual claims from text.

        Simple approach: split into sentences, filter for claims with numbers/names/dates.

        Args:
            text: Text to extract claims from

        Returns:
            List of factual claims
        """
        # Split into sentences
        sentences = re.split(r"[.!?]+", text)

        claims = []
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            # Check if sentence contains factual content
            words = sentence.split()
            if len(words) < GroundednessScorer.MIN_CLAIM_LENGTH:
                continue

            # Check for factual indicators (numbers, dates, etc.)
            has_factual_content = any(
                re.search(pattern, sentence) for pattern in GroundednessScorer.CLAIM_PATTERNS
            )

            if has_factual_content:
                claims.append(sentence)

        return claims

    def _is_claim_grounded(self, claim: str, context_text: str) -> bool:
        """Check if claim is grounded in context.

        Simple approach: substring match or word overlap.

        Args:
            claim: Claim to verify
            context_text: Context text

        Returns:
            True if claim is grounded
        """
        claim_lower = claim.lower()
        context_lower = context_text.lower()

        # Check 1: Direct substring match
        if claim_lower in context_lower:
            return True

        # Check 2: Key words match (simplified similarity)
        claim_words = set(claim_lower.split())
        context_words = set(context_lower.split())

        # Remove common words
        common_words = {"the", "a", "an", "is", "are", "was", "were", "and", "or", "for", "to", "of", "in", "on"}
        claim_words -= common_words
        context_words -= common_words

        if not claim_words:
            return True  # No significant words to check

        # Calculate word overlap
        overlap = len(claim_words & context_words)
        overlap_ratio = overlap / len(claim_words)

        return overlap_ratio >= self.similarity_threshold
