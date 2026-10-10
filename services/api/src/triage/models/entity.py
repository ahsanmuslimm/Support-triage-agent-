"""Entity extraction and linking models for Sprint 2."""

from pydantic import BaseModel, Field
from enum import Enum
from typing import Optional, List


class EntityType(str, Enum):
    """Supported entity types."""

    ORDER_ID = "ORDER_ID"
    AMOUNT = "AMOUNT"
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    ACCOUNT_ID = "ACCOUNT_ID"
    CREDIT_CARD = "CREDIT_CARD"
    SSN = "SSN"
    PRODUCT = "PRODUCT"
    DATE = "DATE"
    TRACKING_NUMBER = "TRACKING_NUMBER"


class ExtractedEntity(BaseModel):
    """A single extracted entity from message text."""

    entity_type: EntityType
    value: str
    normalized_value: Optional[str] = Field(default=None, description="Normalized form (e.g., E.164 phone)")
    confidence: float = Field(ge=0.0, le=1.0, description="Extraction confidence [0, 1]")
    start_pos: Optional[int] = Field(default=None, description="Character offset in original text")
    end_pos: Optional[int] = Field(default=None, description="Character offset in original text")
    linked_id: Optional[int] = Field(default=None, description="Link to DB record (customer, order, etc.)")
    is_pii: bool = Field(default=False, description="Whether this is personally identifiable information")
    pseudonym: Optional[str] = Field(default=None, description="PII replacement token (VAULT_xyz...)")

    class Config:
        json_schema_extra = {
            "example": {
                "entity_type": "ORDER_ID",
                "value": "ORDER-123456",
                "normalized_value": "123456",
                "confidence": 0.98,
                "start_pos": 23,
                "end_pos": 33,
                "linked_id": 789,
                "is_pii": False,
                "pseudonym": None,
            }
        }


class EntityExtractionResult(BaseModel):
    """Result of entity extraction on a message."""

    message_id: str
    entities: List[ExtractedEntity] = Field(default_factory=list)
    redacted_text: Optional[str] = Field(
        default=None, description="Message text with PII redacted to tokens"
    )
    extraction_errors: List[str] = Field(default_factory=list, description="Errors during extraction")

    class Config:
        json_schema_extra = {
            "example": {
                "message_id": "msg-123",
                "entities": [
                    {
                        "entity_type": "ORDER_ID",
                        "value": "ORDER-123456",
                        "normalized_value": "123456",
                        "confidence": 0.98,
                        "start_pos": 23,
                        "end_pos": 33,
                        "linked_id": 789,
                        "is_pii": False,
                        "pseudonym": None,
                    }
                ],
                "redacted_text": "I want a refund for order ORDER-123456",
                "extraction_errors": [],
            }
        }


class EntityValidationResult(BaseModel):
    """Result of validating entities for tool binding."""

    entity_id: str
    valid: bool
    reason: Optional[str] = Field(default=None, description="Why valid/invalid")
    can_bind_to_tool: bool = Field(default=False, description="Safe to pass to tool executor")
    cross_tenant_risk: bool = Field(default=False, description="Cross-tenant leak risk detected")

    class Config:
        json_schema_extra = {
            "example": {
                "entity_id": "entity-123",
                "valid": True,
                "reason": "Order linked and verified",
                "can_bind_to_tool": True,
                "cross_tenant_risk": False,
            }
        }
