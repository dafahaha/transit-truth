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
import socket
from collections import Counter
from typing import Optional
from urllib.parse import urlparse

from ..core.statistical_analyzer import StatisticalVerdict
from ..utils.http_client import AsyncAPIClient
from ..utils.ssrf_guard import _is_blocked_ip, validate_public_url
from .battery import run_battery
from .reference import load_reference_analyzer
from .report import build_report, error_report

logger = logging.getLogger(__name__)


# Whole-battery reachability precheck (F3): before spending the battery's
# retries+backoff against a base-url whose port accepts nobody, probe raw TCP
# reachability with a short timeout. A dead port otherwise burns the full
# total_timeout (90s) and surfaces as the misleading ``battery_timeout``.
_PRECHECK_TIMEOUT = 8.0
# Per-connect attempt budget: dual-stack hosts may list an unroutable IPv6
# address first; a single long budget would hang on it. ~4s per attempt, first
# success wins (typical worst case = IPv6(4s) + IPv4 = ~8s).
_PRECHECK_ATTEMPT_TIMEOUT = 4.0


class _PrecheckNonPublic(Exception):
    """All re-resolved addresses are non-public (DNS-rebinding window)."""


async def _precheck_tcp_reachable(
    hostname: str, port: int, *, allow_local: bool
) -> None:
    """Re-resolve ``hostname`` NOW, drop non-public IPs, then bare-connect.

    This closes the DNS-rebinding TOCTOU between ``validate_public_url`` (which
    resolved at URL-validation time) and the real battery: a hostile resolver can
    swap in an internal address later, so we re-resolve at connect time and apply
    the same SSRF blocklist (skipped when the operator opted in via
    ``allow_local``). For https targets this deliberately only proves *a server
    is listening* -- TLS handshake errors / 4xx are handled later by the battery.
    A refused connection, DNS failure, or timeout here means nothing useful can
    come of probing, so the caller fails closed immediately.
    """
    loop = asyncio.get_event_loop()
    try:
        infos = await loop.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError, OSError) as exc:
        raise OSError(f"precheck DNS failure for {hostname}: {exc}") from exc

    ips: list[str] = []
    for _family, _type, _proto, _canon, sockaddr in infos:
        ip = str(sockaddr[0])
        if ip not in ips:
            ips.append(ip)

    reachable_ips: list[str] = []
    for ip in ips:
        if not allow_local and _is_blocked_ip(ip):
            logger.warning(
                "precheck dropped non-public resolved address %s for host %s",
                ip,
                hostname,
            )
            continue
        reachable_ips.append(ip)
    if not reachable_ips:
        raise _PrecheckNonPublic(hostname)

    last_exc: Optional[Exception] = None
    for ip in reachable_ips:
        try:
            _reader, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, port),
                timeout=_PRECHECK_ATTEMPT_TIMEOUT,
            )
        except (asyncio.TimeoutError, OSError) as exc:
            last_exc = exc
            continue
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:  # noqa: BLE001 - closing best-effort
            pass
        return
    if last_exc is not None:
        raise last_exc


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

# v0.4.4 coverage gate: coverage is measured against the CLIENT-SENT probe
# universe, so a backend cannot pass by answering only a subset of probes.
# behavioral_coverage = overlapping probes with >= _MIN_BEHAVIORAL_SAMPLES
# successful observations / overlapping probes the battery SENT. Below this
# (or with any fully-starved n=0 overlapping probe), the run is
# non-cooperative / evidence-insufficient and the Bayesian numbers are withheld.
_MIN_BEHAVIORAL_COVERAGE = 0.8
# The whole-battery non-200 rate must stay bounded: if most requests failed,
# whatever slipped through is not a trustworthy fingerprint.
_MAX_BATTERY_FAILURE_RATE = 0.5


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


# Reason text reused by the hard-cap helper; kept module-level so unit tests can
# assert on stable substrings without duplicating the prose.
_HARD_CAP_TOKENIZER_ONLY_REASON = (
    "Reference fingerprint has no behavioral distribution (tokenizer-only "
    "catalog). Tokenizer prompt-token counts are self-reported by the endpoint "
    "and fully public, so they alone cannot certify model identity. Tokenizer "
    "match alone is necessary but not sufficient: result is insufficient_evidence, "
    "not a certification; collect a behavioral reference (e.g. Zenodo 165-model "
    "fingerprint dataset, CC-BY-4.0) or verify against a baseline with behavioral "
    "data before trusting."
)
_HARD_CAP_NO_OBSERVATIONS_REASON = (
    "Reference carries a behavioral distribution, but this run obtained no "
    "matching behavioral observation (the endpoint may be rate-limited or the "
    "behavioral probes were starved). Fail closed: insufficient_evidence; retry "
    "or check network/rate limits before trusting."
)


