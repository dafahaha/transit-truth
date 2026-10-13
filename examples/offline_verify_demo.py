"""Offline, reproducible demo of the verifier (no network, no paid key).

Spins up a local OpenAI-compatible stub that serves REAL measured Qwen tokenizer
counts, then runs the verifier twice:

  1. claim "qwen2.5-0.5b-instruct" against the Qwen stub  -> expect pass
  2. claim "gpt-4o-mini"            against the Qwen stub  -> expect suspicious

Run from the repo root with the venv::

    .venv\\Scripts\\python.exe examples\\offline_verify_demo.py
"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time

import uvicorn
from fastapi import FastAPI, Request

from app.verify import verify_endpoint

# Real Qwen tokenizer counts (data/fingerprints/qwen2.5-0.5b-instruct.json).
QWEN_TOKENS = {
    "a    b    c    d    e    f    g    h": 20,
    "def foo(x): return x*2+1  # test": 18,
    "https://api.example.com/v1/chat/completions?model=gpt-4": 22,
    "café résumé naïve über 日本語 한국어 العربية": 18,
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa": 11,
}


def start_stub() -> tuple[str, uvicorn.Server]:
    app = FastAPI(title="offline demo stub")

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


async def main():
    url, server = start_stub()
    try:
        for claim in ["qwen2.5-0.5b-instruct", "gpt-4o-mini"]:
            report = await verify_endpoint(
                base_url=url,
                claimed_model=claim,
                api_key="offline-demo-key",
                allow_local=True,
            )
            print(f"\n=== claimed_model={claim} ===")
            print(f"verdict: {report['verdict']}")
            print(f"reason : {report['evidence_reason']}")
            tc = (report.get("statistics") or {}).get("tokenizer_consistency") or {}
            print(f"tokenizer score: {tc.get('score')} ({tc.get('verdict')})")
    finally:
        server.should_exit = True


if __name__ == "__main__":
    asyncio.run(main())
