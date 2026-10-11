"""Enrichment data layer for triage context collection."""

from .models import (
    CustomerContext,
    OrderContext,
    BillingContext,
    SentimentContext,
    EnrichmentBundle,
)
from .customer_enricher import CustomerEnricher
from .order_enricher import OrderEnricher
from .billing_enricher import BillingEnricher
from .exceptions import EnrichmentError, APITimeoutError, CacheError

__all__ = [
    # Models
    "CustomerContext",
    "OrderContext",
    "BillingContext",
    "SentimentContext",
    "EnrichmentBundle",
    # Enrichers
    "CustomerEnricher",
    "OrderEnricher",
    "BillingEnricher",
    # Exceptions
    "EnrichmentError",
    "APITimeoutError",
    "CacheError",
]
