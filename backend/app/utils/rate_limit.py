"""In-process per-IP rate limiting for write / outbound endpoints (S2).

This service has no API-key auth: any caller can trigger server-side outbound
audits (seconds of egress + cost) or hammer the anonymous contribution queue.
A simple fixed-window counter per client IP caps abuse without adding a auth
system. It is intentionally process-local (single-process demo deployments)
and resettable so the full TestClient suite is never throttled.

Tune with :func:`configure` / clear with :func:`reset` (used by tests).
"""
import threading
import time

from fastapi import HTTPException, Request

# Default quota: N requests per rolling window, per client IP.
_REQUESTS: int = 60
_WINDOW_SECONDS: float = 60.0

_lock = threading.Lock()
# ip -> (window_start_monotonic, count)
_windows: dict[str, tuple[float, int]] = {}


def configure(requests: int, window_seconds: float) -> None:
    """Override the quota (used by tests to set a tiny limit)."""
    global _REQUESTS, _WINDOW_SECONDS
    with _lock:
        _REQUESTS = requests
        _WINDOW_SECONDS = window_seconds
        _windows.clear()


def reset() -> None:
    """Clear all per-IP counters (call between tests)."""
    with _lock:
        _windows.clear()


def _check(ip: str) -> bool:
    now = time.monotonic()
    with _lock:
        start, count = _windows.get(ip, (now, 0))
        if now - start > _WINDOW_SECONDS:
            start, count = now, 0
        count += 1
        _windows[ip] = (start, count)
        return count <= _REQUESTS


async def enforce_rate_limit(request: Request) -> None:
    """FastAPI dependency: reject bursty callers with HTTP 429."""
    ip = request.client.host if request.client else "unknown"
    if not _check(ip):
        raise HTTPException(status_code=429, detail="Too many requests; please slow down")
