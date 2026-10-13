"""Offline, key-free, network-free end-to-end tests for the verifier.

These tests stand up a *local OpenAI-compatible stub backend* (a FastAPI app on
the loopback interface) and run :func:`app.verify.verify_endpoint` against it.
The stub is explicitly a TEST STUB: it replays canned responses that do or do not
match the shipped real reference fingerprint (data/baselines/gpt-4o-mini.json).
No real API key, no outbound network.
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

# --- Canned reference values that reproduce the gpt-4o-mini baseline -------
_HONEST_TOKENS = {
    "a    b    c    d    e    f    g    h": 27,
    "def foo(x): return x*2+1  # test": 25,
    "https://api.example.com/v1/chat/completions?model=gpt-4": 29,
    "café résumé naïve über 日本語 한국어 العربية": 22,
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa": 18,
}
# A "cheating" relay that actually serves a Qwen-like tokenizer behind a
# gpt-4o-mini claim: token counts look nothing like the reference.
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
    app = FastAPI(title="transit-truth test stub")

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
    """Start the stub on an ephemeral loopback port; return (base_url, server)."""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    app = _build_stub(mode)
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)

    def run():
        asyncio.run(server.serve(sockets=[sock]))

    t = threading.Thread(target=run, daemon=True)
    t.start()
    for _ in range(50):
        if server.started:
            break
        time.sleep(0.1)
    return f"http://127.0.0.1:{port}/v1", server


@pytest.fixture(params=["honest", "cheat"])
def stub_server(request):
    base_url, server = _start_server(request.param)
    yield base_url, request.param
    server.should_exit = True
    time.sleep(0.1)


@pytest.mark.asyncio
async def test_honest_stub_passes():
    base_url, _ = _start_server("honest")
    report = await asyncio.wait_for(
        verify_endpoint(
            base_url=base_url,
            claimed_model="gpt-4o-mini",
            api_key="sk-test-do-not-leak",
            allow_local=True,
        ),
        timeout=30,
    )
    assert report["verdict"] == "pass", json.dumps(report, indent=2)
    assert report["error"] is None
    # The key must never appear anywhere in the report.
    assert "sk-test-do-not-leak" not in json.dumps(report)


@pytest.mark.asyncio
async def test_cheat_stub_not_pass():
    base_url, _ = _start_server("cheat")
    report = await asyncio.wait_for(
        verify_endpoint(
            base_url=base_url,
            claimed_model="gpt-4o-mini",
            api_key="sk-test-do-not-leak",
            allow_local=True,
        ),
        timeout=30,
    )
    # A mismatched relay must not be certified as honest.
    assert report["verdict"] != "pass", json.dumps(report, indent=2)


@pytest.mark.asyncio
async def test_missing_key_is_insufficient_evidence(monkeypatch):
    base_url, _ = _start_server("honest")
    monkeypatch.delenv("TRANSIT_TRUTH_API_KEY", raising=False)
    report = await verify_endpoint(
        base_url=base_url,
        claimed_model="gpt-4o-mini",
        api_key=None,
        api_key_env="TRANSIT_TRUTH_API_KEY",
        allow_local=True,
    )
    assert report["verdict"] == "insufficient_evidence"
    assert report["error"]["code"] == "missing_api_key"


@pytest.mark.asyncio
async def test_unknown_model_no_reference_is_insufficient():
    base_url, _ = _start_server("honest")
    report = await verify_endpoint(
        base_url=base_url,
        claimed_model="totally-unknown-model-xyz",
        api_key="sk-test",
        allow_local=True,
    )
    assert report["verdict"] == "insufficient_evidence"
    assert report["statistics"] is None or report["statistics"].get(
        "matched_reference_model"
    ) in (None, "totally-unknown-model-xyz")


@pytest.mark.asyncio
async def test_non_public_url_blocked_by_default():
    # Loopback must be rejected unless --allow-local / allow_local=True.
    report = await verify_endpoint(
        base_url="http://127.0.0.1:9/v1",
        claimed_model="gpt-4o-mini",
        api_key="sk-test",
        allow_local=False,
    )
    assert report["verdict"] == "insufficient_evidence"
    assert report["error"]["code"] == "invalid_endpoint"
    assert "sk-test" not in json.dumps(report)


# Imported at the bottom to keep the stub readable above.
from app.verify import verify_endpoint  # noqa: E402
