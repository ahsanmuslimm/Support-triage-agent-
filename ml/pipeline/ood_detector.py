"""S8.4: Out-of-Distribution Detector.

Energy-based and centroid-distance methods:
- Energy = -log(sum(exp(logits)))
- Centroid distance in embedding space
- Ensemble: max(norm_energy, norm_distance) > threshold
- Threshold calibration for 80% recall on novel intents
"""

import logging
from dataclasses import dataclass

import numpy as np
from scipy.spatial.distance import cdist

logger = logging.getLogger(__name__)


@dataclass
class OODMetrics:
    """OOD detection performance."""
    auc_roc: float
    threshold: float
    recall_at_80: float
    precision_at_80: float
    f1_at_80: float


class EnergyDetector:
    """Energy-based OOD detection."""

    @staticmethod
    def compute_energy(logits: np.ndarray) -> np.ndarray:
        """Energy = -log(sum(exp(logits)))."""
        # Numerically stable version
        max_logits = np.max(logits, axis=1, keepdims=True)
        exp_logits = np.exp(logits - max_logits)
        sum_exp = np.sum(exp_logits, axis=1)
        energy = -np.log(sum_exp + 1e-7)

        return energy


class CentroidDetector:
    """Centroid distance-based OOD detection."""

    def __init__(self):
        self.centroids = None  # per-class centroid
        self.class_labels = None

    def fit(
        self,
        embeddings: np.ndarray,
        labels: np.ndarray,
    ):
        """Compute centroids for each class."""
        unique_labels = np.unique(labels)
        centroids = {}

        for label in unique_labels:
            mask = labels == label
            centroid = np.mean(embeddings[mask], axis=0)
            centroids[label] = centroid

        self.centroids = centroids
        self.class_labels = unique_labels
        logger.info(f"Fitted {len(centroids)} class centroids")

    def compute_centroid_distances(self, embeddings: np.ndarray) -> np.ndarray:
        """Distance to nearest class centroid."""
        if self.centroids is None:
            raise RuntimeError("Must call fit() first")

        centroid_array = np.array([
            self.centroids[label] for label in sorted(self.centroids.keys())
        ])

        # Shape: (n_samples, n_classes)
        distances = cdist(embeddings, centroid_array, metric="euclidean")

        # Nearest centroid distance
        min_distances = np.min(distances, axis=1)

        return min_distances

    def normalize_distances(self, distances: np.ndarray) -> np.ndarray:
        """Normalize distances to [0, 1]."""
        min_dist = np.min(distances)
        max_dist = np.max(distances)

        if max_dist == min_dist:
            return np.zeros_like(distances)

        normalized = (distances - min_dist) / (max_dist - min_dist)
        return normalized


