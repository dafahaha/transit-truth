"""v0.4.5 regression locks.

Two independently-reviewed issues:

1. **Version drift** -- ``backend/pyproject.toml`` still pinned ``0.4.3`` while
   everything else had moved to ``0.4.4``. The four shipped version sources must
   always agree; this test fails the build when they drift again.

2. **Tokenizer match threshold was optimistic** -- recalibration showed Qwen2.5
   and o200k (gpt-4o) agree on 4/5 battery probes (only mixed-unicode diverges by
   3). Calling that 0.8 agreement ``match`` over-claimed a family identity. At
   full probe overlap a match now requires an *exact* 1.0; a 4/5 near-agreement
   is reported ``ambiguous`` with a weak-signal note. Self-vs-self (gpt against
   the gpt baseline, Qwen against the Qwen fingerprint) must remain exact
   ``match``.
"""

from __future__ import annotations

import re
from pathlib import Path

from app import __version__
from app.config import APP_VERSION
from app.verify.reference import load_reference_analyzer, tokenizer_consistency
from app.verify.tokenizer_caliber import expected_battery_tokenizer_counts

REPO = Path(__file__).resolve().parents[2]


def _pyproject_version(path: Path) -> str:
    """Regex-extract the [project] version so the test stays 3.10-compatible
    (tomllib only exists on 3.11+, and CI tests 3.10/3.11/3.12)."""
    text = path.read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert match, f"no version line found in {path}"
    return match.group(1)


def test_shipped_version_sources_agree():
    """All version sources must resolve to the same shipped version."""
    versions = {
        "root pyproject.toml": _pyproject_version(REPO / "pyproject.toml"),
        "backend/pyproject.toml": _pyproject_version(
            REPO / "backend" / "pyproject.toml"
        ),
        "app.config.APP_VERSION": APP_VERSION,
        "app.__version__": __version__,
    }
    assert len(set(versions.values())) == 1, versions
    assert versions["root pyproject.toml"] == "0.5.0", versions


def _gpt_min_baseline():
    analyzer = load_reference_analyzer()
    baseline = analyzer._resolve_baseline("gpt-4o-mini")
    assert baseline is not None
    return baseline


def test_exact_o200k_observation_still_matches_gpt_baseline():
    """Self-consistency is preserved: exact counts -> match(1.0)."""
    baseline = _gpt_min_baseline()
    observed = expected_battery_tokenizer_counts()
    tc = tokenizer_consistency(observed, baseline)
    assert tc["verdict"] == "match", tc
    assert tc["score"] == 1.0, tc


def test_qwen_numbers_claiming_gpt_are_ambiguous_not_match():
    """The recalibrated near-case: 4/5 agreement at full overlap -> ambiguous.

    This is the exact Qwen-claiming-gpt-4o-mini scenario the e2e stub replays:
    Qwen2.5 counts equal o200k on 4 of the 5 battery probes, only
    mixed-unicode diverges by 3 tokens. Under the old 0.8 cutoff that was called
    ``match``; now it must be ``ambiguous`` (weak signal), never ``match``.
    """
    baseline = _gpt_min_baseline()
    expected = expected_battery_tokenizer_counts()
    # Qwen's mixed-unicode count is 3 tokens above o200k's (41 vs 38); every
    # other probe coincides.
    observed = {pid: cnt for pid, cnt in expected.items()}
    observed["tok-mixed-unicode"] += 3

    tc = tokenizer_consistency(observed, baseline)
    assert tc["overlap"] == 5, tc
    assert tc["consistent"] == 4, tc
    assert abs(tc["score"] - 0.8) < 0.01, tc
    assert tc["verdict"] != "match", tc
    assert tc["verdict"] == "ambiguous", tc
    assert "note" in tc, tc  # weak-signal explanation must ship with the report


def test_qwen_against_own_fingerprint_is_exact_match():
    """Qwen self-consistency must remain match(1.0), not regressed."""
    analyzer = load_reference_analyzer()
    baseline = analyzer._resolve_baseline("qwen2.5-0.5b-instruct")
    assert baseline is not None
    observed = {
        pid: samples[0] for pid, samples in baseline.tokenizer_distributions.items()
    }
    # Only the 5 probes the battery actually sends overlap the shipped baselines.
    from app.verify.battery import DEFAULT_TOKENIZER_IDS

    observed = {pid: v for pid, v in observed.items() if pid in DEFAULT_TOKENIZER_IDS}
    tc = tokenizer_consistency(observed, baseline)
    assert tc["verdict"] == "match", tc
    assert tc["score"] == 1.0, tc



def test_glm_against_own_fingerprint_is_exact_match():
    """GLM self-consistency must be match(1.0) once its fingerprint ships."""
    analyzer = load_reference_analyzer()
    baseline = analyzer._resolve_baseline('glm-4-9b-chat')
    assert baseline is not None
    observed = {
        pid: samples[0] for pid, samples in baseline.tokenizer_distributions.items()
    }
    from app.verify.battery import DEFAULT_TOKENIZER_IDS

    observed = {pid: v for pid, v in observed.items() if pid in DEFAULT_TOKENIZER_IDS}
    tc = tokenizer_consistency(observed, baseline)
    assert tc['verdict'] == 'match', tc
    assert tc['score'] == 1.0, tc

def test_low_overlap_still_insufficient_and_divergence_still_mismatch():
    """The low-overlap guard and the mismatch band are unchanged."""
    baseline = _gpt_min_baseline()
    expected = expected_battery_tokenizer_counts()
    # Two probes that DO exist in the shipped gpt baseline (the offline
    # expected map also lists tok-digits/tok-cjk/tok-emoji, which the gpt
    # baseline does not cover -- picking those would yield no_overlap).
    two_probes = {
        "tok-whitespace": expected["tok-whitespace"],
        "tok-code": expected["tok-code"],
    }
    tc = tokenizer_consistency(two_probes, baseline)
    assert tc["overlap"] == 2, tc
    assert tc["verdict"] == "insufficient_overlap", tc

    # 2/5 = 0.4 < 0.5 -> mismatch band (different family divergence). The
    # perturbed probes must be ones the baseline actually covers.
    observed = dict(expected)
    for pid in ("tok-whitespace", "tok-code", "tok-url"):
        observed[pid] += 100  # wildly off -> inconsistent
    tc = tokenizer_consistency(observed, baseline)
    assert tc["overlap"] == 5, tc
    assert tc["consistent"] == 2, tc
    assert tc["verdict"] == "mismatch", tc
