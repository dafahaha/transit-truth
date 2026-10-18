"""v0.5.9 P3-1 regression: a malformed 200 must be counted as a failed
observation and must never enter the statistics or yield a pass.

The v0.4.7 battery resilience test (``test_v047_nonjson_and_tokenizer_band``)
proves that ONE malformed repeat does not abort the whole battery; it does not
pin two harder contracts:

1. **Client layer:** a 200 whose body is non-JSON (HTML WAF / plain text /
   empty) or a non-object JSON body (array) must be counted as ``failed`` (not
   ``successful``) and returned with an ``error`` code -- it must never be
   treated as usable evidence.
2. **End-to-end:** when every probe returns such a body, the run fails closed
   as ``no_observations`` / ``insufficient_evidence``: no posterior, no
   behavioral evidence, never a ``pass``.
"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time

import pytest
import uvicorn
from fastapi import FastAPI, Response

from app.utils.http_client import AsyncAPIClient
from app.verify import verify_endpoint

_SHAPES = {
    "html_waf": ("html", "<html><body>WAF block</body></html>", "text/html"),
    "plain_text": ("text", "service unavailable, try later", "text/plain"),
    "empty_body": ("empty", b"", "application/json"),
    "json_array": ("array", '[{"choices":[]}]', "application/json"),
}


def _start(route_shape: str):
    """Local stub whose single POST returns the selected malformed 200 body."""
    kind, content, media = _SHAPES[route_shape]
    app = FastAPI(title="v0.5.9 malformed-200 stub")

    @app.post("/v1/chat/completions")
    async def chat():
        if kind == "html":
            return Response(content=content, media_type=media, status_code=200)
        if kind == "text":
            return Response(content=content, media_type=media, status_code=200)
        if kind == "empty":
            return Response(content=content, media_type=media, status_code=200)
        return Response(content=content, media_type=media, status_code=200)

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
@pytest.mark.parametrize("shape", list(_SHAPES.keys()))
async def test_client_counts_malformed_200_as_failure_not_success(monkeypatch, shape):
    """Client layer: non-JSON / non-object 200 -> failed, error code set."""
    monkeypatch.setattr("app.utils.http_client.MAX_RETRIES", 0)
    url, server = _start(shape)
    try:
        async with AsyncAPIClient(
            api_key="sk-test", base_url=url, ssrf_guard=False
        ) as client:
            out = await client.chat_completion(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "hi"}],
            )
    finally:
        server.should_exit = True

    err = out.get("error") or {}
    if shape == "json_array":
        assert err.get("error") == "non_json_object", json.dumps(out)
    else:
        assert err.get("error") == "non_json_response", json.dumps(out)
    # Counted as a failed observation, never as a successful usable response.
    assert client._stats["failed"] == 1, client._stats
    assert client._stats["successful"] == 0, client._stats


@pytest.mark.asyncio
@pytest.mark.parametrize("shape", list(_SHAPES.keys()))
async def test_all_malformed_run_fails_closed_never_passes(monkeypatch, shape):
    """End-to-end: every probe malformed -> no_observations / insufficient_evidence."""
    monkeypatch.setattr("app.utils.http_client.MAX_RETRIES", 0)
    url, server = _start(shape)
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

    blob = json.dumps(report, indent=2)
    err = report["error"]
    # Fail-closed: the only allowed error is no_observations; never transport_error.
    assert err is None or err.get("code") == "no_observations", blob
    assert (err or {}).get("code") != "transport_error", blob

    # Nothing usable reached observations; no posterior is built from zero evidence.
    obs = report.get("observations") or {}
    assert obs.get("tokenizer", []) == [], blob
    assert sum(len(v) for v in obs.get("behavioral", {}).values()) == 0, blob
    stats = report.get("statistics") or {}
    assert stats.get("posterior") is None, blob
    assert stats.get("likelihood_ratio") is None, blob

    # Never pass; the fail-closed verdict is insufficient_evidence.
    assert report["verdict"] != "pass", blob
    assert report["verdict"] == "insufficient_evidence", blob
