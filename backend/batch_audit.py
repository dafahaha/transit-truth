"""Batch audit script for academic data collection.

Audits multiple relay/model combinations and outputs structured JSON
for research purposes. Designed for collecting benchmark data on
LLM API proxy trustworthiness.

Usage:
    python batch_audit.py --config config.json --output results.json
    python batch_audit.py --relays relays.json --models gpt-4o,gpt-4o-mini

Config format (JSON):
{
    "relays": [
        {"name": "wolfai", "base_url": "https://wolfai.top/v1", "api_key": "sk-xxx"},
        {"name": "official", "base_url": "https://api.openai.com/v1", "api_key": "sk-xxx"}
    ],
    "models": ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"],
    "probe_count": 5,
    "delay_between_audits": 5
}
"""
import argparse
import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.core.auditor import AuditEngine
from app.models import AuditRequest, AuditMode


async def run_batch_audit(config: dict, output_path: str) -> dict:
    """Run batch audit across multiple relays and models."""
    engine = AuditEngine()
    results = []
    errors = []

    relays = config.get("relays", [])
    models = config.get("models", [])
    probe_count = config.get("probe_count", 5)
    delay = config.get("delay_between_audits", 5)

    total = len(relays) * len(models)
    current = 0

    print(f"Starting batch audit: {len(relays)} relays x {len(models)} models = {total} audits")
    print(f"Probe count: {probe_count}, Delay: {delay}s")
    print("=" * 70)

    for relay in relays:
        for model in models:
            current += 1
            relay_name = relay.get("name", relay["base_url"])
            print(f"[{current}/{total}] Auditing {relay_name} / {model}...", end=" ", flush=True)

            try:
                request = AuditRequest(
                    api_key=relay["api_key"],
                    base_url=relay["base_url"],
                    model=model,
                    mode=AuditMode.QUICK,
                    probe_count=probe_count,
                )
                result = await engine.run_audit(request)

                if result.status == "completed":
                    results.append({
                        "relay": relay_name,
                        "base_url": relay["base_url"],
                        "model": model,
                        "overall_score": result.overall_score,
                        "trust_level": result.trust_level,
                        "token_comparison": result.token_comparison.model_dump() if result.token_comparison else None,
                        "fingerprint": {
                            "claimed_model": result.fingerprint.claimed_model if result.fingerprint else None,
                            "detected_family": result.fingerprint.detected_family if result.fingerprint else None,
                            "family_match": result.fingerprint.family_match if result.fingerprint else None,
                            "confidence": result.fingerprint.confidence if result.fingerprint else None,
                        } if result.fingerprint else None,
                        "checks": [
                            {
                                "check_type": c.check_type,
                                "score": c.score,
                                "passed": c.passed,
                                "details": c.details,
                            }
                            for c in result.checks
                        ],
                        "audit_id": result.audit_id,
                        "timestamp": datetime.now().isoformat(),
                    })
                    print(f"✓ Score: {result.overall_score}/100 ({result.trust_level})")
                else:
                    error_msg = result.error or "Unknown error"
                    errors.append({
                        "relay": relay_name,
                        "model": model,
                        "error": error_msg,
                    })
                    print(f"✗ Failed: {error_msg[:80]}")

            except Exception as e:
                errors.append({
                    "relay": relay_name,
                    "model": model,
                    "error": str(e),
                })
                print(f"✗ Exception: {str(e)[:80]}")

            # Delay between audits to avoid rate limiting
            if current < total:
                await asyncio.sleep(delay)

    print("=" * 70)
    print(f"Batch audit complete: {len(results)} successful, {len(errors)} failed")

    # Generate summary statistics
    summary = generate_summary(results)

    output = {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "total_audits": total,
            "successful": len(results),
            "failed": len(errors),
            "config": config,
        },
        "summary": summary,
        "results": results,
        "errors": errors,
    }

    # Save to file
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"Results saved to: {output_path}")

    return output


def generate_summary(results: list[dict]) -> dict:
    """Generate summary statistics from batch audit results."""
    if not results:
        return {"error": "no results"}

    scores = [r["overall_score"] for r in results]
    token_inflations = [
        r["token_comparison"]["prompt_inflation_pct"]
        for r in results
        if r.get("token_comparison") and r["token_comparison"].get("prompt_inflation_pct") is not None
    ]

    # Group by relay
    by_relay = {}
    for r in results:
        relay = r["relay"]
        if relay not in by_relay:
            by_relay[relay] = []
        by_relay[relay].append(r)

    relay_stats = {}
    for relay, relay_results in by_relay.items():
        relay_scores = [r["overall_score"] for r in relay_results]
        relay_stats[relay] = {
            "count": len(relay_results),
            "avg_score": round(sum(relay_scores) / len(relay_scores), 1),
            "min_score": min(relay_scores),
            "max_score": max(relay_scores),
            "models_tested": [r["model"] for r in relay_results],
        }

    return {
        "total_audits": len(results),
        "avg_score": round(sum(scores) / len(scores), 1),
        "median_score": sorted(scores)[len(scores) // 2],
        "min_score": min(scores),
        "max_score": max(scores),
        "avg_token_inflation": round(sum(token_inflations) / len(token_inflations), 1) if token_inflations else None,
        "trust_level_distribution": {
            level: sum(1 for r in results if r["trust_level"] == level)
            for level in ["high", "medium", "low", "critical"]
        },
        "by_relay": relay_stats,
    }


def main():
    parser = argparse.ArgumentParser(description="Batch audit multiple LLM API relays")
    parser.add_argument("--config", type=str, help="Path to config JSON file")
    parser.add_argument("--output", type=str, default="batch_audit_results.json", help="Output JSON file path")
    parser.add_argument("--relays", type=str, help="Path to relays JSON file")
    parser.add_argument("--models", type=str, help="Comma-separated list of models")
    parser.add_argument("--probe-count", type=int, default=5, help="Number of probes per audit")
    parser.add_argument("--delay", type=int, default=5, help="Delay between audits in seconds")

    args = parser.parse_args()

    # Load config
    if args.config:
        with open(args.config, "r", encoding="utf-8") as f:
            config = json.load(f)
    elif args.relays:
        with open(args.relays, "r", encoding="utf-8") as f:
            relays = json.load(f)
        config = {
            "relays": relays,
            "models": args.models.split(",") if args.models else ["gpt-4o"],
            "probe_count": args.probe_count,
            "delay_between_audits": args.delay,
        }
    else:
        print("Error: Please provide --config or --relays")
        parser.print_help()
        sys.exit(1)

    # Run batch audit
    asyncio.run(run_batch_audit(config, args.output))


if __name__ == "__main__":
    main()
