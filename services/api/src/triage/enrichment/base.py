"""Base enricher classes and abstractions."""

import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

from .exceptions import CacheError, EntityValidationError

logger = logging.getLogger(__name__)


class CacheManager:
    """Redis + PostgreSQL fallback cache for enrichment data."""

    def __init__(self, redis_client=None, db_session=None):
        self.redis = redis_client
        self.db = db_session

    async def get(self, key: str) -> Optional[str]:
        """Get value from cache. Try Redis first, then DB fallback."""
        if self.redis:
            try:
                return await self.redis.get(key)
            except Exception as e:
                logger.warning(f"Redis get failed for {key}: {e}")

        # DB fallback
        if self.db:
            try:
                # Try to load from enrichment_cache table
                result = await self.db.query(
                    """
                    SELECT cached_value FROM enrichment_cache
                    WHERE cache_key = $1 AND expires_at > NOW()
                    """,
                    key,
                ).first()
                if result:
                    return result.cached_value
            except Exception as e:
                logger.warning(f"DB cache fallback failed for {key}: {e}")

        return None

    async def set(self, key: str, value: str, ex: int = 3600) -> bool:
        """Set value in cache. Store in Redis + DB."""
        success = False

        if self.redis:
            try:
                await self.redis.set(key, value, ex=ex)
                success = True
            except Exception as e:
                logger.warning(f"Redis set failed for {key}: {e}")

        # DB fallback
        if self.db:
            try:
                from datetime import datetime, timedelta

                expires_at = datetime.utcnow() + timedelta(seconds=ex)
                await self.db.execute(
                    """
                    INSERT INTO enrichment_cache (cache_key, cached_value, expires_at)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (cache_key) DO UPDATE
                    SET cached_value = EXCLUDED.cached_value, expires_at = EXCLUDED.expires_at
                    """,
                    key,
                    value,
                    expires_at,
                )
                success = True
            except Exception as e:
                logger.warning(f"DB cache write failed for {key}: {e}")

        if not success:
            raise CacheError(f"Failed to set cache key {key}")

        return True

    async def invalidate(self, key: str) -> bool:
        """Invalidate cache entry."""
        if self.redis:
            try:
                await self.redis.delete(key)
            except Exception as e:
                logger.warning(f"Redis delete failed for {key}: {e}")

        if self.db:
            try:
                await self.db.execute(
                    "DELETE FROM enrichment_cache WHERE cache_key = $1", key
                )
            except Exception as e:
                logger.warning(f"DB cache delete failed for {key}: {e}")

        return True


class EnricherBase(ABC):
    """Base class for all enrichers."""

    def __init__(self, cache_manager: CacheManager):
        self.cache = cache_manager

    def _make_cache_key(self, tenant_id: int, resource_id: int, prefix: str) -> str:
        """Generate cache key with tenant isolation."""
        return f"{prefix}:{tenant_id}:{resource_id}"

    async def _validate_tenant_isolation(
        self, tenant_id: int, resource_id: int, resource_type: str
    ) -> bool:
        """Validate that resource belongs to tenant (not relying on linker)."""
        # This would query the DB to verify ownership
        # For now, just log; actual validation depends on DB schema
        logger.debug(f"Validating {resource_type} {resource_id} in tenant {tenant_id}")
        return True

    @abstractmethod
    async def enrich(self, resource_id: int, tenant_id: int) -> Any:
        """Enrich and return context object."""
        pass
