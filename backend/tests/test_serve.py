"""Regression tests for the local web UI (``transit-truth serve``).

Covers: static UI reachable; honest / mismatch / no-key verdicts; the marker
API key never appears in the response, the static page, or server logs; clean
JSON errors for malformed input; no wildcard CORS; the defense-in-depth
sanitizer; and the CLI bind gate (default 127.0.0.1, 0.0.0.0 needs
--allow-public).
"""

from __future__ import annotations

import asyncio
import json
import logging
import socket
import threading
import time

import pytest
import uvicorn
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.verify.serve import build_serve_app, is_loopback_host, sanitize_report

MARKER = "sk-VERIFY-SECRET-MARKER-9f3c"

# --- Canned gpt-4o-mini reference values (same caliber as test_verify.py) ---
_HONEST_TOKENS = {
    "a    b    c    d    e    f    g    h": 43,
    "def foo(x): return x*2+1  # test": 41,
    "https://api.example.com/v1/chat/completions?model=gpt-4": 45,
    "café résumé naïve über 日本語 한국어 العربية": 38,
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa": 34,
}
_CHEAT_TOKENS = {
    "a    b    c    d    e    f    g    h": 15,
    "def foo(x): return x*2+1  # test": 13,
    "https://api.example.com/v1/chat/completions?model=gpt-4": 20,
    "café résumé naïve über 日本語 한국어 العربية": 12,
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa": 9,
}
_HONEST_BEH = {
    "between 1 and 10": "7",
    "Flip a coin": "Heads",
    "random color": "Cerulean",
    "six-sided die": "4",
}
_CHEAT_BEH = {
    "between 1 and 10": "3",
    "Flip a coin": "Tails",
    "random color": "Orange",
    "six-sided die": "2",
}


def _build_stub(mode: str) -> FastAPI:
    app = FastAPI(title="serve test stub")

    @app.post("/v1/chat/completions")
    async def chat(request: Request):
        body = await request.json()
        messages = body.get("messages", [])
        user = next(
            (m["content"] for m in reversed(messages) if m.get("role") == "user"), ""
        )
        tokens = _CHEAT_TOKENS if mode == "cheat" else _HONEST_TOKENS
        beh = _CHEAT_BEH if mode == "cheat" else _HONEST_BEH
        content = ""
        prompt_tokens = 10
        if "Repeat this string exactly: " in user:
            s = user.split("Repeat this string exactly: ", 1)[1]
            prompt_tokens = tokens.get(s, 10)
            content = s
        else:
            for key, reply in beh.items():
                if key in user:
                    content = reply
                    break
        return {
            "id": "chatcmpl-stub",
            "choices": [
                {"index": 0, "message": {"role": "assistant", "content": content}}
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": 2,
                "total_tokens": prompt_tokens + 2,
            },
        }

    return app


def _start_server(mode: str) -> tuple[str, uvicorn.Server]:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(
            _build_stub(mode), host="127.0.0.1", port=port, log_level="error"
        )
    )
    threading.Thread(
        target=lambda: asyncio.run(server.serve(sockets=[sock])), daemon=True
    ).start()
    for _ in range(50):
        if server.started:
            break
        time.sleep(0.1)
    return f"http://127.0.0.1:{port}/v1", server


@pytest.fixture(scope="module")
def client():
    # allow_local=True only so tests can hit the loopback stub; production keeps
    # the public SSRF guard on. loopback_only=False because TestClient sends
    # Host: testserver (not a loopback literal); the Host whitelist is covered
    # separately against a loopback_only=True app.
    app = build_serve_app(allow_local=True, loopback_only=False)
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def loopback_client():
    # Host whitelist active: only loopback Host names are accepted.
    app = build_serve_app(allow_local=True, loopback_only=True)
    with TestClient(app) as c:
        yield c


