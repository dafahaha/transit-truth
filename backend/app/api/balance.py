"""
余额查询 API 端点
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from app.core.balance_checker import BalanceChecker
from app.utils.ssrf_guard import require_public_url_async
from app.utils.rate_limit import enforce_rate_limit

router = APIRouter(prefix="/api/balance", tags=["balance"])


class BalanceCheckRequest(BaseModel):
    """余额查询请求"""
    api_key: str = Field(..., description="API密钥")
    base_url: str = Field(..., description="基础URL")
    account_name: str = Field("default", description="账户名称")
    custom_endpoint: Optional[str] = Field(None, description="自定义余额查询端点")


class BatchBalanceCheckRequest(BaseModel):
    """批量余额查询请求

    Each element is validated as :class:`BalanceCheckRequest` (N7): a missing
    ``api_key``/``base_url`` now returns 422 instead of a downstream KeyError.
    """
    accounts: list[BalanceCheckRequest] = Field(..., description="账户列表", max_length=5)


@router.post("/check", dependencies=[Depends(enforce_rate_limit)])
async def check_balance(request: BalanceCheckRequest):
    """查询单个账户余额"""
    await require_public_url_async(request.base_url)
    checker = BalanceChecker()
    try:
        result = await checker.check_balance(
            api_key=request.api_key,
            base_url=request.base_url,
            account_name=request.account_name,
            custom_endpoint=request.custom_endpoint,
        )
    except ValueError as exc:
        # Invalid custom_endpoint (e.g. userinfo '@' / scheme-relative '//').
        # URL-layer defense in depth; the connect-level guard would also block
        # the resulting request, but we reject up front with a clear 400.
        raise HTTPException(status_code=400, detail=str(exc))
    return result.to_dict()


@router.post("/batch", dependencies=[Depends(enforce_rate_limit)])
async def batch_check_balance(request: BatchBalanceCheckRequest):
    """批量查询多个账户余额"""
    # SSRF guard: every account must point at a public host before we fan out.
    for acc in request.accounts:
        await require_public_url_async(acc.base_url)
    checker = BalanceChecker()
    # Pass plain dicts to the checker (it already works with dict access).
    account_dicts = [acc.model_dump() for acc in request.accounts]
    try:
        results = await checker.check_multiple(account_dicts)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "results": [r.to_dict() for r in results],
        "summary": checker.format_summary(results),
        "low_balance_alerts": [
            r.to_dict() for r in checker.get_low_balance_alerts(results)
        ],
    }


@router.get("/endpoints")
async def list_supported_endpoints():
    """列出支持的余额查询端点"""
    from app.core.balance_checker import COMMON_BALANCE_ENDPOINTS
    return {
        "endpoints": COMMON_BALANCE_ENDPOINTS,
        "description": "自动尝试以下端点，直到找到可用的。也可以通过custom_endpoint参数指定自定义端点。",
    }
