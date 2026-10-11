"""SSRF guard for outbound requests initiated by the API.

Every server-side outbound request targets a caller-supplied ``base_url``.
Without restrictions an attacker could point the server at internal services
(cloud metadata at 169.254.169.254, loopback admin ports, RFC1918 hosts).

Defense in depth, two layers:

1. **URL-level check** (:func:`validate_public_url`): only ``http``/``https``
   schemes; the host must not be (or resolve to) a loopback / private /
   link-local / reserved / unspecified address. DNS is resolved here so that
   hostnames pointing at internal IPs are blocked up front.

2. **Connect-time check** (:class:`GuardedAsyncNetworkBackend` /
   :class:`SSRFAsyncTransport`): the URL-level check resolves the hostname
   *once*, but httpx re-resolves it when it actually connects. A hostile DNS
   (TTL=0 rebinding) can return a public IP for layer 1 and an internal IP a
   few milliseconds later for the real connect. We wrap httpcore's network
   backend and re-validate the *actual* peer sockaddr the kernel connected to,
   so even a second, poisoned resolution can never reach an internal address.

Error messages are intentionally generic: they never leak the resolved
internal address back to the caller.
"""

import asyncio
import ipaddress
import logging
import socket
from typing import Optional

import httpx
from fastapi import HTTPException

logger = logging.getLogger(__name__)

ALLOWED_SCHEMES = {"http", "https"}

# Non-routable ranges that Python's ``ipaddress`` safety flags do NOT already
# cover (verified empirically). Python flags catch loopback, RFC1918,
# link-local, multicast, reserved, unspecified, the TEST-NETs and the
# benchmarking range; RFC6598 CGNAT is the one remaining public-looking block
# that must never be proxied (it is also Tailscale's default internal range).
# Default-deny every address in these networks.
_EXTRA_BLOCKED_V4 = (
    ipaddress.ip_network("100.64.0.0/10"),  # RFC6598 shared address space / CGNAT
)


def _ip_for_v4_network_check(ip: "ipaddress._BaseAddress"):
    """Return the IPv4 address to test against ``_EXTRA_BLOCKED_V4``.

    Plain IPv4 addresses test as themselves; IPv4-mapped IPv6 addresses
    (``::ffff:a.b.c.d``) look through to the embedded v4 address.
    """
    if ip.version == 4:
        return ip
    return getattr(ip, "ipv4_mapped", None)


