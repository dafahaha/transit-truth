"""Report construction and three-state verdict classification.

The verifier always emits a single machine-readable JSON report. Crucially,
when evidence is missing or ambiguous it MUST return
``insufficient_evidence`` rather than guessing a ``pass``/``suspicious``: a
false "pass" is the worst outcome for a trust tool.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from ..core.statistical_analyzer import StatisticalVerdict

VERDICTS = ("pass", "suspicious", "insufficient_evidence")

DISCLAIMER = (
    "Probabilistic auxiliary evidence from black-box probes, NOT a cryptographic "
    "proof. A relay may pass by luck and a borderline 'suspicious' may be a "
    "model/version drift. This tool does not adjudicate authenticity."
)

REPORT_SCHEMA = "transit-truth/verify-report/v1"


def classify_verdict(
    verdict: StatisticalVerdict, baseline_found: bool
) -> tuple[str, str]:
    """Map a :class:`StatisticalVerdict` to the public three-state verdict.

    Returns ``(verdict, human_reason)``.

    "Insufficient evidence" is reserved for genuinely weak evidence: no
    reference fingerprint to compare against, or a statistical conclusion that
    is ambiguous. The sample-adequacy caveat (e.g. a small reference n) is
    surfaced in the report as a confidence note rather than forcing a verdict,
    because the shipped reference baselines are deliberately small (n=50).
    """
    if not baseline_found:
        return (
            "insufficient_evidence",
            f"no reference fingerprint available for '{verdict.claimed_model}'; "
            "cannot compare the endpoint against anything.",
        )
    if verdict.conclusion == "match":
        note = ""
        if verdict.sample_adequacy == "insufficient":
            note = " (note: reference sample is small; treat as indicative)"
        return (
            "pass",
            "observed fingerprint is statistically consistent with the "
            f"claimed reference.{note}",
        )
    if verdict.conclusion == "mismatch":
        return (
            "suspicious",
            "observed fingerprint differs significantly from the claimed reference.",
        )
    return (
        "insufficient_evidence",
        "inconclusive: evidence is ambiguous and does not meet the decision "
        "threshold; gather more samples.",
    )


def build_report(
    *,
    claimed_model: str,
    endpoint_base_url: str,
    verdict: StatisticalVerdict,
    baseline_found: bool,
    sample_sizes: dict,
    observations: dict,
    error: Optional[dict] = None,
) -> dict:
    """Assemble the final JSON-serializable report.

    The API key is NEVER passed in here and NEVER appears in the output.
    """
    state, reason = classify_verdict(verdict, baseline_found)

    statistics = {
        "matched_reference_model": (
            verdict.details.get("baseline_model") if baseline_found else None
        ),
        "baseline_sample_size": (
            verdict.details.get("baseline_sample_size") if baseline_found else None
        ),
        "observed_sample_size": verdict.observed_sample_size,
        "ks_pvalue": verdict.ks_pvalue,
        "chi2_pvalue": verdict.chi2_pvalue,
        "likelihood_ratio": verdict.details.get("likelihood_ratio"),
        "posterior": verdict.posterior_probability,
        "posterior_ci_95": [
            round(verdict.posterior_ci_lower, 3),
            round(verdict.posterior_ci_upper, 3),
        ],
        "sample_adequacy": verdict.sample_adequacy,
    }

    return {
        "schema": REPORT_SCHEMA,
        "claimed_model": claimed_model,
        # Host only; credentials are never echoed.
        "endpoint_base_url": endpoint_base_url,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "verdict": state,
        "confidence": verdict.confidence_level if baseline_found else "low",
        "sample_sizes": sample_sizes,
        "statistics": statistics,
        "observations": observations,
        "evidence_reason": reason,
        "error": error,
        "disclaimer": DISCLAIMER,
    }


def error_report(
    *, claimed_model: str, endpoint_base_url: str, code: str, message: str
) -> dict:
    """Fail-closed report for infrastructure errors (network, timeout, bad URL).

    Always ``insufficient_evidence``: we never return ``pass`` when we could
    not actually probe the endpoint. The message is sanitized upstream so it
    cannot carry the API key.
    """
    return {
        "schema": REPORT_SCHEMA,
        "claimed_model": claimed_model,
        "endpoint_base_url": endpoint_base_url,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "verdict": "insufficient_evidence",
        "confidence": "low",
        "sample_sizes": {},
        "statistics": None,
        "observations": {},
        "evidence_reason": "verification could not be completed due to an error.",
        "error": {"code": code, "message": message},
        "disclaimer": DISCLAIMER,
    }
