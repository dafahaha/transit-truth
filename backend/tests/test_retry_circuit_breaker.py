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