def _apply_hard_cap(report: dict, *, behavioral_reference_probes: set) -> None:
    """Apply the no-real-behavioral hard cap by mutating ``report`` in place.

    Split into a pure helper so the two evidence-kind branches are unit-testable
    and a regression that unconditionally overwrites ``evidence_reason`` (or
    mislabels the starved-distribution case) is caught by a failing test rather
    than silently shipping a self-contradictory report.

    Branches:
      (a) ``behavioral_reference_probes`` empty -> tokenizer-only reference;
          evidence label ``none_tokenizer_only``, certification
          ``not_certified_tokenizer_only``.
      (b) probes present but this run got zero overlap -> reference HAS a
          behavioral distribution but was starved/rate-limited; evidence label
          ``no_behavioral_observations``; this is NOT a tokenizer-only case, so
          the certification must NOT carry the tokenizer-only tag.

    A tokenizer-family mismatch already raised ``verdict`` to ``suspicious`` with
    its own reason; that reason must be preserved (never overwritten here).
    """
    if report["verdict"] == "pass":
        report["verdict"] = "insufficient_evidence"

    if behavioral_reference_probes:
        # (b) Reference carries a behavioral distribution but this run obtained
        # zero overlap: do NOT stamp the tokenizer-only certification tag.
        report["statistics"]["behavioral_evidence"] = "no_behavioral_observations"
        report["statistics"]["certification"] = "not_certified_no_observations"
        if report["verdict"] != "suspicious":
            report["evidence_reason"] = _HARD_CAP_NO_OBSERVATIONS_REASON
    else:
        # (a) Reference itself has no behavioral distribution at all.
        report["statistics"]["behavioral_evidence"] = "none_tokenizer_only"
        report["statistics"]["certification"] = "not_certified_tokenizer_only"
        if report["verdict"] != "suspicious":
            report["evidence_reason"] = _HARD_CAP_TOKENIZER_ONLY_REASON


