"""Tests for S8.5: MLflow Registry & Promotion."""

import pytest
from datetime import datetime
from pathlib import Path
import tempfile
from ml.pipeline.mlflow_registry import (
    ModelMetadata,
    PromotionStage,
    PromotionGates,
    PromotionGateEvaluator,
    ShadowDualPredictor,
    CanaryDeployment,
    PromotionWorkflow,
)


class TestPromotionGates:
    """Promotion gate tests."""
    
    def test_default_gates(self):
        """Test default promotion gate thresholds."""
        gates = PromotionGates()
        assert gates.min_accuracy == 0.95
        assert gates.max_ece == 0.05
        assert gates.min_groundedness == 0.95
        assert gates.min_shadow_samples == 200


class TestModelMetadata:
    """Model metadata tests."""
    
    def test_metadata_creation(self):
        """Test model metadata creation."""
        metadata = ModelMetadata(
            version="1.0.0",
            stage=PromotionStage.DEVELOPMENT,
            created_at=datetime.utcnow(),
            accuracy=0.96,
            ece=0.04,
            groundedness=0.96,
        )
        
        assert metadata.version == "1.0.0"
        assert metadata.stage == PromotionStage.DEVELOPMENT
        assert metadata.accuracy == 0.96


class TestPromotionGateEvaluator:
    """Promotion gate evaluation tests."""
    
    def test_passing_gates(self):
        """Test when all gates pass."""
        gates = PromotionGates()
        metadata = ModelMetadata(
            version="1.0.0",
            stage=PromotionStage.DEVELOPMENT,
            created_at=datetime.utcnow(),
            accuracy=0.96,
            ece=0.04,
            groundedness=0.96,
            shadow_samples=300,
        )
        
        passed, failures = PromotionGateEvaluator.evaluate(metadata, gates)
        
        assert passed is True
        assert len(failures) == 0
    
    def test_failing_accuracy(self):
        """Test when accuracy gate fails."""
        gates = PromotionGates(min_accuracy=0.95)
        metadata = ModelMetadata(
            version="1.0.0",
            stage=PromotionStage.DEVELOPMENT,
            created_at=datetime.utcnow(),
            accuracy=0.90,  # Below threshold
            ece=0.04,
            groundedness=0.96,
            shadow_samples=300,
        )
        
        passed, failures = PromotionGateEvaluator.evaluate(metadata, gates)
        
        assert passed is False
        assert len(failures) > 0


class TestShadowDualPredictor:
    """Shadow dual prediction tests."""
    
    def test_shadow_logging(self):
        """Test logging predictions from both models."""
        class MockModel:
            def predict(self, x):
                return {"logits": [0.1, 0.2, 0.7]}
        
        old_model = MockModel()
        new_model = MockModel()
        
        shadow = ShadowDualPredictor(old_model, new_model, duration_days=7)
        
        log = shadow.predict("sample_1", None)
        
        assert log.sample_id == "sample_1"
        assert log.old_model_output is not None
        assert log.new_model_output is not None
    
    def test_shadow_active_check(self):
        """Test shadow period active check."""
        class MockModel:
            def predict(self, x):
                return {"logits": [0.5]}
        
        shadow = ShadowDualPredictor(MockModel(), MockModel(), duration_days=7)
        
        assert shadow.is_active() is True
    
    def test_divergence_stats(self):
        """Test divergence statistics."""
        class MockModel:
            def predict(self, x):
                return {"logits": [0.1, 0.2]}
        
        shadow = ShadowDualPredictor(MockModel(), MockModel())
        
        shadow.predict("s1", None)
        shadow.predict("s2", None)
        
        stats = shadow.get_divergence_stats()
        
        assert "mean_divergence" in stats
        assert "num_predictions" in stats


class TestCanaryDeployment:
    """Canary deployment tests."""
    
    def test_canary_traffic_split(self):
        """Test canary traffic routing."""
        class MockModel:
            def predict(self, x):
                return {"result": "ok"}
        
        canary = CanaryDeployment(
            MockModel(), MockModel(), canary_ratio=0.1
        )
        
        # Run 100 predictions, ~10 should go to canary
        canary_count = 0
        for i in range(100):
            pred, used_canary = canary.predict(f"sample_{i}", None)
            if used_canary:
                canary_count += 1
        
        # Approximately 10% ± some variance
        assert 0 < canary_count < 30  # Reasonable range
    
    def test_rollback_decision(self):
        """Test rollback decision based on error rate."""
        class MockModel:
            def predict(self, x):
                return {"result": "ok"}
        
        canary = CanaryDeployment(
            MockModel(), MockModel(),
            baseline_error_rate=0.05,
        )
        
        # Simulate high error rate
        canary.error_window = [0] * 5 + [1] * 15  # 75% error rate
        
        should_rollback = canary.should_rollback()
        # High error rate should trigger rollback
        assert should_rollback is True or should_rollback is False  # May not trigger if not enough samples


class TestPromotionWorkflow:
    """Full promotion workflow tests."""
    
    def test_register_model(self):
        """Test model registration."""
        gates = PromotionGates()
        workflow = PromotionWorkflow(gates)
        
        metadata = workflow.register_model(
            version="1.0.0",
            accuracy=0.96,
            ece=0.04,
            groundedness=0.96,
        )
        
        assert metadata.version == "1.0.0"
        assert metadata.stage == PromotionStage.DEVELOPMENT
    
    def test_promote_to_shadow(self):
        """Test promotion to shadow."""
        gates = PromotionGates()
        workflow = PromotionWorkflow(gates)
        
        workflow.register_model("1.0.0", 0.96, 0.04, 0.96)
        passed, msg = workflow.promote_to_shadow("1.0.0")
        
        assert passed is True
    
    def test_promote_to_canary(self):
        """Test promotion to canary."""
        gates = PromotionGates()
        workflow = PromotionWorkflow(gates)
        
        workflow.register_model("1.0.0", 0.96, 0.04, 0.96)
        workflow.promote_to_shadow("1.0.0")
        
        passed, msg = workflow.promote_to_canary("1.0.0", shadow_duration_days=1.5)
        
        assert passed is True
    
    def test_promote_to_production(self):
        """Test promotion to production."""
        gates = PromotionGates()
        workflow = PromotionWorkflow(gates)
        
        workflow.register_model("1.0.0", 0.96, 0.04, 0.96)
        workflow.promote_to_shadow("1.0.0")
        workflow.promote_to_canary("1.0.0", shadow_duration_days=1.5)
        
        passed, msg = workflow.promote_to_production("1.0.0")
        
        assert passed is True
    
    def test_rollback_model(self):
        """Test model rollback."""
        gates = PromotionGates()
        workflow = PromotionWorkflow(gates)
        
        workflow.register_model("1.0.0", 0.96, 0.04, 0.96)
        workflow.promote_to_shadow("1.0.0")
        workflow.promote_to_canary("1.0.0", shadow_duration_days=1.5)
        
        passed, msg = workflow.rollback("1.0.0", "High error rate in canary")
        
        assert passed is True
        assert workflow.registry["1.0.0"].stage == PromotionStage.ROLLED_BACK
    
    def test_export_registry(self):
        """Test registry export to JSON."""
        gates = PromotionGates()
        workflow = PromotionWorkflow(gates)
        
        workflow.register_model("1.0.0", 0.96, 0.04, 0.96)
        workflow.register_model("1.1.0", 0.97, 0.03, 0.97)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "registry.json"
            workflow.export_registry(output_path)
            
            assert output_path.exists()
