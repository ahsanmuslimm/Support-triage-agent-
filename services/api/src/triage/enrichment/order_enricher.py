"""S3.2: Order & Transaction Enrichment."""

import json
import logging
from datetime import datetime, timedelta
from statistics import median
from typing import Optional

from .base import CacheManager, EnricherBase
from .exceptions import APITimeoutError, EnrichmentError
from .models import OrderContext

logger = logging.getLogger(__name__)


class OrderEnricher(EnricherBase):
    """Enrich order history, RFM analysis, and risk signals."""

    def __init__(
        self,
        cache_manager: CacheManager,
        shopify_client=None,
        db_session=None,
    ):
        super().__init__(cache_manager)
        self.shopify = shopify_client
        self.db = db_session

    async def enrich(self, customer_id: int, tenant_id: int) -> OrderContext:
        """
        Fetch and cache order enrichment (last 90 days).

        Tries: Redis cache → Shopify API → DB fallback
        """
        cache_key = self._make_cache_key(tenant_id, customer_id, "order_enrichment")

        # Try cache first
        cached = await self.cache.get(cache_key)
        if cached:
            try:
                data = json.loads(cached)
                return OrderContext(**data)
            except Exception as e:
                logger.warning(f"Failed to deserialize cached order context: {e}")

        # Fetch from APIs
        try:
            await self._validate_tenant_isolation(tenant_id, customer_id, "customer")

            orders_90d = await self._fetch_orders_90d(customer_id, tenant_id)
            refunds_90d = await self._fetch_refunds_90d(customer_id, tenant_id)
            chargebacks_90d = await self._fetch_chargebacks_90d(customer_id, tenant_id)

            # Calculate statistics
            order_count = len(orders_90d)
            refund_count = len(refunds_90d)
            chargeback_count = len(chargebacks_90d)
            total_value = sum(o.get("total", 0) for o in orders_90d)
            avg_order_value = total_value / order_count if order_count > 0 else 0

            # Count high-value orders (>$500)
            high_value_orders = sum(1 for o in orders_90d if o.get("total", 0) > 500)

            # Calculate return rate
            return_rate = refund_count / order_count if order_count > 0 else 0

            # Calculate ordering frequency
            ordering_frequency_median = self._calculate_frequency_median(orders_90d)

            # Detect high velocity
            is_high_velocity = self._is_high_velocity(orders_90d)

            # Compute risk score (0.0 - 1.0)
            risk_score = self._compute_risk_score(
                refund_count, chargeback_count, high_value_orders, order_count
            )

            context = OrderContext(
                customer_id=customer_id,
                tenant_id=tenant_id,
                order_count_90d=order_count,
                refund_count_90d=refund_count,
                chargeback_count_90d=chargeback_count,
                total_value_90d=total_value,
                avg_order_value_90d=avg_order_value,
                high_value_orders=high_value_orders,
                return_rate=return_rate,
                is_high_velocity=is_high_velocity,
                ordering_frequency_median=ordering_frequency_median,
                risk_score=risk_score,
                fetched_at=datetime.utcnow(),
            )

            # Cache the result
            try:
                cache_data = context.__dict__.copy()
                if isinstance(cache_data.get("fetched_at"), datetime):
                    cache_data["fetched_at"] = cache_data["fetched_at"].isoformat()

                await self.cache.set(
                    cache_key,
                    json.dumps(cache_data),
                    ex=context.cache_ttl_seconds,
                )
            except Exception as e:
                logger.warning(f"Failed to cache order context: {e}")

            return context

        except APITimeoutError:
            raise
        except Exception as e:
            logger.error(f"Order enrichment fetch failed: {e}")
            if self.db:
                return await self._fetch_from_db(customer_id, tenant_id)
            raise EnrichmentError(f"Failed to enrich orders for customer {customer_id}: {e}")

    async def _fetch_orders_90d(self, customer_id: int, tenant_id: int) -> list[dict]:
        """Fetch orders from last 90 days."""
        if not self.shopify:
            return []

        try:
            cutoff = datetime.utcnow() - timedelta(days=90)
            orders = await self.shopify.orders.list(customer_id=customer_id)
            result = []

            for o in orders:
                created_at = o.get("created_at")
                if created_at:
                    if isinstance(created_at, str):
                        created_at = datetime.fromisoformat(
                            created_at.replace("Z", "+00:00")
                        )

                    if created_at >= cutoff:
                        result.append(
                            {
                                "id": o.get("id"),
                                "total": float(o.get("total_price", 0)),
                                "created_at": created_at,
                                "status": o.get("financial_status"),
                            }
                        )

            # Sort by date descending
            result.sort(key=lambda x: x["created_at"], reverse=True)
            return result
        except Exception as e:
            logger.error(f"Failed to fetch orders from Shopify: {e}")
            raise APITimeoutError(f"Shopify API error: {e}")

    async def _fetch_refunds_90d(self, customer_id: int, tenant_id: int) -> list[dict]:
        """Fetch refunds from last 90 days."""
        if not self.shopify:
            return []

        try:
            cutoff = datetime.utcnow() - timedelta(days=90)
            refunds = await self.shopify.refunds.list(customer_id=customer_id)
            result = []

            for r in refunds:
                created_at = r.get("created_at")
                if created_at:
                    if isinstance(created_at, str):
                        created_at = datetime.fromisoformat(
                            created_at.replace("Z", "+00:00")
                        )

                    if created_at >= cutoff:
                        result.append(
                            {
                                "id": r.get("id"),
                                "order_id": r.get("order_id"),
                                "created_at": created_at,
                                "amount": float(r.get("amount", 0)),
                            }
                        )

            return result
        except Exception as e:
            logger.warning(f"Failed to fetch refunds: {e}")
            return []

    async def _fetch_chargebacks_90d(
        self, customer_id: int, tenant_id: int
    ) -> list[dict]:
        """Fetch chargebacks from last 90 days (from DB)."""
        if not self.db:
            return []

        try:
            cutoff = datetime.utcnow() - timedelta(days=90)
            chargebacks = await self.db.query(
                """
                SELECT * FROM chargebacks
                WHERE tenant_id = $1 AND customer_id = $2 AND created_at >= $3
                """,
                tenant_id,
                customer_id,
                cutoff,
            ).all()

            return [
                {
                    "id": c.id,
                    "order_id": c.order_id,
                    "created_at": c.created_at,
                    "amount": c.amount,
                }
                for c in chargebacks
            ]
        except Exception as e:
            logger.warning(f"Failed to fetch chargebacks: {e}")
            return []

    def _calculate_frequency_median(self, orders: list[dict]) -> float:
        """Calculate median days between orders."""
        if len(orders) < 2:
            return 0.0

        sorted_orders = sorted(orders, key=lambda x: x["created_at"], reverse=True)
        intervals = []

        for i in range(len(sorted_orders) - 1):
            interval_days = (
                sorted_orders[i]["created_at"] - sorted_orders[i + 1]["created_at"]
            ).days
            if interval_days > 0:
                intervals.append(interval_days)

        return median(intervals) if intervals else 0.0

    def _is_high_velocity(self, orders: list[dict]) -> bool:
        """Detect high velocity (>5 orders in last 30 days)."""
        cutoff = datetime.utcnow() - timedelta(days=30)
        recent_orders = sum(
            1 for o in orders if o["created_at"] >= cutoff
        )
        return recent_orders > 5

    def _compute_risk_score(
        self,
        refund_count: int,
        chargeback_count: int,
        high_value_orders: int,
        order_count: int,
    ) -> float:
        """
        Compute risk score as weighted sum (0.0 - 1.0).

        - Refunds >3 in 90d: +0.3
        - Chargebacks: +0.4 per chargeback
        - High-value orders: +0.2
        - High order count: increases chargeback weight
        """
        score = 0.0

        # Refund risk
        if refund_count > 3:
            score += min(0.3, 0.1 * (refund_count - 3))

        # Chargeback risk (weighted heavily)
        score += min(0.4, 0.15 * chargeback_count)

        # High-value order risk
        if high_value_orders > 0:
            score += min(0.2, 0.05 * high_value_orders)

        # Normalize to [0, 1]
        return min(1.0, score)

    async def _fetch_from_db(self, customer_id: int, tenant_id: int) -> OrderContext:
        """Fallback: fetch cached context from DB."""
        if not self.db:
            raise EnrichmentError("No DB session available for fallback")

        try:
            result = await self.db.query(
                """
                SELECT context_data FROM order_enrichment_cache
                WHERE tenant_id = $1 AND customer_id = $2
                """,
                tenant_id,
                customer_id,
            ).first()

            if result:
                data = json.loads(result.context_data)
                return OrderContext(**data)

            raise EnrichmentError(f"No cached order context for customer {customer_id}")
        except Exception as e:
            logger.error(f"DB fallback failed: {e}")
            raise EnrichmentError(f"Could not retrieve cached context: {e}")
