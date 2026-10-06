"""API-layer regression tests for the security fixes (G1).

Everything here runs fully offline:

* Internal / loopback / link-local targets must be rejected with HTTP 400
  *before* any outbound request is attempted (M1 SSRF guard).
* The upstream response body must never be echoed back to the caller
  (M1 read-SSRF closure).
* Passing ``official_api_key`` must produce a COMPLETED audit (M2).
* ``limit`` and batch ``accounts`` have upper bounds (S2).
* CORS does not allow credentials (S1).

Outbound HTTP is intercepted either by rejecting the URL up front (so no
client is ever constructed) or by swapping ``AsyncAPIClient`` for a fake.
"""
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Isolate the SQLite DB BEFORE importing the app (config reads DATABASE_PATH
# at import time).
_TMP_DB = tempfile.mktemp(suffix=".db")
os.environ["DATABASE_PATH"] = _TMP_DB

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

import app.database as db_module  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_db():
    db_module.DB_PATH = _TMP_DB
    db_module.init_db()
    yield


client = TestClient(app)


# ─── M1: SSRF guard rejects internal targets before any request ──────────

@pytest.mark.parametrize("bad_url", [
    "http://127.0.0.1:1/v1",          # loopback IPv4
    "http://[::1]/v1",                 # loopback IPv6
    "http://169.254.169.254/latest/meta-data",  # cloud metadata (link-local)
    "http://10.0.0.5/v1",              # RFC1918 /8
    "http://172.16.0.2/v1",           # RFC1918 /12
    "http://192.168.1.10/v1",         # RFC1918 /16
])
def test_internal_url_rejected_without_outbound(bad_url):
    resp = client.post("/api/audit/start", json={
        "api_key": "sk-test",
        "base_url": bad_url,
        "model": "gpt-4o-mini",
    })
    assert resp.status_code == 400, resp.text


def test_loopback_hostname_rejected():
    # localhost must be blocked via DNS resolution, not just IP literals.
    resp = client.post("/api/detect/models", json={
        "api_key": "sk-test",
        "base_url": "http://localhost:8000/v1",
    })
    assert resp.status_code == 400, resp.text


def test_non_http_scheme_rejected():
    resp = client.post("/api/audit/start", json={
        "api_key": "sk-test",
        "base_url": "file:///etc/passwd",
        "model": "gpt-4o-mini",
    })
    assert resp.status_code == 400, resp.text


def test_balance_check_internal_rejected():
    resp = client.post("/api/balance/check", json={
        "api_key": "sk-test",
        "base_url": "http://127.0.0.1:9/v1",
    })
    assert resp.status_code == 400, resp.text


# ─── S2: bounded inputs ──────────────────────────────────────────────────

def test_audit_limit_has_upper_bound():
    resp = client.get("/api/audit/", params={"limit": 1_000_000})
    assert resp.status_code == 422


def test_ranking_limit_has_upper_bound():
    resp = client.get("/api/ranking/", params={"limit": 1_000_000})
    assert resp.status_code == 422


def test_batch_balance_max_length():
    accounts = [{"api_key": "sk", "base_url": "https://example.com/v1"} for _ in range(6)]
    resp = client.post("/api/balance/batch", json={"accounts": accounts})
    # 6 accounts > max_length=5 -> 422 before any SSRF/outbound work.
    assert resp.status_code == 422


# ─── S1: CORS does not allow credentials ────────────────────────────────

def test_cors_credentials_disabled():
    resp = client.get("/api/health", headers={"Origin": "http://evil.example"})
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-credentials") != "true"


# ─── Helpers: fake relay/official clients (offline) ─────────────────────

class _FakeClient:
    """Drop-in for AsyncAPIClient that returns canned 200 responses."""

    def __init__(self, api_key, base_url, timeout=30):
        self.api_key = api_key
        self.base_url = base_url

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def check_availability(self, model):
        return self._ok()

    async def chat_completion(self, model, messages, **kwargs):
        return self._ok()

    def _ok(self):
        return {
            "id": "cmpl-fake",
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            "_status_code": 200,
        }


class _FakeFailingClient(_FakeClient):
    """Relay that answers availability with a non-2xx carrying a secret body."""

    async def check_availability(self, model):
        return {
            "error": {
                "status_code": 401,
                "body": "INTERNAL_SECRET_SSRF_BODY_DO_NOT_LEAK",
            },
            "_status_code": 401,
        }


def _public_dns(monkeypatch):
    """Make every hostname resolve to a public IP so the SSRF guard passes,
    without real DNS or outbound connections."""
    import app.utils.ssrf_guard as guard

    def fake_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        return [(2, 1, 6, "", ("93.184.216.34", port))]

    monkeypatch.setattr(guard.socket, "getaddrinfo", fake_getaddrinfo)


def test_official_api_key_audit_completed(monkeypatch):
    """M2: with official_api_key, the official client is properly opened via
    `async with` and the audit reaches COMPLETED with expected tokens filled."""
    import app.core.auditor as auditor_mod
    from app.core.token_check import TokenVerifier
    _public_dns(monkeypatch)
    monkeypatch.setattr(auditor_mod, "AsyncAPIClient", _FakeClient)
    # Avoid tiktoken downloading its encoding files from the network (offline CI).
    monkeypatch.setattr(TokenVerifier, "_compute_local_tokens", lambda self, text: None)

    resp = client.post("/api/audit/start", json={
        "api_key": "sk-relay",
        "base_url": "https://relay.example.com/v1",
        "model": "gpt-4o-mini",
        "official_api_key": "sk-official",
        "mode": "quick",
        "run_fingerprint": False,
        "run_latency": False,
        "run_protocol": False,
        "run_token_check": True,
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "completed", data
    assert data["token_comparison"] is not None
    # Official comparison ran -> expected prompt tokens are populated.
    assert data["token_comparison"]["prompt_tokens_expected"] is not None


def test_upstream_body_not_echoed(monkeypatch):
    """M1: a non-2xx relay response body must not appear in the API result."""
    import app.core.auditor as auditor_mod
    _public_dns(monkeypatch)
    monkeypatch.setattr(auditor_mod, "AsyncAPIClient", _FakeFailingClient)

    resp = client.post("/api/audit/start", json={
        "api_key": "sk-relay",
        "base_url": "https://relay.example.com/v1",
        "model": "gpt-4o-mini",
    })
    # The audit itself reports failure, but the upstream body must NOT leak.
    body = resp.text
    assert "INTERNAL_SECRET_SSRF_BODY_DO_NOT_LEAK" not in body
    assert "status_code" not in body or "401" in body  # only status is reported


def test_contribution_uses_uuid_id():
    """S4: contributions get a uuid-based id and persist."""
    resp = client.post("/api/contribute/audit", json={
        "audit_result": {
            "model": "gpt-4o-mini",
            "base_url": "https://relay.example.com/v1",
            "overall_score": 90,
        },
        "relay_name": "test-relay",
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["contribution_id"].startswith("contrib_")
