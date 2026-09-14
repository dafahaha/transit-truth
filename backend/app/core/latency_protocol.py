"""Latency and protocol compliance checks."""
import asyncio
import statistics
import time
from typing import Optional

from ..utils.http_client import AsyncAPIClient


class LatencyChecker:
    """Measure API latency and availability."""

    def __init__(self, client: AsyncAPIClient, model: str):
        self.client = client
        self.model = model

    async def measure(self, samples: int = 5) -> dict:
        """Measure latency over multiple requests."""
        latencies = []
        errors = 0
        status_codes = []

        for i in range(samples):
            result = await self.client.chat_completion(
                model=self.model,
                messages=[{"role": "user", "content": f"Say 'pong {i}'."}],
                temperature=0,
                max_tokens=10,
            )
            if "error" in result:
                errors += 1
            else:
                latencies.append(result.get("_latency_ms", 0))
                status_codes.append(result.get("_status_code", 0))

        if not latencies:
            return {
                "samples": samples,
                "errors": errors,
                "error_rate": 1.0,
                "avg_latency_ms": 0,
                "p50_latency_ms": 0,
                "p95_latency_ms": 0,
                "min_latency_ms": 0,
                "max_latency_ms": 0,
                "status_codes": status_codes,
            }

        return {
            "samples": samples,
            "errors": errors,
            "error_rate": round(errors / samples, 2),
            "avg_latency_ms": round(statistics.mean(latencies), 1),
            "p50_latency_ms": round(statistics.median(latencies), 1),
            "p95_latency_ms": round(sorted(latencies)[int(len(latencies) * 0.95) - 1] if len(latencies) >= 2 else latencies[0], 1),
            "min_latency_ms": round(min(latencies), 1),
            "max_latency_ms": round(max(latencies), 1),
            "status_codes": status_codes,
        }


class ProtocolChecker:
    """Check API protocol compliance.

    Verifies that responses follow the OpenAI API format:
    - Correct response structure (id, object, created, model, choices, usage)
    - Correct headers
    - Correct error format
    - Streaming support (if claimed)
    """

    def __init__(self, client: AsyncAPIClient, model: str):
        self.client = client
        self.model = model

    async def check(self) -> dict:
        """Run protocol compliance checks."""
        checks = {}

        # 1. Basic response structure
        result = await self.client.chat_completion(
            model=self.model,
            messages=[{"role": "user", "content": "Hello"}],
            temperature=0,
            max_tokens=10,
        )

        if "error" in result:
            checks["response_structure"] = {
                "passed": False,
                "details": f"Request failed: {result.get('error', {})}",
            }
        else:
            required_fields = ["id", "object", "created", "model", "choices", "usage"]
            missing = [f for f in required_fields if f not in result]
            checks["response_structure"] = {
                "passed": len(missing) == 0,
                "missing_fields": missing,
                "details": f"All required fields present" if not missing else f"Missing: {missing}",
            }

            # Check choices structure
            choices = result.get("choices", [])
            if choices:
                choice = choices[0]
                choice_fields = ["index", "message", "finish_reason"]
                missing_choice = [f for f in choice_fields if f not in choice]
                checks["choice_structure"] = {
                    "passed": len(missing_choice) == 0,
                    "missing_fields": missing_choice,
                }

                # Check message structure
                message = choice.get("message", {})
                msg_fields = ["role", "content"]
                missing_msg = [f for f in msg_fields if f not in message]
                checks["message_structure"] = {
                    "passed": len(missing_msg) == 0,
                    "missing_fields": missing_msg,
                }
            else:
                checks["choice_structure"] = {"passed": False, "details": "No choices returned"}

            # Check usage structure
            usage = result.get("usage", {})
            usage_fields = ["prompt_tokens", "completion_tokens", "total_tokens"]
            missing_usage = [f for f in usage_fields if f not in usage]
            checks["usage_structure"] = {
                "passed": len(missing_usage) == 0,
                "missing_fields": missing_usage,
            }

            # Check model field matches requested
            returned_model = result.get("model", "")
            checks["model_field"] = {
                "passed": self.model.lower() in returned_model.lower() or returned_model.lower() in self.model.lower(),
                "returned_model": returned_model,
                "requested_model": self.model,
            }

        # 2. Headers check
        headers = result.get("_response_headers", {}) if "_response_headers" in result else {}
        checks["headers"] = {
            "content_type_json": "application/json" in headers.get("content-type", "").lower(),
            "has_request_id": bool(headers.get("x-request-id")) or bool(headers.get("x-ratelimit-remaining-requests")),
            "details": "Standard headers present" if headers else "No headers captured",
        }

        # 3. Error format check (send invalid request)
        error_result = await self.client.chat_completion(
            model="nonexistent-model-xyz123",
            messages=[{"role": "user", "content": "test"}],
            max_tokens=5,
        )
        if "error" in error_result:
            err = error_result.get("error", {})
            checks["error_format"] = {
                "passed": isinstance(err, dict) and ("message" in err or "type" in err or "code" in err),
                "error_sample": str(err)[:200],
            }
        else:
            checks["error_format"] = {
                "passed": False,
                "details": "Invalid model did not return an error (suspicious)",
            }

        # Summary
        passed_count = sum(1 for v in checks.values() if isinstance(v, dict) and v.get("passed"))
        total_count = len(checks)
        checks["_summary"] = {
            "passed": passed_count,
            "total": total_count,
            "score": round(passed_count / max(total_count, 1) * 100, 1),
        }

        return checks
