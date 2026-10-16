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

from app.verify.serve import build_serve_app, sanitize_report

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
    # the public SSRF guard on.
    app = build_serve_app(allow_local=True)
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
