#!/usr/bin/env python3
"""Collect baseline data for model fingerprinting.

Runs probes against a model (local Ollama or OpenAI-compatible API)
and collects tokenizer/behavioral/capability data for statistical analysis.

Usage:
    # Local Ollama model
    python collect_baseline.py --model llama3.1 --samples 500 --output data/baselines/llama3.1.json

    # OpenAI-compatible API
    python collect_baseline.py --model gpt-4o-mini --samples 500 \
        --base-url https://api.openai.com/v1 --api-key sk-xxx \
        --output data/baselines/gpt-4o-mini.json

    # Google Gemini (via OpenAI-compatible endpoint)
    python collect_baseline.py --model gemini-1.5-pro --samples 500 \
        --base-url https://generativelanguage.googleapis.com/v1beta/openai/ \
        --api-key AIza... --output data/baselines/gemini-1.5-pro.json
"""
import argparse
import asyncio
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from app.core.probes import TOKENIZER_PROBES, BEHAVIORAL_PROBES, CAPABILITY_PROBES


async def collect_baseline(
    model: str,
    samples: int,
    base_url: str = "http://localhost:11434/v1",
    api_key: str = "ollama",
    output_path: str = None,
    delay: float = 0.1,
    concurrency: int = 5,
):
    """Collect baseline data for a model.

    Args:
        model: Model name (e.g., "llama3.1", "gpt-4o-mini")
        samples: Number of samples to collect per probe
        base_url: OpenAI-compatible API base URL
        api_key: API key (use "ollama" for local Ollama)
        output_path: Path to save baseline JSON
        delay: Delay between requests in seconds
        concurrency: Number of concurrent requests (default: 5)
    """
    print(f"Collecting baseline for model: {model}")
    print(f"  Base URL: {base_url}")
    print(f"  Samples per probe: {samples}")
    print(f"  Total probes: {len(TOKENIZER_PROBES) + len(BEHAVIORAL_PROBES) + len(CAPABILITY_PROBES)}")
    print(f"  Estimated total requests: {samples * (len(TOKENIZER_PROBES) + len(BEHAVIORAL_PROBES) + len(CAPABILITY_PROBES))}")
    print("=" * 60)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    all_results = {
        "metadata": {
            "model": model,
            "base_url": base_url,
            "samples_per_probe": samples,
            "collected_at": datetime.now().isoformat(),
            "total_requests": 0,
            "failed_requests": 0,
        },
        "tokenizer": {},
        "behavioral": {},
        "capability": {},
        "latency": [],
    }

    start_time = time.time()
    total_requests = 0
    failed_requests = 0

    async with httpx.AsyncClient(timeout=60.0) as client:
        semaphore = asyncio.Semaphore(concurrency)

        async def run_request(messages, max_tokens, temperature):
            """Run a single API request with concurrency control."""
            async with semaphore:
                try:
                    req_start = time.time()
                    response = await client.post(
                        f"{base_url}/chat/completions",
                        headers=headers,
                        json={
                            "model": model,
                            "messages": messages,
                            "max_tokens": max_tokens,
                            "temperature": temperature,
                        },
                    )
                    latency = (time.time() - req_start) * 1000
                    return response, latency, None
                except Exception as e:
                    return None, 0, str(e)

        # ─── Tokenizer Probes ────────────────────────────────────
        print("\n[1/3] Collecting tokenizer probe data...")
        for i, probe in enumerate(TOKENIZER_PROBES):
            print(f"  Probe {i+1}/{len(TOKENIZER_PROBES)}: {probe.id}...", end=" ", flush=True)

            # Run all samples concurrently
            tasks = [
                run_request(
                    [{"role": "user", "content": probe.prompt}],
                    128, 0
                )
                for _ in range(samples)
            ]
            results = await asyncio.gather(*tasks)

            prompt_tokens_list = []
            completion_tokens_list = []
            latencies = []
            responses = []

            for response, latency, error in results:
                total_requests += 1
                if error or response is None or response.status_code != 200:
                    failed_requests += 1
                    continue
                try:
                    data = response.json()
                    usage = data.get("usage", {})
                    prompt_tokens_list.append(usage.get("prompt_tokens", 0))
                    completion_tokens_list.append(usage.get("completion_tokens", 0))
                    latencies.append(latency)
                    try:
                        content = data["choices"][0]["message"]["content"]
                        responses.append(content[:100])
                    except (KeyError, IndexError):
                        responses.append("")
                except Exception:
                    failed_requests += 1

            if prompt_tokens_list:
                all_results["tokenizer"][probe.id] = {
                    "description": probe.description,
                    "prompt_tokens": {
                        "mean": statistics.mean(prompt_tokens_list),
                        "std": statistics.stdev(prompt_tokens_list) if len(prompt_tokens_list) > 1 else 0,
                        "min": min(prompt_tokens_list),
                        "max": max(prompt_tokens_list),
                        "median": statistics.median(prompt_tokens_list),
                        "samples": prompt_tokens_list,
                        "sample_count": len(prompt_tokens_list),
                    },
                    "completion_tokens": {
                        "mean": statistics.mean(completion_tokens_list),
                        "std": statistics.stdev(completion_tokens_list) if len(completion_tokens_list) > 1 else 0,
                        "sample_count": len(completion_tokens_list),
                    },
                    "latency_ms": {
                        "mean": statistics.mean(latencies),
                        "std": statistics.stdev(latencies) if len(latencies) > 1 else 0,
                        "sample_count": len(latencies),
                    },
                    "response_samples": responses[:5],
                }
                all_results["latency"].extend(latencies)
                print(f"✓ mean_prompt_tokens={statistics.mean(prompt_tokens_list):.1f}, n={len(prompt_tokens_list)}")
            else:
                print(f"✗ all requests failed")

        # ─── Behavioral Probes ───────────────────────────────────
        print("\n[2/3] Collecting behavioral probe data...")
        for i, probe in enumerate(BEHAVIORAL_PROBES):
            print(f"  Probe {i+1}/{len(BEHAVIORAL_PROBES)}: {probe.id}...", end=" ", flush=True)

            tasks = [
                run_request(
                    [{"role": "user", "content": probe.prompt}],
                    probe.max_tokens, probe.temperature
                )
                for _ in range(samples)
            ]
            results = await asyncio.gather(*tasks)

            responses = []
            latencies = []

            for response, latency, error in results:
                total_requests += 1
                if error or response is None or response.status_code != 200:
                    failed_requests += 1
                    continue
                try:
                    data = response.json()
                    try:
                        content = data["choices"][0]["message"]["content"].strip()
                        responses.append(content)
                    except (KeyError, IndexError):
                        responses.append("")
                    latencies.append(latency)
                except Exception:
                    failed_requests += 1

            if responses:
                # Count frequency of each response
                from collections import Counter
                counter = Counter(responses)
                all_results["behavioral"][probe.id] = {
                    "description": probe.description,
                    "response_distribution": dict(counter.most_common(20)),
                    "unique_responses": len(counter),
                    "sample_count": len(responses),
                    "latency_ms": {
                        "mean": statistics.mean(latencies) if latencies else 0,
                        "sample_count": len(latencies),
                    },
                }
                all_results["latency"].extend(latencies)
                print(f"✓ unique_responses={len(counter)}, top={counter.most_common(1)[0] if counter else 'N/A'}")
            else:
                print(f"✗ all requests failed")

        # ─── Capability Probes ───────────────────────────────────
        print("\n[3/3] Collecting capability probe data...")
        for i, probe in enumerate(CAPABILITY_PROBES):
            print(f"  Probe {i+1}/{len(CAPABILITY_PROBES)}: {probe.id}...", end=" ", flush=True)

            n_samples = min(samples, 50)  # Capability probes only need 50 samples
            tasks = [
                run_request(
                    [{"role": "user", "content": probe.prompt}],
                    probe.max_tokens, probe.temperature
                )
                for _ in range(n_samples)
            ]
            results = await asyncio.gather(*tasks)

            responses = []
            latencies = []

            for response, latency, error in results:
                total_requests += 1
                if error or response is None or response.status_code != 200:
                    failed_requests += 1
                    continue
                try:
                    data = response.json()
                    try:
                        content = data["choices"][0]["message"]["content"].strip()
                        responses.append(content)
                    except (KeyError, IndexError):
                        responses.append("")
                    latencies.append(latency)
                except Exception:
                    failed_requests += 1

            if responses:
                all_results["capability"][probe.id] = {
                    "description": probe.description,
                    "responses": responses[:10],
                    "sample_count": len(responses),
                    "latency_ms": {
                        "mean": statistics.mean(latencies) if latencies else 0,
                        "sample_count": len(latencies),
                    },
                }
                all_results["latency"].extend(latencies)
                print(f"✓ n={len(responses)}, sample='{responses[0][:40]}...'")
            else:
                print(f"✗ all requests failed")

    # ─── Compute aggregate statistics ───────────────────────────
    elapsed = time.time() - start_time
    all_results["metadata"]["total_requests"] = total_requests
    all_results["metadata"]["failed_requests"] = failed_requests
    all_results["metadata"]["elapsed_seconds"] = round(elapsed, 1)

    if all_results["latency"]:
        all_results["latency_overall"] = {
            "mean": statistics.mean(all_results["latency"]),
            "std": statistics.stdev(all_results["latency"]) if len(all_results["latency"]) > 1 else 0,
            "min": min(all_results["latency"]),
            "max": max(all_results["latency"]),
            "median": statistics.median(all_results["latency"]),
            "p95": sorted(all_results["latency"])[int(len(all_results["latency"]) * 0.95)],
            "sample_count": len(all_results["latency"]),
        }

    # ─── Save results ───────────────────────────────────────────
    if output_path:
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(all_results, f, indent=2, ensure_ascii=False)
        print(f"\n✓ Baseline data saved to: {output_file}")
        print(f"  File size: {output_file.stat().st_size / 1024:.1f} KB")

    # ─── Print summary ──────────────────────────────────────────
    print("\n" + "=" * 60)
    print("COLLECTION SUMMARY")
    print("=" * 60)
    print(f"  Model: {model}")
    print(f"  Total requests: {total_requests}")
    print(f"  Failed requests: {failed_requests} ({failed_requests/max(total_requests,1)*100:.1f}%)")
    print(f"  Elapsed time: {elapsed:.1f}s ({elapsed/60:.1f}min)")
    print(f"  Requests/sec: {total_requests/max(elapsed,1):.1f}")
    if all_results["latency"]:
        print(f"  Avg latency: {statistics.mean(all_results['latency']):.0f}ms")
        print(f"  P95 latency: {all_results['latency_overall']['p95']:.0f}ms")

    return all_results


