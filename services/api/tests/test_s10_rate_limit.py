"""Tests for S10.1, S10.2 - Rate Limiting."""

import time

from triage.api.rate_limit import RateLimitBypass, RateLimiter


class TestRateLimiter:
    """Test rate limiting."""

    def test_check_limit_allowed(self):
        """Test request allowed under limit."""
        limiter = RateLimiter(requests_per_minute=1000)

        allowed, headers = limiter.check_limit("key_123")

        assert allowed
        assert "RateLimit-Limit" in headers
        assert headers["RateLimit-Limit"] == 1000
        assert headers["RateLimit-Remaining"] >= 0

    def test_check_limit_headers(self):
        """Test rate limit headers."""
        limiter = RateLimiter(requests_per_minute=100)

        allowed, headers = limiter.check_limit("key_test")

        assert "RateLimit-Limit" in headers
        assert "RateLimit-Remaining" in headers
        assert "RateLimit-Reset" in headers
        assert headers["RateLimit-Limit"] == 100

    def test_rate_limit_exhaustion(self):
        """Test exhausting rate limit."""
        limiter = RateLimiter(requests_per_minute=5)

        # Make 5 requests (fill bucket)
        for i in range(5):
            allowed, _ = limiter.check_limit("key_exhaust")
            assert allowed

        # 6th request should fail
        allowed, _ = limiter.check_limit("key_exhaust")
        assert not allowed

    def test_rate_limit_per_key(self):
        """Test rate limit is per-key."""
        limiter = RateLimiter(requests_per_minute=2)

        # Key 1: 2 requests
        limiter.check_limit("key_a")
        limiter.check_limit("key_a")
        allowed, _ = limiter.check_limit("key_a")
        assert not allowed

        # Key 2: should have own limit
        allowed, _ = limiter.check_limit("key_b")
        assert allowed

    def test_get_status(self):
        """Test getting rate limit status."""
        limiter = RateLimiter(requests_per_minute=100)

        # Make a request
        limiter.check_limit("key_status")

        status = limiter.get_status("key_status")

        assert status["RateLimit-Limit"] == 100
        assert status["RateLimit-Remaining"] <= 99

    def test_reset_single_key(self):
        """Test resetting rate limit for single key."""
        limiter = RateLimiter(requests_per_minute=2)

        # Exhaust key
        limiter.check_limit("key_reset")
        limiter.check_limit("key_reset")
        limiter.check_limit("key_reset")

        # Reset
        limiter.reset("key_reset")

        # Should work again
        allowed, _ = limiter.check_limit("key_reset")
        assert allowed

    def test_reset_all(self):
        """Test resetting all rate limits."""
        limiter = RateLimiter(requests_per_minute=2)

        # Exhaust multiple keys
        limiter.check_limit("key_x")
        limiter.check_limit("key_x")
        limiter.check_limit("key_y")
        limiter.check_limit("key_y")

        # Reset all
        limiter.reset()

        # Both should work
        allowed_x, _ = limiter.check_limit("key_x")
        allowed_y, _ = limiter.check_limit("key_y")

        assert allowed_x
        assert allowed_y

    def test_token_bucket_refill(self):
        """Test token bucket refills over time."""
        limiter = RateLimiter(requests_per_minute=60)

        # Make requests
        for _ in range(30):
            allowed, _ = limiter.check_limit("key_refill")
            assert allowed

        # Wait a bit and more should be available
        time.sleep(0.1)

        allowed, _ = limiter.check_limit("key_refill")
        assert allowed


class TestRateLimitBypass:
    """Test rate limit bypass whitelist."""

    def test_add_bypass(self):
        """Test adding key to bypass list."""
        bypass = RateLimitBypass()

        bypass.add_bypass("admin_key_1")

        assert bypass.is_bypassed("admin_key_1")

    def test_remove_bypass(self):
        """Test removing key from bypass list."""
        bypass = RateLimitBypass()

        bypass.add_bypass("admin_key_2")
        bypass.remove_bypass("admin_key_2")

        assert not bypass.is_bypassed("admin_key_2")

    def test_bypass_not_in_list(self):
        """Test key not in bypass list."""
        bypass = RateLimitBypass()

        assert not bypass.is_bypassed("normal_key")

    def test_multiple_bypasses(self):
        """Test multiple keys in bypass list."""
        bypass = RateLimitBypass()

        bypass.add_bypass("admin_1")
        bypass.add_bypass("admin_2")
        bypass.add_bypass("admin_3")

        assert bypass.is_bypassed("admin_1")
        assert bypass.is_bypassed("admin_2")
        assert bypass.is_bypassed("admin_3")
        assert not bypass.is_bypassed("user_1")
