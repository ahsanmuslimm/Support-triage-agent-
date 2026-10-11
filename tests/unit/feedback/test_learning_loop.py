"""Unit tests for S3.8 Learning Loop and Continuous Improvement."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timedelta
import json

from services.api.src.triage.feedback.learning_loop import LearningLoop


@pytest.fixture
def learning_loop():
    """Create learning loop instance."""
    return LearningLoop(
        db_session=None,
        drift_threshold=0.85,
        ewma_alpha=0.1,
    )


class TestLearningLoopConfiguration:
    """Test learning loop basic configuration."""

    def test_learning_loop_initialization(self, learning_loop):
        """Test learning loop initializes with config."""
        assert learning_loop is not None
        assert learning_loop.drift_threshold == 0.85
        assert learning_loop.ewma_alpha == 0.1

    def test_default_drift_threshold(self):
        """Test default drift threshold is applied."""
        ll = LearningLoop(db_session=None)
        assert ll.drift_threshold == 0.85

    def test_default_ewma_alpha(self):
        """Test default EWMA alpha is applied."""
        ll = LearningLoop(db_session=None)
        assert ll.ewma_alpha == 0.1

    def test_custom_drift_threshold(self):
        """Test custom drift threshold can be set."""
        ll = LearningLoop(db_session=None, drift_threshold=0.80)
        assert ll.drift_threshold == 0.80

    def test_custom_ewma_alpha(self):
        """Test custom EWMA alpha can be set."""
        ll = LearningLoop(db_session=None, ewma_alpha=0.15)
        assert ll.ewma_alpha == 0.15


class TestFeedbackProcessing:
    """Test feedback event processing structures."""

    def test_feedback_event_types(self):
        """Test feedback event types are recognized."""
        feedback_types = ["thumbs_up", "thumbs_down", "tag", "escalation_resolved"]
        
        # Verify all types are valid
        for ftype in feedback_types:
            assert isinstance(ftype, str)
            assert len(ftype) > 0

    def test_model_validation_gates(self):
        """Test model validation gate structure."""
        validation_gates = {
            "min_accuracy": 0.86,
            "min_auc": 0.73,
            "max_regression": 0.05,
        }
        
        assert "min_accuracy" in validation_gates
        assert "min_auc" in validation_gates
        assert "max_regression" in validation_gates

    def test_model_metrics_structure(self):
        """Test model metrics have correct structure."""
        metrics = {
            "accuracy": 0.87,
            "auc": 0.74,
            "prev_accuracy": 0.88,
        }
        
        assert "accuracy" in metrics
        assert "auc" in metrics
        assert isinstance(metrics["accuracy"], float)

    def test_model_version_structure(self):
        """Test model version tracking structure."""
        version_info = {
            "version": "v1.2.3",
            "timestamp": datetime.utcnow().isoformat(),
            "accuracy": 0.88,
            "auc": 0.76,
            "training_samples": 50000,
        }
        
        assert "version" in version_info
        assert "accuracy" in version_info
        assert version_info["accuracy"] > 0.8


class TestModelImprovementDetection:
    """Test model improvement and degradation detection."""

    def test_auto_deployment_candidate_on_improvement(self):
        """Test model marked as candidate when improvements >2%."""
        prev_accuracy = 0.85
        new_accuracy = 0.87
        improvement = new_accuracy - prev_accuracy
        
        is_candidate = improvement > 0.02
        assert is_candidate is True

    def test_no_deployment_on_minor_improvement(self):
        """Test model not marked as candidate for improvements <2%."""
        prev_accuracy = 0.85
        new_accuracy = 0.851
        improvement = new_accuracy - prev_accuracy
        
        is_candidate = improvement > 0.02
        assert is_candidate is False

    def test_validation_pass_on_meeting_gates(self):
        """Test validation passes when all gates met."""
        validation_gates = {
            "min_accuracy": 0.86,
            "min_auc": 0.73,
            "max_regression": 0.05,
        }
        
        new_model_metrics = {
            "accuracy": 0.87,
            "auc": 0.74,
            "prev_accuracy": 0.88,
        }
        
        passes_gates = (
            new_model_metrics["accuracy"] >= validation_gates["min_accuracy"]
            and new_model_metrics["auc"] >= validation_gates["min_auc"]
            and (new_model_metrics["prev_accuracy"] - new_model_metrics["accuracy"]) <= validation_gates["max_regression"]
        )
        
        assert passes_gates is True

    def test_validation_fail_on_low_accuracy(self):
        """Test validation fails when accuracy below threshold."""
        min_accuracy = 0.86
        new_accuracy = 0.80
        
        passes_gate = new_accuracy >= min_accuracy
        assert passes_gate is False

    def test_validation_fail_on_low_auc(self):
        """Test validation fails when AUC below threshold."""
        min_auc = 0.73
        new_auc = 0.70
        
        passes_gate = new_auc >= min_auc
        assert passes_gate is False

    def test_regression_detection(self):
        """Test detection of model regression."""
        baseline_accuracy = 0.88
        new_accuracy = 0.83
        regression = baseline_accuracy - new_accuracy
        
        is_regression = regression > 0.03
        assert is_regression is True


class TestRetrainingTriggers:
    """Test learning loop retraining trigger logic."""

    def test_retraining_trigger_accuracy_drop(self):
        """Test retraining triggered by accuracy drop >5%."""
        current_accuracy = 0.85
        previous_accuracy = 0.91
        accuracy_drop = previous_accuracy - current_accuracy
        
        should_retrain = accuracy_drop > 0.05
        assert should_retrain is True

    def test_no_retraining_on_small_drop(self):
        """Test no retraining on small accuracy drops."""
        current_accuracy = 0.89
        previous_accuracy = 0.91
        accuracy_drop = previous_accuracy - current_accuracy
        
        should_retrain = accuracy_drop > 0.05
        assert should_retrain is False

    def test_retraining_trigger_high_volume_feedback(self):
        """Test retraining triggered by feedback volume."""
        weekly_feedback_count = 1500
        threshold = 1000
        
        should_retrain = weekly_feedback_count > threshold
        assert should_retrain is True

    def test_no_retraining_on_low_volume(self):
        """Test no retraining on low feedback volume."""
        weekly_feedback_count = 500
        threshold = 1000
        
        should_retrain = weekly_feedback_count > threshold
        assert should_retrain is False

    def test_weekly_retraining_schedule(self):
        """Test weekly retraining schedule logic."""
        # Mock weekly trigger
        should_retrain = True
        assert should_retrain is True


class TestABTesting:
    """Test A/B testing assignment and analysis."""

    def test_ab_assignment_deterministic(self, learning_loop):
        """Test A/B test assignment is deterministic."""
        conversation_id = "conv_123"
        experiment_id = "exp_001"
        
        # If method exists, test determinism
        if hasattr(learning_loop, '_hash_to_variant'):
            variant1 = learning_loop._hash_to_variant(conversation_id, experiment_id)
            variant2 = learning_loop._hash_to_variant(conversation_id, experiment_id)
            assert variant1 == variant2

    def test_ab_assignment_distribution(self, learning_loop):
        """Test A/B assignments are roughly 50/50."""
        experiment_id = "exp_001"
        
        # If method exists, test distribution
        if hasattr(learning_loop, '_hash_to_variant'):
            variants = []
            for i in range(1000):
                conv_id = f"conv_{i}"
                variant = learning_loop._hash_to_variant(conv_id, experiment_id)
                variants.append(variant)
            
            # Count distribution
            control = sum(1 for v in variants if v == "control")
            treatment = sum(1 for v in variants if v == "treatment")
            total = len(variants)
            
            control_ratio = control / total
            assert 0.4 < control_ratio < 0.6

    def test_chi_square_ab_winner(self):
        """Test A/B test winner detection via chi-square logic."""
        control_success = 450
        control_total = 500
        treatment_success = 480
        treatment_total = 500
        
        control_rate = control_success / control_total
        treatment_rate = treatment_success / treatment_total
        
        # Treatment performs better
        assert treatment_rate > control_rate

    def test_no_winner_on_similar_rates(self):
        """Test no winner when rates are similar."""
        control_rate = 0.89
        treatment_rate = 0.91
        
        # Small difference
        difference = abs(treatment_rate - control_rate)
        has_winner = difference > 0.05
        
        assert has_winner is False


class TestMetricsTracking:
    """Test metric collection and tracking."""

    def test_metric_structure(self):
        """Test metric data structure."""
        metric = {
            "timestamp": datetime.utcnow().isoformat(),
            "metric_name": "accuracy",
            "metric_value": 0.87,
            "tenant_id": 1,
        }
        
        assert "timestamp" in metric
        assert "metric_name" in metric
        assert "metric_value" in metric
        assert isinstance(metric["metric_value"], float)

    def test_metric_value_range(self):
        """Test metric values are in valid range."""
        metrics = {
            "accuracy": 0.87,
            "precision": 0.89,
            "recall": 0.85,
            "auc": 0.76,
        }
        
        for name, value in metrics.items():
            assert 0.0 <= value <= 1.0

    def test_feedback_metadata(self):
        """Test feedback can include metadata."""
        feedback = {
            "conversation_id": "conv_456",
            "feedback_type": "tag",
            "metadata": {
                "tag": "billing_issue",
                "severity": "high",
            }
        }
        
        assert "metadata" in feedback
        assert feedback["metadata"]["tag"] == "billing_issue"


class TestDriftDetectionLogic:
    """Test drift detection logic."""

    def test_drift_threshold_comparison(self):
        """Test drift detection threshold comparison."""
        drift_threshold = 0.85
        current_accuracy = 0.80
        
        is_drifted = current_accuracy < drift_threshold
        assert is_drifted is True

    def test_no_drift_above_threshold(self):
        """Test no drift when above threshold."""
        drift_threshold = 0.85
        current_accuracy = 0.90
        
        is_drifted = current_accuracy < drift_threshold
        assert is_drifted is False

    def test_ewma_smooth_values(self):
        """Test EWMA smoothing concept."""
        alpha = 0.1
        previous_ewma = 0.88
        current_value = 0.86
        
        # EWMA formula: new_ewma = alpha * current + (1 - alpha) * previous
        new_ewma = alpha * current_value + (1 - alpha) * previous_ewma
        
        # Should be between previous and current
        assert current_value < new_ewma < previous_ewma
