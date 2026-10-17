"""v0.5.7 weak-pass confidence honesty test (product P3-2).

A tokenizer match over a merely inconclusive behavioral posterior in
``[0.5, 0.7)`` must never be labelled medium/high confidence; a ``pass`` on
that band is capped to ``low``. A high posterior (>=0.7) is left untouched, and
a non-pass verdict is never coerced by this guard.
"""

from app.verify.core import _cap_weak_pass_confidence


def test_weak_pass_posterior_0p6_capped_low():
    report = {
        "verdict": "pass",
        "confidence": "medium",
        "statistics": {"posterior": 0.6},
    }
    _cap_weak_pass_confidence(report)
    assert report["confidence"] == "low"


def test_strong_pass_posterior_0p95_untouched():
    report = {
        "verdict": "pass",
        "confidence": "high",
        "statistics": {"posterior": 0.95},
    }
    _cap_weak_pass_confidence(report)
    assert report["confidence"] == "high"


def test_non_pass_verdict_untouched():
    report = {
        "verdict": "insufficient_evidence",
        "confidence": "high",
        "statistics": {"posterior": 0.6},
    }
    _cap_weak_pass_confidence(report)
    # Not a pass: the guard does not coerce an unrelated confidence label.
    assert report["confidence"] == "high"
