"""v0.5.5 hard-cap self-consistency regression (P2-4).

When a tokenizer-family mismatch flips the verdict to ``suspicious``, the
hard-cap block must NOT overwrite the mismatch-specific ``evidence_reason``
with the tokenizer-match / family-consistent wording. Otherwise the report reads
``verdict=suspicious`` at the top while the body still claims
"family-consistent" -- a self-contradiction (reproducible on the official
no-key self-test path when the claimed and actual tokenizer families differ).

This test drives ``verify_endpoint`` against an in-process loopback stub that
reports an off-baseline tokenizer count (family mismatch) and modal behavioral
replies, then asserts the verdict and reason agree.
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

from app.verify import verify_endpoint

_HONEST_TOKENS = {
    "a    b    c    d    e    f    g    h": 43,
    "def foo(x): return x*2+1  # test": 41,
    "https://api.example.com/v1/chat/completions?model=gpt-4": 45,
    "café résumé naïve über 日本語 한국어 العربية": 38,
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa": 34,
}
_BEH_KEYS = ["between 1 and 10", "Flip a coin", "random color", "six-sided die"]
_MODAL = {
    "between 1 and 10": "7",
    "Flip a coin": "Heads",
    "random color": "Cerulean",
    "six-sided die": "4",
}


def _build_stub() -> FastAPI:
    app = FastAPI(title="v0.5.5 hard-cap consistency stub")

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
        if "Repeat this string exactly: " in user:
            s = user.split("Repeat this string exactly: ", 1)[1]
            # Family mismatch: every tokenizer probe reports prompt_tokens=999.
            return {
                "choices": [
                    {"index": 0, "message": {"role": "assistant", "content": s}}
                ],
                "usage": {
                    "prompt_tokens": 999,
                    "completion_tokens": 2,
                    "total_tokens": 1001,
                },
            }
        key = next((k for k in _BEH_KEYS if k in user), None)
        return {
            "choices": [
                {"index": 0, "message": {"role": "assistant", "content": _MODAL[key]}}
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
        }

    return app


def _start() -> tuple[str, uvicorn.Server]:
    app = _build_stub()
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
async def test_tokenizer_mismatch_suspicious_reason_not_family_consistent(monkeypatch):
    monkeypatch.setattr("app.utils.http_client.MAX_RETRIES", 0)
    url, server = _start()
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
    # Mismatch overrides to suspicious; hard-cap must keep the mismatch reason.
    assert report["verdict"] == "suspicious", blob
    reason = report["evidence_reason"] or ""
    # No family-consistent wording may survive next to verdict=suspicious.
    assert "family-consistent" not in reason.lower(), blob
    assert "family consistent" not in reason.lower(), blob
    # The reason must describe the family mismatch, not a match/no-certification.
    low = reason.lower()
    assert (
        "disagree" in low or "different model family" in low or "mismatch" in low
    ), blob


class _TokenizerOnlyBaseline:
    """Fake reference with tokenizer counts but NO behavioral distribution.

    Carries every ``BaselineDistribution`` field so the real analyzer's
    analyze() never AttributeErrors; behavioral_distributions is empty so the
    hard-cap branch (a) executes.
    """

    model_family = "fake"
    model_name = "fake-tokenizer-only"
    tokenizer_distributions: dict = {"tok-whitespace": [43, 43, 43]}
    behavioral_distributions: dict = {}
    latency_distribution: list = []
    sample_size = 0
    collected_at = ""


@pytest.mark.asyncio
async def test_tokenizer_only_baseline_hardcap_executes(monkeypatch):
    """P3-1: force the hard-cap branch with a tokenizer-only (no behavioral
    distribution) reference. The old unconditional reason-overwrite would
    clobber the mismatch reason; this test must FAIL if that regression returns.
    """
    monkeypatch.setattr("app.utils.http_client.MAX_RETRIES", 0)
    # Keep the real analyzer (analyze() runs normally) but force baseline
    # resolution to a tokenizer-only reference so hard-cap branch (a) executes.
    from app.verify.reference import load_reference_analyzer

    real = load_reference_analyzer()
    monkeypatch.setattr(
        real, "_resolve_baseline", lambda claimed_model: _TokenizerOnlyBaseline()
    )
    monkeypatch.setattr(
        "app.verify.core.load_reference_analyzer", lambda reference_dirs=None: real
    )
    url, server = _start()
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
    # Hard-cap branch (a) labels the tokenizer-only evidence kind explicitly.
    assert report["statistics"]["behavioral_evidence"] == "none_tokenizer_only", blob
    # The tokenizer-only reason must never carry family-consistent wording.
    reason = report["evidence_reason"] or ""
    assert "family-consistent" not in reason.lower(), blob
    assert "family consistent" not in reason.lower(), blob
    assert report["statistics"]["certification"] == "not_certified_tokenizer_only", blob
