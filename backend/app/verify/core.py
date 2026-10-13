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
    # Normalize + record host only (no credentials in the report).
    parsed = urlparse(base_url)
    host_label = f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else base_url

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

    return build_report(
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
