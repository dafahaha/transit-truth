"""Ranking API endpoints."""
from fastapi import APIRouter
from ..database import get_rankings

router = APIRouter(prefix="/api/ranking", tags=["ranking"])


@router.get("/")
async def get_public_rankings(model: str = None, limit: int = 100):
    """Get the public relay ranking."""
    rankings = get_rankings(model=model, limit=limit)
    return {
        "total": len(rankings),
        "model_filter": model,
        "rankings": rankings,
    }
