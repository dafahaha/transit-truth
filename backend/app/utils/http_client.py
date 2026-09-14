"""Async HTTP client for API calls."""
import asyncio
import logging
import time
from typing import Optional

import httpx

from ..config import REQUEST_TIMEOUT, MAX_RETRIES

logger = logging.getLogger(__name__)


class AsyncAPIClient:
    """Async client for OpenAI-compatible APIs with exponential backoff retry."""

    def __init__(self, api_key: str, base_url: str, timeout: int = REQUEST_TIMEOUT):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        # 统计信息
        self._stats = {
            "total_requests": 0,
            "successful": 0,
            "failed": 0,
            "retries": 0,
            "rate_limited": 0,
            "timeouts": 0,
        }

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            timeout=self.timeout,
            headers=self._default_headers(),
        )
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()
            self._client = None

    def _default_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _is_retryable_status(self, status_code: int) -> bool:
        """判断状态码是否可重试"""
        return status_code in (429, 500, 502, 503, 504)

    def _is_rate_limit(self, status_code: int, body: str = "") -> bool:
        """判断是否是限流错误"""
        if status_code == 429:
            return True
        if status_code == 402:
            return True
        body_lower = body.lower() if body else ""
        return any(kw in body_lower for kw in [
            "rate limit", "too many requests", "quota",
            "insufficient quota", "billing", "429",
        ])

    def _parse_retry_after(self, headers: dict) -> Optional[float]:
        """解析Retry-After头"""
        retry_after = headers.get("retry-after") or headers.get("Retry-After")
        if not retry_after:
            return None
        try:
            seconds = float(retry_after)
            return min(seconds, 300.0)
        except ValueError:
            return None

    async def _calculate_delay(self, attempt: int, status_code: int, headers: dict) -> float:
        """
        计算重试延迟（指数退避 + 限流检测 + 随机抖动）

        - 普通错误：1s, 2s, 4s, 8s...（指数退避）
        - 限流错误：使用Retry-After头，或加倍延迟
        - 添加随机抖动（0.5-1.0倍），避免惊群效应
        """
        import random

        base_delay = min(1.0 * (2 ** attempt), 30.0)  # 指数退避，最大30秒

        if self._is_rate_limit(status_code):
            self._stats["rate_limited"] += 1
            retry_after = self._parse_retry_after(headers)
            if retry_after:
                logger.info(f"Rate limited (429), waiting {retry_after:.1f}s per Retry-After header")
                return retry_after
            base_delay = min(base_delay * 2, 60.0)  # 限流时加倍延迟
            logger.info(f"Rate limited (429), waiting {base_delay:.1f}s (exponential backoff)")

        # 添加随机抖动（0.5-1.0倍）
        jitter = 0.5 + random.random() * 0.5
        return base_delay * jitter

    async def chat_completion(
        self,
        model: str,
        messages: list[dict],
        temperature: float = 0.0,
        max_tokens: int = 64,
        stream: bool = False,
    ) -> dict:
        """Send a chat completion request with exponential backoff retry."""
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }

        self._stats["total_requests"] += 1
        last_error = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                start = time.perf_counter()
                response = await self._client.post(url, json=payload)
                latency_ms = (time.perf_counter() - start) * 1000

                if response.status_code == 200:
                    data = response.json()
                    data["_latency_ms"] = latency_ms
                    data["_status_code"] = 200
                    data["_response_headers"] = dict(response.headers)
                    data["_attempts"] = attempt + 1
                    self._stats["successful"] += 1
                    if attempt > 0:
                        self._stats["retries"] += attempt
                        logger.info(f"Success on attempt {attempt + 1} for model={model}")
                    return data
                else:
                    last_error = {
                        "status_code": response.status_code,
                        "body": response.text[:500],
                        "latency_ms": latency_ms,
                    }

                    # 不可重试的错误（401、400、404等）
                    if not self._is_retryable_status(response.status_code):
                        logger.warning(f"Non-retryable error {response.status_code} for model={model}: {response.text[:100]}")
                        self._stats["failed"] += 1
                        return {
                            "error": last_error,
                            "_latency_ms": latency_ms,
                            "_status_code": response.status_code,
                            "_response_headers": dict(response.headers),
                            "_attempts": attempt + 1,
                        }

                    # 可重试的错误
                    if attempt < MAX_RETRIES:
                        delay = await self._calculate_delay(attempt, response.status_code, dict(response.headers))
                        logger.warning(
                            f"Attempt {attempt + 1}/{MAX_RETRIES + 1} failed for model={model}: "
                            f"status={response.status_code}, retrying in {delay:.1f}s..."
                        )
                        await asyncio.sleep(delay)
                        continue
                    else:
                        logger.error(f"All {MAX_RETRIES + 1} attempts failed for model={model}: {response.status_code}")
                        self._stats["failed"] += 1
                        return {"error": last_error or {"error": "max_retries_exceeded"}}

            except httpx.TimeoutException as e:
                self._stats["timeouts"] += 1
                last_error = {"error": "timeout", "message": str(e)}
                if attempt < MAX_RETRIES:
                    delay = min(1.0 * (2 ** attempt), 10.0)
                    logger.warning(f"Timeout on attempt {attempt + 1} for model={model}, retrying in {delay:.1f}s...")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"All attempts timed out for model={model}")
                    self._stats["failed"] += 1

            except httpx.RequestError as e:
                last_error = {"error": "request_error", "message": str(e)}
                if attempt < MAX_RETRIES:
                    delay = min(1.0 * (2 ** attempt), 10.0)
                    logger.warning(f"Request error on attempt {attempt + 1} for model={model}: {e}, retrying in {delay:.1f}s...")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"All attempts failed with request error for model={model}: {e}")
                    self._stats["failed"] += 1

        return {"error": last_error or {"error": "unknown"}}

    async def check_availability(self, model: str = "gpt-3.5-turbo") -> dict:
        """Quick check if the API is available."""
        return await self.chat_completion(
            model=model,
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=5,
            temperature=0,
        )

    @property
    def stats(self) -> dict:
        """获取请求统计信息"""
        return self._stats.copy()
