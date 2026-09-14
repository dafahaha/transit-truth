"""TransitTruth - AI API Relay Audit Tool

Main FastAPI application entry point.
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .config import BASE_DIR
from .database import init_db
from .api.audit import router as audit_router
from .api.ranking import router as ranking_router
from .api.detect import router as detect_router
from .api.balance import router as balance_router
from .api.contribute import router as contribute_router

app = FastAPI(
    title="TransitTruth",
    description="AI API Relay Audit Tool - Verify token counts, model authenticity, and protocol compliance",
    version="0.2.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    return {"status": "ok", "service": "TransitTruth", "version": "0.2.0"}
