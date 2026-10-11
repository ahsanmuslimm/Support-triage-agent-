"""Triage agent state for LangGraph."""

from typing import List, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime


class TriageState(BaseModel):
    """Complete state for triage agent execution."""

    # Input
    message_id: str
    message_text: str
    customer_id: str
    tenant_id: str
    conversation_id: str

    # Classification
    intents: List[dict] = Field(default_factory=list)  # [{intent: str, confidence: float}]
    primary_intent: Optional[str] = None
    intent_confidence: float = 0.0

    # Entity extraction
    entities: List[dict] = Field(default_factory=list)
    extracted_amount: Optional[float] = None

    # Decision
    autonomy_level: Optional[int] = None  # 0-3
    autonomy_reason: Optional[str] = None
    decision_rule: Optional[str] = None

    # Retrieval
    retrieved_docs: List[dict] = Field(default_factory=list)
    retrieval_query: Optional[str] = None

    # Response generation
    response_text: Optional[str] = None
    response_valid: bool = False
    grounding_score: Optional[float] = None
    generation_error: Optional[str] = None

    # Tool execution
    tool_name: Optional[str] = None
    tool_args: Optional[dict] = None
    tool_executed: bool = False
    tool_result: Optional[dict] = None
    tool_error: Optional[str] = None

    # Escalation
    escalate: bool = False
    escalation_reason: Optional[str] = None
    escalation_route: Optional[str] = None

    # Metadata
    safety_flags: List[str] = Field(default_factory=list)
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
