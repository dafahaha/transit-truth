"""v0.4.2 honesty / anti-replay hotfix regressions.

P1: when there is NO behavioral evidence at all (the reference behavioral
distribution is empty, or zero observed behavioral responses overlap it), the
report must NOT print a high-confidence posterior / LR / CI -- those fields
must be null (NA) and the JSON must agree with the verdict
(``insufficient_evidence``). No more ``posterior=0.913, LR=4.5`` next to a
verdict that says we did not certify anything.

P2: behavioral probes run at temperature=0, so the shipped public baselines
are point masses (e.g. ``beh-number-1-10`` is always "7"). A deterministic
backend that just replays the ~4 public modal strings must NOT earn an
unreserved high-confidence pass: the report must flag
``deterministic_replay_risk`` and cap the confidence.
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
from app.verify.core import _behavioral_degeneracy

# Public gpt-4o-mini tokenizer numbers (the battery's 5 tokenizer probes).
_HONEST_TOKENS = {
    "a    b    c    d    e    f    g    h": 27,
    "def foo(x): return x*2+1  # test": 25,
    "https://api.example.com/v1/chat/completions?model=gpt-4": 29,
    "café résumé naïve über 日本語 한국어 العربية": 22,
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa": 18,
}
# Public Qwen tokenizer counts (open-source catalog, tokenizer-only).
_PUBLIC_QWEN = {
    "a    b    c    d    e    f    g    h": 43,
    "def foo(x): return x*2+1  # test": 41,
    "https://api.example.com/v1/chat/completions?model=gpt-4": 45,
    "café résumé naïve über 日本語 한국어 العربية": 41,
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa": 34,
}


def _start_qwen_stub_with_garbage_behavioral(
    tok_map: dict[str, int] | None = None,
) -> tuple[str, uvicorn.Server]:
    """Reports a fixed tokenizer map and a fixed garbage behavioral string every
    time. By default it reports the PUBLIC Qwen numbers (the open-source catalog
    has no behavioral reference); callers passing gpt-4o-mini should instead
    pass a clearly-mismatched map so the tokenizer check stays a mismatch."""
    tok_map = _PUBLIC_QWEN if tok_map is None else tok_map
    app = FastAPI(title="qwen public-numbers stub")

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
        content = "GARBAGE-BEHAVIOR-DO-NOT-TRUST"
        if "Repeat this string exactly: " in user:
            s = user.split("Repeat this string exactly: ", 1)[1]
            pt = tok_map.get(s, 10)
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


# --------------------------------------------------------------------------- #
# P1: zero behavioral evidence -> posterior/LR/CI must be null, not 0.913/4.5
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_no_behavioral_evidence_stats_are_null():
    url, server = _start_qwen_stub_with_garbage_behavioral()
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

    # verdict must stay capped (tokenizer-only catalog).
    assert report["verdict"] == "insufficient_evidence", json.dumps(report, indent=2)
    stats = report["statistics"]
    # The P1 bug: empty behavioral data still printed posterior=0.913, CI, LR=4.5.
    # All high-confidence numbers must now be null/NA.
    assert stats["posterior"] is None, json.dumps(stats, indent=2)
    assert stats["likelihood_ratio"] is None, json.dumps(stats, indent=2)
    assert stats["posterior_ci_95"] is None, json.dumps(stats, indent=2)
    assert stats["chi2_pvalue"] is None, json.dumps(stats, indent=2)
    assert stats["behavioral_evidence"] in (
        "none",
        "none_tokenizer_only",
    ), json.dumps(stats, indent=2)
    # And the old fabricated numbers must nowhere appear.
    blob = json.dumps(report)
    assert "0.913" not in blob
    assert '"likelihood_ratio": 4.5' not in blob


@pytest.mark.asyncio
async def test_real_behavioral_baseline_keeps_numbers():
    """Control: the SAME garbage backend claimed against gpt-4o-mini DOES have
    behavioral overlap, so the statistics must stay real numbers (not nulled).

    It reports a clearly DIFFERENT tokenizer (the old user-only gpt counts, which
    now mismatch the recalibrated system+user baseline) so the tokenizer check
    stays a mismatch. (After v0.4.4 the Qwen system+user numbers nearly coincide
    with the gpt-4o-mini baseline, so reusing them here would flip this to a
    match and defeat the test's intent.)"""
    _MISMATCH = {
        "a    b    c    d    e    f    g    h": 27,
        "def foo(x): return x*2+1  # test": 25,
        "https://api.example.com/v1/chat/completions?model=gpt-4": 29,
        "café résumé naïve über 日本語 한국어 العربية": 22,
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa": 18,
    }
    url, server = _start_qwen_stub_with_garbage_behavioral(tok_map=_MISMATCH)
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
    # Garbage behavioral answers vs the real baseline -> suspicious, as before.
    assert report["verdict"] == "suspicious", json.dumps(report, indent=2)
    stats = report["statistics"]
    # Behavioral evidence overlaps the baseline -> numbers are NOT nulled.
    assert stats["posterior"] is not None, json.dumps(stats, indent=2)
    assert stats["likelihood_ratio"] is not None, json.dumps(stats, indent=2)
    assert stats["posterior_ci_95"] is not None, json.dumps(stats, indent=2)
    assert stats["behavioral_evidence"] == "present", json.dumps(stats, indent=2)


# --------------------------------------------------------------------------- #
# P2: deterministic replay of public modal strings -> replay risk flag + cap
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_deterministic_replay_backend_not_unreserved():
    """Adversary claims gpt-4o-mini: tokenizer numbers = public ones, and the 4
    behavioral probes hard-coded to the public modal strings. That must NOT
    yield an unreserved high-confidence pass: deterministic_replay_risk flagged
    and confidence capped (the honest stub in test_verify.py IS this backend)."""
    from tests.test_verify import _start_server

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
    # Point-mass behavioral evidence must be flagged as replayable.
    drr = stats.get("deterministic_replay_risk") or {}
    assert drr.get("flag") is True, json.dumps(stats, indent=2)
    assert drr.get("degenerate_probes"), json.dumps(stats, indent=2)
    for probe, info in drr["degenerate_probes"].items():
        assert info["point_mass"] is True, probe
        assert info["mode_fraction"] >= 0.99, probe
    # If the verdict is a pass, it must NOT be an unreserved high-confidence one.
    if report["verdict"] == "pass":
        assert report["confidence"] == "low", json.dumps(report, indent=2)


# --------------------------------------------------------------------------- #
# Unit: degeneracy helper + analyze() null path
# --------------------------------------------------------------------------- #
def test_behavioral_degeneracy_detects_point_mass():
    deg = _behavioral_degeneracy(
        {
            "beh-number-1-10": ["7", "7", "7"],  # point mass
            "beh-coin-flip": ["Heads", "Tails", "Heads"],  # mixed
            "short": ["only-one"],  # n=1 -> ALWAYS a point mass (v0.4.3)
        }
    )
    assert deg["beh-number-1-10"]["point_mass"] is True
    assert deg["beh-number-1-10"]["mode"] == "7"
    assert deg["beh-number-1-10"]["mode_fraction"] == 1.0
    assert deg["beh-number-1-10"]["shannon_entropy_nats"] == 0.0
    assert deg["beh-coin-flip"]["point_mass"] is False
    # v0.4.3: n=1 is now counted and is a point mass by construction.
    assert deg["short"]["point_mass"] is True
    assert deg["short"]["n"] == 1
    assert deg["short"]["mode_fraction"] == 1.0
    assert deg["short"]["shannon_entropy_nats"] == 0.0


def test_analyze_no_overlap_nulls_posterior():
    from app.core.statistical_analyzer import StatisticalAnalyzer

    an = StatisticalAnalyzer()
    an.load_real_baselines()
    # Baseline exists (gpt-4o-mini) but ZERO observed behavioral overlap.
    v = an.analyze(
        "gpt-4o-mini",
        observed_tokenizer={"tok-whitespace": 27},
        observed_behavioral={},  # nothing observed
    )
    assert v.posterior_probability is None
    assert v.posterior_ci_lower is None
    assert v.posterior_ci_upper is None
    assert v.chi2_pvalue is None
    assert v.details["likelihood_ratio"] is None
    assert v.details["behavioral_evidence"] == "none"
    assert v.details["posterior_95ci"] is None
    assert v.conclusion == "inconclusive"
    assert v.confidence_level == "low"
