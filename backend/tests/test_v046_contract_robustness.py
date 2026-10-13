"""v0.4.6 contract & robustness regressions.

Three independently-reviewed P2s plus one P3:

1. **A single malformed field must not abort the whole battery** -- a behavioral
   repeat returning ``content:null`` used to raise ``AttributeError`` (not
   covered by the old ``(KeyError, IndexError, TypeError)`` catch) and a
   tokenizer response with ``usage:null`` raised ``None.get(...)`` the same way.
   Either one nuked the ~16 good evidence rows with ``transport_error``. One
   malformed observation must ONLY count as one failed/missing observation.

2. **stdout carries exactly one machine-readable JSON** -- baseline-loading
   diagnostics (``Loaded real baseline: ...``) used to print to stdout and break
   ``jq`` / ``json.load``. All diagnostics now go to stderr; verified at the
   subprocess level: stdout ``json.loads`` to one object with no log text.

3. **The demo banner must not contradict the seed rows** -- (Pages HTML, not a
   Python test.)

4. **A tokenizer-driven negative verdict must not display a behavioral
   posterior** -- when a tokenizer mismatch flips the verdict to
   ``suspicious``, the behavioral posterior/LR/CI/chi2 are withheld so the
   report is self-consistent.
"""

from __future__ import annotations

import asyncio
import json
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from fastapi import FastAPI, Request

from app.verify import verify_endpoint

# Battery system+user o200k tokenizer numbers (the recalibrated gpt-4o-mini baseline).
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


