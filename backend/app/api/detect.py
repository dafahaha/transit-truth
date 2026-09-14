"""Detection API endpoints - auto-detect base URL and fetch models."""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from ..core.detect import detect_and_suggest, fetch_models

router = APIRouter(prefix="/api/detect", tags=["detect"])


class DetectRequest(BaseModel):
    api_key: str
    base_url: Optional[str] = None


class ModelsRequest(BaseModel):
    api_key: str
    base_url: str


@router.post("/")
async def detect_relay(request: DetectRequest):
    """Auto-detect relay base URL and suggest likely services."""
    result = await detect_and_suggest(request.api_key, request.base_url)
    return result


@router.post("/models")
async def get_models(request: ModelsRequest):
    """Fetch supported models from a relay's /models endpoint."""
    models = await fetch_models(request.base_url, request.api_key)
    return {
        "base_url": request.base_url,
        "models": models,
        "count": len(models),
        "available": len(models) > 0,
    }
