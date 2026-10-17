"""Enrichment layer exceptions."""


class EnrichmentError(Exception):
    """Base enrichment error."""



class APITimeoutError(EnrichmentError):
    """External API timeout during enrichment."""



class CacheError(EnrichmentError):
    """Cache operation error."""



class EntityValidationError(EnrichmentError):
    """Entity validation failed (e.g., tenant mismatch)."""



class WebhookSignatureError(EnrichmentError):
    """Webhook signature validation failed."""

