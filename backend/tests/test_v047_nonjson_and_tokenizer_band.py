"""v0.4.7 regressions.

Two independently-reviewed issues:

1. **P2: a 200 response body that is NOT a JSON object must not nuke the whole
   battery.** Upstream can return 200 with an HTML WAF / maintenance page,
   plain text, an empty body, or a JSON array (``[...]``) -- the OpenAI schema
   requires an object. Previously ``response.json()`` raised
   ``json.JSONDecodeError`` (a ``ValueError`` subclass) / ``TypeError``, which
   escaped the retry/exception capture in ``chat_completion`` and propagated
   through ``battery.py``'s ``asyncio.gather`` (no ``return_exceptions``) as a
   whole-battery ``transport_error``, discarding the ~16 good evidence rows.
   The v0.4.6 contract ("one malformed observation must not abort the battery")
   only hardened legal-JSON null content/usage. v0.4.7 closes the non-JSON
   body hole with double insurance: (a) the 200 branch in ``chat_completion``
   catches ``ValueError / TypeError`` and treats a non-object body as one
   failed observation (retryable then recorded), and (b) ``gather`` now uses
   ``return_exceptions=True`` so any single per-request exception only degrades
   that one probe.

2. **P3-1: tokenizer match must not upgrade to ``pass`` in the Bayesian
   uncertain band.** When behavioral evidence is neutral-to-against the claim
   (e.g. distribution-replay scenarios with LR≈0.45, posterior≈0.51), a
   tokenizer match alone is necessary-but-not-sufficient: it says "same
   tokenizer family", not "this is the claimed model". Previously the tokenizer
   override flipped ``insufficient_evidence`` straight to ``pass`` (with
   confidence=low), which over-certified. v0.4.7 requires the behavioral
   evidence to actually support the claim (LR≥1 AND posterior≥0.5) before a
   tokenizer match can upgrade to pass; otherwise the result stays
   ``insufficient_evidence`` with the deterministic-replay / thin-evidence
   flags preserved.
"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time

import pytest
import uvicorn
from fastapi import FastAPI, Request, Response

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

# The four non-JSON 200 body shapes the P2 is about.
_NON_JSON_SHAPES = {
    "html_waf": (
        Response(
            content="<html><body>WAF block</body></html>",
            media_type="text/html",
            status_code=200,
        ),
        "HTML WAF page",
    ),
    "plain_text": (
        Response(
            content="service unavailable, try later",
            media_type="text/plain",
            status_code=200,
        ),
        "plain-text body",
    ),
    "empty_body": (
        Response(content=b"", media_type="application/json", status_code=200),
        "empty body",
    ),
    "json_array": (
        Response(
            content='[{"choices":[]}]',
            media_type="application/json",
            status_code=200,
        ),
        "JSON array (not an object)",
    ),
}


def _build_stub(
    non_json_shape: str | None,
    poison_beh: bool = False,
    uncertain_band: bool = False,
) -> FastAPI:
    """Build a stub endpoint.

    Args:
        non_json_shape: if set, the FIRST repeat of "random color" returns this
            non-JSON 200 body (exactly 1 of 17 requests malformed).
        poison_beh: if True, every behavioral repeat returns a wildly
            off-baseline string (chi2 p << 0.01 -> mismatch -> suspicious).
        uncertain_band: if True, reproduce the exact v0.4.7 P3-1 scenario:
            number/color/dice modal, coin-flip = Heads, Heads, Tails (2:1).
            With the shipped gpt-4o-mini baseline (39 Heads / 10 Heads. /
            1 Tails), chi2 lands at p=0.0205 -> LR=0.45, posterior=0.512,
            conclusion=inconclusive. Tokenizer numbers are exactly the o200k
            honest counts (match).
    """
    app = FastAPI(title="v0.4.7 non-JSON / tokenizer-band stub")
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
        with lock:
            calls[key] = calls.get(key, 0) + 1
            nth = calls[key]

        # P2: poison the FIRST repeat of ONE specific behavioral probe
        # ("random color") with a non-JSON 200 body. The other 3 probes and
        # the remaining 2 repeats of "random color" return normal chat objects,
        # so exactly 1 of the 17 requests is malformed.
        if non_json_shape is not None and key == "random color" and nth == 1:
            resp, _label = _NON_JSON_SHAPES[non_json_shape]
            return resp

        if uncertain_band:
            # Exact v0.4.7 P3-1 repro: number/color/dice modal, coin 2 Heads + 1 Tails.
            if key == "Flip a coin":
                resp = "Heads" if nth <= 2 else "Tails"
            else:
                resp = _MODAL[key]
            return {
                "choices": [
                    {"index": 0, "message": {"role": "assistant", "content": resp}}
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 2,
                    "total_tokens": 12,
                },
            }

        if poison_beh:
            # Deliberately non-modal: a string the reference distribution does
            # not contain. The chi-square / Bayesian update lands LR<1
            # (behavioral evidence argues against the claim), but tokenizer
            # numbers are still exactly the gpt-4o-mini baseline (match).
            poison = {
                "between 1 and 10": "3",
                "Flip a coin": "Tails",
                "random color": "Maroon",
                "six-sided die": "1",
            }[key]
            return {
                "choices": [
                    {"index": 0, "message": {"role": "assistant", "content": poison}}
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 2,
                    "total_tokens": 12,
                },
            }

        return {
            "choices": [
                {"index": 0, "message": {"role": "assistant", "content": _MODAL[key]}}
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
        }

    return app


def _start(
    non_json_shape: str | None = None,
    poison_beh: bool = False,
    uncertain_band: bool = False,
):
    app = _build_stub(
        non_json_shape, poison_beh=poison_beh, uncertain_band=uncertain_band
    )
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
@pytest.mark.parametrize("shape", list(_NON_JSON_SHAPES.keys()))
async def test_non_json_200_body_does_not_abort_battery(monkeypatch, shape):
    """P2: 17 probes, the FIRST behavioral repeat returns a non-JSON 200 body.

    Old behavior: ``response.json()`` raised -> whole battery aborted ->
    ``transport_error`` and the other ~16 good evidence rows were discarded.
    New behavior: that one repeat counts as a failed observation; the run
    completes and emits a valid three-state JSON; the other good evidence
    (4 tokenizer probes + 11 behavioral repeats) is preserved.
    """
    monkeypatch.setattr("app.utils.http_client.MAX_RETRIES", 0)
    url, server = _start(non_json_shape=shape)
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
    # Must NOT be a whole-battery transport_error.
    assert report["error"] is None, blob
    assert (report.get("error") or {}).get("code") != "transport_error", blob
    assert report.get("verdict") in (
        "pass",
        "suspicious",
        "insufficient_evidence",
    ), blob
    sizes = report["sample_sizes"]
    # 5 tokenizer probes + 4 behavioral probes * 3 repeats = 17.
    assert sizes["requests_used"] == 17, blob
    # Exactly one repeat failed (the poisoned first behavioral repeat).
    assert sizes["request_failures"] == 1, blob
    # All 5 tokenizer probes still landed (the poisoned one was a behavioral
    # repeat, not a tokenizer probe).
    assert len(report["observations"]["tokenizer"]) == 5, blob
    # 12 behavioral repeats total, minus the 1 poisoned = 11.
    beh = report["observations"]["behavioral"]
    assert sum(len(v) for v in beh.values()) == 11, blob


@pytest.mark.asyncio
async def test_uncertain_band_behavior_plus_tokenizer_match_does_not_pass(monkeypatch):
    """P3-1 exact repro: number/color/dice modal, coin = Heads, Heads, Tails.

    With the shipped gpt-4o-mini baseline this lands chi2 p=0.0205, LR=0.45,
    posterior=0.512, conclusion=inconclusive. Tokenizer numbers match exactly
    (tok_check=match). The OLD code flipped insufficient_evidence -> pass. The
    v0.4.7 guard must NOT upgrade: behavioral LR<1 means the evidence is not
    supporting the claim, and a tokenizer match alone cannot certify identity.
    Verdict must stay insufficient_evidence (not pass, not suspicious -- the
    tokenizer match says same family, the behavior is just inconclusive)."""
    monkeypatch.setattr("app.utils.http_client.MAX_RETRIES", 0)
    url, server = _start(non_json_shape=None, uncertain_band=True)
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
    # Tokenizer consistency must be a match (poison only touched behavior).
    tc = report["statistics"].get("tokenizer_consistency") or {}
    assert tc.get("verdict") == "match", blob
    # The behavioral LR / posterior must be in the uncertain band.
    lr = report["statistics"].get("likelihood_ratio")
    post = report["statistics"].get("posterior")
    assert lr is not None and lr < 1.0, blob
    assert post is not None and post < 0.6, blob
    # The verdict must NOT be pass.
    assert report["verdict"] != "pass", blob
    # And it should be insufficient_evidence (not suspicious -- tokenizer
    # match means same family; behavioral evidence is just inconclusive).
    assert report["verdict"] == "insufficient_evidence", blob


@pytest.mark.asyncio
async def test_normal_behavior_match_plus_tokenizer_match_still_passes(monkeypatch):
    """Control: with normal modal (matching) behavioral evidence AND a tokenizer
    match, the verdict must still be pass -- the v0.4.7 guard must not have
    broken the honest path."""
    monkeypatch.setattr("app.utils.http_client.MAX_RETRIES", 0)
    url, server = _start(non_json_shape=None, poison_beh=False)
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
    assert report["verdict"] == "pass", blob
    tc = report["statistics"].get("tokenizer_consistency") or {}
    assert tc.get("verdict") == "match", blob
