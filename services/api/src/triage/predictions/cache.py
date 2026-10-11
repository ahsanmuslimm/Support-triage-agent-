"""Redis-backed prediction cache."""

from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class PredictionCache:
    """Simple Redis-backed cache for predictions (mocked for testing)."""

    def __init__(self):
        """Initialize cache."""
        self._store: Dict[str, tuple] = {}  # {key: (value, expiry_time)}

    def _make_key(
        self, prediction_type: str, tenant_id: int, customer_id: int
    ) -> str:
        """Build cache key."""
        return f"prediction:{prediction_type}:{tenant_id}:{customer_id}"

    async def set_prediction(
        self,
        prediction_type: str,
        customer_id: int,
        tenant_id: int,
        data: Dict,
        ttl_seconds: int = 3600,
    ) -> None:
        """
        Store prediction in cache.

        Args:
            prediction_type: Type of prediction (lstm_next_issue, churn_72h, volume_forecast)
            customer_id: Customer ID
            tenant_id: Tenant ID
            data: Prediction data dict
            ttl_seconds: Time-to-live in seconds (default 1 hour)
        """
        key = self._make_key(prediction_type, tenant_id, customer_id)
        import time

        expiry_time = time.time() + ttl_seconds
        self._store[key] = (data, expiry_time)
        logger.debug(f"Cached prediction: {key}")

    async def get_prediction(
        self, prediction_type: str, customer_id: int, tenant_id: int
    ) -> Optional[Dict]:
        """
        Retrieve prediction from cache.

        Args:
            prediction_type: Type of prediction
            customer_id: Customer ID
            tenant_id: Tenant ID

        Returns:
            Prediction data dict or None if expired/missing
        """
        key = self._make_key(prediction_type, tenant_id, customer_id)
        if key not in self._store:
            return None

        data, expiry_time = self._store[key]
        import time

        if time.time() > expiry_time:
            del self._store[key]
            return None

        return data

    async def invalidate_prediction(
        self, customer_id: int, tenant_id: int
    ) -> None:
        """
        Invalidate all predictions for a customer.

        Args:
            customer_id: Customer ID
            tenant_id: Tenant ID
        """
        prefix = f"prediction:*:{tenant_id}:{customer_id}"
        keys_to_delete = [k for k in self._store.keys() if k.endswith(f":{tenant_id}:{customer_id}")]
        for key in keys_to_delete:
            del self._store[key]
        logger.debug(f"Invalidated {len(keys_to_delete)} predictions for customer {customer_id}")

    def clear(self) -> None:
        """Clear all cached predictions."""
        self._store.clear()
