"""v0.5.7 hard-cap branch unit tests (P3-2/P3-3 mutation safety net).

The hard-cap decision was extracted into the pure ``_apply_hard_cap`` helper so
both evidence-kind branches can be exercised directly. These tests exist to
FAIL under the old regressions:

* Old logic unconditionally overwrote ``evidence_reason`` with the tokenizer-only
  match wording, clobbering a tokenizer-family mismatch reason (report read
  ``suspicious`` at top while the body claimed family-consistent).
* Old branch-b (reference HAS a behavioral distribution but this run got zero
  overlap) stamped the ``not_certified_tokenizer_only`` certification tag, which
  only applies to a tokenizer-only reference.

Run with pytest; no network, no browser, no asyncio required.
"""

from app.verify.core import _apply_hard_cap


def _report(verdict: str, reason: str = "") -> dict:
    return {"verdict": verdict, "evidence_reason": reason, "statistics": {}}


# ── Branch A: tokenizer-only reference (no behavioral distribution) ──────────


def test_branch_a_tokenizer_only_labels_and_keeps_mismatch_reason():
    # A tokenizer-family mismatch already raised verdict to suspicious with its
    # own reason; the hard cap must preserve it (never overwrite with the
    # tokenizer-only match wording) and label the evidence kind correctly.
    mismatch_reason = (
        "Tokenizer prompt-token counts disagree with the claimed reference "
        "across multiple probes: likely a different model family."
    )
    report = _report("suspicious", mismatch_reason)

    _apply_hard_cap(report, behavioral_reference_probes=set())

    stats = report["statistics"]
    assert stats["behavioral_evidence"] == "none_tokenizer_only"
    assert stats["certification"] == "not_certified_tokenizer_only"
    # Mismatch reason preserved: no family-consistent wording may survive.
    reason = report["evidence_reason"].lower()
    assert "family-consistent" not in reason
    assert "family consistent" not in reason
    assert (
        "disagree" in reason
        or "different model family" in reason
        or "mismatch" in reason
    )


def test_branch_a_pass_is_downgraded_to_insufficient_evidence():
    report = _report("pass")
    _apply_hard_cap(report, behavioral_reference_probes=set())
    assert report["verdict"] == "insufficient_evidence"
    assert report["statistics"]["behavioral_evidence"] == "none_tokenizer_only"


# ── Branch B: reference HAS a behavioral distribution, zero overlap ──────────


def test_branch_b_starved_distribution_not_labeled_tokenizer_only():
    # The reference carries a behavioral distribution but this run obtained zero
    # overlap (rate-limited / starved probes). This is NOT a tokenizer-only case,
    # so the certification must NOT carry the tokenizer-only tag.
    report = _report("insufficient_evidence")

    _apply_hard_cap(report, behavioral_reference_probes={"beh-number", "beh-color"})

    stats = report["statistics"]
    assert stats["behavioral_evidence"] == "no_behavioral_observations"
    # The old mislabel stamped not_certified_tokenizer_only here; that must not
    # happen for a starved-but-present behavioral distribution.
    assert stats["certification"] != "not_certified_tokenizer_only"
    assert stats["certification"] == "not_certified_no_observations"
    reason = report["evidence_reason"].lower()
    assert "rate-limited" in reason or "starved" in reason or "no matching" in reason


def test_branch_b_suspicious_mismatch_reason_preserved():
    # Even in branch B, a suspicious mismatch reason must not be overwritten.
    mismatch_reason = (
        "Tokenizer prompt-token counts disagree with the claimed reference "
        "across multiple probes: likely a different model family."
    )
    report = _report("suspicious", mismatch_reason)

    _apply_hard_cap(report, behavioral_reference_probes={"beh-number"})

    assert report["statistics"]["behavioral_evidence"] == "no_behavioral_observations"
    reason = report["evidence_reason"].lower()
    assert "family-consistent" not in reason
    assert "disagree" in reason or "mismatch" in reason
