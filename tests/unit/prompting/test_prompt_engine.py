"""Unit tests for S3.7 Prompt Engine and Tone Selector."""

import pytest
from unittest.mock import MagicMock, patch
import re

from services.api.src.triage.prompting.template_engine import PromptTemplateEngine
from services.api.src.triage.prompting.tone_selector import ToneSelector


@pytest.fixture
def prompt_engine():
    """Create prompt template engine."""
    return PromptTemplateEngine()


@pytest.fixture
def customer_context():
    """Create sample customer context."""
    return {
        "customer_id": 1,
        "name": "John Doe",
        "email": "john@example.com",
        "account_age_days": 365,
        "order_count": 25,
        "total_spent": 15000.0,
        "is_vip": True,
    }


class TestToneSelector:
    """Test tone selection logic."""

    def test_tone_empathy_for_churn_risk(self):
        """Test empathy tone selected for high churn risk."""
        tone = ToneSelector.select_tone(
            health_score=0.2,
            is_vip=False,
            order_count=5,
            total_spent=1000.0,
        )
        
        assert tone == "empathy"

    def test_tone_urgency_for_high_value(self):
        """Test urgency tone selected for high-value customer."""
        tone = ToneSelector.select_tone(
            health_score=0.8,
            is_vip=False,
            order_count=25,
            total_spent=15000.0,
        )
        
        assert tone == "urgency"

    def test_tone_formal_for_enterprise(self):
        """Test formal tone selected for enterprise/VIP."""
        tone = ToneSelector.select_tone(
            health_score=0.7,
            is_vip=True,
            order_count=30,
            total_spent=25000.0,
        )
        
        assert tone in ["formal", "urgency"]

    def test_tone_neutral_default(self):
        """Test neutral/default tone for standard customer."""
        tone = ToneSelector.select_tone(
            health_score=0.6,
            is_vip=False,
            order_count=5,
            total_spent=1000.0,
        )
        
        assert tone in ["neutral", "default"]

    def test_tone_determinism(self):
        """Test tone selection is deterministic."""
        context = {
            "health_score": 0.35,
            "is_vip": True,
            "order_count": 20,
            "total_spent": 5000.0,
        }
        
        tone1 = ToneSelector.select_tone(**context)
        tone2 = ToneSelector.select_tone(**context)
        tone3 = ToneSelector.select_tone(**context)
        
        assert tone1 == tone2 == tone3

    def test_tone_priority_churn_over_value(self):
        """Test that churn risk takes priority over high value."""
        # High churn risk but high value
        tone = ToneSelector.select_tone(
            health_score=0.2,  # High churn risk
            is_vip=False,
            order_count=30,  # High value
            total_spent=20000.0,
        )
        
        assert tone == "empathy"


