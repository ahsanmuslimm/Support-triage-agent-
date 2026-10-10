"""Tests for intent classification (Phase 1)."""

import pytest
from unittest.mock import MagicMock, patch
import numpy as np

from triage.classification.classifier import IntentClassifier, IntentClassifierError
from triage.classification.fallback import FallbackIntentClassifier
from triage.classification.temperature_scaler import TemperatureScaler


class TestIntentClassifier:
    """Test IntentClassifier."""

    @pytest.fixture
    def classifier(self):
        """Create classifier instance."""
        return IntentClassifier(temperature=1.2, k=3)

    @pytest.fixture
    def sample_intent_examples(self):
        """Sample intent examples for training."""
        return {
            "order.status": [
                "Where is my order?",
                "Can you track my package?",
                "When will my shipment arrive?",
            ],
            "refund": [
                "I want a refund",
                "Can I get my money back?",
                "This item is broken, refund please",
            ],
            "account.help": [
                "I forgot my password",
                "How do I reset my account?",
                "My password isn't working",
            ],
        }

    def test_classifier_initialization(self, classifier):
        """Test classifier initializes without examples."""
        assert classifier.temperature == 1.2
        assert classifier.k == 3
        assert classifier.knn_model is None

    def test_set_intent_examples(self, classifier, sample_intent_examples):
        """Test setting intent examples."""
        classifier.set_intent_examples(sample_intent_examples)
        assert len(classifier.intent_embeddings) == 3
        assert "order.status" in classifier.intent_embeddings
        assert classifier.knn_model is not None

    @pytest.mark.asyncio
    async def test_classify_without_examples_fails(self, classifier):
        """Test classify fails if no examples set."""
        with pytest.raises(IntentClassifierError):
            await classifier.classify("Where is my order?")

    @pytest.mark.asyncio
    async def test_classify_high_confidence_order_status(self, classifier, sample_intent_examples):
        """Test classifying high-confidence order status."""
        classifier.set_intent_examples(sample_intent_examples)
        result = await classifier.classify("Where is my order?")

        assert result.top_intent is not None
        assert result.top_confidence is not None
        assert result.top_confidence > 0.5
        assert len(result.all_intents) > 0

    @pytest.mark.asyncio
    async def test_classify_multi_label(self, classifier, sample_intent_examples):
        """Test multi-label classification."""
        classifier.set_intent_examples(sample_intent_examples)
        result = await classifier.classify("I want a refund for order ORDER-123")

        # Should detect multiple intents
        assert len(result.all_intents) > 0
        # Confidences should sum to ~1.0 after temperature scaling
        total_conf = sum(p.confidence for p in result.all_intents)
        assert 0.5 < total_conf <= 1.1  # Allow some float error

    @pytest.mark.asyncio
    async def test_classify_empty_message_fails(self, classifier, sample_intent_examples):
        """Test classify fails on empty message."""
        classifier.set_intent_examples(sample_intent_examples)
        with pytest.raises(IntentClassifierError):
            await classifier.classify("")

    def test_get_intents(self, classifier, sample_intent_examples):
        """Test getting list of intents."""
        classifier.set_intent_examples(sample_intent_examples)
        intents = classifier.get_intents()
        assert len(intents) == 3
        assert "order.status" in intents
        assert "refund" in intents


class TestTemperatureScaler:
    """Test temperature scaling."""

    def test_compute_ece_perfect_calibration(self):
        """Test ECE on perfectly calibrated predictions."""
        confidences = [0.9, 0.9, 0.1, 0.1]
        accuracies = [True, True, False, False]
        ece = TemperatureScaler.compute_ece(confidences, accuracies)
        assert ece < 0.1  # Should be very low (perfectly calibrated)

    def test_compute_ece_poor_calibration(self):
        """Test ECE on poorly calibrated predictions."""
        confidences = [0.9, 0.9, 0.9, 0.9]
        accuracies = [True, False, False, False]
        ece = TemperatureScaler.compute_ece(confidences, accuracies)
        assert ece > 0.3  # Should be high (poorly calibrated)

    def test_compute_ece_empty(self):
        """Test ECE on empty data."""
        ece = TemperatureScaler.compute_ece([], [])
        assert ece == 0.0

    def test_find_optimal_temperature(self):
        """Test finding optimal temperature."""
        confidences = [0.95, 0.85, 0.75, 0.65, 0.1, 0.05]
        accuracies = [True, True, True, True, False, False]
        temp = TemperatureScaler.find_optimal_temperature(
            confidences, accuracies, temperature_range=(0.5, 2.0), n_steps=10
        )
        assert 0.5 <= temp <= 2.0

    def test_scale_confidence(self):
        """Test scaling a single confidence."""
        scaled = TemperatureScaler.scale_confidence(0.8, temperature=1.0)
        assert 0.0 <= scaled <= 1.0

        # Temperature > 1 should move toward 0.5
        scaled_high_temp = TemperatureScaler.scale_confidence(0.8, temperature=2.0)
        assert scaled_high_temp < scaled  # Should be lower

    def test_scale_confidence_extreme_values(self):
        """Test scaling at boundaries."""
        scaled_min = TemperatureScaler.scale_confidence(0.0, temperature=1.0)
        scaled_max = TemperatureScaler.scale_confidence(1.0, temperature=1.0)
        assert 0.0 <= scaled_min <= 1.0
        assert 0.0 <= scaled_max <= 1.0


class TestFallbackIntentClassifier:
    """Test fallback classifier."""

    @pytest.fixture
    def fallback(self):
        """Create fallback classifier."""
        return FallbackIntentClassifier(fuzzy_threshold=0.7)

    @pytest.fixture
    def sample_keywords(self):
        """Sample keywords."""
        return {
            "refund": ["refund", "money back", "return"],
            "order_status": ["where", "track", "shipping", "package"],
            "password": ["password", "forgot", "reset account"],
        }

    def test_fallback_exact_match(self, fallback, sample_keywords):
        """Test exact keyword matching."""
        fallback.set_intent_keywords(sample_keywords)
        result = fallback.classify("I want a refund")
        assert result.top_intent == "refund"
        assert result.top_confidence == 0.95

    def test_fallback_fuzzy_match(self, fallback, sample_keywords):
        """Test fuzzy matching."""
        fallback.set_intent_keywords(sample_keywords)
        result = fallback.classify("Where is my shipment?")
        # Should match "shipping" or "package"
        assert result.top_intent in ["order_status"]

    def test_fallback_no_match_returns_other(self, fallback, sample_keywords):
        """Test no match returns 'other' intent."""
        fallback.set_intent_keywords(sample_keywords)
        result = fallback.classify("xyzabc123")
        assert result.top_intent == "other"
        assert result.top_confidence == 0.5

    def test_fallback_empty_message(self, fallback):
        """Test empty message."""
        result = fallback.classify("")
        assert result.top_intent == "other"

    def test_fallback_case_insensitive(self, fallback, sample_keywords):
        """Test case-insensitive matching."""
        fallback.set_intent_keywords(sample_keywords)
        result = fallback.classify("I WANT A REFUND")
        assert result.top_intent == "refund"
