"""TransitTruth - AI API Relay Audit Tool

Main FastAPI application entry point.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api.audit import router as audit_router
from .api.balance import router as balance_router
from .api.contribute import router as contribute_router
from .api.detect import router as detect_router
from .api.ranking import router as ranking_router
from .config import APP_VERSION, BASE_DIR
from .database import init_db

# Shared 1 MiB request-body cap (declared Content-Length fast path + chunked
# streaming guard). Re-exported here for backwards compatibility; the verify
# serve app imports the same middleware from utils.body_limit directly.
from .utils.body_limit import (
    MAX_BODY_BYTES,
    RequestBodyLimitMiddleware,
    _RequestBodyTooLarge,
)

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

# Hard cap on request body size (N3 / R3-1): the anonymous /api/contribute
# endpoint stores the submitted JSON; without a cap a caller could upload
# multi-MB blobs to fill the DB or exhaust memory. 1 MiB is far above any
# legitimate audit payload. The cap is *inclusive*: exactly 1 MiB is accepted,
# anything larger (>= 1 MiB + 1 byte) is rejected with 413. The middleware
# (declared Content-Length fast path + chunked streaming guard) lives in
# utils.body_limit and is shared with the verify serve app.
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
