"""Benchmark data collector.

Collects model fingerprint benchmark data from an API endpoint.
This data can be used for:
1. Comparing against relay services to detect model downgrades
2. Academic research (publishable dataset)
3. Continuously updating the model fingerprint database
"""
import asyncio
import statistics
from collections import Counter
from datetime import datetime
from typing import Optional

from .probes import TOKENIZER_PROBES, BEHAVIORAL_PROBES, CAPABILITY_PROBES, Probe
from ..utils.http_client import AsyncAPIClient


async def collect_benchmark(
    api_key: str,
    base_url: str,
    model: str,
    samples: int = 5,
    timeout: int = 30,
) -> dict:
    """Collect benchmark data for a model.

    Args:
        api_key: API key for the endpoint
        base_url: Base URL of the API
        model: Model name
        samples: Number of samples per behavioral probe
        timeout: Request timeout in seconds

    Returns:
        Structured benchmark data dictionary
    """
    result = {
        "model": model,
        "base_url": base_url,
        "collected_at": datetime.now().isoformat(),
        "samples_per_behavioral_probe": samples,
        "tokenizer": {},
        "behavioral": {},
        "capability": {},
    }

    async with AsyncAPIClient(api_key, base_url, timeout=timeout) as client:
        # 1. Tokenizer probes
        print(f"  Collecting {len(TOKENIZER_PROBES)} tokenizer probes...")
        tokenizer_tasks = [_run_tokenizer_probe(client, model, p) for p in TOKENIZER_PROBES]
        tokenizer_results = await asyncio.gather(*tokenizer_tasks)
        for probe_id, data in tokenizer_results:
            result["tokenizer"][probe_id] = data

        # 2. Behavioral probes (multiple samples each)
        print(f"  Collecting {len(BEHAVIORAL_PROBES)} behavioral probes x {samples} samples...")
        behavioral_tasks = [_run_behavioral_probe(client, model, p, samples) for p in BEHAVIORAL_PROBES]
        behavioral_results = await asyncio.gather(*behavioral_tasks)
        for probe_id, data in behavioral_results:
            result["behavioral"][probe_id] = data

        # 3. Capability probes
        print(f"  Collecting {len(CAPABILITY_PROBES)} capability probes...")
        capability_tasks = [_run_capability_probe(client, model, p) for p in CAPABILITY_PROBES]
        capability_results = await asyncio.gather(*capability_tasks)
        for probe_id, data in capability_results:
            result["capability"][probe_id] = data

    # Compute summary statistics
    result["summary"] = _compute_summary(result)
    print(f"  ✅ Benchmark collection complete")
    return result


async def _run_tokenizer_probe(client: AsyncAPIClient, model: str, probe: Probe) -> tuple[str, dict]:
    """Run a single tokenizer probe."""
    response = await client.chat_completion(
        model=model,
        messages=[{"role": "user", "content": probe.prompt}],
        temperature=0,
        max_tokens=128,
    )

    if "error" in response:
        return probe.id, {"error": str(response["error"])[:200]}

    usage = response.get("usage", {})
    content = ""
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        pass

    return probe.id, {
        "prompt": probe.prompt[:100],
        "description": probe.description,
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
        "latency_ms": round(response.get("_latency_ms", 0), 1),
        "response_preview": content[:80],
        "expected_tokens_range": list(probe.expected_tokens_range) if probe.expected_tokens_range else None,
    }


async def _run_behavioral_probe(
    client: AsyncAPIClient, model: str, probe: Probe, samples: int
) -> tuple[str, dict]:
    """Run a behavioral probe with multiple samples."""
    responses = []
    latencies = []

    for _ in range(samples):
        response = await client.chat_completion(
            model=model,
            messages=[{"role": "user", "content": probe.prompt}],
            temperature=probe.temperature,
            max_tokens=probe.max_tokens,
        )
        if "error" not in response:
            try:
                content = response["choices"][0]["message"]["content"].strip()
                responses.append(content)
                latencies.append(response.get("_latency_ms", 0))
            except (KeyError, IndexError):
                pass

    if not responses:
        return probe.id, {"error": "all requests failed"}

    counter = Counter(responses)
    distribution = dict(counter.most_common(10))

    return probe.id, {
        "prompt": probe.prompt[:100],
        "description": probe.description,
        "sample_count": len(responses),
        "unique_responses": len(counter),
        "distribution": distribution,
        "all_responses": responses,
        "avg_latency_ms": round(statistics.mean(latencies), 1) if latencies else 0,
        "diversity_score": round(len(counter) / max(len(responses), 1), 3),
    }


async def _run_capability_probe(client: AsyncAPIClient, model: str, probe: Probe) -> tuple[str, dict]:
    """Run a capability probe."""
    response = await client.chat_completion(
        model=model,
        messages=[{"role": "user", "content": probe.prompt}],
        temperature=probe.temperature,
        max_tokens=probe.max_tokens,
    )

    if "error" in response:
        return probe.id, {"error": str(response["error"])[:200]}

    try:
        content = response["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError):
        content = ""

    # Simple expected answer checking
    expected = {
        "cap-simple-math": {"391"},
        "cap-logic": {"no"},
        "cap-following-instructions": {"1,2,4,5", "1, 2, 4, 5"},
    }
    passed = content.lower() in expected.get(probe.id, set())

    return probe.id, {
        "prompt": probe.prompt[:100],
        "description": probe.description,
        "response": content[:100],
        "passed": passed,
        "latency_ms": round(response.get("_latency_ms", 0), 1),
    }


def _compute_summary(data: dict) -> dict:
    """Compute summary statistics from benchmark data."""
    # Tokenizer summary
    tokenizer_data = data.get("tokenizer", {})
    valid_tokenizer = {k: v for k, v in tokenizer_data.items() if "error" not in v}
    avg_prompt_tokens = (
        statistics.mean([v["prompt_tokens"] for v in valid_tokenizer.values()])
        if valid_tokenizer else 0
    )
    avg_latency_tokenizer = (
        statistics.mean([v["latency_ms"] for v in valid_tokenizer.values()])
        if valid_tokenizer else 0
    )

    # Behavioral summary
    behavioral_data = data.get("behavioral", {})
    valid_behavioral = {k: v for k, v in behavioral_data.items() if "error" not in v}
    avg_diversity = (
        statistics.mean([v["diversity_score"] for v in valid_behavioral.values()])
        if valid_behavioral else 0
    )

    # Capability summary
    capability_data = data.get("capability", {})
    valid_capability = {k: v for k, v in capability_data.items() if "error" not in v}
    pass_rate = (
        sum(1 for v in valid_capability.values() if v.get("passed")) / max(len(valid_capability), 1)
        if valid_capability else 0
    )

    return {
        "tokenizer_probes_collected": len(valid_tokenizer),
        "behavioral_probes_collected": len(valid_behavioral),
        "capability_probes_collected": len(valid_capability),
        "avg_prompt_tokens": round(avg_prompt_tokens, 1),
        "avg_latency_tokenizer_ms": round(avg_latency_tokenizer, 1),
        "avg_behavioral_diversity": round(avg_diversity, 3),
        "capability_pass_rate": round(pass_rate, 2),
    }
