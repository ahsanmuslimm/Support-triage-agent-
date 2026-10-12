"""Triage agent state for LangGraph."""

from datetime import datetime

from pydantic import BaseModel, Field


class TriageState(BaseModel):
    """Complete state for triage agent execution."""

    # Input
    message_id: str
    message_text: str
    customer_id: str
    tenant_id: str
    conversation_id: str

    # Classification
    intents: list[dict] = Field(default_factory=list)  # [{intent: str, confidence: float}]
    primary_intent: str | None = None
    intent_confidence: float = 0.0

    # Entity extraction
    entities: list[dict] = Field(default_factory=list)
    extracted_amount: float | None = None

    # Decision
    autonomy_level: int | None = None  # 0-3
    autonomy_reason: str | None = None
    decision_rule: str | None = None

    # Retrieval
    retrieved_docs: list[dict] = Field(default_factory=list)
    retrieval_query: str | None = None

    # Response generation
    response_text: str | None = None
    response_valid: bool = False
    grounding_score: float | None = None
    generation_error: str | None = None

    # Tool execution
    tool_name: str | None = None
    tool_args: dict | None = None
    tool_executed: bool = False
    tool_result: dict | None = None
    tool_error: str | None = None

    # Escalation
    escalate: bool = False
    escalation_reason: str | None = None
    escalation_route: str | None = None

    # Metadata
    safety_flags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    latency_ms: float = 0.0
    phase: str = "START"  # Track current phase

    class Config:
        json_schema_extra = {
            "example": {
                "message_id": "msg-123",
                "message_text": "Where is my order?",
                "customer_id": "cust-456",
                "tenant_id": "tenant-789",
                "conversation_id": "conv-001",
                "intents": [{"intent": "order_status", "confidence": 0.92}],
                "primary_intent": "order_status",
                "autonomy_level": 1,
                "response_text": "Your order 123 is on the way.",
            }
        }
