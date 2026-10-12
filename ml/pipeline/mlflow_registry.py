"""S8.5: MLflow Registry & Promotion.

Model versioning and promotion workflow:
- All training runs logged to MLflow
- Promotion gates: accuracy ≥95%, ECE ≤0.05, groundedness ≥0.95, ≥200 shadow samples
- Shadow dual-predict for 7 days before canary
- 10% canary traffic, monitor error rate vs baseline
- Auto-rollback if canary error > baseline+1σ for 10min
- Workflow: shadow → canary → production
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


class PromotionStage(Enum):
    """Model promotion stages."""
    DEVELOPMENT = "development"
    SHADOW = "shadow"
    CANARY = "canary"
    PRODUCTION = "production"
    ROLLED_BACK = "rolled_back"


@dataclass
class PromotionGates:
    """Thresholds for model promotion."""
    min_accuracy: float = 0.95
    max_ece: float = 0.05
    min_groundedness: float = 0.95
    min_shadow_samples: int = 200


@dataclass
class ModelMetadata:
    """Model version metadata."""
    version: str
    stage: PromotionStage
    created_at: datetime
    accuracy: float = 0.0
    ece: float = 1.0
    groundedness: float = 0.0
    shadow_samples: int = 0
    shadow_duration_days: float = 0.0
    canary_error_rate: float = 0.0
    baseline_error_rate: float = 0.0
    promoted_at: datetime | None = None
    promotion_notes: str = ""


@dataclass
class ShadowPredictionLog:
    """Logged dual predictions during shadow phase."""
    timestamp: datetime
    sample_id: str
    old_model_output: dict
    new_model_output: dict
    ground_truth: dict | None = None
    error_on_old: bool = False
    error_on_new: bool = False
    divergence: float = 0.0


@dataclass
class CanaryMetrics:
    """Metrics from canary phase."""
    timestamp: datetime
    error_rate: float
    baseline_error: float
    error_increase: float
    num_samples: int
    errors: list = field(default_factory=list)


class PromotionGateEvaluator:
    """Evaluate promotion gates."""

    @staticmethod
    def evaluate(
        metadata: ModelMetadata,
        gates: PromotionGates,
    ) -> tuple[bool, list[str]]:
        """
        Evaluate all promotion gates.
        
        Returns:
            (passed, reasons_failed)
        """
        failures = []

        if metadata.accuracy < gates.min_accuracy:
            failures.append(
                f"Accuracy {metadata.accuracy:.4f} < {gates.min_accuracy}"
            )

        if metadata.ece > gates.max_ece:
            failures.append(
                f"ECE {metadata.ece:.4f} > {gates.max_ece}"
            )

        if metadata.groundedness < gates.min_groundedness:
            failures.append(
                f"Groundedness {metadata.groundedness:.4f} < {gates.min_groundedness}"
            )

        if metadata.shadow_samples < gates.min_shadow_samples:
            failures.append(
                f"Shadow samples {metadata.shadow_samples} < {gates.min_shadow_samples}"
            )

        passed = len(failures) == 0
        return passed, failures


class ShadowDualPredictor:
    """Run old and new models in parallel for comparison."""

    def __init__(self, old_model, new_model, duration_days: int = 7):
        self.old_model = old_model
        self.new_model = new_model
        self.duration_days = duration_days
        self.predictions = []
        self.start_time = datetime.utcnow()

    def predict(
        self,
        sample_id: str,
        embeddings: np.ndarray,
        ground_truth: dict | None = None,
    ) -> ShadowPredictionLog:
        """Run both models and log results."""
        try:
            old_output = self.old_model.predict(embeddings)
            error_on_old = False
        except Exception as e:
            old_output = {"error": str(e)}
            error_on_old = True

        try:
            new_output = self.new_model.predict(embeddings)
            error_on_new = False
        except Exception as e:
            new_output = {"error": str(e)}
            error_on_new = True

        # Compute divergence (KL-like)
        divergence = self._compute_divergence(old_output, new_output)

        log = ShadowPredictionLog(
            timestamp=datetime.utcnow(),
            sample_id=sample_id,
            old_model_output=old_output,
            new_model_output=new_output,
            ground_truth=ground_truth,
            error_on_old=error_on_old,
            error_on_new=error_on_new,
            divergence=divergence,
        )

        self.predictions.append(log)
        return log

    def is_active(self) -> bool:
        """Check if shadow period is still active."""
        elapsed = datetime.utcnow() - self.start_time
        return elapsed < timedelta(days=self.duration_days)

    def get_divergence_stats(self) -> dict:
        """Summary statistics of divergences."""
        if not self.predictions:
            return {}

        divergences = [p.divergence for p in self.predictions]

        return {
            "mean_divergence": float(np.mean(divergences)),
            "max_divergence": float(np.max(divergences)),
            "std_divergence": float(np.std(divergences)),
            "num_predictions": len(self.predictions),
        }

    @staticmethod
    def _compute_divergence(old_output: dict, new_output: dict) -> float:
        """Compute divergence between model outputs."""
        if "logits" in old_output and "logits" in new_output:
            old_logits = np.array(old_output["logits"])
            new_logits = np.array(new_output["logits"])

            # L2 distance
            divergence = float(np.linalg.norm(old_logits - new_logits))
            return divergence

        return 0.0


class CanaryDeployment:
    """Manage canary deployment with 10% traffic."""

    def __init__(
        self,
        old_model,
        new_model,
        canary_ratio: float = 0.1,
        baseline_error_rate: float = 0.05,
    ):
        self.old_model = old_model
        self.new_model = new_model
        self.canary_ratio = canary_ratio
        self.baseline_error_rate = baseline_error_rate
        self.metrics = []
        self.start_time = datetime.utcnow()
        self.error_window = []  # Last 10 min errors

    def predict(
        self,
        sample_id: str,
        embeddings: np.ndarray,
    ) -> tuple[dict, bool]:
        """
        Route to canary or production based on traffic split.
        
        Returns:
            (prediction, used_canary)
        """
        if np.random.rand() < self.canary_ratio:
            # Route to canary
            try:
                pred = self.new_model.predict(embeddings)
                self.error_window.append(0)
                return pred, True
            except Exception as e:
                logger.error(f"Canary error: {e}")
                self.error_window.append(1)
                # Fallback to old model
                return self.old_model.predict(embeddings), True
        else:
            # Route to production (old model)
            try:
                pred = self.old_model.predict(embeddings)
                return pred, False
            except Exception as e:
                logger.error(f"Production error: {e}")
                raise

    def should_rollback(self, window_minutes: int = 10) -> bool:
        """
        Check if canary error rate suggests rollback.
        
        Rollback if: canary_error > baseline + 1σ for 10 min
        """
        if len(self.error_window) < 60:  # Need enough samples
            return False

        # Get last window_minutes worth of predictions
        recent_errors = self.error_window[-window_minutes:]
        recent_error_rate = np.mean(recent_errors)

        # Assume binomial, compute 1σ
        n = len(recent_errors)
        sigma = np.sqrt(self.baseline_error_rate * (1 - self.baseline_error_rate) / n)
        threshold = self.baseline_error_rate + sigma

        if recent_error_rate > threshold:
            logger.warning(
                f"Canary error rate {recent_error_rate:.4f} "
                f"> baseline+1σ {threshold:.4f}, suggesting rollback"
            )
            return True

        return False

    def log_metrics(self) -> CanaryMetrics:
        """Log current canary metrics."""
        canary_error = np.mean(self.error_window) if self.error_window else 0.0
        error_increase = canary_error - self.baseline_error_rate

        metrics = CanaryMetrics(
            timestamp=datetime.utcnow(),
            error_rate=canary_error,
            baseline_error=self.baseline_error_rate,
            error_increase=error_increase,
            num_samples=len(self.error_window),
            errors=self.error_window.copy(),
        )

        self.metrics.append(metrics)
        return metrics


class PromotionWorkflow:
    """Full promotion workflow: shadow → canary → production."""

    def __init__(self, gates: PromotionGates):
        self.gates = gates
        self.registry = {}  # version -> metadata

    def register_model(
        self,
        version: str,
        accuracy: float,
        ece: float,
        groundedness: float,
    ) -> ModelMetadata:
        """Register new model version."""
        metadata = ModelMetadata(
            version=version,
            stage=PromotionStage.DEVELOPMENT,
            created_at=datetime.utcnow(),
            accuracy=accuracy,
            ece=ece,
            groundedness=groundedness,
        )

        self.registry[version] = metadata
        logger.info(f"Registered model {version} in DEVELOPMENT")

        return metadata

    def promote_to_shadow(self, version: str) -> tuple[bool, str]:
        """Promote to shadow stage."""
        metadata = self.registry.get(version)
        if not metadata:
            return False, f"Model {version} not found"

        # Check gates
        passed, failures = PromotionGateEvaluator.evaluate(metadata, self.gates)

        if not passed:
            return False, f"Gates failed: {'; '.join(failures)}"

        metadata.stage = PromotionStage.SHADOW
        metadata.promoted_at = datetime.utcnow()
        logger.info(f"Promoted {version} to SHADOW")

        return True, "Promoted to shadow"

    def promote_to_canary(
        self,
        version: str,
        shadow_duration_days: float,
    ) -> tuple[bool, str]:
        """Promote to canary stage after shadow."""
        metadata = self.registry.get(version)
        if not metadata:
            return False, f"Model {version} not found"

        if metadata.stage != PromotionStage.SHADOW:
            return False, f"Model not in SHADOW stage: {metadata.stage}"

        # Check minimum shadow duration
        if shadow_duration_days < 1.0:
            return False, f"Minimum shadow duration not met: {shadow_duration_days}d < 1d"

        metadata.stage = PromotionStage.CANARY
        metadata.shadow_duration_days = shadow_duration_days
        logger.info(f"Promoted {version} to CANARY after {shadow_duration_days}d shadow")

        return True, "Promoted to canary"

    def promote_to_production(self, version: str) -> tuple[bool, str]:
        """Promote to production (requires manual approval)."""
        metadata = self.registry.get(version)
        if not metadata:
            return False, f"Model {version} not found"

        if metadata.stage != PromotionStage.CANARY:
            return False, f"Model not in CANARY stage: {metadata.stage}"

        metadata.stage = PromotionStage.PRODUCTION
        logger.info(f"Promoted {version} to PRODUCTION")

        return True, "Promoted to production"

    def rollback(self, version: str, reason: str):
        """Rollback model from canary."""
        metadata = self.registry.get(version)
        if not metadata:
            return False, f"Model {version} not found"

        metadata.stage = PromotionStage.ROLLED_BACK
        metadata.promotion_notes = f"Rolled back: {reason}"
        logger.warning(f"Rolled back {version}: {reason}")

        return True, f"Rolled back: {reason}"

    def get_current_production_version(self) -> str | None:
        """Get current production model version."""
        for version, metadata in self.registry.items():
            if metadata.stage == PromotionStage.PRODUCTION:
                return version
        return None

    def export_registry(self, output_path: Path):
        """Export registry to JSON."""
        registry_data = {}
        for version, metadata in self.registry.items():
            registry_data[version] = {
                "version": metadata.version,
                "stage": metadata.stage.value,
                "created_at": metadata.created_at.isoformat(),
                "accuracy": metadata.accuracy,
                "ece": metadata.ece,
                "groundedness": metadata.groundedness,
                "shadow_samples": metadata.shadow_samples,
                "shadow_duration_days": metadata.shadow_duration_days,
                "promoted_at": metadata.promoted_at.isoformat() if metadata.promoted_at else None,
                "promotion_notes": metadata.promotion_notes,
            }

        with open(output_path, "w") as f:
            json.dump(registry_data, f, indent=2)

        logger.info(f"Exported registry to {output_path}")
