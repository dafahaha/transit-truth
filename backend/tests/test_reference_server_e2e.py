"""v0.4.1 hotfix regression tests.

P0-1: ``reference_server.build_app`` must serve POST /v1/chat/completions with a
real 200 (not 422). The 422 happened because FastAPI/Request were imported inside
``build_app`` while ``from __future__ import annotations`` made ``request: Request``
unresolvable at route-registration time, so FastAPI treated it as a required query
param. We cover it both with a direct TestClient POST and a real-HTTP uvicorn ->
verify e2e that proves observations are non-empty.

P0-2: a backend that reports only the PUBLIC tokenizer numbers and returns a fixed
garbage behavioral string must NEVER be certified as ``pass`` for a tokenizer-only
reference (the open-source catalog has no behavioral distribution).
"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time

import pytest
import uvicorn
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.verify import verify_endpoint
from app.verify.reference_server import ReferenceBackend, build_app


# --------------------------------------------------------------------------- #
# P0-1: the route must not 422
# --------------------------------------------------------------------------- #
def test_build_app_post_chat_completions_is_not_422(monkeypatch):
    # Force stub mode so the test needs no network / tokenizer download.
    monkeypatch.setattr(
        ReferenceBackend, "load", lambda self: setattr(self, "mode", "stub") or "stub"
    )
    app, backend = build_app("qwen2.5-0.5b-instruct")
    client = TestClient(app)
    resp = client.post(
        "/v1/chat/completions",
        json={
            "model": "qwen2.5-0.5b-instruct",
            "messages": [
                {"role": "system", "content": "be brief"},
                {"role": "user", "content": "Repeat this string exactly: abc"},
            ],
        },
    )
    # The bug was HTTP 422 "Field required: request". It must be 200.
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "usage" in body and "prompt_tokens" in body["usage"]
    assert body["choices"][0]["message"]["content"]


def _start_reference_server(monkeypatch) -> tuple[str, uvicorn.Server]:
    monkeypatch.setattr(
        ReferenceBackend, "load", lambda self: setattr(self, "mode", "stub") or "stub"
    )
    app, _backend = build_app("qwen2.5-0.5b-instruct")
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    )
    threading.Thread(
        target=lambda: asyncio.run(server.serve(sockets=[sock])), daemon=True
    ).start()
    for _ in range(50):
        if server.started:
            break
        time.sleep(0.1)
    return f"http://127.0.0.1:{port}/v1", server


@pytest.mark.asyncio
async def test_reference_server_e2e_has_observations(monkeypatch):
    """Real-HTTP: run the full verify battery against the published reference
    server and prove probes land (no no_observations / 422)."""
    url, server = _start_reference_server(monkeypatch)
    try:
        report = await asyncio.wait_for(
            verify_endpoint(
                base_url=url,
                claimed_model="qwen2.5-0.5b-instruct",
                api_key="sk-test",
                allow_local=True,
            ),
            timeout=40,
        )
    finally:
        server.should_exit = True
    # The whole point: observations must be non-empty (the 422 path produced
    # error.code == "no_observations").
    assert report["error"] is None, json.dumps(report, indent=2)
    sizes = report.get("sample_sizes") or {}
    assert (sizes.get("tokenizer_probes") or 0) > 0, json.dumps(report, indent=2)
    # A stub-mode reference server cannot certify anything: verdict must be one
    # of the three states and must NOT be a false pass.
    assert report["verdict"] in ("pass", "suspicious", "insufficient_evidence")


# --------------------------------------------------------------------------- #
# P0-2: public tokenizer numbers + behavioral garbage must NOT pass
# --------------------------------------------------------------------------- #
def _start_fake_qwen() -> tuple[str, uvicorn.Server]:
    """A relay that reports the PUBLIC Qwen tokenizer counts but answers every
    behavioral probe with the same literal garbage."""
    app = FastAPI(title="fake qwen relay")
    PUBLIC_QWEN = {
        "a    b    c    d    e    f    g    h": 43,
        "def foo(x): return x*2+1  # test": 41,
        "https://api.example.com/v1/chat/completions?model=gpt-4": 45,
        "café résumé naïve über 日本語 한국어 العربية": 41,
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa": 34,
    }

    @app.post("/v1/chat/completions")
    async def chat(request: Request):
        body = await request.json()
        user = next(
            (
                m["content"]
                for m in reversed(body.get("messages", []))
                if m.get("role") == "user"
            ),
            "",
        )
        pt = 10
        content = "PWNED-GARBAGE-RESPONSE-12345"
        if "Repeat this string exactly: " in user:
            s = user.split("Repeat this string exactly: ", 1)[1]
            pt = PUBLIC_QWEN.get(s, 10)
        return {
            "choices": [
                {"index": 0, "message": {"role": "assistant", "content": content}}
            ],
            "usage": {
                "prompt_tokens": pt,
                "completion_tokens": 2,
                "total_tokens": pt + 2,
            },
        }

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    )
    threading.Thread(
        target=lambda: asyncio.run(server.serve(sockets=[sock])), daemon=True
    ).start()
    for _ in range(50):
        if server.started:
            break
        time.sleep(0.1)
    return f"http://127.0.0.1:{port}/v1", server


@pytest.mark.asyncio
async def test_fake_qwen_public_numbers_plus_garbage_never_passes():
    url, server = _start_fake_qwen()
    try:
        report = await asyncio.wait_for(
            verify_endpoint(
                base_url=url,
                claimed_model="qwen2.5-0.5b-instruct",
                api_key="sk-test",
                allow_local=True,
            ),
            timeout=40,
        )
    finally:
        server.should_exit = True
    tc = (report.get("statistics") or {}).get("tokenizer_consistency") or {}
    # Tokenizer numbers ARE the public ones -> tokenizer signal matches.
    assert tc.get("verdict") == "match", json.dumps(report, indent=2)
    # ...but that must NOT certify the relay: it has no behavioral evidence.
    assert report["verdict"] != "pass", json.dumps(report, indent=2)
    assert report["verdict"] == "insufficient_evidence", json.dumps(report, indent=2)


@pytest.mark.asyncio
async def test_garbage_against_baseline_with_behavioral_is_suspicious():
    """Control: a baseline WITH real behavioral data (gpt-4o-mini) must still
    catch the constant-garbage behavioral answer as suspicious."""
    url, server = _start_fake_qwen()
    try:
        report = await asyncio.wait_for(
            verify_endpoint(
                base_url=url,
                claimed_model="gpt-4o-mini",
                api_key="sk-test",
                allow_local=True,
            ),
            timeout=40,
        )
    finally:
        server.should_exit = True
    assert report["verdict"] == "suspicious", json.dumps(report, indent=2)
