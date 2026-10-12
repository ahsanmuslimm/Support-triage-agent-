"""Intent classification and prediction models for Sprint 2."""

from typing import Any, ClassVar

from pydantic import BaseModel, Field


class IntentPrediction(BaseModel):
    """Single intent prediction result."""

    intent_name: str = Field(description="Name of the predicted intent")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score [0, 1]")
    temperature_scaled: bool = Field(default=True, description="Whether confidence was temperature-scaled")


class IntentClassifierResult(BaseModel):
    """Result of intent classification on a message."""

    message_id: str
    top_intent: str | None = Field(default=None, description="Highest-confidence intent")
    top_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    all_intents: list[IntentPrediction] = Field(default_factory=list, description="All intents above threshold")
    fallback_used: bool = Field(default=False, description="Whether fallback classifier was used")
    model_error: str | None = Field(default=None, description="Error message if classification failed")

    class Config:
        json_schema_extra: ClassVar[dict[str, dict[str, Any]]] = {
            "example": {
                "message_id": "msg-123",
                "top_intent": "order.status",
                "top_confidence": 0.92,
                "all_intents": [
                    {"intent_name": "order.status", "confidence": 0.92, "temperature_scaled": True},
                    {"intent_name": "shipping.delay", "confidence": 0.08, "temperature_scaled": True},
                ],
                "fallback_used": False,
                "model_error": None,
            }
        }
