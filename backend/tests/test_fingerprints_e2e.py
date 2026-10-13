"""v2 e2e: the open-source fingerprint catalog distinguishes model families.

Uses a local stub that replays REAL measured tokenizer counts for
qwen2.5-0.5b-instruct (data/fingerprints/qwen2.5-0.5b-instruct.json, measured
with the real Qwen tokenizer via hf-mirror). No network, no paid key.
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
from tests.test_verify import _start_server

from app.verify import verify_endpoint

# Real Qwen tokenizer counts measured on 2026-10-14 (see fingerprint file).
QWEN_TOKENS = {
    "a    b    c    d    e    f    g    h": 20,
    "def foo(x): return x*2+1  # test": 18,
    "https://api.example.com/v1/chat/completions?model=gpt-4": 22,
    "café résumé naïve über 日本語 한국어 العربية": 18,
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa": 11,
}


def _start_qwen_stub() -> tuple[str, "uvicorn.Server"]:
    """A stub serving REAL Qwen token counts (behavioral is a fixed stub)."""
    app = FastAPI(title="qwen-real-token stub")

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
        if "Repeat this string exactly: " in user:
            s = user.split("Repeat this string exactly: ", 1)[1]
            pt = QWEN_TOKENS.get(s, 10)
        return {
            "choices": [
                {"index": 0, "message": {"role": "assistant", "content": "stub"}}
            ],
            "usage": {
                "prompt_tokens": pt,
                "completion_tokens": 1,
                "total_tokens": pt + 1,
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
async def test_qwen_tokenizer_matches_qwen_claim():
    url, server = _start_qwen_stub()
    try:
        report = await verify_endpoint(
            base_url=url,
            claimed_model="qwen2.5-0.5b-instruct",
            api_key="sk-test",
            allow_local=True,
        )
    finally:
        server.should_exit = True
    assert report["verdict"] == "pass", json.dumps(report, indent=2)
    tc = report["statistics"]["tokenizer_consistency"]
    assert tc["verdict"] == "match"
    assert tc["score"] == 1.0


@pytest.mark.asyncio
async def test_qwen_tokenizer_rejects_gpt_claim():
    url, server = _start_qwen_stub()
    try:
        report = await verify_endpoint(
            base_url=url,
            claimed_model="gpt-4o-mini",
            api_key="sk-test",
            allow_local=True,
        )
    finally:
        server.should_exit = True
    # Qwen token counts must NOT be certified as gpt-4o-mini.
    assert report["verdict"] == "suspicious", json.dumps(report, indent=2)
    tc = report["statistics"]["tokenizer_consistency"]
    assert tc["verdict"] == "mismatch"
