"""v0.4.4 coverage-gate / non-cooperation hotfix + tokenizer caliber-lock tests.

P1 (starvation 2.0): the thin-evidence gate only counted probes the backend
actually answered. An adversarial backend that answers ONE overlapping
behavioral probe with a 2:1 split and 504s the OTHER overlapping probes entirely
(n=0) used to earn pass/medium with a spurious posterior=0.913 and no flag.
The v0.4.4 coverage gate uses the CLIENT-SENT probe universe as the denominator,
so a probe we sent but got zero usable responses for counts as n=0: coverage
drops, ``non_cooperation`` fires, the verdict may not be pass, and the Bayesian
posterior/LR/CI/chi-square are withheld (null).

P2 (caliber lock): the gpt-4o / gpt-4o-mini baselines must equal the offline
o200k count of the battery's exact system+user request, and a real-caliber
observation must produce tokenizer_consistency=match (never a forced
suspicious).
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
from fastapi.responses import JSONResponse

from app.verify import verify_endpoint
from app.verify.reference import load_reference_analyzer, tokenizer_consistency
from app.verify.tokenizer_caliber import expected_battery_tokenizer_counts

# Battery system+user o200k tokenizer numbers (the recalibrated gpt-4o-mini baseline).
_HONEST_TOKENS = {
    "a    b    c    d    e    f    g    h": 43,
    "def foo(x): return x*2+1  # test": 41,
    "https://api.example.com/v1/chat/completions?model=gpt-4": 45,
    "café résumé naïve über 日本語 한국어 العربية": 38,
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa": 34,
}
# Overlapping behavioral probes (battery sends 4, all overlap the gpt-4o-mini
# baseline). Key = substring matched on the user prompt.
_BEH_KEYS = ["between 1 and 10", "Flip a coin", "random color", "six-sided die"]
_MODAL = {
    "between 1 and 10": "7",
    "Flip a coin": "Heads",
    "random color": "Cerulean",
    "six-sided die": "4",
}


def _build_stub(mode: str) -> FastAPI:
    """mode='starve_one': answer only random-color (2:1 split), 504 the rest.
    mode='n1_each': answer each behavioral probe once, 504 repeats."""
    app = FastAPI(title="v0.4.4 adversarial stub")
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
            pt = _HONEST_TOKENS.get(s, 10)
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
        if key is None:
            return JSONResponse(status_code=504, content={"error": "nope"})

        with lock:
            calls[key] = calls.get(key, 0) + 1
            nth = calls[key]

        if mode == "starve_one":
            # Only random-color answers; the other 3 overlapping probes are n=0.
            if key != "random color":
                return JSONResponse(status_code=504, content={"error": "hungry"})
            reply = "Cerulean" if nth <= 2 else "Turquoise"  # 2:1 split, mode<0.99
            return _beh_response(reply)

        # n1_each: modal string once, then 504.
        if nth > 1:
            return JSONResponse(status_code=504, content={"error": "hungry"})
        return _beh_response(_MODAL[key])

    return app


def _beh_response(reply: str) -> dict:
    return {
        "choices": [{"index": 0, "message": {"role": "assistant", "content": reply}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
    }


def _start(mode: str) -> tuple[str, uvicorn.Server]:
    app = _build_stub(mode)
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
async def test_starved_one_probe_not_pass_nulled(monkeypatch):
    """Repro P1: only 1 overlapping probe answered (n=3, 2:1), other 3 all 504."""
    monkeypatch.setattr("app.utils.http_client.MAX_RETRIES", 0)
    url, server = _start("starve_one")
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
    # Must NOT be a pass.
    assert report["verdict"] != "pass", blob
    assert report["confidence"] == "low", blob
    stats = report["statistics"]
    # non_cooperation must fire, listing the starved probes.
    nc = stats.get("non_cooperation") or {}
    assert nc.get("flag") is True, blob
    assert len(nc.get("starved_probes", {})) >= 3, blob
    assert nc.get("behavioral_coverage", 1.0) < 0.8, blob
    # Bayesian numbers withheld.
    assert stats["posterior"] is None, blob
    assert stats["likelihood_ratio"] is None, blob
    assert stats["posterior_ci_95"] is None, blob
    assert stats["chi2_pvalue"] is None, blob
    assert "0.913" not in blob


@pytest.mark.asyncio
async def test_all_answered_n1_each_still_capped(monkeypatch):
    """P1-②: every overlapping probe answered but only once (n=1 each)."""
    monkeypatch.setattr("app.utils.http_client.MAX_RETRIES", 0)
    url, server = _start("n1_each")
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
    assert report["verdict"] != "pass", blob
    assert report["confidence"] == "low", blob
    stats = report["statistics"]
    # thin_evidence fires (n=1 each) AND the coverage gate fires.
    te = stats.get("thin_evidence") or {}
    assert te.get("flag") is True, blob
    assert len(te.get("thin_probes", {})) == 4, blob
    assert stats.get("non_cooperation", {}).get("flag") is True, blob
    assert stats["posterior"] is None, blob
    assert stats["likelihood_ratio"] is None, blob
    assert stats["chi2_pvalue"] is None, blob
    assert "0.913" not in blob


@pytest.mark.asyncio
async def test_cooperative_full_sampling_unaffected(monkeypatch):
    """P1-③ control: a cooperative backend (n=3 per probe) must NOT be gated and
    keeps its real Bayesian numbers."""
    from tests.test_verify import _start_server

    monkeypatch.setattr("app.utils.http_client.MAX_RETRIES", 0)
    url, server = _start_server("honest")
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

    stats = report["statistics"]
    assert not stats.get("non_cooperation"), json.dumps(stats, indent=2)
    assert not stats.get("thin_evidence"), json.dumps(stats, indent=2)
    assert stats["posterior"] is not None, json.dumps(stats, indent=2)
    assert stats["likelihood_ratio"] is not None, json.dumps(stats, indent=2)
    assert stats["chi2_pvalue"] is not None, json.dumps(stats, indent=2)


def test_baseline_tokenizer_caliber_lock():
    """P2 lock: shipped gpt baseline prompt-token means must equal the offline
    o200k count of the battery's exact system+user request, and a real-caliber
    observation must yield tokenizer_consistency=match."""
    import json
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    expected = expected_battery_tokenizer_counts()

    for model in ("gpt-4o-mini", "gpt-4o"):
        data = json.loads(
            (repo / "data" / "baselines" / f"{model}.json").read_text(encoding="utf-8")
        )
        for pid, probe in data["tokenizer"].items():
            mean = probe["prompt_tokens"]["mean"]
            assert mean == expected[pid], (
                f"{model} {pid}: baseline mean={mean} != o200k battery count "
                f"= {expected[pid]} (caliber drift)"
            )

    # A real-caliber observation against the gpt-4o-mini baseline must MATCH,
    # not force suspicious.
    analyzer = load_reference_analyzer()
    baseline = analyzer._resolve_baseline("gpt-4o-mini")
    observed = {
        pid: expected[pid]
        for pid in (
            "tok-whitespace",
            "tok-code",
            "tok-url",
            "tok-mixed-unicode",
            "tok-repeated-chars",
        )
    }
    tc = tokenizer_consistency(observed, baseline)
    assert tc["verdict"] == "match", json.dumps(tc, indent=2)
    assert tc["score"] == 1.0, json.dumps(tc, indent=2)
