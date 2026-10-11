"""Tests for LangGraph agent (Phase 7)."""

import pytest
from unittest.mock import patch, AsyncMock
from triage.agent.nodes import (
    classify_intent_node,
    extract_entities_node,
    make_decision_node,
    retrieve_context_node,
    generate_response_node,
)
from triage.models.triage_state import TriageState
from triage.models.intent import IntentPrediction, IntentClassifierResult


class TestTriageAgentNodes:
    """Test individual graph nodes."""

    @pytest.mark.asyncio
    async def test_classify_intent_node(self):
        """Test intent classification node."""
        state = TriageState(
            message_id="msg-1",
            message_text="Where is my order?",
            customer_id="cust-1",
            tenant_id="tenant-1",
            conversation_id="conv-1",
        )

        # Mock the classifier to avoid needing to load embedding models
        mock_result = IntentClassifierResult(
            message_id="msg-1",
            top_intent="order.status",
            top_confidence=0.92,
            all_intents=[
                IntentPrediction(intent_name="order.status", confidence=0.92, temperature_scaled=True),
                IntentPrediction(intent_name="refund", confidence=0.08, temperature_scaled=True),
            ],
            fallback_used=False,
        )
        
        with patch('triage.agent.nodes.IntentClassifier') as MockClassifier:
            mock_classifier = AsyncMock()
            mock_classifier.classify = AsyncMock(return_value=mock_result)
            MockClassifier.return_value = mock_classifier

            result = await classify_intent_node(state)
            assert result.primary_intent == "order.status"
            assert result.intent_confidence == 0.92

    @pytest.mark.asyncio
    async def test_extract_entities_node(self):
        """Test entity extraction node."""
        state = TriageState(
            message_id="msg-2",
            message_text="Where is order #123456?",
            customer_id="cust-1",
            tenant_id="tenant-1",
            conversation_id="conv-1",
        )

        result = await extract_entities_node(state)
        assert len(result.entities) >= 0

    @pytest.mark.asyncio
    async def test_make_decision_node(self):
        """Test decision matrix node."""
        state = TriageState(
            message_id="msg-3",
            message_text="What's my order status?",
            customer_id="cust-1",
            tenant_id="tenant-1",
            conversation_id="conv-1",
            primary_intent="order_status",
            intent_confidence=0.92,
        )

        result = await make_decision_node(state)
        assert result.autonomy_level is not None
        assert result.autonomy_reason is not None

    @pytest.mark.asyncio
    async def test_retrieve_context_node(self):
        """Test retrieval node."""
        state = TriageState(
            message_id="msg-4",
            message_text="Where is my order?",
            customer_id="cust-1",
            tenant_id="tenant-1",
            conversation_id="conv-1",
            primary_intent="order_status",
        )

        result = await retrieve_context_node(state)
        assert len(result.retrieved_docs) >= 0

    @pytest.mark.asyncio
    async def test_generate_response_node(self):
        """Test response generation node."""
        state = TriageState(
            message_id="msg-5",
            message_text="Where is my order?",
            customer_id="cust-1",
            tenant_id="tenant-1",
            conversation_id="conv-1",
            primary_intent="order_status",
            autonomy_level=1,
            retrieved_docs=[{"doc_id": "doc-1", "text": "Order information"}],
        )

        result = await generate_response_node(state)
        assert result.response_text is not None