def _cap_weak_pass_confidence(report: dict) -> None:
    """Cap a weak-pass confidence to ``low`` (product P3-2).

    A tokenizer match over a merely inconclusive behavioral posterior in
    ``[0.5, 0.7)`` is NOT a high-confidence pass; such a pass must never carry a
    medium/high confidence label regardless of the analyzer's own level.
    """
    post = report["statistics"].get("posterior")
    if report["verdict"] == "pass" and post is not None and 0.5 <= post < 0.7:
        report["confidence"] = "low"


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
            # validate_public_url does a blocking socket.getaddrinfo; offload it
            # to a thread so DNS resolution never stalls the event loop (mirrors
            # require_public_url_async in the legacy audit API).
            await asyncio.to_thread(validate_public_url, base_url)
    except Exception as exc:  # noqa: BLE001 - sanitized below
        message = str(exc)
        # Loopback/private targets are rejected by design; tell the operator
        # the exact flag that opts in (otherwise the error reads as a broken
        # URL even though the URL itself is fine).
        if "not a public internet address" in message and not allow_local:
            # Ensure the sanitized message ends with a sentence period so the
            # appended hint never reads as "address Hint: ..." (punctuation run-on).
            message = message.rstrip()
            if not message.endswith("."):
                message += "."
            message += " Hint: loopback/private targets need --allow-local."
        return error_report(
            claimed_model=claimed_model,
            endpoint_base_url=host_label,
            code="invalid_endpoint",
            message=message,
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

    # -- Fast reachability precheck (F3) ----------------------------------
    # A base-url whose host:port accepts nobody otherwise makes every probe
    # retry into the void until total_timeout expires and is then mislabelled
    # battery_timeout. Re-resolve NOW (closing the DNS-rebinding window between
    # the URL check and the battery), drop non-public IPs (unless --allow-local),
    # and bare-connect first: refused / DNS failure / timeout fail closed HERE
    # with an actionable error code. A reachable port (even if it 401s/404s on
    # the API) proceeds to the battery.
    precheck_host = parsed.hostname or ""
    precheck_port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        await _precheck_tcp_reachable(
            precheck_host, precheck_port, allow_local=allow_local
        )
    except _PrecheckNonPublic:
        logger.warning(
            "verify_endpoint precheck: all re-resolved addresses of %s are "
            "non-public (possible DNS rebinding); refusing to probe",
            precheck_host,
        )
        return error_report(
            claimed_model=claimed_model,
            endpoint_base_url=host_label,
            code="invalid_endpoint",
            message=(
                f"Host '{precheck_host}' re-resolved to non-public address(es) "
                "at connect time (possible DNS rebinding). Check host/network; "
                "loopback/private targets need --allow-local."
            ),
        )
    except Exception as exc:  # noqa: BLE001 - DNS/refused/timeout, all fatal
        logger.warning(
            "verify_endpoint reachability precheck failed: %s", type(exc).__name__
        )
        return error_report(
            claimed_model=claimed_model,
            endpoint_base_url=host_label,
            code="endpoint_unreachable",
            message=(
                f"Could not connect to {precheck_host}: no server is reachable "
                "at the given base-url. Check host/port, that the server is "
                "running, and your network."
            ),
        )

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
            # Self-consistency contract (v0.4.6): a tokenizer-family mismatch
            # OVERRIDES the behavioral statistical match. The behavioral
            # posterior/LR/CI/chi2 were computed from modal (possibly replayed)
            # strings; leaving posterior=0.913 / LR=4.5 displayed next to
            # verdict=suspicious is self-contradictory, so withhold them.
            report["statistics"]["posterior"] = None
            report["statistics"]["likelihood_ratio"] = None
            report["statistics"]["posterior_ci_95"] = None
            report["statistics"]["chi2_pvalue"] = None
            report["confidence"] = "low"
        elif (
            tok_check.get("verdict") == "match"
            and report["verdict"] == "insufficient_evidence"
            and real_behavioral_evidence
        ):
            # v0.4.7 P3-1: a tokenizer match alone must NOT flip an
            # inconclusive/uncertain behavioral verdict into ``pass``. When
            # the behavioral LR < 1 (or posterior is on the non-support side
            # of 0.5), the behavioral evidence is actively neutral-to-against
            # the claim -- e.g. a distribution-replay scenario where the
            # observed behavioral distribution is point-mass / degenerate and
            # the chi-square update lands at LR≈0.45, posterior≈0.51. In that
            # band a tokenizer match is necessary-but-not-sufficient: it
            # says "same tokenizer family", NOT "this is the claimed model".
            # Leaving the verdict at insufficient_evidence (which the
            # deterministic-replay / thin-evidence layer below may then
            # annotate) is the honest outcome.
            lr = report["statistics"].get("likelihood_ratio")
            post = report["statistics"].get("posterior")
            behavioral_supports = (
                lr is not None and lr >= 1.0 and post is not None and post >= 0.5
            )
            if behavioral_supports:
                report["verdict"] = "pass"
                report["evidence_reason"] = (
                    "Tokenizer prompt-token counts match the claimed reference AND "
                    "behavioral evidence overlaps the reference distribution."
                )
            else:
                # Keep the deterministic-replay / thin-evidence flags intact;
                # do not flip to suspicious (tokenizer match is not a family
                # mismatch) -- just decline to certify.
                report["evidence_reason"] = (
                    "Tokenizer prompt-token counts match the claimed reference, "
                    "but behavioral evidence does not support the claim "
                    "(LR<1 / posterior on the non-support side of 0.5, e.g. "
                    "degenerate / replayable distribution). Tokenizer match "
                    "alone is necessary but not sufficient to certify model "
                    "identity; result is insufficient_evidence pending "
                    "non-degenerate behavioral evidence."
                )

    # Hard cap: no real behavioral reference => never output pass. The decision
    # lives in the pure ``_apply_hard_cap`` helper so both evidence-kind branches
    # are unit-tested and a reason-overwrite / mislabel regression fails a test.
    if baseline_found and not real_behavioral_evidence:
        _apply_hard_cap(report, behavioral_reference_probes=behavioral_reference_probes)

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

    # -- Behavioral coverage / sample-size gate (v0.4.3 thin + v0.4.4 coverage)
    # The denominator is the CLIENT-SENT probe universe
    # (``battery.planned_behavioral_ids``), NOT just the probes the backend
    # deigned to answer. A starving backend that 504s every repeat of 3 of the 4
    # overlapping probes and answers the 4th with a 2:1 split used to earn
    # pass/medium with a spurious posterior=0.913: the n=0 probes never entered
    # ``observed_behavioral`` so the old gate was blind to them. Now a probe we
    # sent but got zero usable responses for is counted as n=0, coverage drops,
    # and the run is judged non-cooperative / evidence-insufficient.
    expected_overlap = sorted(
        pid
        for pid in battery.planned_behavioral_ids
        if pid in behavioral_reference_probes
    )
    overlap_samples = {
        pid: len(battery.observed_behavioral.get(pid, [])) for pid in expected_overlap
    }
    total_overlap = sum(overlap_samples.values())
    starved_probes = {pid: n for pid, n in overlap_samples.items() if n == 0}
    thin_probes = {
        pid: n
        for pid, n in overlap_samples.items()
        if 0 < n < _MIN_BEHAVIORAL_SAMPLES_PER_PROBE
    }
    well_sampled = sum(
        1 for n in overlap_samples.values() if n >= _MIN_BEHAVIORAL_SAMPLES_PER_PROBE
    )
    behavioral_coverage = (
        well_sampled / len(expected_overlap) if expected_overlap else 0.0
    )
    battery_failure_rate = (
        battery.failures / battery.requests_used if battery.requests_used else 0.0
    )

    thin_evidence = bool(real_behavioral_evidence) and (
        bool(thin_probes) or total_overlap < _MIN_TOTAL_BEHAVIORAL_OBS
    )
    non_cooperation = (
        bool(real_behavioral_evidence)
        and bool(expected_overlap)
        and (
            bool(starved_probes)
            or behavioral_coverage < _MIN_BEHAVIORAL_COVERAGE
            or battery_failure_rate > _MAX_BATTERY_FAILURE_RATE
        )
    )
    withheld = thin_evidence or non_cooperation

    if non_cooperation:
        report["statistics"]["non_cooperation"] = {
            "flag": True,
            "starved_probes": starved_probes,
            "expected_overlap_probes": len(expected_overlap),
            "well_sampled_overlap_probes": well_sampled,
            "behavioral_coverage": round(behavioral_coverage, 3),
            "battery_failure_rate": round(battery_failure_rate, 3),
            "reason": (
                "The endpoint did not cooperate with the probe battery: it fully "
                "starved (0 usable responses) or under-sampled too many of the "
                "overlapping behavioral probes the client actually sent, or the "
                f"whole-battery failure rate exceeded {_MAX_BATTERY_FAILURE_RATE:.0%}. "
                "Selectively answering only a subset of probes (504ing the rest) "
                "cannot certify identity, so confidence is capped low and the "
                "Bayesian posterior/LR/CI/chi-square are withheld."
            ),
        }
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
    if withheld:
        # Honest contract: never present a spurious posterior=0.913 / LR next to
        # evidence this thin / non-cooperative. Chi-square over a degenerate or
        # selectively-sampled subset (p~=1.0) must also be withheld.
        report["statistics"]["posterior"] = None
        report["statistics"]["likelihood_ratio"] = None
        report["statistics"]["posterior_ci_95"] = None
        report["statistics"]["chi2_pvalue"] = None
        report["confidence"] = "low"
        if report["verdict"] == "pass":
            report["verdict"] = "insufficient_evidence"
        caveat = (
            " Caveat: behavioral coverage/evidence is insufficient (some overlapping "
            "probes the client sent were starved or under-sampled); confidence "
            "capped low and Bayesian posterior/LR/CI/chi-square withheld."
            if non_cooperation
            else " Caveat: behavioral evidence is too thin (fewer than "
            f"{_MIN_BEHAVIORAL_SAMPLES_PER_PROBE} successful samples per overlapping "
            "probe); confidence capped low and Bayesian posterior/LR/CI withheld."
        )
        report["evidence_reason"] = report.get("evidence_reason", "") + caveat

    # Weak-pass honesty (product P3-2): a tokenizer match over a merely
    # inconclusive behavioral posterior in [0.5, 0.7) is NOT a high-confidence
    # pass; such a pass must never be labelled medium/high confidence.
    _cap_weak_pass_confidence(report)

    return report
