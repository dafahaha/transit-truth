"""Stateless, pipelinable model-identity verifier.

``verify_endpoint`` probes an OpenAI-compatible endpoint with a *bounded*
battery, compares the observed fingerprint to local reference distributions
(``data/baselines`` + ``data/fingerprints``), and returns a single
machine-readable report dict. The API key is read from the environment and is
never written to disk, logged, or included in the report.
"""

from __future__ import annotations

import logging
import os
from typing import Optional
from urllib.parse import urlparse

from ..core.statistical_analyzer import StatisticalVerdict
from ..utils.http_client import AsyncAPIClient
from ..utils.ssrf_guard import validate_public_url
from .battery import run_battery
from .reference import load_reference_analyzer
from .report import build_report, error_report

logger = logging.getLogger(__name__)


# A key never leaves the process; we only keep a redacted fingerprint for logs.
def _redact(key: Optional[str]) -> str:
    if not key:
        return "<none>"
    return f"{key[:3]}…({len(key)} chars)"


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
) -> dict:
    """Probe *base_url* and return a verify-report dict.

    Args:
        base_url: OpenAI-compatible endpoint, e.g. ``https://relay.example/v1``.
        claimed_model: the model name the endpoint claims to serve.
        api_key: explicit key. If ``None``, read from ``os.environ[api_key_env]``.
        allow_local: permit loopback/private targets (for the local reference
            server and tests). Default ``False`` enforces the public-URL SSRF
            guard.
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

    # -- Probe the endpoint -------------------------------------------------
    try:
        async with AsyncAPIClient(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            ssrf_guard=not allow_local,
        ) as client:
            battery = await run_battery(
                client,
                claimed_model,
                max_requests=max_requests,
                behavioral_samples=behavioral_samples,
                concurrency=concurrency,
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
            "reference (e.g. Zenodo 176-model fingerprint dataset, CC-BY-4.0) or verify "
            "against a baseline with behavioral data before trusting."
        )
        report["statistics"]["behavioral_evidence"] = "none_tokenizer_only"
        report["statistics"]["certification"] = "not_certified_tokenizer_only"

    return report
