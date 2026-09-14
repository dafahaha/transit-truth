"""Audit API endpoints."""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from ..models import AuditRequest, AuditResult
from ..core.auditor import AuditEngine
from ..database import save_audit, get_audit, list_audits

router = APIRouter(prefix="/api/audit", tags=["audit"])

_engine = AuditEngine()


@router.post("/start", response_model=AuditResult)
async def start_audit(request: AuditRequest):
    """Start a new audit (synchronous for MVP)."""
    result = await _engine.run_audit(request)
    save_audit(result)
    return result


@router.get("/{audit_id}")
async def get_audit_result(audit_id: str):
    """Get an audit result by ID."""
    audit = get_audit(audit_id)
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")
    return audit


@router.get("/")
async def list_audit_results(limit: int = 50, model: str = None, base_url: str = None):
    """List recent audit results."""
    return list_audits(limit=limit, model=model, base_url=base_url)
