"""S3.3: Billing & Payment History Context."""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from .base import CacheManager, EnricherBase
from .exceptions import APITimeoutError, EnrichmentError
from .models import BillingContext

logger = logging.getLogger(__name__)


class BillingEnricher(EnricherBase):
    """Enrich payment methods, billing history, and churn signals."""

    def __init__(
        self,
        cache_manager: CacheManager,
        stripe_client=None,
        db_session=None,
    ):
        super().__init__(cache_manager)
        self.stripe = stripe_client
        self.db = db_session

    async def enrich(self, customer_id: int, tenant_id: int) -> BillingContext:
        """
        Fetch and cache billing enrichment.

        Tries: Redis cache → Stripe API → DB fallback
        """
        cache_key = self._make_cache_key(tenant_id, customer_id, "billing_enrichment")

        # Try cache first
        cached = await self.cache.get(cache_key)
        if cached:
            try:
                data = json.loads(cached)
                return BillingContext(**data)
            except Exception as e:
                logger.warning(f"Failed to deserialize cached billing context: {e}")

        # Fetch from APIs
        try:
            await self._validate_tenant_isolation(tenant_id, customer_id, "customer")

            payment_methods = await self._fetch_payment_methods(customer_id, tenant_id)
            invoices_90d = await self._fetch_invoices_90d(customer_id, tenant_id)
            subscription = await self._fetch_subscription(customer_id, tenant_id)

            # Calculate payment statistics
            payment_method_count = len(payment_methods)
            primary_payment_type = (
                payment_methods[0].get("type", "unknown")
                if payment_methods
                else "unknown"
            )

            # Card expiry check
            card_expiring_soon = False
            card_expiry_days = None
            if payment_methods and payment_methods[0].get("type") == "card":
                expiry_date = payment_methods[0].get("expiry_date")
                if expiry_date:
                    days_to_expiry = (expiry_date - datetime.utcnow().date()).days
                    card_expiry_days = max(0, days_to_expiry)
                    card_expiring_soon = 0 <= days_to_expiry < 30

            # Calculate payment health
            successful = sum(1 for i in invoices_90d if i.get("status") == "paid")
            failed = sum(1 for i in invoices_90d if i.get("status") == "failed")
            total_invoices = len(invoices_90d)
            payment_success_rate = (
                successful / total_invoices if total_invoices > 0 else 1.0
            )

            # Dunning and churn risk
            dunning_stage = subscription.get("dunning_stage", "none")
            dunning_days = subscription.get("dunning_days", 0)
            is_churn_risk = (
                dunning_stage in ["final", "suspended"] or failed >= 3
            )

            # Address and verification (placeholder)
            billing_address_valid = True
            phone_verified = False

            context = BillingContext(
                customer_id=customer_id,
                tenant_id=tenant_id,
                payment_method_count=payment_method_count,
                primary_payment_type=primary_payment_type,
                card_expiring_soon=card_expiring_soon,
                card_expiry_days=card_expiry_days,
                failed_payments_90d=failed,
                successful_payments_90d=successful,
                payment_success_rate=payment_success_rate,
                dunning_stage=dunning_stage,
                is_churn_risk=is_churn_risk,
                dunning_days=dunning_days,
                billing_address_valid=billing_address_valid,
                phone_verified=phone_verified,
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
                logger.warning(f"Failed to cache billing context: {e}")

            return context

        except APITimeoutError:
            raise
        except Exception as e:
            logger.error(f"Billing enrichment fetch failed: {e}")
            if self.db:
                return await self._fetch_from_db(customer_id, tenant_id)
            raise EnrichmentError(
                f"Failed to enrich billing for customer {customer_id}: {e}"
            )

    async def _fetch_payment_methods(
        self, customer_id: int, tenant_id: int
    ) -> list[dict]:
        """Fetch payment methods from Stripe."""
        if not self.stripe:
            return []

        try:
            payment_methods = await self.stripe.payment_methods.list(
                customer_id=customer_id
            )
            result = []

            for pm in payment_methods:
                method_type = pm.get("type", "unknown")
                data = {
                    "id": pm.get("id"),
                    "type": method_type,
                }

                if method_type == "card":
                    card = pm.get("card", {})
                    exp_month = card.get("exp_month")
                    exp_year = card.get("exp_year")
                    if exp_month and exp_year:
                        # Last day of expiry month
                        if exp_month == 12:
                            expiry_date = datetime(exp_year + 1, 1, 1).date() - timedelta(
                                days=1
                            )
                        else:
                            expiry_date = (
                                datetime(exp_year, exp_month + 1, 1).date()
                                - timedelta(days=1)
                            )
                        data["expiry_date"] = expiry_date

                result.append(data)

            return result
        except Exception as e:
            logger.error(f"Failed to fetch payment methods from Stripe: {e}")
            raise APITimeoutError(f"Stripe API error: {e}")

    async def _fetch_invoices_90d(self, customer_id: int, tenant_id: int) -> list[dict]:
        """Fetch invoices from last 90 days."""
        if not self.stripe:
            return []

        try:
            cutoff = int(
                (datetime.utcnow() - timedelta(days=90)).timestamp()
            )
            invoices = await self.stripe.invoices.list(
                customer_id=customer_id, created={"gte": cutoff}
            )
            result = []

            for inv in invoices:
                result.append(
                    {
                        "id": inv.get("id"),
                        "status": inv.get("status"),  # 'paid', 'failed', 'draft', etc.
                        "amount": inv.get("amount_paid", 0),
                        "created_at": datetime.fromtimestamp(inv.get("created")),
                    }
                )

            return result
        except Exception as e:
            logger.error(f"Failed to fetch invoices from Stripe: {e}")
            raise APITimeoutError(f"Stripe API error: {e}")

    async def _fetch_subscription(self, customer_id: int, tenant_id: int) -> dict:
        """Fetch subscription and dunning info from Stripe."""
        if not self.stripe:
            return {"dunning_stage": "none", "dunning_days": 0}

        try:
            subscriptions = await self.stripe.subscriptions.list(
                customer_id=customer_id
            )

            if subscriptions:
                sub = subscriptions[0]

                # Map Stripe dunning status to our stages
                # Based on subscription status and payment_settings
                status = sub.get("status")
                payment_settings = sub.get("payment_settings", {})
                
                # Determine dunning stage from subscription status
                if status == "active":
                    dunning_stage = "none"
                elif status == "past_due":
                    # Check payment settings for retry logic
                    dunning_stage = "initial"
                elif status == "unpaid":
                    dunning_stage = "escalation"
                elif status == "canceled":
                    dunning_stage = "final"
                else:
                    dunning_stage = "none"

                # Calculate dunning days (from first failed payment)
                dunning_days = 0
                if dunning_stage != "none":
                    # In real implementation, fetch from dunning history
                    # For now, estimate from payment_settings retry info
                    dunning_days = 0

                return {
                    "dunning_stage": dunning_stage,
                    "dunning_days": dunning_days,
                }

            return {"dunning_stage": "none", "dunning_days": 0}
        except Exception as e:
            logger.warning(f"Failed to fetch subscription: {e}")
            return {"dunning_stage": "none", "dunning_days": 0}

    async def _fetch_from_db(self, customer_id: int, tenant_id: int) -> BillingContext:
        """Fallback: fetch cached context from DB."""
        if not self.db:
            raise EnrichmentError("No DB session available for fallback")

        try:
            result = await self.db.query(
                """
                SELECT context_data FROM billing_enrichment_cache
                WHERE tenant_id = $1 AND customer_id = $2
                """,
                tenant_id,
                customer_id,
            ).first()

            if result:
                data = json.loads(result.context_data)
                return BillingContext(**data)

            raise EnrichmentError(f"No cached billing context for customer {customer_id}")
        except Exception as e:
            logger.error(f"DB fallback failed: {e}")
            raise EnrichmentError(f"Could not retrieve cached context: {e}")
