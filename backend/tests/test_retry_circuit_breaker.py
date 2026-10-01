"""Tests for CircuitBreaker half-open rate limiting."""
import time
from app.core.retry import CircuitBreaker


class TestCircuitBreakerHalfOpen:
    def test_half_open_limits_concurrent_probes(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.05,
                            half_open_max_requests=2)
        # Trip it.
        cb.record_failure("e1")
        cb.record_failure("e2")
        assert cb.state == "OPEN"

        # Wait past recovery window.
        time.sleep(0.06)

        # First two calls pass; third must be blocked until success/failure.
        assert cb.can_execute() is True
        assert cb.can_execute() is True
        assert cb.can_execute() is False

    def test_half_open_success_closes(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.05,
                            half_open_max_requests=2)
        cb.record_failure("e1")
        cb.record_failure("e2")
        time.sleep(0.06)
        assert cb.can_execute() is True
        cb.record_success()
        assert cb.state == "CLOSED"

    def test_half_open_failure_trips_back(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.05,
                            half_open_max_requests=2)
        cb.record_failure("e1")
        cb.record_failure("e2")
        time.sleep(0.06)
        assert cb.can_execute() is True
        cb.record_failure("e2 again")
        assert cb.state == "OPEN"


# ─── Round-2 fix: P2-1 HTTP-date Retry-After ─────────────────────────
from app.core.retry import parse_retry_after
from datetime import datetime, timedelta, timezone


class TestRetryAfterHeader:
    def test_numeric_retry_after(self):
        assert parse_retry_after({"retry-after": "120"}) == 120.0

    def test_http_date_retry_after_parses(self):
        # 60 seconds in the future -> a positive, finite wait (<=300 cap)
        future = datetime.now(timezone.utc) + timedelta(seconds=60)
        rfc = future.strftime("%a, %d %b %Y %H:%M:%S GMT")
        v = parse_retry_after({"retry-after": rfc})
        assert v is not None, "HTTP-date Retry-After returned None (datetime NameError?)"
        assert 0 < v <= 300.0

    def test_garbage_retry_after_returns_none(self):
        assert parse_retry_after({"retry-after": "not-a-date"}) is None
