"""LangGraph state model for Sprint 2 triage agent."""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from .intent import IntentPrediction
from .entity import ExtractedEntity
from .decision import AutonomyLevel, DecisionResult


class TriageState(BaseModel):
    """Mutable state passed through LangGraph nodes."""

    # ========== INPUT ==========
    message_id: str
    message_text: str
    customer_id: str
    tenant_id: str
    channel: str = Field(default="email")
    conversation_id: Optional[str] = Field(default=None)

    # ========== CLASSIFICATION PHASE ==========
    intents: List[IntentPrediction] = Field(default_factory=list, description="All intents above threshold")
    top_intent: Optional[str] = Field(default=None, description="Primary intent")
    intent_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    # ========== ENTITY PHASE ==========
    entities: List[ExtractedEntity] = Field(default_factory=list)
    redacted_text: Optional[str] = Field(default=None, description="Text with PII replaced")

    # ========== POLICY & AUTONOMY PHASE ==========
    customer_ial: int = Field(default=0, ge=0, le=3, description="Identity Assurance Level")
    customer_tier: str = Field(default="standard")  # standard, premium, enterprise
    autonomy_level: Optional[AutonomyLevel] = Field(default=None)
    safety_flags: List[str] = Field(default_factory=list)

    # ========== RETRIEVAL PHASE (STUB) ==========
    retrieved_chunks: List[str] = Field(default_factory=list, description="Retrieved knowledge base chunks")

    # ========== RESPONSE GENERATION PHASE (STUB) ==========
    response_text: Optional[str] = Field(default=None)
    response_valid: bool = Field(default=False)
    response_error: Optional[str] = Field(default=None)

    # ========== DECISION PHASE ==========
    decision_result: Optional[DecisionResult] = Field(default=None)
    action: Optional[str] = Field(default=None)  # escalate, compose_draft, execute_tools, hold_for_agent

    # ========== EXECUTION PHASE (STUB) ==========
    tool_to_execute: Optional[str] = Field(default=None)
    tool_args: Dict[str, Any] = Field(default_factory=dict)
    tool_result: Optional[Dict[str, Any]] = Field(default=None)
    tool_error: Optional[str] = Field(default=None)

    # ========== AUDIT & TIMING ==========
    reasoning: List[Dict[str, Any]] = Field(
        default_factory=list, description="Reasoning trail for audit and debugging"
    )
    latency_ms: Optional[float] = Field(default=None)
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None,
        }

    def add_reasoning(self, step: str, details: Dict[str, Any] | None = None) -> None:
        """Log a reasoning step to the trail."""
        entry = {"step": step, "timestamp": datetime.utcnow().isoformat()}
        if details:
            entry.update(details)
        self.reasoning.append(entry)

    def model_dump_json(self, **kwargs) -> str:
        """Override to ensure JSON serializable for Postgres checkpointer."""
        # Ensure all datetime fields are ISO strings
        data = self.model_dump(**kwargs)
        if self.started_at:
            data["started_at"] = self.started_at.isoformat()
        if self.completed_at:
            data["completed_at"] = self.completed_at.isoformat()
        import json
        return json.dumps(data, default=str)
