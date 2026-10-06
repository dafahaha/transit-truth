"""Round-2 security regression tests.

Covers:
* N1: DNS-rebinding TOCTOU at the transport layer (internal connect blocked).
* N2: anonymous contributions go to a pending queue and do NOT write the
  public ranking until an operator approves; audit_count accumulates.
* N3: contributed audit payloads are size/shape bounded (422 / 413).
* S2: per-IP rate limiting returns 429 once the quota is exceeded.
* N7: batch balance accounts are validated as BaseModel elements (422).

Everything runs offline against an isolated SQLite DB.
"""
import asyncio
import os
import socket
import sys
import tempfile
from pathlib import Path

import pytest

# Isolate the SQLite DB BEFORE importing the app (config reads it at import).
_TMP_DB = tempfile.mktemp(suffix=".db")
os.environ["DATABASE_PATH"] = _TMP_DB

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

import app.database as db_module  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)


@pytest.fixture(autouse=True)
def _isolated_db():
    db_module.DB_PATH = _TMP_DB
    db_module.init_db()
    yield


# ─── N1: connect-time SSRF re-validation (DNS rebinding) ─────────────────

class _FakeStream:
    """Minimal stand-in for httpcore's AsyncNetworkStream."""

    def __init__(self, peer):
        self._peer = peer
        self.closed = False

    def get_extra_info(self, info):
        if info == "server_addr":
            return self._peer
        return None

    async def aclose(self):
        self.closed = True

    async def read(self, max_bytes, timeout=None):
        return b""

    async def write(self, buffer, timeout=None):
        pass

    async def start_tls(self, *args, **kwargs):
        return self


class _FakeInner:
    """Inner backend returning a stream with a fixed peer address."""

    def __init__(self, peer):
        self.stream = _FakeStream(peer)

    async def connect_tcp(self, host, port, **kwargs):
        return self.stream

    async def connect_unix_socket(self, path, **kwargs):
        return self.stream

    async def sleep(self, seconds):
        pass


def test_guarded_backend_blocks_loopback_peer():
    import httpcore
    from app.utils.ssrf_guard import GuardedAsyncNetworkBackend

    inner = _FakeInner(("127.0.0.1", 12345))
    bw = GuardedAsyncNetworkBackend(inner)
    with pytest.raises(httpcore.ConnectError):
        asyncio.run(bw.connect_tcp("rebind.example.com", 80))
    # The leaked internal connection must be closed, not left open.
    assert inner.stream.closed is True


def test_guarded_backend_blocks_metadata_peer():
    import httpcore
    from app.utils.ssrf_guard import GuardedAsyncNetworkBackend

    inner = _FakeInner(("169.254.169.254", 80))
    bw = GuardedAsyncNetworkBackend(inner)
    with pytest.raises(httpcore.ConnectError):
        asyncio.run(bw.connect_tcp("rebind.example.com", 80))
    assert inner.stream.closed is True


def test_guarded_backend_allows_public_peer():
    from app.utils.ssrf_guard import GuardedAsyncNetworkBackend

    inner = _FakeInner(("93.184.216.34", 443))
    bw = GuardedAsyncNetworkBackend(inner)
    stream = asyncio.run(bw.connect_tcp("example.com", 443))
    assert stream is inner.stream
    assert inner.stream.closed is False


def test_guarded_backend_fails_closed_when_peer_unknown():
    # R3-4: if the actual peer address cannot be determined (httpcore version
    # drift / unexpected backend), the guard must refuse the connection rather
    # than silently proxying to an address we haven't proven public.
    import httpcore
    from app.utils.ssrf_guard import GuardedAsyncNetworkBackend

    inner = _FakeInner(None)  # get_extra_info("server_addr") -> None
    bw = GuardedAsyncNetworkBackend(inner)
    with pytest.raises(httpcore.ConnectError):
        asyncio.run(bw.connect_tcp("mystery.example.com", 80))
    assert inner.stream.closed is True