def _build_stub(behavior: str) -> FastAPI:
    """behavior:
    - 'null_content': the 2nd 'random color' repeat returns content:null.
    - 'null_usage': the FIRST tokenizer request returns usage:null.
    - 'tok_wild': every tokenizer request reports prompt_tokens=999 (family mismatch).
    All behavioral repeats otherwise return the modal strings (n=3/probe)."""
    app = FastAPI(title="v0.4.6 malformed-field stub")
    lock = threading.Lock()
    calls: dict[str, int] = {}

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
            with lock:
                calls["tok"] = calls.get("tok", 0) + 1
            pt = 999 if behavior == "tok_wild" else _HONEST_TOKENS.get(s, 10)
            if behavior == "null_usage" and calls["tok"] == 1:
                # Malformed: usage is JSON null.
                return {
                    "choices": [
                        {"index": 0, "message": {"role": "assistant", "content": s}}
                    ],
                    "usage": None,
                }
            return {
                "choices": [
                    {"index": 0, "message": {"role": "assistant", "content": s}}
                ],
                "usage": {
                    "prompt_tokens": pt,
                    "completion_tokens": 2,
                    "total_tokens": pt + 2,
                },
            }

        key = next((k for k in _BEH_KEYS if k in user), None)
        with lock:
            calls[key] = calls.get(key, 0) + 1
            nth = calls[key]
        if behavior == "null_content" and key == "random color" and nth == 2:
            # Malformed: content is JSON null.
            return {
                "choices": [
                    {"index": 0, "message": {"role": "assistant", "content": None}}
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 0,
                    "total_tokens": 10,
                },
            }
        return {
            "choices": [
                {"index": 0, "message": {"role": "assistant", "content": _MODAL[key]}}
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
        }

    return app


def _start(behavior: str) -> tuple[str, uvicorn.Server]:
    app = _build_stub(behavior)
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
async def test_single_null_content_repeat_does_not_abort_battery(monkeypatch):
    """P2 repro: 17 probes, exactly 1 behavioral repeat returns content:null.

    Old behavior: AttributeError -> whole battery aborted -> transport_error and
    the other ~16 good evidence rows were discarded. New behavior: that one
    repeat counts as a failed/missing observation; the run completes and emits
    a valid three-state JSON (the thin-evidence gate correctly caps it).
    """
    monkeypatch.setattr("app.utils.http_client.MAX_RETRIES", 0)
    url, server = _start("null_content")
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
    assert report["error"] is None, blob
    assert report["error"] is None and report.get("verdict") in (
        "pass",
        "suspicious",
        "insufficient_evidence",
    ), blob
    sizes = report["sample_sizes"]
    assert sizes["requests_used"] == 17, blob
    assert sizes["request_failures"] == 1, blob  # exactly the one null repeat
    beh = report["observations"]["behavioral"]
    assert len(beh["beh-random-color"]) == 2, blob  # 3 repeats - 1 null
    assert sum(len(v) for v in beh.values()) == 11, blob


@pytest.mark.asyncio
async def test_single_null_usage_tok_does_not_abort_battery(monkeypatch):
    """P2 repro (tokenizer side): one tokenizer response returns usage:null."""
    monkeypatch.setattr("app.utils.http_client.MAX_RETRIES", 0)
    url, server = _start("null_usage")
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
    assert report["error"] is None, blob
    sizes = report["sample_sizes"]
    assert sizes["request_failures"] == 1, blob
    tok = report["observations"]["tokenizer"]
    assert len(tok) == 4, blob  # 5 tok probes - 1 null usage
    # All 12 behavioral responses still landed.
    assert (
        sum(len(v) for v in report["observations"]["behavioral"].values()) == 12
    ), blob


@pytest.mark.asyncio
async def test_tokenizer_mismatch_flip_nulls_behavioral_numbers(monkeypatch):
    """P3: when a tokenizer mismatch overrides the verdict to suspicious, the
    behavioral posterior/LR/CI/chi2 must NOT remain displayed (self-contradictory
    next to verdict=suspicious)."""
    monkeypatch.setattr("app.utils.http_client.MAX_RETRIES", 0)
    url, server = _start("tok_wild")
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
    assert report["verdict"] == "suspicious", blob
    assert report["confidence"] == "low", blob
    stats = report["statistics"]
    assert stats["posterior"] is None, blob
    assert stats["likelihood_ratio"] is None, blob
    assert stats["posterior_ci_95"] is None, blob
    assert stats["chi2_pvalue"] is None, blob
    assert "0.913" not in blob


def test_baseline_loading_diagnostics_go_to_stderr(capsys):
    """P2 contract: baseline/fingerprint diagnostics must never touch stdout."""
    from app.verify.reference import load_reference_analyzer

    load_reference_analyzer()
    captured = capsys.readouterr()
    assert "Loaded" not in captured.out, captured.out
    assert "Loaded real baseline" in captured.err, captured.err


_SUBPROCESS_SCRIPT = r"""
import asyncio, json, socket, threading, time
import uvicorn
from fastapi import FastAPI, Request

HONEST = {
    "a    b    c    d    e    f    g    h": 43,
    "def foo(x): return x*2+1  # test": 41,
    "https://api.example.com/v1/chat/completions?model=gpt-4": 45,
    "café résumé naïve über 日本語 한국어 العربية": 38,
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa": 34,
}
KEYS = ["between 1 and 10", "Flip a coin", "random color", "six-sided die"]
MODAL = {"between 1 and 10": "7", "Flip a coin": "Heads",
         "random color": "Cerulean", "six-sided die": "4"}

app = FastAPI()
@app.post("/v1/chat/completions")
async def chat(request: Request):
    body = await request.json()
    user = next((m["content"] for m in reversed(body.get("messages", []))
                 if m.get("role") == "user"), "")
    if "Repeat this string exactly: " in user:
        s = user.split("Repeat this string exactly: ", 1)[1]
        pt = HONEST.get(s, 10)
        return {"choices": [{"index": 0, "message": {"role": "assistant", "content": s}}],
                "usage": {"prompt_tokens": pt, "completion_tokens": 2, "total_tokens": pt + 2}}
    key = next((k for k in KEYS if k in user), None)
    return {"choices": [{"index": 0, "message": {"role": "assistant", "content": MODAL[key]}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}}

sock = socket.socket(); sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]
server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
threading.Thread(target=lambda: asyncio.run(server.serve(sockets=[sock])), daemon=True).start()
for _ in range(50):
    if server.started: break
    time.sleep(0.1)

from app.verify import verify_endpoint
report = asyncio.run(verify_endpoint(
    base_url=f"http://127.0.0.1:{port}/v1",
    claimed_model="gpt-4o-mini", api_key="sk-test",
    allow_local=True, timeout=5.0, total_timeout=30.0))
server.should_exit = True
print(json.dumps(report))
"""


def test_verify_stdout_is_single_clean_json_subprocess():
    """P2 contract, subprocess level: stdout must json.loads as ONE JSON object
    and must not contain diagnostic log text; stderr carries the diagnostics."""
    backend_dir = str(Path(__file__).resolve().parents[1])
    env = dict(__import__("os").environ)
    env["PYTHONPATH"] = backend_dir
    proc = subprocess.run(
        [sys.executable, "-c", _SUBPROCESS_SCRIPT],
        cwd=backend_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    # stdout is exactly one machine-readable JSON object.
    report = json.loads(proc.stdout)
    assert isinstance(report, dict)
    assert "Loaded" not in proc.stdout
    assert "Loaded real baseline" in proc.stderr
    assert report["error"] is None, json.dumps(report, indent=2)
