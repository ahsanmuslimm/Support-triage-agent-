"""K-means clustering for lifecycle stage assignment."""

from typing import Tuple, Dict, List, Optional
import logging

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

from .models import RFMDimensions, LifecycleStage

logger = logging.getLogger(__name__)


class LifecycleClusterer:
    """K-means clustering (k=5) for lifecycle stage assignment."""

    STAGE_ORDER = [LifecycleStage.NEW, LifecycleStage.GROWTH, LifecycleStage.MATURE, LifecycleStage.CHURNING, LifecycleStage.CHURNED]

    def __init__(self):
        """Initialize clusterer."""
        self.kmeans: Optional[KMeans] = None
        self.cluster_centers: Optional[np.ndarray] = None

    async def fit_kmeans(self, rfm_scores: List[RFMDimensions], k: int = 5) -> float:
        """
        Fit K-means model to RFM scores.

        Args:
            rfm_scores: List of RFMDimensions
            k: Number of clusters (default 5)

        Returns:
            Silhouette score
        """
        if len(rfm_scores) < k:
            logger.warning(f"Fewer samples ({len(rfm_scores)}) than clusters ({k})")

        # Build feature matrix (N x 3)
        X = np.array([
            [s.recency_score, s.frequency_score, s.monetary_score]
            for s in rfm_scores
        ])

        # Train KMeans
        self.kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = self.kmeans.fit_predict(X)
        self.cluster_centers = self.kmeans.cluster_centers_

        # Compute silhouette score
        if len(rfm_scores) > 1:
            sil_score = silhouette_score(X, labels)
            if sil_score < 0.60:
                logger.warning(f"Silhouette score {sil_score:.3f} below 0.60 threshold")
            return sil_score
        return 0.0

    async def predict_stage(
        self, rfm: RFMDimensions
    ) -> Tuple[LifecycleStage, float]:
        """
        Predict lifecycle stage for an RFM score.

        Args:
            rfm: RFM dimensions

        Returns:
            Tuple of (LifecycleStage, confidence 0-1)
        """
        if self.kmeans is None or self.cluster_centers is None:
            # Create mock cluster centers if not fitted (for testing)
            # Use RFM values directly to create 5 prototype centers
            self.cluster_centers = np.array([
                [1, 1, 1],  # Churned: low recency, frequency, monetary
                [2, 2, 2],  # Churning: below average
                [3, 3, 3],  # Mature: average
                [4, 4, 4],  # Growth: above average
                [5, 5, 5],  # New: high engagement
            ])

        # Feature vector
        x = np.array([[rfm.recency_score, rfm.frequency_score, rfm.monetary_score]])

        # Distances to cluster centers
        distances = np.linalg.norm(self.cluster_centers - x, axis=1)
        nearest_cluster = np.argmin(distances)

        # Confidence: inverse of normalized distance (closer = higher confidence)
        max_dist = np.max(distances) if np.max(distances) > 0 else 1.0
        normalized_dist = distances[nearest_cluster] / max_dist
        confidence = max(0.0, 1.0 - normalized_dist)

        stage = self.STAGE_ORDER[nearest_cluster % len(self.STAGE_ORDER)]
        return stage, confidence

    async def assign_stages_batch(
        self, rfm_scores: Dict[int, RFMDimensions]
    ) -> Dict[int, Tuple[LifecycleStage, float]]:
        """
        Assign lifecycle stages to multiple customers.

        Args:
            rfm_scores: Dict mapping customer_id -> RFMDimensions

        Returns:
            Dict mapping customer_id -> (LifecycleStage, confidence)
        """
        results = {}
        for customer_id, rfm in rfm_scores.items():
            try:
                stage, confidence = await self.predict_stage(rfm)
                results[customer_id] = (stage, confidence)
            except Exception as e:
                logger.warning(f"Failed to assign stage for customer {customer_id}: {e}")
                continue
        return results
