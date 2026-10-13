"""v0.4.3 thin-evidence / starving-backend hotfix regressions.

P2-A: an adversarial backend can answer each behavioral probe exactly ONCE with
the public modal string and 504 every repeat, so every overlapping probe ends up
with n=1. Before v0.4.3 that single sample still chi2-matched a point-mass
baseline (p~=1.0) and the verifier returned pass/medium with a spurious
posterior=0.913 -- no replay warning, no confidence cap.

After the fix:
  * n=1 is always a point mass (``_behavioral_degeneracy`` now counts n>=1), so
    ``deterministic_replay_risk`` fires;
  * a new ``thin_evidence`` gate requires >= MIN_BEHAVIORAL_SAMPLES_PER_PROBE
    successful repeats per overlapping probe. Below it, confidence is capped to
    ``low`` AND the Bayesian posterior/LR/CI are withheld (null), exactly like
    the v0.4.2 "no behavioral evidence" honesty contract.

The normal fully-sampled path (honest stub, n=3 per probe) must keep working: it
is still a point mass (replay flagged) but NOT thin, so its Bayesian numbers
stay real and are not nulled.
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

# Public gpt-4o-mini tokenizer numbers (the battery's 5 tokenizer probes).
# v0.4.4: battery system+user o200k counts.
_HONEST_TOKENS = {
    "a    b    c    d    e    f    g    h": 43,
    "def foo(x): return x*2+1  # test": 41,
    "https://api.example.com/v1/chat/completions?model=gpt-4": 45,
    "café résumé naïve über 日本語 한국어 العربية": 38,
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa": 34,
}
# Public modal behavioral strings (temperature=0 point-mass baselines).
_HONEST_BEH = {
    "between 1 and 10": "7",
    "Flip a coin": "Heads",
    "random color": "Cerulean",
    "six-sided die": "4",
}


def _start_hungry_stub() -> tuple[str, uvicorn.Server]:
    """Adversarial backend: answers each behavioral probe exactly ONCE with the
    public modal string, then 504s every repeat -> n=1 per behavioral probe.

    Tokenizer probes always succeed (they are the public, self-reported numbers).
    """
    app = FastAPI(title="hungry backend stub")
    lock = threading.Lock()
    answered: dict[str, int] = {}

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
        # Tokenizer probe: always succeed with the public numbers.
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

        # Behavioral probe: serve the modal string exactly once, then 504.
        reply, key = "", None
        for k, v in _HONEST_BEH.items():
            if k in user:
                reply, key = v, k
                break
        with lock:
            answered[key] = answered.get(key, 0) + 1
            first = answered[key] == 1
        if not first:
            # Mirrors the reported repro: a starving upstream returns 504.
            return JSONResponse(status_code=504, content={"error": "hungry"})
        return {
            "choices": [
                {"index": 0, "message": {"role": "assistant", "content": reply}}
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 2,
                "total_tokens": 12,
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
async def test_hungry_backend_n1_capped_thin_and_nulled(monkeypatch):
    """The exact P2-A repro: one modal answer + two 504s per behavioral probe."""
    # 504s are retryable with exponential backoff; for a fast, deterministic test
    # we disable retries so the starving 504s fail immediately (n=1 each).
    monkeypatch.setattr("app.utils.http_client.MAX_RETRIES", 0)

    url, server = _start_hungry_stub()
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
    # (1) Must NOT be a medium/high-confidence result.
    assert report["confidence"] == "low", blob
    assert not (
        report["verdict"] == "pass" and report["confidence"] in ("medium", "high")
    ), blob
    stats = report["statistics"]
    # (2) thin_evidence flagged, with the thin per-probe counts.
    te = stats.get("thin_evidence") or {}
    assert te.get("flag") is True, blob
    assert te.get("thin_probes"), blob
    for _pid, n in te["thin_probes"].items():
        assert n == 1, blob
    # (3) n=1 is a point mass -> deterministic replay risk must fire now.
    drr = stats.get("deterministic_replay_risk") or {}
    assert drr.get("flag") is True, blob
    assert drr.get("degenerate_probes"), blob
    # (4) Bayesian certification numbers withheld (honest contract).
    assert stats["posterior"] is None, blob
    assert stats["likelihood_ratio"] is None, blob
    assert stats["posterior_ci_95"] is None, blob
    # The old fabricated number must nowhere appear.
    assert "0.913" not in blob


@pytest.mark.asyncio
async def test_fully_sampled_path_not_thin(monkeypatch):
    """Control: the honest stub answers all 3 repeats per probe (n=3). It is
    still a point mass (replay flagged) but NOT thin: the Bayesian numbers must
    stay real and thin_evidence must NOT fire."""
    from tests.test_verify import _start_server

    monkeypatch.setattr("app.utils.http_client.MAX_RETRIES", 0)
    base_url, server = _start_server("honest")
    try:
        report = await asyncio.wait_for(
            verify_endpoint(
                base_url=base_url,
                claimed_model="gpt-4o-mini",
                api_key="sk-test",
                allow_local=True,
            ),
            timeout=40,
        )
    finally:
        server.should_exit = True

    stats = report["statistics"]
    # Not thin: n=3 per probe meets the floor.
    assert not stats.get("thin_evidence"), json.dumps(stats, indent=2)
    # But still point-mass replayable (temperature=0 baselines).
    drr = stats.get("deterministic_replay_risk") or {}
    assert drr.get("flag") is True, json.dumps(stats, indent=2)
    # Fully-sampled behavioral overlap -> Bayesian numbers stay real.
    assert stats["posterior"] is not None, json.dumps(stats, indent=2)
    assert stats["likelihood_ratio"] is not None, json.dumps(stats, indent=2)
    assert stats["posterior_ci_95"] is not None, json.dumps(stats, indent=2)


def test_unknown_model_posterior_is_null():
    """P3: a model with no reference must print posterior/LR/CI as null, not the
    fabricated prior 0.5 / [0,1]."""
    from app.core.statistical_analyzer import StatisticalAnalyzer

    an = StatisticalAnalyzer()
    an.load_real_baselines()
    v = an.analyze(
        "totally-unknown-model-xyz",
        observed_tokenizer={"tok-whitespace": 27},
        observed_behavioral={"beh-number-1-10": ["7"]},
    )
    assert v.posterior_probability is None
    assert v.posterior_ci_lower is None
    assert v.posterior_ci_upper is None
    assert v.conclusion == "inconclusive"
    assert v.confidence_level == "low"
