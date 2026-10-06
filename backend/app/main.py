"""TransitTruth - AI API Relay Audit Tool

Main FastAPI application entry point.
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

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

# Hard cap on request body size (N3). The anonymous /api/contribute endpoint
# stores the submitted JSON; without a cap a caller could upload multi-MB
# blobs to fill the DB. 1 MiB is far above any legitimate audit payload.
MAX_BODY_BYTES = 1 * 1024 * 1024


@app.middleware("http")
async def limit_request_body_size(request: Request, call_next):
    length = request.headers.get("content-length")
    if length is not None:
        try:
            if int(length) > MAX_BODY_BYTES:
                return JSONResponse(
                    status_code=413,
                    content={"detail": "Request body too large"},
                )
        except ValueError:
            pass
    return await call_next(request)

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
