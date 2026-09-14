"""Relay detection and model discovery.

Auto-detect base URL from API key format and known relay list,
and fetch supported models from the relay's /models endpoint.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

import httpx


@dataclass
class KnownRelay:
    """A known AI API relay service."""
    name: str
    base_url: str
    key_prefix: str  # API key prefix pattern
    notes: str = ""


# Known relay services - base URLs and key prefix patterns
KNOWN_RELAYS: list[KnownRelay] = [
    KnownRelay(
        name="WolfAI",
        base_url="https://wolfai.top/v1",
        key_prefix="sk-",
        notes="国内主流中转站，支持多模型",
    ),
    KnownRelay(
        name="OpenAI Official",
        base_url="https://api.openai.com/v1",
        key_prefix="sk-proj-",
        notes="OpenAI官方API",
    ),
    KnownRelay(
        name="OpenAI Official (legacy)",
        base_url="https://api.openai.com/v1",
        key_prefix="sk-",
        notes="OpenAI官方API (legacy key format)",
    ),
    KnownRelay(
        name="Azure OpenAI",
        base_url="https://*.openai.azure.com",
        key_prefix="",
        notes="Azure OpenAI服务",
    ),
    KnownRelay(
        name="DeepSeek",
        base_url="https://api.deepseek.com/v1",
        key_prefix="sk-",
        notes="DeepSeek官方API",
    ),
    KnownRelay(
        name="Zhipu AI (GLM)",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        key_prefix="",
        notes="智谱AI官方API",
    ),
    KnownRelay(
        name="Moonshot (Kimi)",
        base_url="https://api.moonshot.cn/v1",
        key_prefix="sk-",
        notes="月之暗面Kimi官方API",
    ),
    KnownRelay(
        name="Qwen (DashScope)",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        key_prefix="sk-",
        notes="阿里通义千问官方API",
    ),
    KnownRelay(
        name="SiliconFlow",
        base_url="https://api.siliconflow.cn/v1",
        key_prefix="sk-",
        notes="硅基流动API",
    ),
    KnownRelay(
        name="Together AI",
        base_url="https://api.together.xyz/v1",
        key_prefix="",
        notes="Together AI官方API",
    ),
    KnownRelay(
        name="Groq",
        base_url="https://api.groq.com/openai/v1",
        key_prefix="gsk_",
        notes="Groq官方API",
    ),
    KnownRelay(
        name="Mistral",
        base_url="https://api.mistral.ai/v1",
        key_prefix="",
        notes="Mistral官方API",
    ),
    KnownRelay(
        name="Cohere",
        base_url="https://api.cohere.com/v1",
        key_prefix="",
        notes="Cohere官方API",
    ),
    KnownRelay(
        name="Anthropic (Claude)",
        base_url="https://api.anthropic.com/v1",
        key_prefix="sk-ant-",
        notes="Anthropic官方API (非OpenAI兼容)",
    ),
    KnownRelay(
        name="Google (Gemini)",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        key_prefix="AIza",
        notes="Google Gemini官方API (非OpenAI兼容)",
    ),
]

# Common relay base URL patterns for auto-detection
COMMON_RELAY_PATTERNS: list[tuple[str, str]] = [
    (r"wolfai", "https://wolfai.top/v1"),
    (r"api2d", "https://openai.api2d.net/v1"),
    (r"closeai", "https://api.closeai-asia.com/v1"),
    (r"ohmygpt", "https://api.ohmygpt.com/v1"),
    (r"aigc", "https://api.aigc369.com/v1"),
    (r"chatanywhere", "https://api.chatanywhere.tech/v1"),
    (r"geekgpt", "https://ai.fakeopen.com/v1"),
    (r"openai-sb", "https://api.openai-sb.com/v1"),
    (r"aidp", "https://api.aidp.cloud/v1"),
    (r"oneapi", "https://api.oneapi.dev/v1"),
    (r"newapi", "https://api.newapi.ai/v1"),
]


def detect_base_url(api_key: str) -> Optional[str]:
    """Auto-detect base URL from API key format.

    Returns the most likely base URL, or None if cannot determine.
    """
    if not api_key:
        return None

    # Check key prefix patterns
    for relay in KNOWN_RELAYS:
        if relay.key_prefix and api_key.startswith(relay.key_prefix):
            # For generic "sk-" prefix, return WolfAI as default guess
            # but mark as uncertain
            if relay.key_prefix == "sk-" and relay.name == "OpenAI Official (legacy)":
                continue
            return relay.base_url

    # Default guess for unknown "sk-" keys: try common relays
    if api_key.startswith("sk-"):
        return "https://wolfai.top/v1"  # Most common default

    return None


def suggest_relays(api_key: str) -> list[dict]:
    """Suggest likely relay services based on API key format.

    Returns list of {name, base_url, confidence} sorted by confidence.
    """
    suggestions = []

    for relay in KNOWN_RELAYS:
        confidence = 0.0
        if relay.key_prefix and api_key.startswith(relay.key_prefix):
            confidence = 0.9 if relay.key_prefix != "sk-" else 0.3
        elif not relay.key_prefix:
            confidence = 0.1

        if confidence > 0:
            suggestions.append({
                "name": relay.name,
                "base_url": relay.base_url,
                "confidence": confidence,
                "notes": relay.notes,
            })

    # Sort by confidence descending
    suggestions.sort(key=lambda x: x["confidence"], reverse=True)
    return suggestions[:5]  # Top 5


async def fetch_models(base_url: str, api_key: str, timeout: float = 10.0) -> list[str]:
    """Fetch supported models from the relay's /models endpoint.

    Returns list of model IDs, or empty list if endpoint not available.
    """
    if not base_url or not api_key:
        return []

    # Normalize base URL (remove trailing slash)
    url = base_url.rstrip("/") + "/models"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, headers=headers)
            if response.status_code == 200:
                data = response.json()
                models = data.get("data", [])
                # Extract model IDs
                model_ids = []
                for m in models:
                    if isinstance(m, dict):
                        mid = m.get("id") or m.get("model") or m.get("name")
                        if mid:
                            model_ids.append(str(mid))
                    elif isinstance(m, str):
                        model_ids.append(m)
                return sorted(model_ids)
            return []
    except Exception:
        return []


async def detect_and_suggest(api_key: str, base_url: str = None) -> dict:
    """Combined detection: suggest base URL and fetch models.

    Returns {
        "detected_base_url": str or None,
        "suggestions": [...],
        "models": [...],  # Only if base_url provided and /models works
        "base_url_working": bool,
    }
    """
    result = {
        "detected_base_url": detect_base_url(api_key),
        "suggestions": suggest_relays(api_key),
        "models": [],
        "base_url_working": False,
    }

    # If base_url provided, try to fetch models
    if base_url:
        models = await fetch_models(base_url, api_key)
        result["models"] = models
        result["base_url_working"] = len(models) > 0

    return result
