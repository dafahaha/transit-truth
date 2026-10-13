"""Tests for the SDK sync wrapper and the optional OTel integration (no dep)."""

from __future__ import annotations

from app.verify import verify_endpoint, verify_endpoint_sync
from app.verify.otel import emit_otel_span, to_openinference_attributes


def test_otel_attributes_are_plain_dict():
    report = {
        "claimed_model": "gpt-4o-mini",
        "endpoint_base_url": "https://relay.example",
        "verdict": "suspicious",
        "confidence": "low",
        "statistics": {
            "matched_reference_model": "gpt-4o-mini",
            "posterior": 0.1,
            "chi2_pvalue": 0.001,
            "tokenizer_consistency": {"score": 0.0, "verdict": "mismatch"},
        },
    }
    attrs = to_openinference_attributes(report)
    assert attrs["genai.request.model"] == "gpt-4o-mini"
    assert attrs["genai.transit_truth.verdict"] == "suspicious"
    assert attrs["genai.transit_truth.tokenizer_score"] == 0.0
    # No None values leaked.
    assert all(v is not None for v in attrs.values())


def test_emit_otel_safe_regardless_of_dependency():
    # opentelemetry is optional; emitting must never raise whether or not it is
    # installed, and must return a bool.
    report = {
        "claimed_model": "x",
        "verdict": "pass",
        "statistics": None,
        "error": None,
    }
    assert emit_otel_span(report) in (True, False)


def test_sdk_entry_signature():
    import inspect

    sig = inspect.signature(verify_endpoint)
    assert "base_url" in sig.parameters
    assert "claimed_model" in sig.parameters
    # Sync wrapper exists and forwards.
    assert callable(verify_endpoint_sync)
