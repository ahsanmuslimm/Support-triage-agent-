"""Tests for Sprint 2 Pydantic models."""

import pytest
from datetime import datetime

from triage.models.intent import IntentPrediction, IntentClassifierResult
from triage.models.decision import (
    AutonomyLevel,
    PolicyInput,
    DecisionResult,
    SafetyFlag,
)
from triage.models.entity import EntityType, ExtractedEntity, EntityExtractionResult
from triage.models.triage_state import TriageState


class TestIntentModels:
    """Test intent-related models."""

    def test_intent_prediction_creation(self):
        """Test IntentPrediction model."""
        pred = IntentPrediction(
            intent_name="order.status",
            confidence=0.92,
            temperature_scaled=True,
        )
        assert pred.intent_name == "order.status"
        assert pred.confidence == 0.92
        assert pred.temperature_scaled is True

    def test_intent_prediction_confidence_bounds(self):
        """Test confidence is in [0, 1]."""
        with pytest.raises(ValueError):
            IntentPrediction(intent_name="test", confidence=1.5)
        with pytest.raises(ValueError):
            IntentPrediction(intent_name="test", confidence=-0.1)

    def test_intent_classifier_result_serialization(self):
        """Test IntentClassifierResult can be serialized."""
        result = IntentClassifierResult(
            message_id="msg-123",
            top_intent="order.status",
            top_confidence=0.92,
            all_intents=[
                IntentPrediction(intent_name="order.status", confidence=0.92),
                IntentPrediction(intent_name="shipping.delay", confidence=0.08),
            ],
            fallback_used=False,
        )
        data = result.model_dump()
        assert data["message_id"] == "msg-123"
        assert data["top_intent"] == "order.status"
        assert len(data["all_intents"]) == 2

        # Test round-trip
        result2 = IntentClassifierResult(**data)
        assert result2.top_intent == result.top_intent


class TestDecisionModels:
    """Test decision and autonomy models."""

    def test_autonomy_level_enum(self):
        """Test AutonomyLevel enum values."""
        assert AutonomyLevel.L0_READ_ONLY == 0
        assert AutonomyLevel.L1_SUGGEST == 1
        assert AutonomyLevel.L2_CONFIRM == 2
        assert AutonomyLevel.L3_AUTO == 3

    def test_policy_input_creation(self):
        """Test PolicyInput model."""
        policy = PolicyInput(
            message_text="I want a refund",
            intent_name="refund",
            intent_confidence=0.85,
            customer_tier="standard",
            customer_ial=2,
            extracted_amount=49.99,
        )
        assert policy.intent_name == "refund"
        assert policy.extracted_amount == 49.99
        assert policy.customer_ial == 2

    def test_policy_input_with_safety_flags(self):
        """Test PolicyInput with safety flags."""
        policy = PolicyInput(
            message_text="This is fraud",
            intent_name="chargeback",
            safety_flags=["chargeback", "legal_threat"],
        )
        assert len(policy.safety_flags) == 2
        assert "chargeback" in policy.safety_flags

    def test_decision_result_serialization(self):
        """Test DecisionResult serialization."""
        decision = DecisionResult(
            autonomy_level=AutonomyLevel.L2_CONFIRM,
            reason="Refund < $500 and customer verified",
            rule_triggered="rule_9_low_risk_refund",
            recommended_action="execute_tools",
        )
        data = decision.model_dump()
        assert data["autonomy_level"] == 2
        assert data["recommended_action"] == "execute_tools"

        # Round-trip
        decision2 = DecisionResult(**data)
        assert decision2.autonomy_level == AutonomyLevel.L2_CONFIRM


class TestEntityModels:
    """Test entity extraction models."""

    def test_extracted_entity_creation(self):
        """Test ExtractedEntity model."""
        entity = ExtractedEntity(
            entity_type=EntityType.ORDER_ID,
            value="ORDER-123456",
            normalized_value="123456",
            confidence=0.98,
            start_pos=23,
            end_pos=33,
            linked_id=789,
            is_pii=False,
        )
        assert entity.entity_type == EntityType.ORDER_ID
        assert entity.value == "ORDER-123456"
        assert entity.confidence == 0.98

    def test_extracted_entity_pii_flag(self):
        """Test PII flagging."""
        entity = ExtractedEntity(
            entity_type=EntityType.CREDIT_CARD,
            value="4111111111111111",
            confidence=0.99,
            is_pii=True,
            pseudonym="VAULT_cc_xyz123",
        )
        assert entity.is_pii is True
        assert entity.pseudonym == "VAULT_cc_xyz123"

    def test_entity_extraction_result_serialization(self):
        """Test EntityExtractionResult."""
        result = EntityExtractionResult(
            message_id="msg-123",
            entities=[
                ExtractedEntity(
                    entity_type=EntityType.ORDER_ID,
                    value="ORDER-123",
                    confidence=0.98,
                )
            ],
            redacted_text="I want a refund for order ORDER-123",
        )
        data = result.model_dump()
        assert data["message_id"] == "msg-123"
        assert len(data["entities"]) == 1


class TestTriageState:
    """Test TriageState model."""

    def test_triage_state_creation(self):
        """Test TriageState initialization."""
        state = TriageState(
            message_id="msg-123",
            message_text="Where is my order?",
            customer_id="cust-456",
            tenant_id="tenant-789",
            conversation_id="conv-001",
        )
        assert state.message_id == "msg-123"
        assert state.primary_intent is None
        assert len(state.intents) == 0

    def test_triage_state_add_reasoning(self):
        """Test entity and intent tracking."""
        state = TriageState(
            message_id="msg-123",
            message_text="Test",
            customer_id="cust-123",
            tenant_id="tenant-123",
            conversation_id="conv-001",
        )
        state.intents = [{"intent": "order_status", "confidence": 0.92}]
        state.entities = [{"type": "ORDER_ID", "value": "12345"}]

        assert len(state.intents) == 1
        assert state.intents[0]["intent"] == "order_status"
        assert len(state.entities) == 1

    def test_triage_state_serialization(self):
        """Test TriageState serialization."""
        state = TriageState(
            message_id="msg-123",
            message_text="Test message",
            customer_id="cust-123",
            tenant_id="tenant-123",
            conversation_id="conv-001",
            primary_intent="order_status",
            intent_confidence=0.87,
        )
        data = state.model_dump()
        assert data["message_id"] == "msg-123"
        assert data["primary_intent"] == "order_status"
        assert data["intent_confidence"] == 0.87

        # Round-trip
        state2 = TriageState(**data)
        assert state2.primary_intent == "order_status"

    def test_triage_state_autonomy_level(self):
        """Test autonomy level in state."""
        state = TriageState(
            message_id="msg-123",
            message_text="Test",
            customer_id="cust-123",
            tenant_id="tenant-123",
            conversation_id="conv-001",
            autonomy_level=2,
        )
        assert state.autonomy_level == 2
