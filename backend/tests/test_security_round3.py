"""Round-1 adversarial-review regression tests.

Closes the three "silent defense degradation" findings plus the CGNAT gap:

* S-1: the connect-time guarded backend must be *proven* installed on the
  transport pool (mutation M11 used to survive), and if httpx/httpcore ever
  renames the private attributes the swap relies on, transport construction
  must fail closed loudly instead of silently running unguarded.
* S-2: a real upstream (non-2xx) response body must never reach the caller —
  exercised over a REAL local HTTP server through the unmodified
  ``AsyncAPIClient`` (mutation M3 used to survive the fake-client test).
* S-4: RFC6598 CGNAT ``100.64.0.0/10`` (and its IPv4-mapped IPv6 form) is
  blocked, while addresses just outside the range stay reachable.

Everything runs offline on localhost.
"""
import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app.utils import ssrf_guard
from app.utils.ssrf_guard import (
    GuardedAsyncNetworkBackend,
    SSRFAsyncTransport,
    _is_blocked_ip,
)


# ─── S-1: guarded backend installation is proven, not assumed ──────────────

def test_guarded_backend_installed_on_pool():
    # Mutation M11 (deleting the whole backend swap) used to pass the suite:
    # no test ever looked inside the transport pool. Now the pool MUST hold a
    # GuardedAsyncNetworkBackend wrapping the real httpcore backend.
    transport = SSRFAsyncTransport()
    backend = getattr(transport._pool, transport.POOL_BACKEND_ATTR, None)
    assert isinstance(backend, GuardedAsyncNetworkBackend)
    # It must wrap the genuine httpcore backend, not an empty shell.
    assert backend._inner is not None
    assert callable(backend._inner.connect_tcp)


def test_swap_fails_closed_when_pool_attribute_drifts():
    # httpcore renames/removes pool._network_backend -> construction must raise
    # instead of silently falling back to an unguarded backend.
    class _DriftedPool:
        # Deliberately has NO _network_backend attribute.
        pass

    transport = object.__new__(SSRFAsyncTransport)
    transport._pool = _DriftedPool()
    with pytest.raises(RuntimeError, match="SSRF guard abort"):
        transport._install_guarded_backend()


def test_swap_fails_closed_when_pool_missing():
    # httpx restructures the transport so self._pool disappears -> raise.
    transport = object.__new__(SSRFAsyncTransport)
    # no _pool attribute set
    with pytest.raises(RuntimeError, match="SSRF guard abort"):
        transport._install_guarded_backend()


def test_guarded_backend_is_on_live_connection_path(monkeypatch):
    # End-to-end proof: a real TCP connection through guarded_async_client must
    # be observed INSIDE GuardedAsyncNetworkBackend.connect_tcp, and the peer
    # address it inspects must be the real sockaddr the kernel connected to.
    seen = {}

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    original_connect = GuardedAsyncNetworkBackend.connect_tcp

    async def spy_connect(self, host, port, **kwargs):
        stream = await original_connect(self, host, port, **kwargs)
        seen["peer"] = stream.get_extra_info("server_addr")
        return stream

    monkeypatch.setattr(GuardedAsyncNetworkBackend, "connect_tcp", spy_connect)
    # This test only proves the guarded wrapper is traversed; loopback would
    # otherwise be blocked. The blocklist semantics are covered elsewhere.
    monkeypatch.setattr(ssrf_guard, "_is_blocked_ip", lambda ip_str: False)

    async def drive():
        client = ssrf_guard.guarded_async_client()
        try:
            return await client.get(f"http://127.0.0.1:{port}/")
        finally:
            await client.aclose()

    try:
        resp = asyncio.run(drive())
    finally:
        server.shutdown()

    assert resp.status_code == 200
    # The guard saw the REAL peer the kernel connected to.
    assert seen["peer"][0] == "127.0.0.1"


# ─── S-2: real-path upstream body non-disclosure ──────────────────────────

