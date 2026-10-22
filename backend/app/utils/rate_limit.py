"""In-process per-IP rate limiting for write / outbound endpoints (S2).

This service has no API-key auth: any caller can trigger server-side outbound
audits (seconds of egress + cost) or hammer the anonymous contribution queue.
A simple fixed-window counter per client IP caps abuse without adding a auth
system. It is intentionally process-local (single-process demo deployments)
and resettable so the full TestClient suite is never throttled.

Window semantics: this is a **fixed window** (bucket resets at a wall-clock
boundary), NOT a sliding window. A caller can send up to ``_REQUESTS`` just
before a boundary and another ``_REQUESTS`` just after it, i.e. roughly 2x the
quota across the boundary; that accepted trade-off keeps the counter O(1) and
needs no timer heap. Callers needing strict sliding limits should front the
service with a gateway that enforces them.

Stale-bucket hygiene: expired IP keys are swept out opportunistically (and on
demand via :func:`prune_expired`) so a long-running process does not grow the
``_windows`` dict without bound as unseen IPs come and go. The tracked-IP
count is also bounded: once it exceeds :data:`_MAX_TRACKED_IPS`, expired
buckets are dropped and, if still over capacity, the oldest buckets are
evicted first.

Tune with :func:`configure` / clear with :func:`reset` (used by tests).

Trusted-proxy mode (R3-2): by default the bucket key is the direct TCP peer
(``request.client.host``), so a caller can NOT forge a quota identity by
setting ``X-Forwarded-For``. When the service runs behind a reverse proxy /
cloud LB that it does not directly expose, every request's TCP peer is the
proxy and all callers would share one bucket. Set the comma-separated
``TRUSTED_PROXIES`` env var to the proxy IPs; only then is ``X-Forwarded-For``
consulted, and only the first hop *outside* the trusted set is trusted as the
real client identity.
"""

import os
import threading
import time

from fastapi import HTTPException, Request

# Default quota: N requests per window, per client IP.
_REQUESTS: int = 60
_WINDOW_SECONDS: float = 60.0
# Hard bound on tracked IP buckets: beyond this, expired buckets are swept and
# oldest-first eviction keeps the dict bounded under a long-running process.
_MAX_TRACKED_IPS: int = 4096

_lock = threading.Lock()
# ip -> (window_start_monotonic, count)
_windows: dict[str, tuple[float, int]] = {}
# Direct peer IPs whose X-Forwarded-For we are allowed to honour.
_trusted_proxies: set[str] = set()


def configure(requests: int, window_seconds: float) -> None:
    """Override the quota (used by tests to set a tiny limit)."""
    global _REQUESTS, _WINDOW_SECONDS
    with _lock:
        _REQUESTS = requests
        _WINDOW_SECONDS = window_seconds
        _windows.clear()


def configure_trusted_proxies(proxies: str | None = None) -> None:
    """Set the trusted proxy peer IPs.

    ``proxies`` is a comma-separated list. If omitted, read the
    ``TRUSTED_PROXIES`` env var. An empty list (the default) means XFF is
    ignored for everyone and the TCP peer is always the identity.
    """
    global _trusted_proxies
    if proxies is None:
        proxies = os.getenv("TRUSTED_PROXIES", "")
    with _lock:
        _trusted_proxies = {p.strip() for p in proxies.split(",") if p.strip()}


def reset() -> None:
    """Clear all per-IP counters and proxy config (call between tests)."""
    global _trusted_proxies
    with _lock:
        _windows.clear()
        _trusted_proxies = set()


def prune_expired() -> int:
    """Drop buckets whose fixed window has fully elapsed; return the count removed.

    Long-running processes see many transient source IPs; without pruning the
    ``_windows`` dict grows unbounded. Expired buckets carry no live quota, so
    dropping them changes nothing for active callers.
    """
    now = time.monotonic()
    removed = 0
    with _lock:
        stale = [
            ip
            for ip, (start, _count) in _windows.items()
            if now - start > _WINDOW_SECONDS
        ]
        for ip in stale:
            _windows.pop(ip, None)
            removed += 1
    return removed


def _sweep_locked(now: float) -> None:
    """Caller holds ``_lock``. Drop expired buckets; if the tracked-IP count is
    still over :data:`_MAX_TRACKED_IPS`, evict oldest-start buckets first."""
    stale = [
        ip for ip, (start, _count) in _windows.items() if now - start > _WINDOW_SECONDS
    ]
    for ip in stale:
        _windows.pop(ip, None)
    if len(_windows) > _MAX_TRACKED_IPS:
        ordered = sorted(_windows.items(), key=lambda kv: kv[1][0])
        overflow = len(_windows) - _MAX_TRACKED_IPS
        for ip, _ in ordered[:overflow]:
            _windows.pop(ip, None)


def _client_ip(request: Request) -> str:
    """Resolve the bucket key for *request*.

    Default (no TRUSTED_PROXIES): the direct TCP peer. This is deliberate — it
    means a caller cannot supply ``X-Forwarded-For`` to steal another identity's
    quota (or, conversely, to exhaust a victim's bucket).

    Only when the direct peer is itself a configured trusted proxy do we look
    at ``X-Forwarded-For`` and take the rightmost hop that is NOT a trusted
    proxy (each trusted proxy appends itself on the right, so walking right to
    left and skipping trusted hops yields the real client).
    """
    peer = request.client.host if request.client else None
    if peer is None:
        return "unknown"
    if _trusted_proxies and peer in _trusted_proxies:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            hops = [h.strip() for h in xff.split(",") if h.strip()]
            for hop in reversed(hops):
                if hop not in _trusted_proxies:
                    return hop
            # Every hop is trusted; fall through to the peer.
    return peer


def _check(ip: str) -> bool:
    now = time.monotonic()
    with _lock:
        start, count = _windows.get(ip, (now, 0))
        if now - start > _WINDOW_SECONDS:
            start, count = now, 0
        count += 1
        _windows[ip] = (start, count)
        # Opportunistic stale sweep: keep the dict bounded for long-running
        # processes instead of accumulating every IP that ever called once.
        if len(_windows) > _MAX_TRACKED_IPS:
            _sweep_locked(now)
        return count <= _REQUESTS


async def enforce_rate_limit(request: Request) -> None:
    """FastAPI dependency: reject bursty callers with HTTP 429."""
    ip = _client_ip(request)
    if not _check(ip):
        raise HTTPException(
            status_code=429, detail="Too many requests; please slow down"
        )


# Read TRUSTED_PROXIES at import so a deployment configures it purely by env.
configure_trusted_proxies()
