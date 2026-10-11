"""S3.4: Account Health Scoring with LightGBM and SHAP."""

import logging
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Tuple, List

from .features import HealthFeatures

logger = logging.getLogger(__name__)


@dataclass
class HealthScore:
    """Health score result with explainability."""

    churn_risk_score: float  # 0.0 - 1.0
    health_label: str  # 'healthy', 'at_risk'
    shap_drivers: List[dict]  # Top 3 drivers: {feature, impact, direction}
    explanation: str


class AccountHealthScorer:
    """LightGBM-based churn risk scorer with SHAP explanations."""

    def __init__(self, model=None, model_path: Optional[str] = None):
        """
        Initialize scorer.

        Args:
            model: Loaded LightGBM model (for testing)
            model_path: Path to .pkl/.lgb model file
        """
        self.model = model
        self.model_path = model_path
        self.threshold = 0.65  # Churn risk threshold

        if model_path and not model:
            self._load_model(model_path)

    def _load_model(self, model_path: str):
        """Load LightGBM model from disk."""
        try:
            import lightgbm as lgb
            import pickle

            if model_path.endswith(".pkl"):
                with open(model_path, "rb") as f:
                    self.model = pickle.load(f)
            elif model_path.endswith(".lgb"):
                self.model = lgb.Booster(model_file=model_path)
            else:
                raise ValueError(f"Unsupported model format: {model_path}")

            logger.info(f"Loaded model from {model_path}")
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise

    def predict(self, features: HealthFeatures) -> Tuple[float, str]:
        """
        Predict churn risk score (0.0 - 1.0) and label.

        Args:
            features: HealthFeatures object

        Returns:
            (churn_risk_score, label)
        """
        if not HealthFeatures.validate(features):
            raise ValueError("Invalid features")

        if not self.model:
            # Fallback scoring (for tests without model)
            return self._fallback_score(features)

        try:
            import numpy as np

            # Convert features to 2D array for model inference
            X = np.array([features.to_array()])
            
            # Use predict_proba if available (for binary classifiers), otherwise predict
            try:
                # Try predict_proba first (returns probabilities for each class)
                predictions = self.model.predict_proba(X)
                # For binary classifier, take probability of positive class (index 1)
                if predictions.shape[1] == 2:
                    churn_risk_score = float(predictions[0][1])
                else:
                    # Single output - assume it's the risk score
                    churn_risk_score = float(predictions[0])
            except (AttributeError, TypeError):
                # Fallback to predict if predict_proba not available
                prediction = self.model.predict(X)[0]
                churn_risk_score = float(prediction)

            # Ensure score is in [0, 1]
            churn_risk_score = max(0.0, min(1.0, churn_risk_score))

            # Apply threshold
            health_label = "at_risk" if churn_risk_score >= self.threshold else "healthy"

            return churn_risk_score, health_label
        except Exception as e:
            logger.error(f"Model prediction failed: {e}")
            raise

    def explain(self, features: HealthFeatures) -> List[dict]:
        """
        Explain prediction using SHAP (top 3 drivers).

        Returns:
            List of {feature, impact, direction}
        """
        if not self.model:
            return self._fallback_explain(features)

        try:
            import shap
            import numpy as np

            X = np.array([features.to_array()])
            
            try:
                # Try to create SHAP explainer for tree models
                explainer = shap.TreeExplainer(self.model)
                shap_values = explainer.shap_values(X)

                # Handle different SHAP value formats
                if isinstance(shap_values, list):
                    # List of arrays for binary/multiclass - take positive class
                    sv = shap_values[1][0] if len(shap_values) > 1 else shap_values[0][0]
                else:
                    # Single array
                    sv = shap_values[0]

                # Get top 3 drivers by absolute SHAP value
                feature_names = HealthFeatures.feature_names()
                top_indices = np.argsort(np.abs(sv))[::-1][:3]
                
                drivers = []
                for idx in top_indices:
                    drivers.append(
                        {
                            "feature": feature_names[idx],
                            "impact": float(sv[idx]),
                            "direction": "positive" if sv[idx] > 0 else "negative",
                        }
                    )

                return drivers
            except Exception as shap_error:
                logger.warning(f"TreeExplainer failed, trying KernelExplainer: {shap_error}")
                # Fallback to KernelExplainer if TreeExplainer fails
                explainer = shap.KernelExplainer(self.model.predict, X)
                shap_values = explainer.shap_values(X)
                
                if isinstance(shap_values, list):
                    sv = shap_values[1] if len(shap_values) > 1 else shap_values[0]
                else:
                    sv = shap_values
                
                if isinstance(sv, np.ndarray) and len(sv.shape) > 1:
                    sv = sv[0]
                
                feature_names = HealthFeatures.feature_names()
                top_indices = np.argsort(np.abs(sv))[::-1][:3]
                
                drivers = []
                for idx in top_indices:
                    drivers.append(
                        {
                            "feature": feature_names[idx],
                            "impact": float(sv[idx]),
                            "direction": "positive" if sv[idx] > 0 else "negative",
                        }
                    )
                return drivers
                
        except ImportError:
            logger.warning("SHAP not installed, using fallback explanation")
            return self._fallback_explain(features)
        except Exception as e:
            logger.warning(f"SHAP explanation failed: {e}")
            return self._fallback_explain(features)

    def _fallback_score(self, features: HealthFeatures) -> Tuple[float, str]:
        """
        Simple rule-based scoring when model unavailable.

        Heuristic: combines risk signals
        """
        score = 0.0

        # High recency is good (not risky) - lower recency days = lower risk
        if features.recency_days > 90:
            score += 0.2
        elif features.recency_days > 60:
            score += 0.15
        elif features.recency_days > 30:
            score += 0.1

        # Failed payments increase risk
        if features.failed_payments_90d > 0:
            score += min(0.2, 0.05 * features.failed_payments_90d)

        # Chargebacks are very risky
        score += min(0.2, 0.1 * features.chargeback_count)

        # Inactive subscription is risky
        if not features.subscription_status_active:
            score += 0.2

        # High return rate is risky
        score += features.return_rate * 0.15

        # Support contact count high = potential churn signal
        if features.support_contact_count > 5:
            score += min(0.1, 0.02 * features.support_contact_count)

        # Negative sentiment is risky
        score += features.sentiment_negative_ratio * 0.1

        # Normalize
        score = min(1.0, score)

        label = "at_risk" if score >= self.threshold else "healthy"
        return score, label

    def _fallback_explain(self, features: HealthFeatures) -> List[dict]:
        """Simple explanation when SHAP unavailable."""
        drivers = []

        # Top contributors to risk
        if features.failed_payments_90d > 2:
            drivers.append(
                {
                    "feature": "failed_payments_90d",
                    "impact": 0.1 * features.failed_payments_90d,
                    "direction": "positive",
                }
            )

        if features.recency_days > 90:
            drivers.append(
                {
                    "feature": "recency_days",
                    "impact": -0.15,
                    "direction": "negative",
                }
            )

        if features.return_rate > 0.2:
            drivers.append(
                {
                    "feature": "return_rate",
                    "impact": features.return_rate * 0.1,
                    "direction": "positive",
                }
            )

        return drivers[:3]