def _scrubbed_values(obj):
    """Yield every leaf string / every dict key in *obj* (recursively)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield ("key", k)
            yield from _scrubbed_values(v)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            yield from _scrubbed_values(item)
    elif isinstance(obj, str):
        yield ("value", obj)


def test_real_upstream_error_body_never_reaches_caller(monkeypatch):
    # M3: the ONLY pre-existing test replaced AsyncAPIClient with a fake, so
    # adding "body": response.text to last_error went unnoticed. Here we run
    # the REAL AsyncAPIClient over REAL httpx against a local server that
    # answers 401 with a secret body; the secret must appear nowhere in the
    # returned result dict.
    from app.utils.http_client import AsyncAPIClient

    secret = "INTERNAL_SECRET_UPSTREAM_BODY_MARKER"

    class _Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            self.rfile.read(length)  # drain the request body
            body = json.dumps({"error": {"message": secret}}).encode()
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    # Loopback peer would otherwise be refused by the connect-time guard;
    # the blocklist itself is not under test here.
    monkeypatch.setattr(ssrf_guard, "_is_blocked_ip", lambda ip_str: False)

    async def drive():
        client = AsyncAPIClient(
            api_key="sk-test", base_url=f"http://127.0.0.1:{port}/v1"
        )
        async with client:
            return await client.chat_completion(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "hi"}],
            )

    try:
        result = asyncio.run(drive())
    finally:
        server.shutdown()

    # Only the status code may leave the server:
    assert result["error"]["status_code"] == 401
    leaves = list(_scrubbed_values(result))
    assert secret not in [v for kind, v in leaves if kind == "value"]
    assert "body" not in [k for kind, k in leaves if kind == "key"]
    # And the whole JSON view the caller receives must not contain it either.
    assert secret not in json.dumps(result, default=str)


# ─── S-4: RFC6598 CGNAT and special-range coverage ─────────────────────────

@pytest.mark.parametrize("address", [
    # CGNAT boundaries (must be blocked)
    "100.64.0.0",          # network address
    "100.64.0.1",          # the originally-reported gap
    "100.127.255.255",    # broadcast edge of 100.64.0.0/10
    "::ffff:100.64.0.1",  # IPv4-mapped IPv6 form of the same gap
    # regression: previously-covered non-public ranges stay blocked
    "127.0.0.1",
    "::1",
    "169.254.169.254",
    "::ffff:169.254.169.254",
    "0.0.0.0",
    "0.1.2.3",            # 0.0.0.0/8 host
    "10.0.0.1",
    "172.16.0.2",
    "192.168.1.10",
    "192.0.2.1",          # TEST-NET-1
    "198.51.100.1",       # TEST-NET-2
    "203.0.113.1",        # TEST-NET-3
    "fe80::1",            # IPv6 link-local
    "fc00::1",            # IPv6 ULA
    "fd12::dead:beef",
    # encoding forms the URL layer may hand to the guard (fail closed)
    "2130706433",         # decimal 127.0.0.1
    "0x7f000001",         # hex 127.0.0.1
    "0177.0.0.1",         # octal 127.0.0.1
])
def test_non_public_addresses_blocked(address):
    assert _is_blocked_ip(address) is True, address


@pytest.mark.parametrize("address", [
    "100.128.0.1",        # just OUTSIDE CGNAT /10 -> legitimately public
    "93.184.216.34",      # example.com
    "8.8.8.8",
])
def test_public_addresses_allowed(address):
    assert _is_blocked_ip(address) is False, address


def test_cgnat_blocked_at_url_layer():
    # The URL-level guard (validate_public_url) must also reject CGNAT hosts.
    with pytest.raises(ValueError, match="public"):
        ssrf_guard.validate_public_url("http://100.64.0.1/v1")


def test_cgnat_ipv6_mapped_blocked_at_url_layer():
    with pytest.raises(ValueError, match="public"):
        ssrf_guard.validate_public_url("http://[::ffff:100.64.0.1]/v1")


def test_just_outside_cgnat_still_passes_url_layer():
    # Guardrail: we must not over-block the publicly routable tail of 100/8.
    parsed = ssrf_guard.validate_public_url("http://100.128.0.1/v1")
    assert parsed.host == "100.128.0.1"
