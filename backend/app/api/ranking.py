"""Ranking API endpoints."""
from typing import Optional

from fastapi import APIRouter, Query
from ..database import get_rankings

router = APIRouter(prefix="/api/ranking", tags=["ranking"])


@router.get("/")
async def get_public_rankings(
    model: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
):
    """Get the public relay ranking."""
    rankings = get_rankings(model=model, limit=limit)
    return {
        "total": len(rankings),
        "model_filter": model,
        "rankings": rankings,
    }
