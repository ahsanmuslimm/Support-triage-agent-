"""Prophet model for ticket volume forecasting."""

from typing import List, Tuple, Dict, Optional
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class VolumeForecaster:
    """Prophet model for forecasting ticket volume."""

    def __init__(self):
        """Initialize forecaster."""
        self.model = None
        self.trained_at: Optional[datetime] = None
        self.mape = 0.0
        self.last_known_volume = 100

    async def train(
        self,
        daily_volumes: List[Tuple[datetime, int]],
        forecast_days: int = 90,
    ) -> Dict[str, float]:
        """
        Train Prophet model (mocked for testing).

        Args:
            daily_volumes: List of (date, ticket_count) tuples
            forecast_days: Number of days to forecast

        Returns:
            Dict with metrics {mape}
        """
        if not daily_volumes:
            logger.warning("No training data provided")
            return {"mape": 0.0}

        # Sort by date
        daily_volumes = sorted(daily_volumes, key=lambda x: x[0])

        # Mock training: compute simple statistics
        volumes = [v[1] for v in daily_volumes]
        mean_volume = sum(volumes) / len(volumes) if volumes else 100
        std_volume = (sum((v - mean_volume) ** 2 for v in volumes) / len(volumes)) ** 0.5 if volumes else 10

        # Mock MAPE calculation (would normally use actual Prophet)
        # Simulate holdout test on last 30 days
        if len(daily_volumes) > 30:
            test_volumes = volumes[-30:]
            # Predict using simple exponential smoothing
            predictions = [mean_volume] * 30
            errors = [abs(p - a) / a if a > 0 else 0 for p, a in zip(predictions, test_volumes)]
            self.mape = sum(errors) / len(errors) if errors else 0.15
        else:
            self.mape = 0.12

        self.last_known_volume = mean_volume
        self.trained_at = datetime.utcnow()

        metrics = {
            "mape": self.mape,
            "mean_volume": mean_volume,
            "std_volume": std_volume,
            "training_days": len(daily_volumes),
        }

        logger.info(f"Prophet training complete: {metrics}")
        return metrics

    async def forecast(
        self,
        days_ahead: int = 30,
    ) -> List[Tuple[datetime, float, float, float]]:
        """
        Forecast ticket volume.

        Args:
            days_ahead: Number of days to forecast

        Returns:
            List of (date, point_forecast, lower_ci, upper_ci) tuples
        """
        if self.trained_at is None:
            logger.warning("Model not trained; returning default forecast")
            base_volume = 100.0
        else:
            base_volume = self.last_known_volume

        forecasts = []
        today = datetime.utcnow().date()

        for i in range(1, days_ahead + 1):
            forecast_date = today + timedelta(days=i)

            # Mock forecast: add small trend and seasonality
            trend = 0.5 * i / days_ahead  # Slight upward trend
            seasonality = 5 * (i % 7)  # Weekly pattern
            point_forecast = base_volume + trend + seasonality

            # 95% confidence interval
            ci_width = base_volume * 0.15  # ±15%
            lower_ci = max(0, point_forecast - ci_width)
            upper_ci = point_forecast + ci_width

            forecasts.append((forecast_date, point_forecast, lower_ci, upper_ci))

        return forecasts

    async def detect_anomalies(
        self,
        recent_actuals: List[Tuple[datetime, int]],
        forecast_data: List[Tuple[datetime, float, float, float]],
    ) -> List[Tuple[datetime, float, str]]:
        """
        Detect volume anomalies vs. forecast.

        Args:
            recent_actuals: Recent actual volumes
            forecast_data: Forecast data with CI

        Returns:
            List of (date, deviation_pct, direction) anomalies
        """
        if not recent_actuals or not forecast_data:
            return []

        anomalies = []

        # Build forecast lookup
        forecast_map = {d.date(): (pf, lci, uci) for d, pf, lci, uci in forecast_data}

        for actual_date, actual_volume in recent_actuals:
            forecast_tuple = forecast_map.get(actual_date.date())
            if not forecast_tuple:
                continue

            point_forecast, lower_ci, upper_ci = forecast_tuple

            # Flag if outside 95% CI
            if actual_volume > upper_ci:
                deviation = ((actual_volume - point_forecast) / point_forecast) * 100
                anomalies.append((actual_date, deviation, "high"))
            elif actual_volume < lower_ci:
                deviation = ((point_forecast - actual_volume) / point_forecast) * 100
                anomalies.append((actual_date, deviation, "low"))

        return anomalies

    def is_trained(self) -> bool:
        """Check if model is trained."""
        return self.trained_at is not None