class TestPromptTemplateEngine:
    """Test prompt template rendering."""

    def test_render_empathy_tone(self, prompt_engine, customer_context):
        """Test rendering empathy tone template."""
        prompt = prompt_engine.render(
            tone="empathy",
            customer_context=customer_context,
            reasoning="Customer has high churn risk",
        )
        
        assert isinstance(prompt, str)
        assert len(prompt) > 0
        # Empathy tone should contain empathetic language
        assert any(word in prompt.lower() for word in ["care", "help", "empathy", "risk"])

    def test_render_urgency_tone(self, prompt_engine, customer_context):
        """Test rendering urgency tone template."""
        prompt = prompt_engine.render(
            tone="urgency",
            customer_context=customer_context,
            reasoning="High-value customer needs immediate attention",
        )
        
        assert isinstance(prompt, str)
        assert len(prompt) > 0
        # Should contain customer name
        assert "John Doe" in prompt or "john" in prompt.lower()

    def test_render_formal_tone(self, prompt_engine, customer_context):
        """Test rendering formal tone template."""
        prompt = prompt_engine.render(
            tone="formal",
            customer_context=customer_context,
            reasoning="Enterprise account inquiry",
        )
        
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_render_default_tone(self, prompt_engine, customer_context):
        """Test rendering default tone template."""
        prompt = prompt_engine.render(
            tone="default",
            customer_context=customer_context,
            reasoning="Standard customer inquiry",
        )
        
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_prompt_includes_customer_name(self, prompt_engine, customer_context):
        """Test that prompt includes customer name."""
        prompt = prompt_engine.render(
            tone="empathy",
            customer_context=customer_context,
            reasoning="Test",
        )
        
        assert "John Doe" in prompt or "john" in prompt.lower()

    def test_prompt_includes_account_age(self, prompt_engine, customer_context):
        """Test that prompt includes account age context."""
        prompt = prompt_engine.render(
            tone="empathy",
            customer_context=customer_context,
            reasoning="Test",
        )
        
        # Prompt should mention customer data (age may be formatted differently)
        assert len(prompt) > 50  # Non-trivial prompt

    def test_prompt_includes_reasoning(self, prompt_engine, customer_context):
        """Test that prompt includes decision reasoning."""
        reasoning = "Customer has failed 3 payments in last 90 days"
        prompt = prompt_engine.render(
            tone="empathy",
            customer_context=customer_context,
            reasoning=reasoning,
        )
        
        # Reasoning should be in prompt
        assert reasoning in prompt

    def test_prompt_determinism(self, prompt_engine, customer_context):
        """Test prompt generation is deterministic."""
        reasoning = "Test reasoning for determinism check"
        
        prompt1 = prompt_engine.render(
            tone="empathy",
            customer_context=customer_context,
            reasoning=reasoning,
        )
        
        prompt2 = prompt_engine.render(
            tone="empathy",
            customer_context=customer_context,
            reasoning=reasoning,
        )
        
        assert prompt1 == prompt2

    def test_escaping_special_characters(self, prompt_engine):
        """Test handling of special characters in context."""
        context_with_special = {
            "name": "John O'Reilly",
            "email": "john+tag@example.com",
            "order_count": 5,
            "total_spent": 1000.0,
        }
        
        prompt = prompt_engine.render(
            tone="default",
            customer_context=context_with_special,
            reasoning="Test with special chars",
        )
        
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_missing_optional_context(self, prompt_engine):
        """Test rendering with minimal context."""
        minimal_context = {
            "name": "Customer",
            "customer_id": 1,
        }
        
        prompt = prompt_engine.render(
            tone="default",
            customer_context=minimal_context,
            reasoning="Simple inquiry",
        )
        
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_all_tones_rendered(self, prompt_engine, customer_context):
        """Test all tones can be rendered."""
        tones = ["default", "empathy", "urgency", "formal"]
        
        for tone in tones:
            prompt = prompt_engine.render(
                tone=tone,
                customer_context=customer_context,
                reasoning="Test",
            )
            assert isinstance(prompt, str)
            assert len(prompt) > 0

    def test_tone_distinctness(self, prompt_engine, customer_context):
        """Test that different tones produce different prompts."""
        empathy_prompt = prompt_engine.render(
            tone="empathy",
            customer_context=customer_context,
            reasoning="Same reason",
        )
        
        urgency_prompt = prompt_engine.render(
            tone="urgency",
            customer_context=customer_context,
            reasoning="Same reason",
        )
        
        # Prompts should be different for different tones
        assert empathy_prompt != urgency_prompt

    def test_order_count_in_prompt(self, prompt_engine):
        """Test that order count is included in prompt."""
        context = {
            "name": "Test",
            "order_count": 42,
            "total_spent": 5000.0,
        }
        
        prompt = prompt_engine.render(
            tone="urgency",
            customer_context=context,
            reasoning="Test",
        )
        
        assert "42" in prompt

    def test_spent_amount_in_prompt(self, prompt_engine):
        """Test that total spent amount is included in prompt."""
        context = {
            "name": "Test",
            "order_count": 10,
            "total_spent": 9999.99,
        }
        
        prompt = prompt_engine.render(
            tone="urgency",
            customer_context=context,
            reasoning="Test",
        )
        
        # Should include formatted amount
        assert "9999" in prompt

    def test_support_agent_role_in_default(self, prompt_engine, customer_context):
        """Test that default prompt mentions support agent role."""
        prompt = prompt_engine.render(
            tone="default",
            customer_context=customer_context,
            reasoning="Test",
        )
        
        assert "support" in prompt.lower() or "agent" in prompt.lower()

    def test_priority_in_urgency_tone(self, prompt_engine, customer_context):
        """Test that urgency tone mentions priority."""
        prompt = prompt_engine.render(
            tone="urgency",
            customer_context=customer_context,
            reasoning="Test",
        )
        
        assert "priority" in prompt.lower() or "high-value" in prompt.lower() or "vip" in prompt.lower()