def test_dns_rebinding_second_resolution_is_blocked(monkeypatch):
    """First getaddrinfo (URL guard) returns public -> passes; second
    getaddrinfo (connect time) returns internal -> connect is refused."""
    import httpcore
    from app.utils import ssrf_guard

    calls = {"n": 0}

    def fake_getaddrinfo(host, port, *a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            return [(2, 1, 6, "", ("93.184.216.34", port))]
        # Second resolution (the one httpx does at connect time) poisons.
        return [(2, 1, 6, "", ("169.254.169.254", port))]

    monkeypatch.setattr(ssrf_guard.socket, "getaddrinfo", fake_getaddrinfo)

    # Layer 1 passes because the first resolution is a public IP.
    ssrf_guard.validate_public_url("http://rebind.example.com/v1")

    class _ResolvingInner:
        """Mirrors httpcore: connect_tcp itself performs getaddrinfo."""

        async def connect_tcp(self, host, port, **kwargs):
            infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
            peer_ip = infos[0][4][0]
            return _FakeStream((peer_ip, port))

        async def connect_unix_socket(self, path, **kwargs):
            return _FakeStream(None)

        async def sleep(self, seconds):
            pass

    bw = ssrf_guard.GuardedAsyncNetworkBackend(_ResolvingInner())
    with pytest.raises(httpcore.ConnectError):
        asyncio.run(bw.connect_tcp("rebind.example.com", 80))
    assert calls["n"] == 2  # both the URL guard and the connect-time resolution ran


# ─── N2: anonymous contribution -> pending queue, not public ranking ──────

def test_anonymous_contribute_does_not_write_ranking():
    from app.core.contributor_reputation import ContributorReputationSystem
    from app.database import get_rankings, upsert_ranking
    from app.moderation import _build_ranking_entry

    payload = {
        "audit_result": {
            "model": "gpt-4o-selfmade",
            "base_url": "https://evil.example.com/v1",
            "overall_score": 100,
        },
        "relay_name": "self-made-relay",
        "is_anonymous": True,
    }
    r = client.post("/api/contribute/audit", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    cid = body["contribution_id"]
    # Auto quality gate passes (3 required fields present) ...
    assert body["is_valid"] is True

    # ... but the public ranking must NOT contain the self-made entry.
    assert all(e["model"] != "gpt-4o-selfmade" for e in get_rankings())

    # The contribution is sitting in the pending moderation queue.
    sys_ = ContributorReputationSystem()
    contrib = sys_.get_contribution(cid)
    assert contrib is not None
    assert contrib.status == "pending"

    # Operator approves it (the only path that writes the ranking).
    sys_.set_contribution_status(cid, "approved", reviewer="test")
    upsert_ranking(_build_ranking_entry(contrib.content))

    rows = get_rankings(model="gpt-4o-selfmade")
    assert len(rows) == 1
    assert rows[0]["audit_count"] == 1

    # A second approved contribution for the same (base_url, model) must
    # ACCUMULATE audit_count (read old value +1), not reset it to 1.
    r2 = client.post("/api/contribute/audit", json=payload)
    cid2 = r2.json()["contribution_id"]
    sys2 = ContributorReputationSystem()
    sys2.set_contribution_status(cid2, "approved", reviewer="test")
    upsert_ranking(_build_ranking_entry(sys2.get_contribution(cid2).content))

    rows2 = get_rankings(model="gpt-4o-selfmade")
    assert len(rows2) == 1
    assert rows2[0]["audit_count"] == 2


def test_approve_leaves_pending_when_ranking_write_fails(monkeypatch):
    # R3-5/R4-2: if the ranking upsert fails mid-transaction, the whole approve
    # rolls back — the contribution must NOT be left "approved" (and no partial
    # ranking row / audit_count increment survives).
    from types import SimpleNamespace
    from app import moderation
    import app.database as db_module
    from app.core.contributor_reputation import ContributorReputationSystem
    from app.database import get_rankings

    payload = {
        "audit_result": {
            "model": "gpt-4o-r35",
            "base_url": "https://r35.example.com/v1",
            "overall_score": 80,
        },
    }
    cid = client.post("/api/contribute/audit", json=payload).json()["contribution_id"]

    def boom(cursor, entry):
        raise RuntimeError("simulated DB lock")

    monkeypatch.setattr(db_module, "_upsert_ranking_row", boom)

    rc = moderation.cmd_approve(SimpleNamespace(id=cid))
    assert rc == 3
    # rolled back: no public row committed ...
    assert get_rankings(model="gpt-4o-r35") == []
    # ... and the contribution stays pending for a clean retry.
    contrib = ContributorReputationSystem().get_contribution(cid)
    assert contrib.status == "pending"


def test_approve_rolls_back_when_status_flip_fails(monkeypatch):
    # R4-2: the ranking upsert and the contribution status flip are ONE
    # transaction. Simulate the SECOND step (status flip) failing after the
    # upsert ran — the transaction must roll back, so audit_count is NOT
    # incremented and the contribution stays pending (an operator retry then
    # upserts exactly once, instead of double-counting).
    from types import SimpleNamespace
    from app import moderation
    import app.database as db_module
    from app.core.contributor_reputation import ContributorReputationSystem
    from app.database import get_rankings

    payload = {
        "audit_result": {
            "model": "gpt-4o-r42",
            "base_url": "https://r42.example.com/v1",
            "overall_score": 80,
        },
    }
    cid = client.post("/api/contribute/audit", json=payload).json()["contribution_id"]

    def boom(cursor, contribution_id):
        raise RuntimeError("simulated DB lock on status update")

    monkeypatch.setattr(db_module, "_set_contribution_approved", boom)

    rc = moderation.cmd_approve(SimpleNamespace(id=cid))
    assert rc == 3
    # The upsert ran on the transaction's connection but was rolled back:
    # no committed ranking row, hence no audit_count increment.
    assert get_rankings(model="gpt-4o-r42") == []
    contrib = ContributorReputationSystem().get_contribution(cid)
    assert contrib.status == "pending"


# ─── N3: contributed payload size/shape bounds ───────────────────────────


def test_contribute_oversized_string_is_422():
    payload = {
        "audit_result": {
            "model": "gpt-4o",
            "base_url": "https://example.com/v1",
            "overall_score": 90,
            "notes": "x" * 3000,  # exceeds per-string cap
        },
    }
    r = client.post("/api/contribute/audit", json=payload)
    assert r.status_code == 422, r.text


def test_contribute_deep_nesting_is_422():
    deep = {"a": 1}
    for _ in range(12):  # exceeds max depth 6
        deep = {"x": deep}
    payload = {
        "audit_result": {
            "model": "gpt-4o",
            "base_url": "https://example.com/v1",
            "overall_score": 90,
            "nested": deep,
        },
    }
    r = client.post("/api/contribute/audit", json=payload)
    assert r.status_code == 422, r.text


def test_contribute_body_too_large_is_413():
    # Send a body over the 1 MiB middleware cap. Use a raw string payload so
    # Content-Length exceeds the limit before JSON parsing.
    big = {"audit_result": {"pad": "y" * (1100 * 1024)}}
    r = client.post("/api/contribute/audit", json=big)
    assert r.status_code == 413, r.text


# ─── R3-1: streaming body cap covers chunked (no Content-Length) ──────────

def _drive_asgi(chunks, headers):
    """Drive the app directly as ASGI, feeding *chunks* as http.request events.

    No Content-Length is emitted unless the caller passes one, so this can
    exercise the chunked path that TestClient's JSON helper hides. Returns
    (status_code, raw_body_bytes).
    """
    from app.main import app

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "path": "/api/contribute/audit",
        "raw_path": b"/api/contribute/audit",
        "query_string": b"",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers],
        "client": ("203.0.113.9", 50000),
        "server": ("testserver", 80),
    }
    state = {"i": 0}

    async def receive():
        i = state["i"]
        if i < len(chunks):
            state["i"] += 1
            more_body = i < len(chunks) - 1
            return {"type": "http.request", "body": chunks[i], "more_body": more_body}
        return {"type": "http.disconnect"}

    messages = []

    async def send(message):
        messages.append(message)

    asyncio.run(app(scope, receive, send))
    status = messages[0]["status"]
    body = b"".join(
        m.get("body", b"") for m in messages if m["type"] == "http.response.body"
    )
    return status, body