class OODEnsemble:
    """Ensemble of energy + centroid OOD detectors."""

    def __init__(self):
        self.energy_detector = EnergyDetector()
        self.centroid_detector = CentroidDetector()
        self.threshold = 0.5

    def fit(
        self,
        embeddings: np.ndarray,
        logits: np.ndarray,
        labels: np.ndarray,
    ):
        """Fit centroid detector."""
        self.centroid_detector.fit(embeddings, labels)

    def predict_ood(
        self,
        embeddings: np.ndarray,
        logits: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Predict OOD score using ensemble.

        Returns:
            (ood_scores, ood_predictions)
        """
        # Energy scores
        energy = self.energy_detector.compute_energy(logits)
        # Normalize energy: higher energy = more OOD
        energy_norm = (energy - np.min(energy)) / (np.max(energy) - np.min(energy) + 1e-7)

        # Centroid distances
        distances = self.centroid_detector.compute_centroid_distances(embeddings)
        distance_norm = self.centroid_detector.normalize_distances(distances)

        # Ensemble: max of normalized scores
        ood_scores = np.maximum(energy_norm, distance_norm)

        # Binary prediction
        ood_preds = (ood_scores > self.threshold).astype(int)

        return ood_scores, ood_preds

    def calibrate_threshold(
        self,
        embeddings: np.ndarray,
        logits: np.ndarray,
        labels: np.ndarray,
        is_ood: np.ndarray,  # True if sample is OOD
        target_recall: float = 0.80,
    ) -> float:
        """
        Calibrate threshold for target recall on OOD samples.

        Args:
            target_recall: Target recall on known novel/OOD samples
        """
        ood_scores, _ = self.predict_ood(embeddings, logits)

        # Sort by OOD score
        sorted_idx = np.argsort(-ood_scores)
        sorted_scores = ood_scores[sorted_idx]

        # Find threshold that achieves target recall
        n_ood = np.sum(is_ood)
        target_positives = int(target_recall * n_ood)

        if target_positives > 0 and target_positives < len(sorted_idx):
            self.threshold = sorted_scores[target_positives]

        logger.info(f"Calibrated OOD threshold: {self.threshold:.4f}")
        return self.threshold


class ThresholdCalibrator:
    """Calibrate OOD detection threshold on held-out novel intents."""

    @staticmethod
    def calibrate(
        ood_scores: np.ndarray,
        labels: np.ndarray,
        novel_intent_ids: set,
        target_recall: float = 0.80,
    ) -> float:
        """
        Find threshold that achieves target recall on novel intents.

        Args:
            ood_scores: OOD scores for all samples
            labels: Intent labels
            novel_intent_ids: Set of novel intent IDs to detect
            target_recall: Target recall for novel intents
        """
        # Mark samples from novel intents as OOD ground truth
        is_novel = np.array([label in novel_intent_ids for label in labels])

        # Sort by OOD score (descending)
        sorted_idx = np.argsort(-ood_scores)
        sorted_scores = ood_scores[sorted_idx]

        # Find threshold for target recall
        n_novel = np.sum(is_novel)
        target_tp = int(target_recall * n_novel)

        if target_tp > 0 and target_tp < len(sorted_idx):
            threshold = sorted_scores[target_tp]
        else:
            threshold = 0.5

        # Compute metrics at this threshold
        preds = ood_scores > threshold
        tp = np.sum(preds & is_novel)
        fp = np.sum(preds & ~is_novel)
        fn = np.sum(~preds & is_novel)

        recall = tp / (tp + fn + 1e-7)
        precision = tp / (tp + fp + 1e-7)
        f1 = 2 * recall * precision / (recall + precision + 1e-7)

        logger.info(
            f"Threshold calibration: threshold={threshold:.4f}, "
            f"recall={recall:.4f}, precision={precision:.4f}, f1={f1:.4f}"
        )

        return threshold


class OODAnalyzer:
    """Comprehensive OOD analysis."""

    @staticmethod
    def compute_roc_auc(
        ood_scores: np.ndarray,
        is_ood: np.ndarray,
    ) -> float:
        """Compute ROC AUC."""
        from sklearn.metrics import roc_auc_score

        try:
            auc = roc_auc_score(is_ood, ood_scores)
            return auc
        except Exception as e:
            logger.warning(f"Could not compute ROC AUC: {e}")
            return 0.0

    @staticmethod
    def compute_pr_curve(
        ood_scores: np.ndarray,
        is_ood: np.ndarray,
        num_thresholds: int = 100,
    ) -> dict:
        """Compute precision-recall curve."""
        thresholds = np.linspace(0, 1, num_thresholds)
        precisions = []
        recalls = []

        for threshold in thresholds:
            preds = ood_scores > threshold

            tp = np.sum(preds & is_ood)
            fp = np.sum(preds & ~is_ood)
            fn = np.sum(~preds & is_ood)

            precision = tp / (tp + fp + 1e-7)
            recall = tp / (tp + fn + 1e-7)

            precisions.append(precision)
            recalls.append(recall)

        return {
            "thresholds": thresholds.tolist(),
            "precisions": precisions,
            "recalls": recalls,
        }

    @staticmethod
    def analyze(
        embeddings: np.ndarray,
        logits: np.ndarray,
        labels: np.ndarray,
        novel_intent_ids: set,
    ) -> OODMetrics:
        """Full OOD analysis."""
        # Mark novel intents as OOD
        is_ood = np.array([label in novel_intent_ids for label in labels])

        # Create ensemble
        ensemble = OODEnsemble()
        ensemble.fit(embeddings, logits, labels)

        # Predict OOD
        ood_scores, ood_preds = ensemble.predict_ood(embeddings, logits)

        # Compute metrics
        auc = OODAnalyzer.compute_roc_auc(ood_scores, is_ood)

        # Calibrate threshold for 80% recall
        threshold = ThresholdCalibrator.calibrate(
            ood_scores, labels, novel_intent_ids, target_recall=0.80
        )
        ensemble.threshold = threshold

        # Recompute predictions with calibrated threshold
        _, ood_preds = ensemble.predict_ood(embeddings, logits)

        # Compute final metrics
        tp = np.sum(ood_preds & is_ood)
        fp = np.sum(ood_preds & ~is_ood)
        fn = np.sum(~ood_preds & is_ood)

        recall = tp / (tp + fn + 1e-7)
        precision = tp / (tp + fp + 1e-7)
        f1 = 2 * recall * precision / (recall + precision + 1e-7)

        return OODMetrics(
            auc_roc=auc,
            threshold=threshold,
            recall_at_80=recall,
            precision_at_80=precision,
            f1_at_80=f1,
        )
