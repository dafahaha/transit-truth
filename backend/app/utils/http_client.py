"""Async HTTP client for API calls."""
import asyncio
import time
from typing import Optional

import httpx

from ..config import REQUEST_TIMEOUT, MAX_RETRIES


class AsyncAPIClient:
    """Async client for OpenAI-compatible APIs."""

    def __init__(self, api_key: str, base_url: str, timeout: int = REQUEST_TIMEOUT):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

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

    async def chat_completion(
        self,
        model: str,
        messages: list[dict],
        temperature: float = 1.0,
        max_tokens: int = 64,
        stream: bool = False,
    ) -> dict:
        """Send a chat completion request with retries."""
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }

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
                    return data
                else:
                    last_error = {
                        "status_code": response.status_code,
                        "body": response.text[:500],
                        "latency_ms": latency_ms,
                    }
                    if response.status_code in (429, 500, 502, 503, 504):
                        await asyncio.sleep(1 * (attempt + 1))
                        continue
                    # Don't retry auth errors or bad requests
                    return {
                        "error": last_error,
                        "_latency_ms": latency_ms,
                        "_status_code": response.status_code,
                        "_response_headers": dict(response.headers),
                    }
            except httpx.TimeoutException as e:
                last_error = {"error": "timeout", "message": str(e)}
                await asyncio.sleep(1)
            except httpx.RequestError as e:
                last_error = {"error": "request_error", "message": str(e)}
                await asyncio.sleep(1)

        return {"error": last_error or {"error": "unknown"}}

    async def check_availability(self, model: str = "gpt-3.5-turbo") -> dict:
        """Quick check if the API is available."""
        return await self.chat_completion(
            model=model,
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=5,
            temperature=0,
        )
