"""Local single-page web wrapper around the stateless verifier.

``transit-truth serve`` binds a FastAPI app to 127.0.0.1 (by default) and
serves a self-contained static UI (``webapp/index.html``) plus a thin
``POST /api/verify`` JSON endpoint that runs :func:`verify_endpoint` server-side.

Security contract (hard requirements, regression-tested):
- The API key lives in memory only. It is never written to disk, never logged,
  and never echoed into the response. ``sanitize_report`` is a defense-in-depth
  second layer: even if the engine ever carried a key-shaped field, it is
  stripped / redacted before the response leaves the process.
- Same-origin: the UI and API are served from one local server. We deliberately
  do NOT emit ``Access-Control-Allow-Origin: *``; a browser on another origin
  cannot call this endpoint.
- The SSRF guard stays on: outbound targets must be public by default
  (``allow_local`` only for the operator's own loopback self-test reference).
- Default bind is 127.0.0.1; binding 0.0.0.0 requires the explicit
  ``--allow-public`` gate and prints a loud warning (public hosting turns this
  box into a probe proxy).
"""

from __future__ import annotations

import copy
import logging
import os
import re
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from .core import verify_endpoint
from .reference import load_reference_analyzer
from .reference_server import CATALOG_TOKENIZERS

logger = logging.getLogger(__name__)

# Repository root: backend/app/verify/serve.py -> 4 parents up.
_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_STATIC_DIR = _REPO_ROOT / "webapp"

# Field names that may carry a secret under different spellings. Matched
# case-insensitively; any such key is dropped rather than echoed.
_SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "key",
    "secret",
    "authorization",
    "auth",
    "bearer",
    "token",
}

# A free-form string value that looks like a credential (sk-..., Bearer ...)
# is redacted even when it appears under a non-sensitive key, as a final net.
_SK_PREFIX = "sk-"
# Embedded credential patterns (a token may sit inside a log line / note).
_SK_RE = re.compile(r"sk-[A-Za-z0-9_\-]{6,}")
_BEARER_RE = re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]+")


def _redact_string(value: str) -> str:
    """Redact credential-shaped strings (whole value or embedded occurrences)."""
    value = _SK_RE.sub("sk-***redacted***", value)
    value = _BEARER_RE.sub("Bearer ***redacted***", value)
    return value


def sanitize_report(obj: Any) -> Any:
    """Deep-copy ``obj`` and strip / redact any credential-shaped content.

    Defense in depth: the verifier already guarantees the report never contains
    the key, but this walks the whole structure before the response leaves the
    process so a future regressions (or an upstream field) can never leak a key
    into a shareable report or a browser-rendered page.
    """
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            if isinstance(k, str) and k.lower() in _SENSITIVE_KEYS:
                # Drop the sensitive field entirely (do not echo its key name
                # value beyond noting it was removed).
                continue
            out[k] = sanitize_report(v)
        return out
    if isinstance(obj, list):
        return [sanitize_report(v) for v in obj]
    if isinstance(obj, str):
        # Redact whole-value or embedded credential-shaped strings (e.g. an
        # Authorization header / key that slipped into a note or debug block).
        return _redact_string(obj)
    return obj


def _error(code: str, message: str, status: int = 400) -> JSONResponse:
    """Structured, human-readable JSON error (never an HTML stack trace)."""
    return JSONResponse(
        status_code=status,
        content={
            "schema": "transit-truth/verify-error/v1",
            "verdict": "insufficient_evidence",
            "error": {"code": code, "message": message},
            "statistics": None,
        },
    )


def _catalog() -> list[str]:
    """Reference model names available for comparison (deduplicated, sorted)."""
    names: set[str] = set()
    try:
        analyzer = load_reference_analyzer()
        names.update(analyzer.baseline_db.keys())
    except Exception as exc:  # noqa: BLE001 - catalog is advisory
        logger.warning("catalog load failed: %s", exc)
    names.update(CATALOG_TOKENIZERS.keys())
    return sorted(names)


def build_serve_app(
    allow_local: bool = False,
    static_dir: Optional[Path] = None,
) -> FastAPI:
    """Build the local FastAPI app.

    Args:
        allow_local: permit loopback/private targets (operator self-test against
            the local reference server). Default False keeps the public SSRF
            guard on.
        static_dir: override the static UI directory (tests inject a temp dir).
    """
    static_dir = (
        Path(static_dir)
        if static_dir
        else Path(os.environ.get("TRANSIT_TRUTH_WEBAPP_DIR", str(DEFAULT_STATIC_DIR)))
    )
    app = FastAPI(title="TransitTruth local verify", version="0.5.0")

    # NOTE: intentionally NO CORS middleware. The UI and API are same-origin;
    # emitting Access-Control-Allow-Origin:* would let any website drive this
    # local port. Do not add one.

    @app.get("/")
    async def index():
        page = static_dir / "index.html"
        if not page.exists():
            return _error(
                "ui_missing",
                f"Static UI not found at {page}; run from the repository root or "
                "set static_dir.",
                status=500,
            )
        return FileResponse(str(page), media_type="text/html; charset=utf-8")

    @app.get("/api/catalog")
    async def catalog():
        return {"models": _catalog()}

    @app.post("/api/verify")
    async def verify(request: Request):
        # --- Parse body (non-JSON / malformed -> clean 400, not a 500 HTML) ---
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001 - any parse failure
            return _error("invalid_json", "Request body must be a JSON object.")
        if not isinstance(body, dict):
            return _error("invalid_json", "Request body must be a JSON object.")

        base_url = (body.get("base_url") or "").strip()
        claimed_model = (body.get("claimed_model") or body.get("model") or "").strip()
        api_key = body.get("api_key")
        if api_key is not None:
            api_key = str(api_key).strip() or None

        if not base_url:
            return _error(
                "missing_field", "base_url is required (e.g. https://relay.example/v1)."
            )
        if not claimed_model:
            return _error(
                "missing_field", "claimed_model is required (e.g. gpt-4o-mini)."
            )

        def _opt_int(name: str, default: int) -> int:
            val = body.get(name, default)
            try:
                return int(val)
            except (TypeError, ValueError):
                return default

        def _opt_float(name: str, default: float) -> float:
            val = body.get(name, default)
            try:
                return float(val)
            except (TypeError, ValueError):
                return default

        try:
            report = await verify_endpoint(
                base_url=base_url,
                claimed_model=claimed_model,
                api_key=api_key,
                max_requests=_opt_int("max_requests", 20),
                behavioral_samples=_opt_int("behavioral_samples", 3),
                timeout=_opt_float("timeout", 30.0),
                total_timeout=_opt_float("total_timeout", 90.0),
                allow_local=allow_local,
            )
        except Exception as exc:  # noqa: BLE001 - fail closed with clean JSON
            logger.warning("verify_endpoint raised: %s", type(exc).__name__)
            return _error(
                "verify_failed",
                f"Verification could not be completed ({type(exc).__name__}).",
                status=502,
            )

        # Defense in depth: strip any credential-shaped content before replying.
        return sanitize_report(copy.deepcopy(report))

    return app