# (a) static UI reachable
def test_static_ui_served(client):
    resp = client.get("/")
    assert resp.status_code == 200, resp.text
    assert "text/html" in resp.headers["content-type"]
    assert "TransitTruth" in resp.text
    # Marker must never be baked into the static page.
    assert MARKER not in resp.text


# (b) honest / mismatch / no-key verdicts over the JSON API
def test_verify_honest_passes(client):
    url, server = _start_server("honest")
    try:
        resp = client.post(
            "/api/verify",
            json={
                "base_url": url,
                "claimed_model": "gpt-4o-mini",
                "api_key": MARKER,
            },
        )
    finally:
        server.should_exit = True
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["verdict"] == "pass", json.dumps(body, indent=2)
    assert body["error"] is None


def test_verify_cheat_not_pass(client):
    url, server = _start_server("cheat")
    try:
        resp = client.post(
            "/api/verify",
            json={"base_url": url, "claimed_model": "gpt-4o-mini", "api_key": MARKER},
        )
    finally:
        server.should_exit = True
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["verdict"] != "pass", json.dumps(body, indent=2)


def test_verify_no_key_is_insufficient(client, monkeypatch):
    monkeypatch.delenv("TRANSIT_TRUTH_API_KEY", raising=False)
    url, server = _start_server("honest")
    try:
        resp = client.post(
            "/api/verify",
            json={"base_url": url, "claimed_model": "gpt-4o-mini"},
        )
    finally:
        server.should_exit = True
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["verdict"] == "insufficient_evidence"
    assert body["error"]["code"] == "missing_api_key"


# (c) marker key absent from response, static page, and captured logs
def test_marker_key_absent_response_page_and_logs(client):
    records: list[str] = []
    handler = logging.Handler()
    handler.emit = lambda r: records.append(r.getMessage())
    logger = logging.getLogger("app.verify.serve")
    logger.addHandler(handler)
    try:
        url, server = _start_server("honest")
        try:
            resp = client.post(
                "/api/verify",
                json={
                    "base_url": url,
                    "claimed_model": "gpt-4o-mini",
                    "api_key": MARKER,
                },
            )
        finally:
            server.should_exit = True
        assert MARKER not in json.dumps(resp.json())
        assert MARKER not in client.get("/").text
        for line in records:
            assert MARKER not in line
    finally:
        logger.removeHandler(handler)