def main():
    parser = argparse.ArgumentParser(description="Collect baseline data for model fingerprinting")
    parser.add_argument("--model", type=str, required=True, help="Model name (e.g., llama3.1, gpt-4o-mini)")
    parser.add_argument("--samples", type=int, default=500, help="Number of samples per probe (default: 500)")
    parser.add_argument("--base-url", type=str, default="http://localhost:11434/v1",
                        help="OpenAI-compatible API base URL (default: http://localhost:11434/v1)")
    parser.add_argument("--api-key", type=str, default="ollama", help="API key (default: ollama)")
    parser.add_argument("--output", type=str, default=None, help="Output JSON file path")
    parser.add_argument("--delay", type=float, default=0.1, help="Delay between requests in seconds (default: 0.1)")
    parser.add_argument("--concurrency", type=int, default=5, help="Number of concurrent requests (default: 5)")

    args = parser.parse_args()

    # Default output path
    if args.output is None:
        safe_model = args.model.replace("/", "_").replace(":", "_")
        args.output = f"data/baselines/{safe_model}.json"

    asyncio.run(collect_baseline(
        model=args.model,
        samples=args.samples,
        base_url=args.base_url,
        api_key=args.api_key,
        output_path=args.output,
        delay=args.delay,
        concurrency=args.concurrency,
    ))


if __name__ == "__main__":
    main()
