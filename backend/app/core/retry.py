"""
Retry and Resilience Utilities - 重试和弹性工具

提供：
- 指数退避重试（Exponential Backoff）
- 限流检测（Rate Limit Detection，429状态码 + Retry-After头）
- 断路器模式（Circuit Breaker，连续失败后暂时停止请求）
- 详细的失败日志和统计

使用方式：
    from app.core.retry import retry_with_backoff, CircuitBreaker

    # 简单重试
    result = await retry_with_backoff(
        func=make_request,
        max_retries=3,
        initial_delay=1.0,
    )

    # 断路器
    breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=60)
    if breaker.can_execute():
        try:
            result = await make_request()
            breaker.record_success()
        except Exception as e:
            breaker.record_failure()
            raise
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class RetryStats:
    """重试统计信息"""
    attempts: int = 0
    successes: int = 0
    failures: int = 0
    total_delay_seconds: float = 0.0
    last_error: Optional[str] = None
    last_status_code: Optional[int] = None


@dataclass
class CircuitBreaker:
    """
    断路器模式（Circuit Breaker）

    当连续失败次数达到阈值时，断路器打开，暂时停止请求一段时间。
    恢复期过后，断路器进入半开状态，允许少量请求尝试。
    如果成功，断路器关闭；如果失败，重新打开。

    状态：
    - CLOSED：正常状态，允许请求
    - OPEN：熔断状态，拒绝请求
    - HALF_OPEN：半开状态，允许少量请求尝试
    """
    failure_threshold: int = 5  # 连续失败多少次后熔断
    recovery_timeout: float = 60.0  # 熔断后多长时间恢复（秒）
    half_open_max_requests: int = 3  # 半开状态允许的最大请求数

    # 内部状态
    _state: str = field(default="CLOSED", init=False)  # CLOSED / OPEN / HALF_OPEN
    _consecutive_failures: int = field(default=0, init=False)
    _last_failure_time: float = field(default=0.0, init=False)
    _half_open_requests: int = field(default=0, init=False)

    def can_execute(self) -> bool:
        """检查是否可以执行请求"""
        if self._state == "CLOSED":
            return True

        if self._state == "OPEN":
            # 检查是否过了恢复期
            if time.time() - self._last_failure_time >= self.recovery_timeout:
                self._state = "HALF_OPEN"
                self._half_open_requests = 0
                logger.info(f"Circuit breaker transitioning to HALF_OPEN after {self.recovery_timeout}s recovery")
                return True
            return False

        if self._state == "HALF_OPEN":
            return self._half_open_requests < self.half_open_max_requests

        return False

    def record_success(self):
        """记录成功"""
        self._consecutive_failures = 0
        if self._state == "HALF_OPEN":
            self._state = "CLOSED"
            self._half_open_requests = 0
            logger.info("Circuit breaker transitioning to CLOSED after success in HALF_OPEN")

    def record_failure(self, error: Optional[str] = None):
        """记录失败"""
        self._consecutive_failures += 1
        self._last_failure_time = time.time()

        if self._state == "HALF_OPEN":
            self._state = "OPEN"
            self._half_open_requests = 0
            logger.warning(f"Circuit breaker transitioning to OPEN after failure in HALF_OPEN: {error}")
        elif self._consecutive_failures >= self.failure_threshold:
            self._state = "OPEN"
            logger.warning(f"Circuit breaker OPEN after {self._consecutive_failures} consecutive failures: {error}")

    @property
    def state(self) -> str:
        """当前状态"""
        return self._state

    @property
    def consecutive_failures(self) -> int:
        """连续失败次数"""
        return self._consecutive_failures

    def reset(self):
        """重置断路器"""
        self._state = "CLOSED"
        self._consecutive_failures = 0
        self._last_failure_time = 0.0
        self._half_open_requests = 0


def is_rate_limit_error(status_code: int, response_body: str = "") -> bool:
    """
    检测是否是限流错误

    常见限流信号：
    - HTTP 429 Too Many Requests
    - HTTP 402 Payment Required（一些中转站用这个表示额度不足）
    - 响应体包含 "rate limit"、"too many requests"、"quota" 等关键词
    """
    if status_code == 429:
        return True
    if status_code == 402:
        return True

    body_lower = response_body.lower() if response_body else ""
    rate_limit_keywords = [
        "rate limit", "rate-limit", "ratelimit",
        "too many requests", "too many",
        "quota exceeded", "quota",
        "insufficient quota",
        "billing", "payment required",
        "429",
    ]
    return any(kw in body_lower for kw in rate_limit_keywords)


def parse_retry_after(response_headers: dict) -> Optional[float]:
    """
    解析 Retry-After 头，返回需要等待的秒数

    Retry-After 可以是：
    - 秒数（如 "120"）
    - HTTP日期（如 "Wed, 21 Oct 2015 07:28:00 GMT"）
    """
    retry_after = response_headers.get("retry-after") or response_headers.get("Retry-After")
    if not retry_after:
        return None

    try:
        # 尝试解析为秒数
        seconds = float(retry_after)
        return min(seconds, 300.0)  # 最多等待5分钟
    except ValueError:
        pass

    try:
        # 尝试解析为HTTP日期
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(retry_after)
        seconds = (dt - datetime.now(dt.tzinfo)).total_seconds()
        return max(0, min(seconds, 300.0))
    except Exception:
        return None


async def retry_with_backoff(
    func: Callable,
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    retry_on_exceptions: tuple = (Exception,),
    circuit_breaker: Optional[CircuitBreaker] = None,
    *args,
    **kwargs,
) -> Any:
    """
    指数退避重试（Exponential Backoff Retry）

    参数：
    - func: 要执行的异步函数
    - max_retries: 最大重试次数（默认3次，即最多执行4次）
    - initial_delay: 初始延迟（秒，默认1秒）
    - max_delay: 最大延迟（秒，默认30秒）
    - backoff_factor: 退避因子（默认2，即每次延迟翻倍）
    - jitter: 是否添加随机抖动（避免惊群效应）
    - retry_on_exceptions: 需要重试的异常类型（默认所有异常）
    - circuit_breaker: 可选的断路器

    返回：
    - 函数执行结果

    抛出：
    - 最后一次失败的异常（如果所有重试都失败）
    """
    stats = RetryStats()
    delay = initial_delay

    for attempt in range(max_retries + 1):
        stats.attempts = attempt + 1

        # 检查断路器
        if circuit_breaker and not circuit_breaker.can_execute():
            logger.warning(f"Circuit breaker is {circuit_breaker.state}, skipping attempt {attempt + 1}")
            raise RuntimeError(f"Circuit breaker is {circuit_breaker.state}, request blocked")

        try:
            result = await func(*args, **kwargs)
            stats.successes += 1

            if circuit_breaker:
                circuit_breaker.record_success()

            if attempt > 0:
                logger.info(f"Success on attempt {attempt + 1} after {stats.total_delay_seconds:.1f}s total delay")

            return result

        except retry_on_exceptions as e:
            stats.failures += 1
            stats.last_error = str(e)

            # 尝试从异常中提取状态码
            status_code = getattr(e, "status_code", None) or getattr(e, "status", None)
            if status_code:
                stats.last_status_code = status_code

            if circuit_breaker:
                circuit_breaker.record_failure(str(e))

            # 如果是最后一次尝试，不再重试
            if attempt >= max_retries:
                logger.error(f"All {max_retries + 1} attempts failed. Last error: {e}")
                raise

            # 检查是否是限流错误，如果是，使用更长的延迟
            if status_code and is_rate_limit_error(status_code):
                # 尝试从响应头获取Retry-After
                response_headers = getattr(e, "headers", {}) or {}
                retry_after = parse_retry_after(response_headers)
                if retry_after:
                    delay = retry_after
                    logger.info(f"Rate limited (429), waiting {delay:.1f}s per Retry-After header")
                else:
                    delay = min(delay * backoff_factor * 2, max_delay * 2)  # 限流时加倍延迟
                    logger.info(f"Rate limited (429), waiting {delay:.1f}s (exponential backoff)")
            else:
                # 普通错误，指数退避
                delay = min(delay * backoff_factor, max_delay)

            # 添加随机抖动（避免惊群效应）
            if jitter:
                import random
                delay = delay * (0.5 + random.random() * 0.5)

            stats.total_delay_seconds += delay

            logger.warning(
                f"Attempt {attempt + 1}/{max_retries + 1} failed: {e}. "
                f"Retrying in {delay:.1f}s..."
            )

            await asyncio.sleep(delay)

    # 理论上不会到达这里
    raise RuntimeError("Unexpected end of retry loop")


def sync_retry_with_backoff(
    func: Callable,
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    retry_on_exceptions: tuple = (Exception,),
    *args,
    **kwargs,
) -> Any:
    """
    同步版本的指数退避重试

    用于不支持async的场景。
    """
    import time as _time
    import random as _random

    delay = initial_delay

    for attempt in range(max_retries + 1):
        try:
            return func(*args, **kwargs)
        except retry_on_exceptions as e:
            if attempt >= max_retries:
                raise

            delay = min(delay * backoff_factor, max_delay)

            if jitter:
                delay = delay * (0.5 + _random.random() * 0.5)

            logger.warning(f"Attempt {attempt + 1}/{max_retries + 1} failed: {e}. Retrying in {delay:.1f}s...")
            _time.sleep(delay)

    raise RuntimeError("Unexpected end of retry loop")


# 全局断路器实例（可用于整个应用）
_global_breaker = CircuitBreaker(failure_threshold=10, recovery_timeout=30.0)


def get_global_breaker() -> CircuitBreaker:
    """获取全局断路器实例"""
    return _global_breaker