# (d) malformed / missing-field input -> clean structured JSON error
def test_malformed_json_returns_clean_error(client):
    resp = client.post(
        "/api/verify",
        content="{not valid json",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "invalid_json"


def test_missing_field_returns_clean_error(client):
    resp = client.post("/api/verify", json={"claimed_model": "gpt-4o-mini"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "missing_field"


def test_non_object_body_returns_clean_error(client):
    resp = client.post("/api/verify", json=["a", "b"])
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_json"


# (e) no wildcard CORS header (same-origin only)
def test_no_wildcard_cors(client):
    resp = client.get("/")
    assert "access-control-allow-origin" not in {k.lower() for k in resp.headers}
    resp = client.post("/api/verify", json={"base_url": "x", "claimed_model": "y"})
    assert "access-control-allow-origin" not in {k.lower() for k in resp.headers}


# (f) sanitizer strips nested api_key and redacts sk- strings, without mutating
def test_sanitize_report_strips_and_redacts():
    fake = {
        "verdict": "pass",
        "api_key": MARKER,
        "nested": {"authorization": "Bearer abc", "keep": 1},
        "observations": {"note": f"used {MARKER} in log line"},
        "list": [{"key": MARKER}, "plain"],
    }
    out = sanitize_report(fake)
    assert "api_key" not in out
    assert "authorization" not in out["nested"]
    assert out["nested"]["keep"] == 1
    assert MARKER not in json.dumps(out)
    # Input must not be mutated.
    assert fake["api_key"] == MARKER
    assert "authorization" in fake["nested"]


# (g) CLI argparse gating: default 127.0.0.1/8766; 0.0.0.0 needs --allow-public
def test_cli_serve_defaults_and_public_gate(monkeypatch):
    from app import cli

    original_serve = cli.cmd_serve
    captured = {}

    def fake_serve(args):
        captured["host"] = args.host
        captured["port"] = args.port
        captured["allow_public"] = args.allow_public

    monkeypatch.setattr(cli, "cmd_serve", fake_serve)

    # Plain `serve` -> defaults, cmd_serve called (uvicorn stubbed).
    monkeypatch.setattr("sys.argv", ["transit-truth", "serve"])
    cli.main()
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 8766
    assert captured["allow_public"] is False

    # 0.0.0.0 without --allow-public -> the ORIGINAL cmd_serve refuses with exit
    # code 2 before uvicorn ever starts.
    from types import SimpleNamespace

    ns = SimpleNamespace(
        host="0.0.0.0", port=8766, allow_public=False, allow_local=False, open=False
    )
    with pytest.raises(SystemExit) as exc:
        original_serve(ns)
    assert exc.value.code == 2

    # With --allow-public the gate passes (uvicorn stubbed so nothing binds).
    monkeypatch.setattr(
        "sys.argv", ["transit-truth", "serve", "--host", "0.0.0.0", "--allow-public"]
    )
    cli.main()
    assert captured["host"] == "0.0.0.0"
    assert captured["allow_public"] is True


# ── F2: Content-Type / Origin / Sec-Fetch-Site / Host guards ─────────────────


# Only application/json is accepted; text/plain simple cross-site -> 415.
def test_text_plain_rejected_415(client):
    resp = client.post(
        "/api/verify",
        content="hello",
        headers={"Content-Type": "text/plain"},
    )
    assert resp.status_code == 415, resp.text
    assert resp.json()["error"]["code"] == "unsupported_media_type"


def test_charset_suffix_application_json_accepted(client):
    # ; charset=utf-8 is still application/json -> not rejected by the type gate.
    resp = client.post(
        "/api/verify",
        json={"base_url": "x", "claimed_model": "y"},
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    # Reaches field validation (400 missing/invalid target), not 415.
    assert resp.status_code != 415


def test_foreign_origin_rejected_403(client):
    resp = client.post(
        "/api/verify",
        json={"base_url": "x", "claimed_model": "y"},
        headers={"Origin": "https://evil.example"},
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["error"]["code"] == "cross_origin"


def test_cross_site_sec_fetch_rejected_403(client):
    resp = client.post(
        "/api/verify",
        json={"base_url": "x", "claimed_model": "y"},
        headers={"Sec-Fetch-Site": "cross-site"},
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["error"]["code"] == "cross_site"


def test_same_origin_origin_not_rejected(client):
    # Origin host matches the request Host (testserver) -> allowed through the
    # origin gate (fails later on validation, not 403).
    resp = client.post(
        "/api/verify",
        json={"base_url": "x", "claimed_model": "y"},
        headers={"Origin": "http://testserver"},
    )
    assert resp.status_code != 403


def test_loopback_binding_rejects_non_loopback_host(loopback_client):
    # DNS-rebinding / Host attack: Host: evil.com on a loopback-only bind -> 403.
    resp = loopback_client.post(
        "/api/verify",
        json={"base_url": "x", "claimed_model": "y"},
        headers={"Host": "evil.com"},
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["error"]["code"] == "invalid_host"


def test_loopback_binding_accepts_loopback_host(loopback_client):
    resp = loopback_client.post(
        "/api/verify",
        json={"base_url": "x", "claimed_model": "y"},
        headers={"Host": "127.0.0.1:8766"},
    )
    # Passes Host whitelist; rejected later only for the bogus target/fields.
    assert resp.status_code != 403


# ── F3: is_loopback_host helper + CLI bind gate ──────────────────────────────


@pytest.mark.parametrize(
    "host,expected",
    [
        ("127.0.0.1", True),
        ("127.5.6.7", True),
        ("localhost", True),
        ("LOCALHOST", True),
        ("::1", True),
        ("[::1]", True),
        ("127.0.0.1:8766", True),
        ("0.0.0.0", False),
        ("::", False),
        ("192.168.1.5", False),
        ("10.0.0.1", False),
        ("172.16.0.2", False),
        ("8.8.8.8", False),
        ("evil.com", False),
        ("server.local", False),
    ],
)
def test_is_loopback_host(host, expected):
    assert is_loopback_host(host) is expected


def test_cli_rejects_lan_ip_without_flag(monkeypatch):
    from types import SimpleNamespace

    from app import cli

    original_serve = cli.cmd_serve
    for host in ("192.168.1.5", "::", "server.local"):
        ns = SimpleNamespace(
            host=host, port=8766, allow_public=False, allow_local=False, open=False
        )
        with pytest.raises(SystemExit) as exc:
            original_serve(ns)
        assert exc.value.code == 2


def test_cli_accepts_lan_ip_with_flag(monkeypatch):
    from app import cli

    captured = {}

    def fake_serve(args):
        captured["host"] = args.host
        captured["allow_public"] = args.allow_public

    monkeypatch.setattr(cli, "cmd_serve", fake_serve)
    monkeypatch.setattr(
        "sys.argv",
        ["transit-truth", "serve", "--host", "192.168.1.5", "--allow-public"],
    )
    cli.main()
    assert captured["host"] == "192.168.1.5"
    assert captured["allow_public"] is True


# ── P3: parameter clamp, security headers, concurrency cap ────────────────────


def test_out_of_range_parameter_returns_400(client):
    resp = client.post(
        "/api/verify",
        json={
            "base_url": "http://127.0.0.1/v1",
            "claimed_model": "gpt-4o-mini",
            "max_requests": 99999,
        },
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "invalid_parameter"


def test_security_headers_present(client):
    for resp in (client.get("/"), client.post("/api/verify", json={})):
        h = {k.lower(): v for k, v in resp.headers.items()}
        assert h.get("x-content-type-options") == "nosniff"
        assert h.get("x-frame-options") == "DENY"
        assert h.get("referrer-policy") == "no-referrer"
        csp = h.get("content-security-policy", "")
        assert "connect-src 'self'" in csp
        assert "frame-ancestors 'none'" in csp


def test_concurrency_cap_returns_429():
    app = build_serve_app(allow_local=True, loopback_only=False)
    sem = app.state.concurrent_semaphore
    original = sem._value  # drain by flipping the internal counter
    try:
        sem._value = 0
        with TestClient(app) as c:
            resp = c.post(
                "/api/verify",
                json={"base_url": "x", "claimed_model": "y"},
            )
        assert resp.status_code == 429, resp.text
        assert resp.json()["error"]["code"] == "too_many_requests"
    finally:
        sem._value = original


# ── v0.5.2: non-finite rejection, Host guard on all routes, Origin port ──────


def test_nan_parameter_rejected_400(client):
    resp = client.post(
        "/api/verify",
        json={
            "base_url": "http://127.0.0.1/v1",
            "claimed_model": "gpt-4o-mini",
            "max_requests": "NaN",
        },
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "invalid_parameter"


def test_infinity_parameter_rejected_400(client):
    resp = client.post(
        "/api/verify",
        json={
            "base_url": "http://127.0.0.1/v1",
            "claimed_model": "gpt-4o-mini",
            "timeout": "Infinity",
        },
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "invalid_parameter"


def test_host_whitelist_blocks_get_routes(loopback_client):
    # DNS-rebinding Host on a GET (static UI) must be refused, not just POST.
    for path in ("/", "/api/catalog"):
        resp = loopback_client.get(path, headers={"Host": "evil.com"})
        assert resp.status_code == 403, (path, resp.text)
        assert resp.json()["error"]["code"] == "invalid_host"


def test_loopback_host_allowed_on_get(loopback_client):
    resp = loopback_client.get("/", headers={"Host": "127.0.0.1:8766"})
    assert resp.status_code == 200


def test_origin_port_mismatch_rejected(client):
    # Same host, different declared port -> cross-origin 403.
    resp = client.post(
        "/api/verify",
        json={"base_url": "x", "claimed_model": "y"},
        headers={"Origin": "http://testserver:9999"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "cross_origin"


def test_bundled_webapp_resource_present():
    # The wheel bundles app.verify/webapp/index.html as the installed fallback.
    from importlib import resources

    bundled = resources.files("app.verify") / "webapp" / "index.html"
    assert bundled.is_file(), "bundled webapp/index.html missing from package"


def test_static_resolver_finds_index_without_env(monkeypatch):
    monkeypatch.delenv("TRANSIT_TRUTH_WEBAPP_DIR", raising=False)
    from app.verify.serve import _resolve_static_dir

    d = _resolve_static_dir(None)
    assert (d / "index.html").exists()


# ── v0.5.2: non-retryable upstream error body must not leak the key to logs ────


def test_non_retryable_error_body_not_logged(caplog):
    import logging

    from app.utils.http_client import AsyncAPIClient

    # Local stub returning 401 with the marker echoed in the error body.
    stub = FastAPI()

    @stub.post("/v1/chat/completions")
    async def _unauthorized(request: Request):
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=401,
            content={"error": f"invalid credentials {MARKER}"},
        )

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(stub, host="127.0.0.1", port=port, log_level="error")
    )
    threading.Thread(
        target=lambda: asyncio.run(server.serve(sockets=[sock])), daemon=True
    ).start()
    for _ in range(50):
        if server.started:
            break
        time.sleep(0.1)

    caplog.set_level(logging.WARNING, logger="app.utils.http_client")

    async def _run():
        async with AsyncAPIClient(
            api_key=MARKER,
            base_url=f"http://127.0.0.1:{port}/v1",
            ssrf_guard=False,
        ) as client:
            return await client.chat_completion(
                "gpt-4o-mini", [{"role": "user", "content": "hi"}]
            )

    try:
        result = asyncio.run(_run())
    finally:
        server.should_exit = True

    # Marker must appear neither in logs nor in the returned report body.
    for record in caplog.records:
        assert MARKER not in record.getMessage()
    assert MARKER not in json.dumps(result)


# ── v0.5.3: invalid present-but-bad knob -> 400; missing -> default ──────────


def test_invalid_present_max_requests_returns_400(client):
    resp = client.post(
        "/api/verify",
        json={"base_url": "x", "claimed_model": "y", "max_requests": "abc"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_parameter"


def test_invalid_present_timeout_returns_400(client):
    resp = client.post(
        "/api/verify",
        json={"base_url": "x", "claimed_model": "y", "timeout": "xyz"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_parameter"


def test_missing_knobs_use_defaults_not_400(client):
    # Absent knobs fall back to defaults; must NOT be rejected as invalid.
    resp = client.post(
        "/api/verify",
        json={"base_url": "x", "claimed_model": "y"},
    )
    # Reaches upstream/field validation, never a knob invalid_parameter 400.
    assert resp.json()["error"]["code"] != "invalid_parameter"
    assert resp.status_code != 400


# ── v0.5.4: integer knobs reject non-integer (float) values ─────────────────


def test_integer_knob_rejects_float_string(client):
    resp = client.post(
        "/api/verify",
        json={"base_url": "x", "claimed_model": "y", "max_requests": "12.5"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_parameter"


def test_integer_knob_rejects_float_number(client):
    resp = client.post(
        "/api/verify",
        json={"base_url": "x", "claimed_model": "y", "behavioral_samples": 2.5},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_parameter"
