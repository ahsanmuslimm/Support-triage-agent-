"""Recommendation engine models."""

from enum import Enum

from pydantic import BaseModel, Field


class ABTestVariant(str, Enum):
    """AB test variants."""

    CONTROL = "control"
    PERSONALIZED = "personalized"
    COLLABORATIVE = "collaborative"


class RecommendationResult(BaseModel):
    """Recommendation result."""

    article_id: int
    title: str
    rank: int
    score: float = Field(ge=0, le=1)
    reason: str
