"""v4 hardening: fail-closed behavior, key redaction, malformed/forged responses."""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time

import pytest
import uvicorn
from fastapi import FastAPI, Request

from app.verify import verify_endpoint

SUPER_SECRET = "sk-super-secret-ABCD1234-do-not-leak"


def _start_raw_stub(handler) -> tuple[str, uvicorn.Server]:
    app = FastAPI()

    @app.post("/v1/chat/completions")
    async def chat(request: Request):
        return handler(request)

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
async def test_malformed_response_does_not_crash():
    def handler(request):
        return {"unexpected": "no choices, no usage"}  # forged/broken payload

    url, server = _start_raw_stub(handler)
    try:
        report = await verify_endpoint(
            base_url=url,
            claimed_model="gpt-4o-mini",
            api_key=SUPER_SECRET,
            allow_local=True,
        )
    finally:
        server.should_exit = True
    # No observations -> fail closed, not a false pass.
    assert report["verdict"] == "insufficient_evidence"
    assert report["error"]["code"] == "no_observations"
    assert SUPER_SECRET not in json.dumps(report)


@pytest.mark.asyncio
async def test_key_never_in_transport_error():
    # A closed port -> transport_error; the message must not contain the key.
    report = await verify_endpoint(
        base_url="http://127.0.0.1:9/v1",  # nothing listening (with allow_local)
        claimed_model="gpt-4o-mini",
        api_key=SUPER_SECRET,
        allow_local=True,
        timeout=2.0,
    )
    assert report["verdict"] == "insufficient_evidence"
    blob = json.dumps(report)
    assert SUPER_SECRET not in blob
    assert "sk-super" not in blob


@pytest.mark.asyncio
async def test_private_ip_blocked_by_default():
    # Even a RFC1918 target must be refused when allow_local is False.
    report = await verify_endpoint(
        base_url="http://192.168.1.10/v1",
        claimed_model="gpt-4o-mini",
        api_key=SUPER_SECRET,
        allow_local=False,
    )
    assert report["verdict"] == "insufficient_evidence"
    assert report["error"]["code"] == "invalid_endpoint"


@pytest.mark.asyncio
async def test_unknown_protocol_rejected():
    report = await verify_endpoint(
        base_url="ftp://example.com/v1",
        claimed_model="gpt-4o-mini",
        api_key=SUPER_SECRET,
        allow_local=False,
    )
    assert report["verdict"] == "insufficient_evidence"
    assert report["error"]["code"] == "invalid_endpoint"
