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
  do NOT emit ``Access-Control-Allow-Origin: *``. A cross-site browser request
  is rejected on Content-Type, Origin, Sec-Fetch-Site, and (loopback binds) Host.
- The SSRF guard stays on: outbound targets must be public by default
  (``allow_local`` only for the operator's own loopback self-test reference).
- Default bind is 127.0.0.1; any non-loopback bind (0.0.0.0 / :: / RFC1918 /
  public IP / hostname) requires the explicit ``--allow-public`` gate.
"""

from __future__ import annotations

import asyncio
import copy
import ipaddress
import logging
import math
import os
import re
from importlib import resources
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from ..config import APP_VERSION
from .core import verify_endpoint
from .reference import load_reference_analyzer
from .reference_server import CATALOG_TOKENIZERS

logger = logging.getLogger(__name__)

# Repository root: backend/app/verify/serve.py -> 4 parents up.
_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_STATIC_DIR = _REPO_ROOT / "webapp"


def _resolve_static_dir(explicit: Optional[Path]) -> Path:
    """Three-tier static UI resolution:
    1. explicit injection (tests);
    2. ``TRANSIT_TRUTH_WEBAPP_DIR`` env (Docker / custom);
    3. repository-root ``webapp/`` checkout (dev);
    4. bundled package resource shipped inside the installed wheel
       (``app.verify/webapp``) when running from a plain ``pip install``.
    """
    if explicit:
        return Path(explicit)
    env_dir = os.environ.get("TRANSIT_TRUTH_WEBAPP_DIR")
    if env_dir and (Path(env_dir) / "index.html").exists():
        return Path(env_dir)
    # Dev checkout: walk up from this file to a sibling ``webapp/`` with index.html.
    cur = Path(__file__).resolve()
    for parent in cur.parents:
        candidate = parent / "webapp"
        if (candidate / "index.html").exists():
            return candidate
    # Installed wheel: bundled resource inside the package.
    try:
        bundled = resources.files("app.verify") / "webapp"
        if bundled.joinpath("index.html").is_file():
            return Path(str(bundled))
    except (FileNotFoundError, ModuleNotFoundError, TypeError):
        pass
    return DEFAULT_STATIC_DIR


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

# Embedded credential patterns (a token may sit inside a log line / note).
_SK_RE = re.compile(r"sk-[A-Za-z0-9_\-]{6,}")
_BEARER_RE = re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]+")

# Request clamp bounds (P3): keep the local probe battery well-behaved.
_CLAMPS = {
    "max_requests": (1, 200),
    "behavioral_samples": (1, 20),
    "timeout": (1.0, 120.0),
    "total_timeout": (1.0, 300.0),
}

# Concurrency cap: the local UI must not be usable as an open proxy battery.
_MAX_CONCURRENT = 4

# Conservative CSP: same-origin only; inline script/style kept because the UI
# is a single self-contained file; connect-src 'self' blocks direct browser
# calls to third-party relays; frame-ancestors 'none' blocks clickjacking.
_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'"
)


def _redact_string(value: str) -> str:
    """Redact credential-shaped strings (whole value or embedded occurrences)."""
    value = _SK_RE.sub("sk-***redacted***", value)
    value = _BEARER_RE.sub("Bearer ***redacted***", value)
    return value


def sanitize_report(obj: Any) -> Any:
    """Deep-copy ``obj`` and strip / redact any credential-shaped content.

    Defense in depth: the verifier already guarantees the report never contains
    the key, but this walks the whole structure before the response leaves the
    process so a future regression (or an upstream field) can never leak a key
    into a shareable report or a browser-rendered page.
    """
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            if isinstance(k, str) and k.lower() in _SENSITIVE_KEYS:
                # Drop the sensitive field entirely (do not echo its value).
                continue
            out[k] = sanitize_report(v)
        return out
    if isinstance(obj, list):
        return [sanitize_report(v) for v in obj]
    if isinstance(obj, str):
        return _redact_string(obj)
    return obj


def is_loopback_host(host: str) -> bool:
    """Return True if *host* names a loopback interface.

    Accepts ``localhost``, any IPv4 in 127.0.0.0/8, and ``::1`` (with or
    without brackets). Any other literal IP (0.0.0.0, RFC1918, public) or
    arbitrary hostname is NOT loopback and therefore needs ``--allow-public``.
    """
    if not host:
        return False
    host = host.strip().lower()
    # Drop a :port if present; strip [brackets] around an IPv6 literal.
    if host.startswith("["):
        host = host.split("]", 1)[0].lstrip("[")
    elif ":" in host and not host.startswith("::1"):
        host = host.split(":", 1)[0]
    if host == "localhost":
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_loopback


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


def _content_type_ok(request: Request) -> bool:
    ctype = request.headers.get("content-type", "")
    # Allow "application/json; charset=utf-8", reject everything else
    # (text/plain simple cross-site requests need no preflight and must be
    # blocked here).
    main = ctype.split(";", 1)[0].strip().lower()
    return main == "application/json"


def _origin_mismatch(request: Request) -> bool:
    """True when an explicit Origin does not match the request Host (cross-site).

    Compares hostname (userinfo ignored by urlsplit) AND explicit port; a
    missing port on either side is treated as matching only when the other is
    also absent, so a different port is a mismatch.
    """
    origin = request.headers.get("origin")
    if not origin:
        return False
    try:
        o = urlsplit(origin)
        o_host, o_port = (o.hostname or "").lower(), o.port
    except ValueError:
        return True
    host = request.headers.get("host", "")
    h = urlsplit(f"//{host}")
    h_host, h_port = (h.hostname or host.split(":", 1)[0]).lower(), h.port
    if o_host != h_host:
        return True
    # Port differs (explicit vs absent, or two different ports) = cross-origin.
    if o_port != h_port:
        return True
    return False


def _host_is_loopback(request: Request) -> bool:
    """True when the request Host hostname is a loopback name/address."""
    host = request.headers.get("host", "")
    hostname = urlsplit(f"//{host}").hostname or host.split(":", 1)[0]
    return is_loopback_host(hostname)


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
    loopback_only: bool = True,
) -> FastAPI:
    """Build the local FastAPI app.

    Args:
        allow_local: permit loopback/private targets for outbound probing
            (operator self-test against the local reference server). Default
            False keeps the public SSRF guard on.
        static_dir: override the static UI directory (tests inject a temp dir).
        loopback_only: when True (default, local bind) reject any request whose
            ``Host`` is not loopback (DNS-rebinding / Host-header attack). Set
            False only behind the explicit ``--allow-public`` gate; the Origin
            same-origin check still applies.
    """
    # Quiet the outbound httpx/httpcore access chatter so a probe response (or
    # any echoed key) can never land in the server log at INFO level.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    static_dir = _resolve_static_dir(static_dir)
    app = FastAPI(title="TransitTruth local verify", version=APP_VERSION)
    semaphore = asyncio.Semaphore(_MAX_CONCURRENT)
    app.state.concurrent_semaphore = semaphore

    # NOTE: intentionally NO CORS middleware. The UI and API are same-origin;
    # emitting Access-Control-Allow-Origin:* would let any website drive this
    # local port. Do not add one.

    @app.middleware("http")
    async def request_guard(request: Request, call_next):
        # Origin same-origin check applies to every route (GET included).
        if _origin_mismatch(request):
            return _error(
                "cross_origin",
                "Origin does not match this server (same-origin only).",
                status=403,
            )
        if (request.headers.get("sec-fetch-site") or "").lower() == "cross-site":
            return _error(
                "cross_site",
                "Cross-site requests are not allowed.",
                status=403,
            )
        # Host whitelist on loopback binds blocks DNS-rebinding reads on ALL routes.
        if loopback_only and not _host_is_loopback(request):
            return _error(
                "invalid_host",
                "Refused: request Host is not a loopback address.",
                status=403,
            )
        return await call_next(request)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = _CSP
        return response

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
        # --- Content-Type: only application/json (415 otherwise) -------------
        # Origin / Sec-Fetch-Site / Host checks run in the global request_guard
        # middleware for every route (GET included).
        if not _content_type_ok(request):
            return _error(
                "unsupported_media_type",
                "Only application/json requests are accepted.",
                status=415,
            )

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

        # --- Reject non-finite (NaN / Infinity) knob values before clamping ---
        for name in _CLAMPS:
            if name not in body or body[name] is None:
                continue
            try:
                raw = float(body[name])
            except (TypeError, ValueError):
                return _error(
                    "invalid_parameter", f"{name} must be a number.", status=400
                )
            if not math.isfinite(raw):
                return _error(
                    "invalid_parameter",
                    f"{name} must be a finite number (NaN/Infinity rejected).",
                    status=400,
                )
            # Integer knobs must be whole numbers: reject "12.5"/12.5/non-integer.
            if name in ("max_requests", "behavioral_samples") and raw != int(raw):
                return _error(
                    "invalid_parameter",
                    f"{name} must be a whole integer.",
                    status=400,
                )

        # --- Clamp bounded knobs; out-of-range -> clean 400 -------------------
        params: dict[str, float] = {
            "max_requests": _opt_int("max_requests", 20),
            "behavioral_samples": _opt_int("behavioral_samples", 3),
            "timeout": _opt_float("timeout", 30.0),
            "total_timeout": _opt_float("total_timeout", 90.0),
        }
        for name, (lo, hi) in _CLAMPS.items():
            val = params[name]
            if val < lo or val > hi:
                return _error(
                    "invalid_parameter",
                    f"{name} must be between {lo} and {hi}.",
                    status=400,
                )

        # --- Concurrency cap: non-blocking acquire, short grace, then 429 ----
        # No request is queued indefinitely; if all 4 slots are busy we fail
        # fast with 429 rather than letting callers pile up behind a lock.
        try:
            acquired = await asyncio.wait_for(semaphore.acquire(), timeout=2.0)
        except asyncio.TimeoutError:
            acquired = False
        if not acquired:
            return _error(
                "too_many_requests",
                "Server busy (max 4 concurrent verifications). Retry shortly.",
                status=429,
            )
        try:
            report = await verify_endpoint(
                base_url=base_url,
                claimed_model=claimed_model,
                api_key=api_key,
                max_requests=int(params["max_requests"]),
                behavioral_samples=int(params["behavioral_samples"]),
                timeout=float(params["timeout"]),
                total_timeout=float(params["total_timeout"]),
                allow_local=allow_local,
            )
        except Exception as exc:  # noqa: BLE001 - fail closed with clean JSON
            logger.warning("verify_endpoint raised: %s", type(exc).__name__)
            return _error(
                "verify_failed",
                f"Verification could not be completed ({type(exc).__name__}).",
                status=502,
            )
        finally:
            semaphore.release()

        # Defense in depth: strip any credential-shaped content before replying.
        return sanitize_report(copy.deepcopy(report))

    return app
