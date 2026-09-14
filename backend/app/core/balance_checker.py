"""
中转站余额查询模块

支持查询多个中转站账户的余额，低余额自动告警。
由于OpenAI官方API不支持用API key查询余额（需要dashboard session key），
大部分中转站会提供自定义的余额查询端点。本模块自动尝试多个常见端点。
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class BalanceResult:
    """余额查询结果"""
    account_name: str
    base_url: str
    success: bool
    balance: Optional[float] = None
    currency: str = "USD"
    used: Optional[float] = None
    limit: Optional[float] = None
    endpoint_used: Optional[str] = None
    error: Optional[str] = None
    checked_at: datetime = field(default_factory=datetime.now)

    @property
    def is_low(self) -> bool:
        """是否低余额（低于$1）"""
        return self.balance is not None and self.balance < 1.0

    @property
    def is_critical(self) -> bool:
        """是否危急余额（低于$0.1）"""
        return self.balance is not None and self.balance < 0.1

    def to_dict(self) -> dict:
        return {
            "account_name": self.account_name,
            "base_url": self.base_url,
            "success": self.success,
            "balance": self.balance,
            "currency": self.currency,
            "used": self.used,
            "limit": self.limit,
            "endpoint_used": self.endpoint_used,
            "error": self.error,
            "is_low": self.is_low,
            "is_critical": self.is_critical,
            "checked_at": self.checked_at.isoformat(),
        }


# 常见的余额查询端点（按优先级排序）
COMMON_BALANCE_ENDPOINTS = [
    "/v1/dashboard/billing/credit_grants",
    "/v1/billing/credit_grants",
    "/dashboard/billing/credit_grants",
    "/api/billing/credit_grants",
    "/v1/user/balance",
    "/v1/balance",
    "/v1/wallet/balance",
    "/api/user/balance",
]


class BalanceChecker:
    """中转站余额查询器"""

    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout
        self._cache: dict[str, BalanceResult] = {}
        self._cache_ttl = 60  # 缓存60秒

    async def check_balance(
        self,
        api_key: str,
        base_url: str,
        account_name: str = "default",
        custom_endpoint: Optional[str] = None,
    ) -> BalanceResult:
        """
        查询单个账户的余额

        Args:
            api_key: API密钥
            base_url: 基础URL（如 https://api.example.com/v1）
            account_name: 账户名称（用于展示）
            custom_endpoint: 自定义余额查询端点（如 /v1/balance）

        Returns:
            BalanceResult: 余额查询结果
        """
        # 检查缓存
        cache_key = f"{account_name}:{base_url}"
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            if (datetime.now() - cached.checked_at).total_seconds() < self._cache_ttl:
                return cached

        # 规范化base_url
        base_url = base_url.rstrip("/")
        if base_url.endswith("/v1"):
            base_root = base_url[:-3]  # 去掉/v1
        else:
            base_root = base_url + "/"

        # 确定要尝试的端点列表
        if custom_endpoint:
            endpoints = [custom_endpoint]
        else:
            endpoints = COMMON_BALANCE_ENDPOINTS

        # 尝试每个端点
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for endpoint in endpoints:
                url = base_root.rstrip("/") + endpoint
                try:
                    response = await client.get(url, headers=headers)
                    if response.status_code == 200:
                        result = self._parse_response(
                            response.json(), account_name, base_url, endpoint
                        )
                        if result.success:
                            self._cache[cache_key] = result
                            return result
                    elif response.status_code == 401:
                        # API key无效，不需要继续尝试
                        return BalanceResult(
                            account_name=account_name,
                            base_url=base_url,
                            success=False,
                            error="API Key 无效（401）",
                        )
                except httpx.TimeoutException:
                    continue
                except Exception as e:
                    logger.debug(f"端点 {endpoint} 查询失败: {e}")
                    continue

        # 所有端点都失败
        return BalanceResult(
            account_name=account_name,
            base_url=base_url,
            success=False,
            error="未找到可用的余额查询端点，请尝试自定义端点",
        )

    def _parse_response(
        self, data: dict, account_name: str, base_url: str, endpoint: str
    ) -> BalanceResult:
        """
        解析余额查询响应

        支持多种响应格式：
        1. OpenAI格式: {"total_available": 10.0, "total_used": 5.0, "has_payment_method": true}
        2. 简单格式: {"balance": 10.0} 或 {"credit": 10.0}
        3. 嵌套格式: {"data": {"balance": 10.0}}
        4. 数组格式: {"grants": {"data": [{"grant_amount": 10.0}]}}
        """
        try:
            # 格式1: OpenAI credit_grants格式
            if "total_available" in data:
                balance = float(data["total_available"])
                used = float(data.get("total_used", 0))
                limit = float(data.get("total_granted", balance + used))
                return BalanceResult(
                    account_name=account_name,
                    base_url=base_url,
                    success=True,
                    balance=balance,
                    used=used,
                    limit=limit,
                    endpoint_used=endpoint,
                )

            # 格式2: 简单格式
            for key in ["balance", "credit", "credits", "available", "remaining"]:
                if key in data and isinstance(data[key], (int, float)):
                    return BalanceResult(
                        account_name=account_name,
                        base_url=base_url,
                        success=True,
                        balance=float(data[key]),
                        endpoint_used=endpoint,
                    )

            # 格式3: 嵌套格式
            if "data" in data and isinstance(data["data"], dict):
                nested = data["data"]
                for key in ["balance", "credit", "credits", "available", "remaining"]:
                    if key in nested and isinstance(nested[key], (int, float)):
                        return BalanceResult(
                            account_name=account_name,
                            base_url=base_url,
                            success=True,
                            balance=float(nested[key]),
                            endpoint_used=endpoint,
                        )

            # 格式4: OpenAI grants数组格式
            if "grants" in data and isinstance(data["grants"], dict):
                grants_data = data["grants"].get("data", [])
                if grants_data:
                    total = sum(float(g.get("grant_amount", 0)) for g in grants_data)
                    return BalanceResult(
                        account_name=account_name,
                        base_url=base_url,
                        success=True,
                        balance=total,
                        endpoint_used=endpoint,
                    )

            # 格式5: 其他常见字段
            if "object" in data and data["object"] == "credit_summary":
                balance = float(data.get("total_available", 0))
                return BalanceResult(
                    account_name=account_name,
                    base_url=base_url,
                    success=True,
                    balance=balance,
                    endpoint_used=endpoint,
                )

            # 无法解析
            return BalanceResult(
                account_name=account_name,
                base_url=base_url,
                success=False,
                error=f"无法解析响应格式: {list(data.keys())[:5]}",
            )

        except (ValueError, TypeError) as e:
            return BalanceResult(
                account_name=account_name,
                base_url=base_url,
                success=False,
                error=f"解析响应失败: {e}",
            )

    async def check_multiple(
        self, accounts: list[dict]
    ) -> list[BalanceResult]:
        """
        批量查询多个账户的余额

        Args:
            accounts: 账户列表，每个账户包含 api_key, base_url, account_name

        Returns:
            list[BalanceResult]: 余额查询结果列表
        """
        tasks = [
            self.check_balance(
                api_key=acc["api_key"],
                base_url=acc["base_url"],
                account_name=acc.get("account_name", f"account_{i}"),
                custom_endpoint=acc.get("custom_endpoint"),
            )
            for i, acc in enumerate(accounts)
        ]
        return await asyncio.gather(*tasks)

    def get_low_balance_alerts(
        self, results: list[BalanceResult], threshold: float = 1.0
    ) -> list[BalanceResult]:
        """
        获取低余额告警列表

        Args:
            results: 余额查询结果列表
            threshold: 低余额阈值（美元）

        Returns:
            list[BalanceResult]: 低余额的账户列表
        """
        return [
            r for r in results
            if r.success and r.balance is not None and r.balance < threshold
        ]

    def format_summary(self, results: list[BalanceResult]) -> str:
        """
        格式化余额汇总报告

        Args:
            results: 余额查询结果列表

        Returns:
            str: 格式化的汇总报告
        """
        lines = ["📊 中转站余额汇总", "=" * 40]

        total_balance = 0.0
        success_count = 0
        low_count = 0

        for r in results:
            if r.success:
                success_count += 1
                total_balance += r.balance or 0
                status = "🟢"
                if r.is_critical:
                    status = "🔴"
                    low_count += 1
                elif r.is_low:
                    status = "🟡"
                    low_count += 1
                lines.append(
                    f"{status} {r.account_name}: ${r.balance:.2f} "
                    f"(已用 ${r.used:.2f})" if r.used else
                    f"{status} {r.account_name}: ${r.balance:.2f}"
                )
            else:
                lines.append(f"⚪ {r.account_name}: 查询失败 - {r.error}")

        lines.append("=" * 40)
        lines.append(f"总计: {success_count}/{len(results)} 个账户查询成功")
        lines.append(f"总余额: ${total_balance:.2f}")
        if low_count > 0:
            lines.append(f"⚠️  {low_count} 个账户余额偏低")

        return "\n".join(lines)


# 便捷函数
async def check_balance(
    api_key: str,
    base_url: str,
    account_name: str = "default",
    custom_endpoint: Optional[str] = None,
) -> BalanceResult:
    """便捷函数：查询单个账户余额"""
    checker = BalanceChecker()
    return await checker.check_balance(
        api_key, base_url, account_name, custom_endpoint
    )


async def check_multiple_balances(accounts: list[dict]) -> list[BalanceResult]:
    """便捷函数：批量查询多个账户余额"""
    checker = BalanceChecker()
    return await checker.check_multiple(accounts)
