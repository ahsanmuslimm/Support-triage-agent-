"""Prediction orchestrator combining all models."""

import logging
from datetime import datetime
from typing import Any

from .cache import PredictionCache
from .churn_xgb import ChurnXGBoostModel
from .feature_engineering import FeatureEngineer
from .lstm_model import LSTMNextIssuePredictor
from .volume_prophet import VolumeForecaster

logger = logging.getLogger(__name__)


class PredictionOrchestrator:
    """Orchestrates all prediction models with caching."""

    def __init__(self):
        """Initialize orchestrator with all models."""
        self.feature_engineer = FeatureEngineer()
        self.lstm = LSTMNextIssuePredictor()
        self.churn_model = ChurnXGBoostModel()
        self.volume_forecaster = VolumeForecaster()
        self.cache = PredictionCache()

    async def predict_for_customer(
        self,
        customer_id: int,
        tenant_id: int,
        features: dict[str, float] | None = None,
        issue_history: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Predict for a single customer.

        Args:
            customer_id: Customer ID
            tenant_id: Tenant ID
            features: Pre-computed features (optional)
            issue_history: List of past issues (optional)

        Returns:
            Dict with next_issues, churn_72h predictions
        """
        result = {
            "customer_id": customer_id,
            "tenant_id": tenant_id,
            "predicted_at": datetime.utcnow().isoformat(),
            "next_issues": [],
            "churn_72h": {"probability": 0.0, "contributing_factors": {}},
        }

        try:
            # LSTM: Next issue prediction
            if issue_history:
                next_issues = await self.lstm.predict_next_issue(
                    customer_id, issue_history, top_k=3
                )
                result["next_issues"] = [
                    {"intent": intent, "probability": prob}
                    for intent, prob in next_issues
                ]

            # XGBoost: Churn prediction
            if features:
                churn_prob, feature_imp = await self.churn_model.predict_churn_72h(
                    customer_id, features
                )
                result["churn_72h"] = {
                    "probability": churn_prob,
                    "contributing_factors": feature_imp,
                }

            return result

        except Exception as e:
            logger.error(f"Error predicting for customer {customer_id}: {e}")
            return result

    async def train_all_models(
        self,
        lstm_data: list[tuple[list[str], str]] | None = None,
        churn_data: tuple[list[dict], list[int]] | None = None,
        volume_data: list[tuple[datetime, int]] | None = None,
    ) -> dict[str, dict[str, float]]:
        """
        Retrain all models (typically daily at 03:00 UTC).

        Args:
            lstm_data: Training data for LSTM
            churn_data: Tuple of (features, labels) for churn model
            volume_data: Daily volume data for Prophet

        Returns:
            Dict with training metrics for each model
        """
        metrics = {}

        try:
            # Train LSTM
            if lstm_data:
                lstm_metrics = await self.lstm.train(lstm_data, epochs=10)
                metrics["lstm"] = lstm_metrics
                logger.info(f"LSTM trained: {lstm_metrics}")

            # Train XGBoost
            if churn_data:
                features, labels = churn_data
                churn_metrics = await self.churn_model.train(features, labels)
                metrics["churn"] = churn_metrics
                logger.info(f"XGBoost trained: {churn_metrics}")

                # Validate precision/recall thresholds
                if churn_metrics.get("precision", 0) < 0.85:
                    logger.warning(
                        f"XGBoost precision {churn_metrics['precision']:.3f} below 0.85 threshold"
                    )
                if churn_metrics.get("recall", 0) < 0.80:
                    logger.warning(
                        f"XGBoost recall {churn_metrics['recall']:.3f} below 0.80 threshold"
                    )

            # Train Prophet
            if volume_data:
                volume_metrics = await self.volume_forecaster.train(
                    volume_data, forecast_days=90
                )
                metrics["volume"] = volume_metrics
                logger.info(f"Prophet trained: {volume_metrics}")

                # Validate MAPE threshold
                if volume_metrics.get("mape", 1.0) > 0.15:
                    logger.warning(
                        f"Prophet MAPE {volume_metrics['mape']:.3f} above 0.15 threshold"
                    )

            return metrics

        except Exception as e:
            logger.error(f"Error retraining models: {e}")
            return {}

    async def invalidate_customer_predictions(
        self, customer_id: int, tenant_id: int
    ) -> None:
        """
        Invalidate all cached predictions for a customer.

        Args:
            customer_id: Customer ID
            tenant_id: Tenant ID
        """
        await self.cache.invalidate_prediction(customer_id, tenant_id)
        logger.debug(f"Invalidated predictions for customer {customer_id}")

    def get_models_status(self) -> dict[str, bool]:
        """Get training status of all models."""
        return {
            "lstm": self.lstm.is_trained(),
            "churn": self.churn_model.is_trained(),
            "volume": self.volume_forecaster.is_trained(),
        }
