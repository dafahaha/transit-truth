"""
余额查询 API 端点
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from app.core.balance_checker import BalanceChecker, BalanceResult

router = APIRouter(prefix="/api/balance", tags=["balance"])


class BalanceCheckRequest(BaseModel):
    """余额查询请求"""
    api_key: str = Field(..., description="API密钥")
    base_url: str = Field(..., description="基础URL")
    account_name: str = Field("default", description="账户名称")
    custom_endpoint: Optional[str] = Field(None, description="自定义余额查询端点")


class BatchBalanceCheckRequest(BaseModel):
    """批量余额查询请求"""
    accounts: list[dict] = Field(..., description="账户列表")


@router.post("/check")
async def check_balance(request: BalanceCheckRequest):
    """查询单个账户余额"""
    checker = BalanceChecker()
    result = await checker.check_balance(
        api_key=request.api_key,
        base_url=request.base_url,
        account_name=request.account_name,
        custom_endpoint=request.custom_endpoint,
    )
    return result.to_dict()


@router.post("/batch")
async def batch_check_balance(request: BatchBalanceCheckRequest):
    """批量查询多个账户余额"""
    checker = BalanceChecker()
    results = await checker.check_multiple(request.accounts)
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