def test_chunked_body_without_content_length_is_413():
    # The R3-1 bypass: Transfer-Encoding: chunked with NO Content-Length used
    # to slip past the header check and be fully buffered (returning 422). Now
    # the streaming receive guard must abort at 1 MiB with 413.
    mb = 1024 * 1024
    status, _ = _drive_asgi(
        [b" " * mb, b" " * mb],  # ~2 MiB streamed in two chunks, no CL header
        [("content-type", "application/json")],
    )
    assert status == 413, f"expected 413 for chunked upload, got {status}"


def test_declared_content_length_over_limit_is_413():
    # Explicit Content-Length path (declared up front, single chunk).
    mb = 1024 * 1024
    payload = b"{}".ljust(2 * mb, b"x")
    status, _ = _drive_asgi(
        [payload],
        [("content-type", "application/json"), ("content-length", str(len(payload)))],
    )
    assert status == 413, f"expected 413 for over-limit Content-Length, got {status}"


def test_exactly_one_mib_body_is_not_413():
    # Boundary rule (fixed here): the cap is INCLUSIVE on 1 MiB. Exactly
    # 1 MiB must NOT be rejected by the size guard (it reaches the app and is
    # then rejected as invalid JSON with 422 — never 413).
    mb = 1024 * 1024
    status, _ = _drive_asgi(
        [b"x" * mb],  # exactly the cap, not valid JSON
        [("content-type", "application/json")],
    )
    assert status != 413, "exactly 1 MiB must not be treated as over-limit"


