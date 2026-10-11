"""Rate limiting for API (S10.1, S10.2)."""

import time
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from collections import defaultdict


class RateLimiter:
    """Token bucket rate limiter for API keys."""

    def __init__(self, requests_per_minute: int = 1000):
        """Initialize rate limiter.

        Args:
            requests_per_minute: Max requests per minute per key
        """
        self.requests_per_minute = requests_per_minute
        self.requests_per_second = requests_per_minute / 60.0
        # Store: key_id -> {"tokens": float, "last_update": float}
        self._buckets: Dict[str, Dict] = defaultdict(lambda: {
            "tokens": self.requests_per_second * 60,
            "last_update": time.time(),
        })

    def check_limit(self, key_id: str) -> Tuple[bool, Dict[str, int]]:
        """Check if request allowed under rate limit.

        Args:
            key_id: API key ID

        Returns:
            (allowed: bool, headers: Dict[str, int])
                headers contains RateLimit-Limit, RateLimit-Remaining, RateLimit-Reset
        """
        now = time.time()
        bucket = self._buckets[key_id]

        # Add tokens based on time elapsed
        time_elapsed = now - bucket["last_update"]
        bucket["tokens"] = min(
            self.requests_per_second * 60,
            bucket["tokens"] + time_elapsed * self.requests_per_second,
        )
        bucket["last_update"] = now

        # Refill window
        window_start = datetime.utcnow() + timedelta(minutes=1)
        reset_timestamp = int(window_start.timestamp())

        limit_headers = {
            "RateLimit-Limit": self.requests_per_minute,
            "RateLimit-Reset": reset_timestamp,
        }

        # Check if token available
        if bucket["tokens"] >= 1:
            bucket["tokens"] -= 1
            remaining = int(bucket["tokens"])
            limit_headers["RateLimit-Remaining"] = remaining
            return True, limit_headers
        else:
            # No tokens available
            limit_headers["RateLimit-Remaining"] = 0
            return False, limit_headers

    def get_status(self, key_id: str) -> Dict[str, int]:
        """Get current rate limit status.

        Args:
            key_id: API key ID

        Returns:
            Dict with limit, remaining, reset
        """
        bucket = self._buckets[key_id]
        window_start = datetime.utcnow() + timedelta(minutes=1)
        reset_timestamp = int(window_start.timestamp())

        return {
            "RateLimit-Limit": self.requests_per_minute,
            "RateLimit-Remaining": int(bucket["tokens"]),
            "RateLimit-Reset": reset_timestamp,
        }

    def reset(self, key_id: Optional[str] = None):
        """Reset rate limit for key(s).

        Args:
            key_id: Key to reset, or None to reset all
        """
        if key_id:
            if key_id in self._buckets:
                del self._buckets[key_id]
        else:
            self._buckets.clear()


class RateLimitBypass:
    """Whitelist for rate limit bypass (admin keys)."""

    def __init__(self):
        self.bypassed_keys: set = set()

    def add_bypass(self, key_id: str):
        """Add key to bypass list."""
        self.bypassed_keys.add(key_id)

    def remove_bypass(self, key_id: str):
        """Remove key from bypass list."""
        self.bypassed_keys.discard(key_id)

    def is_bypassed(self, key_id: str) -> bool:
        """Check if key bypasses rate limit."""
        return key_id in self.bypassed_keys
