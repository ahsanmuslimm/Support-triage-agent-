"""S3.1: Customer & Account Enrichment."""

import json
import logging
from datetime import datetime
from typing import Optional

from .base import CacheManager, EnricherBase
from .exceptions import APITimeoutError, EnrichmentError
from .models import CustomerContext

logger = logging.getLogger(__name__)


class CustomerEnricher(EnricherBase):
    """Fetch and enrich customer profile, account age, orders, subscription status, and flags."""

    def __init__(
        self,
        cache_manager: CacheManager,
        shopify_client=None,
        stripe_client=None,
        db_session=None,
    ):
        super().__init__(cache_manager)
        self.shopify = shopify_client
        self.stripe = stripe_client
        self.db = db_session

    async def enrich(self, customer_id: int, tenant_id: int) -> CustomerContext:
        """
        Fetch and cache customer enrichment.

        Tries: Redis cache → Shopify/Stripe APIs → DB fallback
        """
        cache_key = self._make_cache_key(tenant_id, customer_id, "customer_enrichment")

        # Try cache first
        cached = await self.cache.get(cache_key)
        if cached:
            try:
                data = json.loads(cached)
                return CustomerContext(**data)
            except Exception as e:
                logger.warning(f"Failed to deserialize cached customer context: {e}")

        # Fetch from APIs
        try:
            await self._validate_tenant_isolation(tenant_id, customer_id, "customer")

            profile = await self._fetch_profile(customer_id, tenant_id)
            orders = await self._fetch_orders(customer_id, tenant_id)
            subscription = await self._fetch_subscription(customer_id, tenant_id)
            flags = await self._fetch_flags(customer_id, tenant_id)

            # Calculate account age
            account_created_at = profile.get("created_at")
            account_age_days = 0
            if account_created_at:
                account_age_days = (datetime.utcnow() - account_created_at).days

            # Calculate order statistics
            total_spent = sum(o.get("total", 0) for o in orders)
            order_count = len(orders)
            avg_order_value = total_spent / order_count if order_count > 0 else 0

            # Compute signals
            is_vip = total_spent > 1000
            is_at_risk = subscription.get("status") in ["paused", "cancelled"]
            is_fraud_flagged = "fraud_flag" in flags

            context = CustomerContext(
                customer_id=customer_id,
                tenant_id=tenant_id,
                name=profile.get("name", ""),
                email=profile.get("email", ""),
                phone=profile.get("phone"),
                account_created_at=account_created_at,
                account_age_days=account_age_days,
                order_count=order_count,
                total_spent=total_spent,
                last_order_date=orders[0].get("date") if orders else None,
                avg_order_value=avg_order_value,
                subscription_status=subscription.get("status", "none"),
                subscription_plan=subscription.get("plan", "none"),
                plan_value_usd=subscription.get("value_usd", 0),
                flags=flags,
                is_vip=is_vip,
                is_at_risk=is_at_risk,
                is_fraud_flagged=is_fraud_flagged,
                fetched_at=datetime.utcnow(),
            )

            # Cache the result
            try:
                cache_data = context.__dict__.copy()
                # Convert datetime to ISO format for JSON serialization
                for key in ["account_created_at", "last_order_date", "fetched_at"]:
                    if isinstance(cache_data.get(key), datetime):
                        cache_data[key] = cache_data[key].isoformat()

                await self.cache.set(
                    cache_key,
                    json.dumps(cache_data),
                    ex=context.cache_ttl_seconds,
                )
            except Exception as e:
                logger.warning(f"Failed to cache customer context: {e}")

            return context

        except APITimeoutError:
            raise
        except Exception as e:
            logger.error(f"Customer enrichment fetch failed: {e}")
            # Fallback to DB if available
            if self.db:
                return await self._fetch_from_db(customer_id, tenant_id)
            raise EnrichmentError(f"Failed to enrich customer {customer_id}: {e}")

    async def _fetch_profile(self, customer_id: int, tenant_id: int) -> dict:
        """Fetch customer profile from Shopify."""
        if not self.shopify:
            return {"name": "", "email": "", "created_at": None, "phone": None}

        try:
            customer = await self.shopify.customers.get(customer_id)
            first_name = customer.get("first_name", "")
            last_name = customer.get("last_name", "")
            return {
                "name": f"{first_name} {last_name}".strip(),
                "email": customer.get("email", ""),
                "phone": customer.get("phone"),
                "created_at": (
                    datetime.fromisoformat(customer["created_at"].replace("Z", "+00:00"))
                    if "created_at" in customer
                    else None
                ),
            }
        except Exception as e:
            logger.error(f"Failed to fetch profile from Shopify: {e}")
            raise APITimeoutError(f"Shopify API error: {e}")

    async def _fetch_orders(self, customer_id: int, tenant_id: int) -> list[dict]:
        """Fetch order history from Shopify."""
        if not self.shopify:
            return []

        try:
            orders = await self.shopify.orders.list(customer_id=customer_id)
            result = []
            for o in orders:
                result.append(
                    {
                        "id": o.get("id"),
                        "total": float(o.get("total_price", 0)),
                        "date": (
                            datetime.fromisoformat(o["created_at"].replace("Z", "+00:00"))
                            if "created_at" in o
                            else None
                        ),
                        "status": o.get("financial_status"),
                    }
                )
            # Sort by date descending (most recent first)
            result.sort(key=lambda x: x["date"] or datetime.min, reverse=True)
            return result
        except Exception as e:
            logger.error(f"Failed to fetch orders from Shopify: {e}")
            raise APITimeoutError(f"Shopify API error: {e}")

    async def _fetch_subscription(self, customer_id: int, tenant_id: int) -> dict:
        """Fetch subscription from Stripe."""
        if not self.stripe:
            return {"status": "none", "plan": "none", "value_usd": 0}

        try:
            subscriptions = await self.stripe.subscriptions.list(
                customer_id=customer_id
            )

            if subscriptions:
                sub = subscriptions[0]
                items = sub.get("items", {}).get("data", [])
                if items:
                    plan = items[0].get("plan", {})
                    return {
                        "status": sub.get("status", "unknown"),
                        "plan": plan.get("nickname", "custom"),
                        "value_usd": plan.get("amount", 0) / 100,
                    }

            return {"status": "none", "plan": "none", "value_usd": 0}
        except Exception as e:
            logger.error(f"Failed to fetch subscription from Stripe: {e}")
            raise APITimeoutError(f"Stripe API error: {e}")

    async def _fetch_flags(self, customer_id: int, tenant_id: int) -> list[str]:
        """Fetch account flags from internal DB."""
        if not self.db:
            return []

        try:
            flags = await self.db.query(
                """
                SELECT flag_name FROM customer_flags
                WHERE tenant_id = $1 AND customer_id = $2 AND is_active = TRUE
                """,
                tenant_id,
                customer_id,
            ).all()

            return [f.flag_name for f in flags]
        except Exception as e:
            logger.warning(f"Failed to fetch customer flags: {e}")
            return []

    async def _fetch_from_db(self, customer_id: int, tenant_id: int) -> CustomerContext:
        """Fallback: fetch cached context from DB."""
        if not self.db:
            raise EnrichmentError("No DB session available for fallback")

        try:
            result = await self.db.query(
                """
                SELECT context_data FROM customer_enrichment_cache
                WHERE tenant_id = $1 AND customer_id = $2
                """,
                tenant_id,
                customer_id,
            ).first()

            if result:
                data = json.loads(result.context_data)
                return CustomerContext(**data)

            raise EnrichmentError(f"No cached context for customer {customer_id}")
        except Exception as e:
            logger.error(f"DB fallback failed: {e}")
            raise EnrichmentError(f"Could not retrieve cached context: {e}")