def test_small_request_still_200():
    # The streaming wrapper must not break normal small requests.
    import json
    payload = json.dumps({
        "audit_result": {"model": "m", "base_url": "https://e.com/v1", "overall_score": 90}
    }).encode()
    status, body = _drive_asgi(
        [payload],
        [("content-type", "application/json"), ("content-length", str(len(payload)))],
    )
    assert status == 200, body


# ─── S2: per-IP rate limiting ────────────────────────────────────────────

def test_rate_limit_returns_429():
    from app.utils import rate_limit
    rate_limit.configure(2, 60)  # only 2 requests per minute per IP
    try:
        statuses = []
        for _ in range(4):
            r = client.post(
                "/api/contribute/audit",
                json={"audit_result": {"model": "x"}},
            )
            statuses.append(r.status_code)
        # First two pass the dependency (then fail body validation), the rest 429.
        assert 429 in statuses
        assert statuses[-1] == 429
    finally:
        rate_limit.configure(100, 60)
        rate_limit.reset()


# ─── R3-2: trusted-proxy X-Forwarded-For resolution ───────────────────────

def _make_request(client_host, xff=None):
    from starlette.requests import Request
    headers = []
    if xff is not None:
        headers.append((b"x-forwarded-for", xff.encode()))
    scope = {"type": "http", "client": (client_host, 1234), "headers": headers}
    return Request(scope)


def test_direct_client_ignores_x_forwarded_for():
    # Default: no trusted proxies configured -> XFF must never be the identity,
    # otherwise a caller could forge it to borrow/steal another bucket.
    from app.utils import rate_limit
    rate_limit.configure_trusted_proxies("")
    req = _make_request("203.0.113.9", xff="1.2.3.4")
    assert rate_limit._client_ip(req) == "203.0.113.9"


def test_trusted_proxy_uses_rightmost_untrusted_xff_hop():
    # Direct peer is a configured trusted proxy; XFF chain client, inner, outer.
    # Walk right-to-left, skip trusted hops, take the first untrusted address.
    from app.utils import rate_limit
    rate_limit.configure_trusted_proxies("10.0.0.1,10.0.0.2")
    req = _make_request("10.0.0.1", xff="1.2.3.4, 10.0.0.2, 10.0.0.1")
    assert rate_limit._client_ip(req) == "1.2.3.4"


def test_forged_xff_ignored_when_peer_not_trusted():
    # A caller NOT behind a trusted proxy forges XFF -> ignored, TCP peer wins.
    from app.utils import rate_limit
    rate_limit.configure_trusted_proxies("10.0.0.1")
    req = _make_request("198.51.100.7", xff="9.9.9.9")
    assert rate_limit._client_ip(req) == "198.51.100.7"


# ─── N7: batch balance accounts are validated elements ──────────────────

def test_batch_account_missing_api_key_is_422():
    resp = client.post("/api/balance/batch", json={
        "accounts": [{"base_url": "https://example.com/v1"}],  # no api_key
    })
    assert resp.status_code == 422, resp.text


def test_batch_account_missing_base_url_is_422():
    resp = client.post("/api/balance/batch", json={
        "accounts": [{"api_key": "sk-test"}],  # no base_url
    })
    assert resp.status_code == 422, resp.text