def _is_blocked_ip(ip_str: str) -> bool:
    """Return True if *ip_str* is an address we must never proxy to."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # unparseable -> fail closed
    if (
        ip.is_loopback  # 127.0.0.0/8, ::1
        or ip.is_private  # 10/8, 172.16/12, 192.168/16, fc00::/7, TEST-NET, ...
        or ip.is_link_local  # 169.254.0.0/16, fe80::/10
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified  # 0.0.0.0, ::
    ):
        return True
    v4 = _ip_for_v4_network_check(ip)
    if v4 is not None:
        for net in _EXTRA_BLOCKED_V4:
            if v4 in net:
                logger.warning("Blocked non-public address %s (range %s)", ip_str, net)
                return True
    return False


def _peer_ip(sockaddr) -> Optional[str]:
    """Extract the IP string from a getaddrinfo-style sockaddr tuple.

    TCP sockaddrs are ``(host, port)`` (IPv4) or ``(host, port, flowinfo,
    scope_id)`` (IPv6). Anything else (uds / unexpected shape) yields None.
    """
    if isinstance(sockaddr, (tuple, list)) and sockaddr:
        return str(sockaddr[0])
    if isinstance(sockaddr, str):
        return sockaddr
    return None


def validate_public_url(url: str) -> httpx.URL:
    """Parse *url*, enforce http(s) and a public target.

    Raises ``ValueError`` with a generic, safe message on any violation.
    The caller is responsible for turning that into an HTTP 400.
    """
    try:
        parsed = httpx.URL(url)
    except Exception as exc:  # malformed URL
        raise ValueError("Invalid URL") from exc

    if parsed.scheme not in ALLOWED_SCHEMES:
        raise ValueError("Only http:// and https:// URLs are allowed")

    host = parsed.host
    if not host:
        raise ValueError("URL must include a host")

    # Resolve the hostname and check every A/AAAA record. This blocks both
    # raw internal IP literals and hostnames that resolve to internal IPs.
    try:
        addr_infos = socket.getaddrinfo(host, parsed.port, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError, OSError) as exc:
        raise ValueError("Unable to resolve URL host") from exc

    for info in addr_infos:
        ip_str = info[4][0]
        if _is_blocked_ip(ip_str):
            logger.warning(
                "Blocked outbound request to host=%s (resolves to %s)", host, ip_str
            )
            raise ValueError("Target is not a public internet address")

    return parsed


def require_public_url(url: str) -> httpx.URL:
    """validate_public_url, raising HTTP 400 on violation (FastAPI helper)."""
    try:
        return validate_public_url(url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


async def require_public_url_async(url: str) -> httpx.URL:
    """Async variant of :func:`require_public_url`.

    ``socket.getaddrinfo`` is a blocking syscall; running it directly inside a
    FastAPI coroutine stalls the event loop on every outbound check (N6).
    Offload it to a thread while keeping the same validation semantics.
    """
    try:
        return await asyncio.to_thread(validate_public_url, url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ─── Connect-time SSRF re-validation (DNS rebinding TOCTOU, N1) ──────────


class GuardedAsyncNetworkBackend:
    """Wrap httpcore's default async network backend.

    After the inner backend establishes a TCP connection we read back the
    *actual* peer address the kernel connected to and re-run the IP blocklist.
    If the second DNS resolution (the one httpx does at connect time) returned
    an internal address, we close the stream and raise ``ConnectError`` so the
    request never reaches the internal service.

    ``connect_unix_socket`` is passed through unchanged: UDS paths are
    operator-controlled filesystem paths, never a caller-supplied network
    target, and this API never exposes UDS to clients.
    """

    def __init__(self, inner):
        self._inner = inner

    async def connect_tcp(
        self, host, port, timeout=None, local_address=None, socket_options=None
    ):
        stream = await self._inner.connect_tcp(
            host,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )
        peer = None
        try:
            peer = stream.get_extra_info("server_addr")
        except Exception:
            peer = None
        ip_str = _peer_ip(peer)
        # Import lazily to avoid a hard import-time dependency at module load.
        import httpcore

        if ip_str is None:
            # Fail CLOSED (R3-4): we could not read the actual peer address
            # (httpcore version drift / unexpected backend). Refusing is safer
            # than silently proxying to an address we have not proven public.
            try:
                await stream.aclose()
            except Exception:
                pass
            logger.warning(
                "Blocked connect to host=%s: unable to determine peer address", host
            )
            raise httpcore.ConnectError("Refused: unable to verify target peer address")
        if _is_blocked_ip(ip_str):
            try:
                await stream.aclose()
            except Exception:
                pass
            logger.warning(
                "Blocked connect to host=%s (actual peer %s is non-public)",
                host,
                ip_str,
            )
            raise httpcore.ConnectError(
                "Refused: target resolves to a non-public address"
            )
        return stream

    async def connect_unix_socket(self, path, timeout=None, socket_options=None):
        return await self._inner.connect_unix_socket(
            path,
            timeout=timeout,
            socket_options=socket_options,
        )

    async def sleep(self, seconds):
        return await self._inner.sleep(seconds)


class SSRFAsyncTransport(httpx.AsyncHTTPTransport):
    """An httpx async transport whose pool re-validates peer IPs at connect.

    httpx's stock transport builds its own httpcore connection pool and does
    not expose ``network_backend``; after ``super().__init__`` we reach into
    the pool and swap its backend for a :class:`GuardedAsyncNetworkBackend`
    wrapping the one it already created.

    Both ``_pool`` and ``pool._network_backend`` are httpcore/httpx PRIVATE
    attributes with no compatibility promise. If either disappears (library
    drift), we **fail closed at construction time** with an explicit error
    instead of silently running the pool with an unguarded backend — a silent
    fallback would quietly remove the connect-time (DNS-rebinding) layer with
    no signal to operators.
    """

    #: httpcore connection-pool attribute holding the async network backend.
    POOL_BACKEND_ATTR = "_network_backend"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._install_guarded_backend()

    def _install_guarded_backend(self):
        """Swap the pool's network backend for the guarded one. Raise on drift."""
        pool = getattr(self, "_pool", None)
        if pool is None:
            raise RuntimeError(
                "SSRF guard abort: httpx transport exposes no connection pool "
                "(expected self._pool); refusing to run without connect-time "
                "peer validation."
            )
        inner = getattr(pool, self.POOL_BACKEND_ATTR, None)
        if inner is None or not callable(getattr(inner, "connect_tcp", None)):
            raise RuntimeError(
                "SSRF guard abort: httpcore pool exposes no callable "
                f"{self.POOL_BACKEND_ATTR} (private API drift); refusing to "
                "run without connect-time peer validation."
            )
        guarded = GuardedAsyncNetworkBackend(inner)
        setattr(pool, self.POOL_BACKEND_ATTR, guarded)
        # Verify the swap actually took effect, then return for tests/inspection.
        if getattr(pool, self.POOL_BACKEND_ATTR, None) is not guarded:
            raise RuntimeError(
                "SSRF guard abort: guarded backend installation could not be "
                "verified; refusing to run without connect-time peer validation."
            )
        return guarded


def guarded_async_client(**kwargs) -> httpx.AsyncClient:
    """Build an :class:`httpx.AsyncClient` with connect-time SSRF re-validation.

    Use this for every server-side outbound request whose target is derived
    from a caller-supplied URL. Requests to hard-coded public hosts are
    unaffected (their peer IPs are public and pass the blocklist).
    """
    kwargs.setdefault("transport", SSRFAsyncTransport())
    return httpx.AsyncClient(**kwargs)
