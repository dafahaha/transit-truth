"""TransitTruth - AI API Relay Audit Tool

Main FastAPI application entry point.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import Headers

from .config import APP_VERSION, BASE_DIR
from .database import init_db
from .api.audit import router as audit_router
from .api.ranking import router as ranking_router
from .api.detect import router as detect_router
from .api.balance import router as balance_router
from .api.contribute import router as contribute_router

app = FastAPI(
    title="TransitTruth",
    description="AI API Relay Audit Tool - Verify token counts, model authenticity, and protocol compliance",
    version=APP_VERSION,
)

# CORS: this service has no cookie/session auth, so credentials are disabled.
# allow_credentials=True with allow_origins=["*"] would otherwise let any site
# drive a victim browser to call this server (e.g. to abuse its SSRF surface).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Hard cap on request body size (N3 / R3-1). The anonymous /api/contribute
# endpoint stores the submitted JSON; without a cap a caller could upload
# multi-MB blobs to fill the DB or exhaust memory. 1 MiB is far above any
# legitimate audit payload. The cap is *inclusive*: exactly 1 MiB is accepted,
# anything larger (>= 1 MiB + 1 byte) is rejected with 413.
MAX_BODY_BYTES = 1 * 1024 * 1024


class _RequestBodyTooLarge(Exception):
    """Internal signal raised by the counting receive once the body exceeds the cap."""


class RequestBodyLimitMiddleware:
    """ASGI middleware enforcing a hard request-body cap.

    The previous implementation only inspected the ``Content-Length`` header,
    so a chunked request (``Transfer-Encoding: chunked``, no ``Content-Length``)
    bypassed the cap entirely: uvicorn streamed the body and FastAPI buffered the
    whole thing into memory before pydantic validation (a single 2 MB chunked
    upload returned 422, not 413). We now wrap the ASGI ``receive`` channel and
    count bytes across every ``http.request`` chunk (honouring ``more_body``),
    aborting the moment the cumulative body exceeds the cap. Both the declared
    ``Content-Length`` path (rejected without reading) and the chunked path
    (counted while streaming) are covered.
    """

    def __init__(self, app):
        self.app = app

    @staticmethod
    def _too_large() -> JSONResponse:
        return JSONResponse(status_code=413, content={"detail": "Request body too large"})

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Fast path: a declared, over-cap length lets us reject without reading
        # a single byte of the body.
        content_length = Headers(scope=scope).get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > MAX_BODY_BYTES:
                    await self._too_large()(scope, receive, send)
                    return
            except ValueError:
                pass  # malformed length header; the streaming guard below still applies

        received = 0
        over = False

        async def limited_receive():
            nonlocal received, over
            event = await receive()
            if event["type"] == "http.request":
                chunk = event.get("body", b"") or b""
                received += len(chunk)
                if received > MAX_BODY_BYTES:
                    # Stop before this chunk reaches downstream: abort the body
                    # read. We can't let the exception propagate as-is — FastAPI
                    # turns any body-read error into a generic 400 — so we flag
                    # the overflow, swallow whatever response downstream then
                    # emits, and send our own authoritative 413 below. At most
                    # ~MAX_BODY_BYTES (+ one TCP chunk) ever lands in memory.
                    over = True
                    raise _RequestBodyTooLarge()
            return event

        async def limited_send(message):
            # Once the body overflowed, downstream will produce an error
            # response (a 400 from FastAPI's body parser); drop it entirely so
            # we can reply with a clean 413 instead.
            if over:
                return
            await send(message)

        await self.app(scope, limited_receive, limited_send)
        if over:
            await self._too_large()(scope, receive, send)


app.add_middleware(RequestBodyLimitMiddleware)

# Initialize database
init_db()

# Include API routers
app.include_router(audit_router)
app.include_router(ranking_router)
app.include_router(detect_router)
app.include_router(balance_router)
app.include_router(contribute_router)

# Serve frontend
FRONTEND_DIR = BASE_DIR / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    async def serve_index():
        return FileResponse(str(FRONTEND_DIR / "index.html"))


@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "TransitTruth", "version": APP_VERSION}
