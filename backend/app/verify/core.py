"""Stateless, pipelinable model-identity verifier.

``verify_endpoint`` probes an OpenAI-compatible endpoint with a *bounded*
battery, compares the observed fingerprint to local reference distributions
(``data/baselines`` + ``data/fingerprints``), and returns a single
machine-readable report dict. The API key is read from the environment and is
never written to disk, logged, or included in the report.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
from collections import Counter
from typing import Optional
from urllib.parse import urlparse

from ..core.statistical_analyzer import StatisticalVerdict
from ..utils.http_client import AsyncAPIClient
from ..utils.ssrf_guard import validate_public_url
from .battery import run_battery
from .reference import load_reference_analyzer
from .report import build_report, error_report

logger = logging.getLogger(__name__)


# A behavioral probe whose empirical mode fraction is at least this close to 1.0
# is treated as a point mass (zero entropy): under temperature=0 the shipped
# public baselines are exactly such point masses, so they are replayable.
_POINT_MASS_MODE_FRACTION = 0.99

# Minimum successful behavioral repeats per *overlapping* probe before the
# observed distribution is worth trusting. A single answer per probe is one
# replayable modal string, NOT a distribution: it still chi2-matches a point-mass
# baseline (p~=1.0) but carries no statistical power to certify identity.
_MIN_BEHAVIORAL_SAMPLES_PER_PROBE = 3
# ...and a floor on the total number of overlapping behavioral observations.
_MIN_TOTAL_BEHAVIORAL_OBS = 3


def _behavioral_degeneracy(
    observed_behavioral: dict[str, list[str]],
) -> dict[str, dict]:
    """Per-probe empirical entropy / mode fraction for behavioral responses.

    Returns ``{probe_id: {n, mode, mode_fraction, shannon_entropy_nats,
    point_mass}}`` for EVERY probe with at least one sample. A point-mass probe
    (mode fraction >= 0.99, zero entropy) is *replayable*: the shipped public
    baselines are collected at temperature=0, so an attacker can hard-code the
    public modal strings and reproduce the distribution deterministically.

    Note that n=1 is *always* a point mass by construction (the single observed
    response IS the mode, mode fraction = 1.0, entropy = 0.0): a starving backend
    that answers each probe exactly once still registers as degenerate even
    though it has no repeated samples to compare.
    """
    out: dict[str, dict] = {}
    for probe_id, responses in observed_behavioral.items():
        n = len(responses)
        if n < 1:
            continue
        counts = Counter(responses)
        mode, mode_n = counts.most_common(1)[0]
        mode_frac = mode_n / n
        entropy = -sum((c / n) * math.log(c / n) for c in counts.values())
        out[probe_id] = {
            "n": n,
            "mode": mode,
            "mode_fraction": round(mode_frac, 3),
            "shannon_entropy_nats": round(entropy, 4),
            "point_mass": mode_frac >= _POINT_MASS_MODE_FRACTION,
        }
    return out


async def verify_endpoint(
    *,
    base_url: str,
    claimed_model: str,
    api_key: Optional[str] = None,
    api_key_env: str = "TRANSIT_TRUTH_API_KEY",
    reference_dirs: Optional[list[str]] = None,
    max_requests: int = 20,
    behavioral_samples: int = 3,
    timeout: float = 30.0,
    concurrency: int = 2,
    allow_local: bool = False,
    total_timeout: float = 90.0,
) -> dict:
    """Probe *base_url* and return a verify-report dict.

    Args:
        base_url: OpenAI-compatible endpoint, e.g. ``https://relay.example/v1``.
        claimed_model: the model name the endpoint claims to serve.
        api_key: explicit key. If ``None``, read from ``os.environ[api_key_env]``.
        allow_local: permit loopback/private targets (for the local reference
            server and tests). Default ``False`` enforces the public-URL SSRF
            guard.
        total_timeout: whole-battery wall-clock cap. A hung / 500-ing backend
            otherwise spends minutes inside retry+backoff; on expiry we fail
            closed with an error report instead of waiting indefinitely.
    """
    # Normalize + record host only (no credentials in the report). Strip any
    # embedded userinfo (`https://user:pass@host/v1`) so credentials never leak
    # into endpoint_base_url / OTel attributes.
    parsed = urlparse(base_url)
    if parsed.netloc:
        host_only = parsed.hostname or ""
        if parsed.port:
            host_only = f"{host_only}:{parsed.port}"
        host_label = f"{parsed.scheme}://{host_only}" if host_only else base_url
    else:
        host_label = base_url

    # -- URL validation (fail closed on bad targets) -----------------------
    try:
        if allow_local:
            # Operator explicitly opted into a local/private target. We still
            # require a sane http(s) URL, but skip the public-IP blocklist.
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                raise ValueError("Only http:// and https:// URLs are allowed")
        else:
            validate_public_url(base_url)
    except Exception as exc:  # noqa: BLE001 - sanitized below
        return error_report(
            claimed_model=claimed_model,
            endpoint_base_url=host_label,
            code="invalid_endpoint",
            message=str(exc),
        )

    # -- Key handling: env fallback, never echoed ---------------------------
    if api_key is None:
        api_key = os.environ.get(api_key_env)
    if not api_key:
        return error_report(
            claimed_model=claimed_model,
            endpoint_base_url=host_label,
            code="missing_api_key",
            message=(
                f"No API key provided. Set it via the '{api_key_env}' environment "
                "variable (it is never written to disk or logged)."
            ),
        )

    # -- Reference distributions ------------------------------------------
    analyzer = load_reference_analyzer(reference_dirs)
    baseline = analyzer._resolve_baseline(claimed_model)
    baseline_found = baseline is not None

    # -- Probe the endpoint (whole-battery wall-clock cap; fail closed) ------
    try:
        async with AsyncAPIClient(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            ssrf_guard=not allow_local,
        ) as client:
            try:
                battery = await asyncio.wait_for(
                    run_battery(
                        client,
                        claimed_model,
                        max_requests=max_requests,
                        behavioral_samples=behavioral_samples,
                        concurrency=concurrency,
                    ),
                    timeout=total_timeout,
                )
            except asyncio.TimeoutError:
                return error_report(
                    claimed_model=claimed_model,
                    endpoint_base_url=host_label,
                    code="battery_timeout",
                    message=(
                        f"The probe battery did not finish within {total_timeout:.0f}s "
                        "(hung or erroring backend). Failing closed: no certification."
                    ),
                )
    except Exception as exc:  # noqa: BLE001 - network/timeout, sanitized
        logger.warning("verify_endpoint transport error: %s", type(exc).__name__)
        return error_report(
            claimed_model=claimed_model,
            endpoint_base_url=host_label,
            code="transport_error",
            message=f"Could not reach the endpoint ({type(exc).__name__}).",
        )

    # If every probe failed, there is nothing to compare.
    if not battery.observed_tokenizer and not battery.observed_behavioral:
        return error_report(
            claimed_model=claimed_model,
            endpoint_base_url=host_label,
            code="no_observations",
            message=(
                f"All {battery.requests_used} probe request(s) failed; the endpoint "
                "returned no usable responses."
            ),
        )

    # -- Statistical comparison --------------------------------------------
    stat: StatisticalVerdict = analyzer.analyze(
        claimed_model=claimed_model,
        observed_tokenizer=battery.observed_tokenizer,
        observed_behavioral=battery.observed_behavioral,
        capability_failure_rate=0.0,  # v1: bounded battery skips capability tier probes.
    )

    # Direct deterministic tokenizer-count check (cross-family signal that does
    # not depend on chi-square power; works on the small open-source catalog).
    from .reference import tokenizer_consistency

    tok_check = tokenizer_consistency(battery.observed_tokenizer, baseline)

    report = build_report(
        claimed_model=claimed_model,
        endpoint_base_url=host_label,
        verdict=stat,
        baseline_found=baseline_found,
        sample_sizes={
            "tokenizer_probes": len(battery.observed_tokenizer),
            "behavioral_samples": sum(
                len(v) for v in battery.observed_behavioral.values()
            ),
            "requests_used": battery.requests_used,
            "request_failures": battery.failures,
        },
        observations={
            "tokenizer": battery.observed_tokenizer,
            "behavioral": battery.observed_behavioral,
        },
    )
    report["statistics"]["tokenizer_consistency"] = tok_check

    # -- Behavioral-evidence guarantee (anti false-pass) --------------------
    # Tokenizer prompt-token counts are *self-reported* by the endpoint in
    # usage.prompt_tokens, and the probe prompts + reference numbers are fully
    # public. An attacker can report the public numbers without running the real
    # model. A matching tokenizer count therefore alone NEVER certifies identity.
    # Only a real behavioral distribution (overlapping a reference with actual
    # behavioral data) can. The open-source catalog currently ships tokenizer-only
    # fingerprints (behavioral={}); for those, the verdict is capped at
    # insufficient_evidence regardless of how good the tokenizer match looks.
    behavioral_reference_probes = (
        set(baseline.behavioral_distributions) if baseline else set()
    )
    behavioral_overlap = sum(
        len(resp)
        for probe_id, resp in battery.observed_behavioral.items()
        if probe_id in behavioral_reference_probes
    )
    real_behavioral_evidence = (
        bool(behavioral_reference_probes) and behavioral_overlap > 0
    )

    # -- Tokenizer override layer -------------------------------------------
    if baseline_found:
        if tok_check.get("verdict") == "mismatch" and report["verdict"] != "suspicious":
            report["verdict"] = "suspicious"
            report["evidence_reason"] = (
                "Tokenizer prompt-token counts disagree with the claimed reference "
                "across multiple probes: likely a different model family."
            )
        elif (
            tok_check.get("verdict") == "match"
            and report["verdict"] == "insufficient_evidence"
            and real_behavioral_evidence
        ):
            report["verdict"] = "pass"
            report["evidence_reason"] = (
                "Tokenizer prompt-token counts match the claimed reference AND "
                "behavioral evidence overlaps the reference distribution."
            )

    # Hard cap: no real behavioral reference => never output pass.
    if baseline_found and not real_behavioral_evidence:
        if report["verdict"] == "pass":
            report["verdict"] = "insufficient_evidence"
        report["evidence_reason"] = (
            "Reference fingerprint has no behavioral distribution (tokenizer-only "
            "catalog). Tokenizer prompt-token counts are self-reported by the endpoint "
            "and fully public, so they alone cannot certify model identity. Result is "
            "tokenizer-family-consistent but NOT a certification: collect a behavioral "
            "reference (e.g. Zenodo 165-model fingerprint dataset, CC-BY-4.0) or verify "
            "against a baseline with behavioral data before trusting."
        )
        report["statistics"]["behavioral_evidence"] = "none_tokenizer_only"
        report["statistics"]["certification"] = "not_certified_tokenizer_only"

    # -- Deterministic-replay honesty (v0.4.2) -----------------------------
    # The shipped behavioral baselines are sampled at temperature=0, so they are
    # point masses (e.g. beh-number-1-10 always answers "7"). The probe prompts
    # and the baselines are public, so an attacker can hard-code ~4 modal
    # strings and "pass" deterministically -- not by luck. We flag degenerate
    # (zero-entropy) behavioral evidence explicitly and never let it carry an
    # unreserved high-confidence pass: a pass on point-mass evidence is capped to
    # low confidence and labelled replayable.
    degeneracy = _behavioral_degeneracy(battery.observed_behavioral)
    degenerate = {pid: d for pid, d in degeneracy.items() if d["point_mass"]}
    if degenerate and real_behavioral_evidence:
        report["statistics"]["deterministic_replay_risk"] = {
            "flag": True,
            "degenerate_probes": degenerate,
            "reason": (
                "Behavioral responses are point-mass (zero empirical entropy): the "
                "public baselines are sampled at temperature=0, so an attacker can "
                "replay the public modal strings verbatim. Behavioral 'match' here is "
                "replayable, NOT a cryptographic identity proof; official attestation "
                "remains the only endgame."
            ),
        }
        if report["verdict"] == "pass":
            report["confidence"] = "low"
            report["evidence_reason"] = (
                report.get("evidence_reason", "")
                + " Caveat: behavioral evidence is point-mass (temperature=0 public "
                "baselines are replayable verbatim), so this pass is low-confidence."
            )

    # -- Behavioral sample-size floor (v0.4.3) -----------------------------
    # A starving adversarial backend can answer each behavioral probe exactly ONCE
    # (the public modal string) and 504 every repeat: every overlapping probe
    # ends up with n=1. That single sample still chi2-matches a point-mass
    # baseline (p~=1.0) and used to yield pass/medium with a spurious
    # posterior=0.913. n=1 is a point mass by construction AND the evidence is
    # statistically too thin to certify. Require at least
    # _MIN_BEHAVIORAL_SAMPLES_PER_PROBE successful observations per overlapping
    # probe (and a non-trivial total overlap). Below the floor we flag
    # ``thin_evidence``, cap confidence to low, and withhold the Bayesian
    # posterior/LR/CI -- the same honesty contract as "no behavioral evidence".
    overlap_samples = {
        pid: len(resp)
        for pid, resp in battery.observed_behavioral.items()
        if pid in behavioral_reference_probes
    }
    total_overlap = sum(overlap_samples.values())
    thin_probes = {
        pid: n
        for pid, n in overlap_samples.items()
        if n < _MIN_BEHAVIORAL_SAMPLES_PER_PROBE
    }
    thin_evidence = bool(real_behavioral_evidence) and (
        bool(thin_probes) or total_overlap < _MIN_TOTAL_BEHAVIORAL_OBS
    )
    if thin_evidence:
        report["statistics"]["thin_evidence"] = {
            "flag": True,
            "thin_probes": thin_probes,
            "total_overlapping_observations": total_overlap,
            "min_samples_per_probe": _MIN_BEHAVIORAL_SAMPLES_PER_PROBE,
            "reason": (
                "Behavioral evidence is too thin to certify: at least "
                f"{_MIN_BEHAVIORAL_SAMPLES_PER_PROBE} successful samples per "
                "overlapping probe are required, but some probe(s) were observed "
                "only once (e.g. a backend that serves the public modal string once "
                "and 504s the repeats). A single replayable answer is a point mass "
                "with no statistical power, so confidence is capped low and the "
                "Bayesian posterior/LR/CI are withheld."
            ),
        }
        # Honest contract: never present a spurious posterior=0.913 / LR next to
        # evidence this thin.
        report["statistics"]["posterior"] = None
        report["statistics"]["likelihood_ratio"] = None
        report["statistics"]["posterior_ci_95"] = None
        report["confidence"] = "low"
        report["evidence_reason"] = (
            report.get("evidence_reason", "")
            + " Caveat: behavioral evidence is too thin (fewer than "
            f"{_MIN_BEHAVIORAL_SAMPLES_PER_PROBE} successful samples per overlapping "
            "probe); confidence capped low and Bayesian posterior/LR/CI withheld."
        )

    return report
