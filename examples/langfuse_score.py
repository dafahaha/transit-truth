"""Langfuse score integration example (OPTIONAL dependency).

Pushes a verify report into Langfuse as a trace score. Langfuse is imported
defensively: if it is not installed, this prints what it would have sent.

Install and configure to actually use it::

    pip install langfuse
    # set LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_HOST
"""

from __future__ import annotations

from app.verify import verify_endpoint_sync


def report_to_langfuse(report: dict, trace_id: str | None = None) -> bool:
    """Send the verdict as a Langfuse score. Returns True on success."""
    try:
        from langfuse import Langfuse  # type: ignore
    except Exception:  # noqa: BLE001 - optional dependency
        print("[langfuse not installed] would score:", report["verdict"])
        return False

    lf = Langfuse()
    value_map = {"pass": 1.0, "insufficient_evidence": 0.5, "suspicious": 0.0}
    lf.score(
        trace_id=trace_id,
        name="model_identity_verdict",
        value=value_map.get(report["verdict"], 0.0),
        comment=report["evidence_reason"],
        data_type="NUMERIC",
    )
    lf.flush()
    return True


if __name__ == "__main__":
    demo = {
        "verdict": "pass",
        "evidence_reason": "tokenizer matches claimed reference",
    }
    report_to_langfuse(demo)
