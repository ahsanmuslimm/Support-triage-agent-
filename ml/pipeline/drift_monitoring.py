"""S8.8: Drift Monitoring.

Detect model and data drift:
- PSI (Population Stability Index): intent distribution shift
- Centroid drift: embedding space drift per class
- OOD rate: % of predictions marked OOD over time
- Concept drift: classification F1 on rolling 7-day window
- Alerts: PSI >0.2 or OOD rate >10%
- Prometheus metrics export
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class DriftMetrics:
    """Drift monitoring metrics."""
    timestamp: datetime
    psi: float
    psi_by_intent: dict[str, float]
    centroid_drift: float
    centroid_drift_by_class: dict[str, float]
    ood_rate: float
    concept_drift_f1: float
    alert_triggered: bool
    alert_reason: str | None = None


class PSIComputer:
    """Population Stability Index for intent distribution shifts."""

    @staticmethod
    def compute_psi(baseline_dist: dict, current_dist: dict) -> float:
        """
        Compute PSI between two intent distributions.

        PSI = sum((current% - baseline%) * ln(current% / baseline%))

        Interpretation:
        - PSI < 0.1: negligible shift
        - PSI 0.1-0.25: small shift
        - PSI > 0.25: significant shift
        """
        psi = 0.0
        all_intents = set(baseline_dist.keys()) | set(current_dist.keys())

        for intent in all_intents:
            baseline_pct = baseline_dist.get(intent, 0.0) + 1e-7
            current_pct = current_dist.get(intent, 0.0) + 1e-7

            psi += (current_pct - baseline_pct) * np.log(current_pct / baseline_pct)

        return psi

    @staticmethod
    def compute_intent_distribution(predictions: list[str]) -> dict[str, float]:
        """Compute intent distribution from predictions."""
        if not predictions:
            return {}

        intent_counts = {}
        for pred in predictions:
            intent_counts[pred] = intent_counts.get(pred, 0) + 1

        total = len(predictions)
        return {intent: count / total for intent, count in intent_counts.items()}

    @staticmethod
    def compute_psi_by_intent(baseline: dict, current: dict) -> dict[str, float]:
        """Compute per-intent PSI contribution."""
        psi_by_intent = {}

        all_intents = set(baseline.keys()) | set(current.keys())
        for intent in all_intents:
            baseline_pct = baseline.get(intent, 0.0) + 1e-7
            current_pct = current.get(intent, 0.0) + 1e-7

            intent_psi = (current_pct - baseline_pct) * np.log(current_pct / baseline_pct)
            psi_by_intent[intent] = float(intent_psi)

        return psi_by_intent


class CentroidDriftDetector:
    """Detect embedding space drift per class."""

    def __init__(self):
        self.baseline_centroids = None  # intent -> centroid

    def fit_baseline(
        self,
        embeddings: np.ndarray,
        labels: list[str],
    ):
        """Fit baseline centroids per intent."""
        self.baseline_centroids = {}

        for intent in set(labels):
            mask = np.array([label == intent for label in labels])
            if np.sum(mask) > 0:
                centroid = np.mean(embeddings[mask], axis=0)
                self.baseline_centroids[intent] = centroid

        logger.info(f"Fitted baseline centroids for {len(self.baseline_centroids)} intents")

    def compute_drift(
        self,
        embeddings: np.ndarray,
        labels: list[str],
    ) -> tuple[float, dict[str, float]]:
        """
        Compute centroid drift.

        Returns:
            (overall_drift, per_class_drift)
        """
        if self.baseline_centroids is None:
            raise RuntimeError("Must call fit_baseline() first")

        per_class_drift = {}
        total_drift = 0.0

        for intent in set(labels):
            if intent not in self.baseline_centroids:
                continue

            mask = np.array([label == intent for label in labels])
            if np.sum(mask) == 0:
                continue

            current_centroid = np.mean(embeddings[mask], axis=0)
            baseline_centroid = self.baseline_centroids[intent]

            # Euclidean distance
            drift = float(np.linalg.norm(current_centroid - baseline_centroid))
            per_class_drift[intent] = drift
            total_drift += drift

        overall_drift = total_drift / max(len(per_class_drift), 1)

        return overall_drift, per_class_drift


class OODRateMonitor:
    """Monitor OOD rate over time."""

    def __init__(self, window_size: int = 100):
        self.window_size = window_size
        self.recent_ood_flags = []

    def update(self, is_ood: bool):
        """Add OOD flag to window."""
        self.recent_ood_flags.append(is_ood)

        if len(self.recent_ood_flags) > self.window_size:
            self.recent_ood_flags.pop(0)

    def get_ood_rate(self) -> float:
        """Get current OOD rate from window."""
        if not self.recent_ood_flags:
            return 0.0

        return sum(self.recent_ood_flags) / len(self.recent_ood_flags)


class ConceptDriftDetector:
    """Detect concept drift: classification performance degradation."""

    def __init__(self, window_days: int = 7):
        self.window_days = window_days
        self.prediction_history = []  # (timestamp, prediction, label)

    def update(
        self,
        prediction: str,
        label: str,
    ):
        """Add prediction to history."""
        self.prediction_history.append((datetime.utcnow(), prediction, label))

        # Cleanup old entries
        cutoff = datetime.utcnow() - timedelta(days=self.window_days + 1)
        self.prediction_history = [
            (ts, pred, lbl) for ts, pred, lbl in self.prediction_history
            if ts > cutoff
        ]

    def compute_f1_on_window(self) -> float:
        """Compute F1 on rolling window."""
        if not self.prediction_history:
            return 0.0

        # Get predictions from window
        cutoff = datetime.utcnow() - timedelta(days=self.window_days)
        window_data = [
            (pred, lbl) for ts, pred, lbl in self.prediction_history
            if ts > cutoff
        ]

        if not window_data:
            return 0.0

        # Compute per-class F1
        intents = {lbl for _, lbl in window_data}
        f1_scores = []

        for intent in intents:
            tp = sum(1 for pred, lbl in window_data if pred == intent and lbl == intent)
            fp = sum(1 for pred, lbl in window_data if pred == intent and lbl != intent)
            fn = sum(1 for pred, lbl in window_data if pred != intent and lbl == intent)

            precision = tp / (tp + fp + 1e-7)
            recall = tp / (tp + fn + 1e-7)
            f1 = 2 * precision * recall / (precision + recall + 1e-7)
            f1_scores.append(f1)

        macro_f1 = np.mean(f1_scores) if f1_scores else 0.0
        return float(macro_f1)


class DriftMonitor:
    """Unified drift monitoring."""

    def __init__(self):
        self.psi_computer = PSIComputer()
        self.centroid_detector = CentroidDriftDetector()
        self.ood_monitor = OODRateMonitor()
        self.concept_detector = ConceptDriftDetector()

        self.baseline_dist = None
        self.metrics_history = []

        # Thresholds
        self.PSI_ALERT_THRESHOLD = 0.25
        self.OOD_RATE_ALERT_THRESHOLD = 0.10

    def fit_baseline(
        self,
        baseline_predictions: list[str],
        baseline_embeddings: np.ndarray,
        baseline_labels: list[str],
    ):
        """Fit baseline for drift detection."""
        self.baseline_dist = self.psi_computer.compute_intent_distribution(baseline_predictions)
        self.centroid_detector.fit_baseline(baseline_embeddings, baseline_labels)

        logger.info("Fitted baseline for drift monitoring")

    def monitor(
        self,
        embeddings: np.ndarray,
        predictions: list[str],
        labels: list[str],
        ood_flags: list[bool],
    ) -> DriftMetrics:
        """Monitor for all drift types."""
        # PSI
        current_dist = self.psi_computer.compute_intent_distribution(predictions)
        psi = self.psi_computer.compute_psi(self.baseline_dist, current_dist)
        psi_by_intent = self.psi_computer.compute_psi_by_intent(self.baseline_dist, current_dist)

        # Centroid drift
        centroid_drift, centroid_by_class = self.centroid_detector.compute_drift(
            embeddings, predictions
        )

        # OOD rate
        for ood in ood_flags:
            self.ood_monitor.update(ood)
        ood_rate = self.ood_monitor.get_ood_rate()

        # Concept drift (update history)
        for pred, label in zip(predictions, labels, strict=True):
            self.concept_detector.update(pred, label)
        concept_drift_f1 = self.concept_detector.compute_f1_on_window()

        # Check alerts
        alert_triggered = False
        alert_reason = None

        if psi > self.PSI_ALERT_THRESHOLD:
            alert_triggered = True
            alert_reason = f"PSI {psi:.4f} > {self.PSI_ALERT_THRESHOLD}"

        if ood_rate > self.OOD_RATE_ALERT_THRESHOLD:
            alert_triggered = True
            alert_reason = f"OOD rate {ood_rate:.4f} > {self.OOD_RATE_ALERT_THRESHOLD}"

        if alert_triggered:
            logger.warning(f"Drift alert: {alert_reason}")

        metrics = DriftMetrics(
            timestamp=datetime.utcnow(),
            psi=psi,
            psi_by_intent=psi_by_intent,
            centroid_drift=centroid_drift,
            centroid_drift_by_class=centroid_by_class,
            ood_rate=ood_rate,
            concept_drift_f1=concept_drift_f1,
            alert_triggered=alert_triggered,
            alert_reason=alert_reason,
        )

        self.metrics_history.append(metrics)
        return metrics

    def export_prometheus_metrics(self, output_path: Path):
        """Export metrics in Prometheus format."""
        if not self.metrics_history:
            return

        latest = self.metrics_history[-1]

        prometheus_lines = [
            "# HELP ml_psi Population Stability Index",
            "# TYPE ml_psi gauge",
            f"ml_psi {latest.psi}",
            "",
            "# HELP ml_centroid_drift Centroid drift in embedding space",
            "# TYPE ml_centroid_drift gauge",
            f"ml_centroid_drift {latest.centroid_drift}",
            "",
            "# HELP ml_ood_rate Out-of-distribution rate",
            "# TYPE ml_ood_rate gauge",
            f"ml_ood_rate {latest.ood_rate}",
            "",
            "# HELP ml_concept_drift_f1 F1 on rolling 7-day window",
            "# TYPE ml_concept_drift_f1 gauge",
            f"ml_concept_drift_f1 {latest.concept_drift_f1}",
            "",
            "# HELP ml_drift_alert Drift alert triggered (1 or 0)",
            "# TYPE ml_drift_alert gauge",
            f"ml_drift_alert {int(latest.alert_triggered)}",
        ]

        with open(output_path, "w") as f:
            f.write("\n".join(prometheus_lines))

        logger.info(f"Exported Prometheus metrics to {output_path}")

    def export_report(self, output_path: Path):
        """Export drift monitoring report."""
        report = {
            "timestamp": datetime.utcnow().isoformat(),
            "metrics_count": len(self.metrics_history),
            "latest_metrics": {
                "psi": self.metrics_history[-1].psi if self.metrics_history else 0.0,
                "centroid_drift": self.metrics_history[-1].centroid_drift if self.metrics_history else 0.0,
                "ood_rate": self.metrics_history[-1].ood_rate if self.metrics_history else 0.0,
                "concept_drift_f1": self.metrics_history[-1].concept_drift_f1 if self.metrics_history else 0.0,
            },
            "alerts": [
                {
                    "timestamp": m.timestamp.isoformat(),
                    "reason": m.alert_reason,
                }
                for m in self.metrics_history if m.alert_triggered
            ],
        }

        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)

        logger.info(f"Exported drift report to {output_path}")
