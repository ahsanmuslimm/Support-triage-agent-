"""Enrichment layer exceptions."""


class EnrichmentError(Exception):
    """Base enrichment error."""

    pass


class APITimeoutError(EnrichmentError):
    """External API timeout during enrichment."""

    pass


class CacheError(EnrichmentError):
    """Cache operation error."""

    pass


class EntityValidationError(EnrichmentError):
    """Entity validation failed (e.g., tenant mismatch)."""

    pass


class WebhookSignatureError(EnrichmentError):
    """Webhook signature validation failed."""

    pass
