"""Audit API endpoints."""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from starlette.concurrency import run_in_threadpool
from ..models import AuditRequest, AuditResult
from ..core.auditor import AuditEngine
from ..database import save_audit, get_audit, list_audits
from ..utils.ssrf_guard import require_public_url

router = APIRouter(prefix="/api/audit", tags=["audit"])

_engine = AuditEngine()


@router.post("/start", response_model=AuditResult)
async def start_audit(request: AuditRequest):
    """Start a new audit (synchronous for MVP)."""
    # SSRF guard: refuse internal/non-http targets before any outbound call.
    require_public_url(request.base_url)
    result = await _engine.run_audit(request)
    # Offload the blocking sqlite write so it doesn't stall the event loop (S7).
    await run_in_threadpool(save_audit, result)
    return result


@router.get("/{audit_id}")
async def get_audit_result(audit_id: str):
    """Get an audit result by ID."""
    audit = get_audit(audit_id)
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")
    return audit


@router.get("/")
async def list_audit_results(
    limit: int = Query(50, ge=1, le=500),
    model: Optional[str] = None,
    base_url: Optional[str] = None,
):
    """List recent audit results."""
    return list_audits(limit=limit, model=model, base_url=base_url)
