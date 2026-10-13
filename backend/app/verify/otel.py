"""Optional OpenTelemetry / OpenInference span integration.

The verifier report is a plain dict. This module maps it onto
OpenInference-style GenAI span attributes WITHOUT requiring opentelemetry as a
dependency:

- ``to_openinference_attributes(report)`` returns a plain dict you can attach to
  any span/telemetry system.
- ``emit_otel_span(report)`` only creates a real OTel span if
  ``opentelemetry`` happens to be installed; otherwise it is a safe no-op.

OTel / OpenInference are NOT required to run the verifier.
"""

from __future__ import annotations

from typing import Any, Optional

VERDICT_TO_ATTR = {
    "pass": "pass",
    "suspicious": "suspicious",
    "insufficient_evidence": "insufficient_evidence",
}


def to_openinference_attributes(report: dict) -> dict[str, Any]:
    """Map a verify report onto OpenInference GenAI span attributes (plain dict)."""
    stats = report.get("statistics") or {}
    attrs = {
        "genai.system": "transit-truth",
        "genai.request.model": report.get("claimed_model"),
        "genai.transit_truth.verdict": VERDICT_TO_ATTR.get(
            report.get("verdict"), report.get("verdict")
        ),
        "genai.transit_truth.confidence": report.get("confidence"),
        "genai.transit_truth.endpoint": report.get("endpoint_base_url"),
        "genai.transit_truth.matched_reference": stats.get("matched_reference_model"),
        "genai.transit_truth.posterior": stats.get("posterior"),
        "genai.transit_truth.chi2_pvalue": stats.get("chi2_pvalue"),
        "genai.transit_truth.ks_pvalue": stats.get("ks_pvalue"),
        "genai.transit_truth.reason": report.get("evidence_reason"),
    }
    tok = stats.get("tokenizer_consistency") or {}
    attrs["genai.transit_truth.tokenizer_score"] = tok.get("score")
    attrs["genai.transit_truth.tokenizer_verdict"] = tok.get("verdict")
    # Drop None values (OTel attributes must be concrete).
    return {k: v for k, v in attrs.items() if v is not None}


def emit_otel_span(report: dict, tracer: Optional[Any] = None) -> bool:
    """Emit a real OTel span if opentelemetry is installed; else no-op.

    Returns True if a span was actually emitted.
    """
    try:
        from opentelemetry import trace  # type: ignore
    except Exception:  # noqa: BLE001 - optional dependency
        return False

    attrs = to_openinference_attributes(report)
    tr = tracer or trace.get_tracer("transit-truth")
    with tr.start_as_current_span("transit_truth.verify") as span:
        for k, v in attrs.items():
            span.set_attribute(k, v)
        if report.get("error"):
            span.set_status(trace.StatusCode.ERROR, str(report["error"].get("code")))
    return True
