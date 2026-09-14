#!/usr/bin/env python3
"""TransitTruth CLI - Command-line interface for AI API relay auditing.

Quick mode (one command):
    transit-truth sk-xxx                          # Auto-detect base URL, use gpt-4o
    transit-truth sk-xxx --model gpt-4o-mini     # Specify model
    transit-truth sk-xxx --base-url https://...   # Specify base URL

Full mode:
    transit-truth audit --api-key sk-xxx --base-url https://api.example.com/v1 --model gpt-4o
    transit-truth list
    transit-truth export --audit-id abc123 --output report.html
    transit-truth benchmark --api-key sk-xxx --model gpt-4o --output benchmark.json

Environment variables:
    TRANSIT_TRUTH_API_KEY    Default API key
    TRANSIT_TRUTH_BASE_URL   Default base URL
    TRANSIT_TRUTH_MODEL      Default model
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from .config import BASE_DIR
from .core.auditor import AuditEngine
from .models import AuditRequest, AuditStatus
from .database import list_audits, get_audit
from .utils.report_generator import generate_html_report


# ─── Known Relay Base URLs for auto-detection ───────────────────────
KNOWN_RELAYS = [
    {"name": "OpenAI Official", "base_url": "https://api.openai.com/v1", "pattern": "api.openai.com"},
    {"name": "WolfAI", "base_url": "https://wolfai.top/v1", "pattern": "wolfai.top"},
    {"name": "API2D", "base_url": "https://openai.api2d.net/v1", "pattern": "api2d.net"},
    {"name": "OhMyGPT", "base_url": "https://api.ohmygpt.com/v1", "pattern": "ohmygpt.com"},
    {"name": "AIHubMix", "base_url": "https://aihubmix.com/v1", "pattern": "aihubmix.com"},
    {"name": "CloseAI", "base_url": "https://api.closeai-asia.com/v1", "pattern": "closeai"},
]

# ─── Color output helpers ────────────────────────────────────────────
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    GRAY = "\033[90m"

    @staticmethod
    def color(text, color):
        if os.name == "nt":  # Windows
            return text
        return f"{color}{text}{Colors.RESET}"

    @staticmethod
    def bold(text):
        return Colors.color(text, Colors.BOLD)

    @staticmethod
    def green(text):
        return Colors.color(text, Colors.GREEN)

    @staticmethod
    def red(text):
        return Colors.color(text, Colors.RED)

    @staticmethod
    def yellow(text):
        return Colors.color(text, Colors.YELLOW)

    @staticmethod
    def blue(text):
        return Colors.color(text, Colors.BLUE)

    @staticmethod
    def cyan(text):
        return Colors.color(text, Colors.CYAN)

    @staticmethod
    def gray(text):
        return Colors.color(text, Colors.GRAY)


def detect_base_url(api_key: str) -> tuple[str, str]:
    """Auto-detect base URL from API key or environment.

    Returns (base_url, relay_name).
    """
    # Check environment variable first
    env_url = os.environ.get("TRANSIT_TRUTH_BASE_URL")
    if env_url:
        return env_url, "Environment"

    # Try to detect from API key prefix (some relays use distinct prefixes)
    # Most relays use sk- prefix, so we can't detect from key alone.
    # Default to OpenAI official for now.
    return "https://api.openai.com/v1", "OpenAI Official (default)"


def print_banner():
    """Print the TransitTruth banner."""
    banner = f"""
{Colors.cyan('╔══════════════════════════════════════════════════════════╗')}
{Colors.cyan('║')}  {Colors.bold('🔍 TransitTruth')} - AI API Relay Audit Tool          {Colors.cyan('║')}
{Colors.cyan('╚══════════════════════════════════════════════════════════╝')}
"""
    print(banner)


def cmd_audit(args):
    """Run an audit."""
    request = AuditRequest(
        api_key=args.api_key,
        base_url=args.base_url,
        model=args.model,
        official_api_key=args.official_key,
        probe_count=args.probes,
        run_token_check=not args.skip_token,
        run_fingerprint=not args.skip_fingerprint,
        run_latency=not args.skip_latency,
        run_protocol=not args.skip_protocol,
    )

    print(f"🔍 Starting audit of {args.model} at {args.base_url}")
    print(f"   Probes: {args.probes} | Token: {'on' if not args.skip_token else 'off'} | "
          f"Fingerprint: {'on' if not args.skip_fingerprint else 'off'} | "
          f"Latency: {'on' if not args.skip_latency else 'off'} | "
          f"Protocol: {'on' if not args.skip_protocol else 'off'}")
    print()

    engine = AuditEngine()
    result = asyncio.run(engine.run_audit(request))

    if result.status == AuditStatus.FAILED:
        print(f"❌ Audit failed: {result.error}")
        sys.exit(1)

    # Print summary
    print(f"{'='*60}")
    print(f"✅ Audit completed | ID: {result.audit_id}")
    print(f"{'='*60}")
    print(f"  Model:        {result.model}")
    print(f"  Base URL:     {result.base_url}")
    print(f"  Overall:      {result.overall_score}/100")
    print(f"  Trust level:  {result.trust_level.upper()}")
    print(f"  Duration:     {(result.completed_at - result.started_at).total_seconds():.1f}s")
    print()

    print("  Checks:")
    for check in result.checks:
        icon = "✅" if check.passed else "❌"
        print(f"    {icon} {check.name}: {check.score:.0f}/100")
        print(f"       {check.details}")
    print()

    if result.recommendations:
        print("  Recommendations:")
        for rec in result.recommendations:
            print(f"    → {rec}")
        print()

    # Export if requested
    if args.output:
        html = generate_html_report(result)
        Path(args.output).write_text(html, encoding="utf-8")
        print(f"  📄 Report exported to: {args.output}")

    # JSON output
    if args.json:
        output = result.model_dump(mode="json")
        output["started_at"] = result.started_at.isoformat()
        if result.completed_at:
            output["completed_at"] = result.completed_at.isoformat()
        print(json.dumps(output, indent=2, ensure_ascii=False))

    return result


def cmd_list(args):
    """List audit history."""
    audits = list_audits(limit=args.limit)
    if not audits:
        print("No audit history found.")
        return

    print(f"{'ID':<10} {'Model':<20} {'Score':<8} {'Trust':<10} {'Status':<10} {'Date'}")
    print("-" * 80)
    for a in audits:
        date = datetime.fromisoformat(a["started_at"]).strftime("%Y-%m-%d %H:%M")
        print(f"{a['audit_id']:<10} {a['model']:<20} {a['overall_score']:<8.0f} "
              f"{a['trust_level']:<10} {a['status']:<10} {date}")


def cmd_export(args):
    """Export an audit report to HTML."""
    audit = get_audit(args.audit_id)
    if not audit:
        print(f"❌ Audit {args.audit_id} not found.")
        sys.exit(1)

    if not audit.get("result_json"):
        print(f"❌ Audit {args.audit_id} has no result data.")
        sys.exit(1)

    from .models import AuditResult
    result = AuditResult.model_validate_json(audit["result_json"])
    html = generate_html_report(result)

    output = args.output or f"transit-truth-report-{args.audit_id}.html"
    Path(output).write_text(html, encoding="utf-8")
    print(f"📄 Report exported to: {output}")


def cmd_benchmark(args):
    """Collect model fingerprint benchmark data."""
    from .core.benchmark_collector import collect_benchmark

    print(f"📊 Collecting benchmark data for {args.model}...")
    data = asyncio.run(collect_benchmark(
        api_key=args.api_key,
        base_url=args.base_url,
        model=args.model,
        samples=args.samples,
    ))

    output = args.output or f"benchmark-{args.model.replace('/', '-')}.json"
    Path(output).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✅ Benchmark data saved to: {output}")
    print(f"   Tokenizer probes: {len(data.get('tokenizer', {}))}")
    print(f"   Behavioral probes: {len(data.get('behavioral', {}))}")
    print(f"   Capability probes: {len(data.get('capability', {}))}")


def cmd_balance(args):
    """Check account balance for one or more relay APIs."""
    from .core.balance_checker import BalanceChecker

    checker = BalanceChecker()

    # 单账户模式
    if args.api_key:
        print(f"💰 Checking balance for {args.account_name}...")
        result = asyncio.run(checker.check_balance(
            api_key=args.api_key,
            base_url=args.base_url,
            account_name=args.account_name,
            custom_endpoint=args.custom_endpoint,
        ))

        if result.success:
            print(f"✅ Balance: ${result.balance:.2f} {result.currency}")
            if result.used is not None:
                print(f"   Used: ${result.used:.2f}")
            if result.limit is not None:
                print(f"   Limit: ${result.limit:.2f}")
            print(f"   Endpoint: {result.endpoint_used}")
            if result.is_critical:
                print(Colors.red("⚠️  CRITICAL: Balance is very low! (< $0.1)"))
            elif result.is_low:
                print(Colors.yellow("⚠️  WARNING: Balance is low (< $1.0)"))
        else:
            print(Colors.red(f"❌ Failed: {result.error}"))
        return

    # 批量模式（从JSON文件读取账户列表）
    if args.accounts_file:
        accounts = json.loads(Path(args.accounts_file).read_text(encoding="utf-8"))
        print(f"💰 Checking balance for {len(accounts)} accounts...")
        results = asyncio.run(checker.check_multiple(accounts))
        print()
        print(checker.format_summary(results))

        # 低余额告警
        alerts = checker.get_low_balance_alerts(results)
        if alerts:
            print()
            print(Colors.yellow(f"⚠️  {len(alerts)} account(s) with low balance:"))
            for a in alerts:
                print(f"   - {a.account_name}: ${a.balance:.2f}")
        return

    print(Colors.red("❌ Error: Provide --api-key for single account, or --accounts-file for batch check."))


def main():
    # Check for quick mode: first argument starts with "sk-"
    if len(sys.argv) > 1 and sys.argv[1].startswith("sk-"):
        quick_mode()
        return

    parser = argparse.ArgumentParser(
        prog="transit-truth",
        description="TransitTruth - AI API Relay Audit Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Quick mode (one command):
  transit-truth sk-xxx                          Auto-detect base URL, use gpt-4o
  transit-truth sk-xxx --model gpt-4o-mini     Specify model
  transit-truth sk-xxx --base-url https://...   Specify base URL

Full mode:
  transit-truth audit --api-key sk-xxx --base-url https://api.example.com/v1 --model gpt-4o
  transit-truth list
  transit-truth export --audit-id abc123 --output report.html
  transit-truth benchmark --api-key sk-xxx --model gpt-4o --output benchmark.json
  transit-truth balance --api-key sk-xxx --base-url https://api.example.com/v1
  transit-truth balance --accounts-file accounts.json

Environment variables:
  TRANSIT_TRUTH_API_KEY    Default API key
  TRANSIT_TRUTH_BASE_URL   Default base URL
  TRANSIT_TRUTH_MODEL      Default model
        """,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Audit command
    audit_parser = subparsers.add_parser("audit", help="Run an audit on a relay API")
    audit_parser.add_argument("--api-key", default=os.environ.get("TRANSIT_TRUTH_API_KEY"), help="API key (or set TRANSIT_TRUTH_API_KEY env var)")
    audit_parser.add_argument("--base-url", default=os.environ.get("TRANSIT_TRUTH_BASE_URL"), help="Base URL (or set TRANSIT_TRUTH_BASE_URL env var)")
    audit_parser.add_argument("--model", default=os.environ.get("TRANSIT_TRUTH_MODEL", "gpt-4o"), help="Model name (default: gpt-4o)")
    audit_parser.add_argument("--official-key", default=None, help="Official API key for precise token comparison")
    audit_parser.add_argument("--probes", type=int, default=10, help="Number of probes per category (default: 10)")
    audit_parser.add_argument("--skip-token", action="store_true", help="Skip token count check")
    audit_parser.add_argument("--skip-fingerprint", action="store_true", help="Skip model fingerprint check")
    audit_parser.add_argument("--skip-latency", action="store_true", help="Skip latency check")
    audit_parser.add_argument("--skip-protocol", action="store_true", help="Skip protocol compliance check")
    audit_parser.add_argument("--output", "-o", default=None, help="Export HTML report to file")
    audit_parser.add_argument("--json", action="store_true", help="Output full result as JSON")
    audit_parser.set_defaults(func=cmd_audit)

    # List command
    list_parser = subparsers.add_parser("list", help="List audit history")
    list_parser.add_argument("--limit", type=int, default=20, help="Number of records (default: 20)")
    list_parser.set_defaults(func=cmd_list)

    # Export command
    export_parser = subparsers.add_parser("export", help="Export an audit report to HTML")
    export_parser.add_argument("--audit-id", required=True, help="Audit ID to export")
    export_parser.add_argument("--output", "-o", default=None, help="Output file path")
    export_parser.set_defaults(func=cmd_export)

    # Benchmark command
    bench_parser = subparsers.add_parser("benchmark", help="Collect model fingerprint benchmark data")
    bench_parser.add_argument("--api-key", default=os.environ.get("TRANSIT_TRUTH_API_KEY"), help="API key")
    bench_parser.add_argument("--base-url", default="https://api.openai.com/v1", help="Base URL (default: OpenAI official)")
    bench_parser.add_argument("--model", required=True, help="Model name")
    bench_parser.add_argument("--samples", type=int, default=5, help="Samples per behavioral probe (default: 5)")
    bench_parser.add_argument("--output", "-o", default=None, help="Output JSON file path")
    bench_parser.set_defaults(func=cmd_benchmark)

    # Balance command
    balance_parser = subparsers.add_parser("balance", help="Check account balance for relay APIs")
    balance_parser.add_argument("--api-key", default=os.environ.get("TRANSIT_TRUTH_API_KEY"), help="API key (single account mode)")
    balance_parser.add_argument("--base-url", default="https://api.openai.com/v1", help="Base URL (default: OpenAI official)")
    balance_parser.add_argument("--account-name", default="default", help="Account name for display")
    balance_parser.add_argument("--custom-endpoint", default=None, help="Custom balance query endpoint (e.g., /v1/balance)")
    balance_parser.add_argument("--accounts-file", default=None, help="JSON file containing account list for batch check")
    balance_parser.set_defaults(func=cmd_balance)

    args = parser.parse_args()
    if not args.command:
        print_banner()
        parser.print_help()
        sys.exit(1)

    # Validate API key for audit/benchmark commands
    if args.command in ("audit", "benchmark") and not args.api_key:
        print(Colors.red("❌ Error: API key required. Use --api-key or set TRANSIT_TRUTH_API_KEY environment variable."))
        sys.exit(1)

    # Auto-detect base URL for audit command if not specified
    if args.command == "audit" and not args.base_url:
        args.base_url, relay_name = detect_base_url(args.api_key)
        print(Colors.gray(f"ℹ Auto-detected base URL: {args.base_url} ({relay_name})"))

    args.func(args)


def quick_mode():
    """Quick mode: transit-truth sk-xxx [--model ...] [--base-url ...]"""
    print_banner()

    api_key = sys.argv[1]

    # Parse optional arguments
    model = os.environ.get("TRANSIT_TRUTH_MODEL", "gpt-4o")
    base_url = None
    output = None
    json_output = False
    probes = 5  # Quick mode uses fewer probes

    i = 2
    while i < len(sys.argv):
        if sys.argv[i] == "--model" and i + 1 < len(sys.argv):
            model = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--base-url" and i + 1 < len(sys.argv):
            base_url = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--output" and i + 1 < len(sys.argv):
            output = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--json":
            json_output = True
            i += 1
        elif sys.argv[i] == "--probes" and i + 1 < len(sys.argv):
            probes = int(sys.argv[i + 1])
            i += 2
        else:
            i += 1

    # Auto-detect base URL
    if not base_url:
        base_url, relay_name = detect_base_url(api_key)
        print(Colors.gray(f"ℹ Auto-detected: {relay_name} → {base_url}"))
    print(Colors.gray(f"ℹ Model: {model} | Probes: {probes}"))
    print()

    # Run audit
    request = AuditRequest(
        api_key=api_key,
        base_url=base_url,
        model=model,
        probe_count=probes,
    )

    print(Colors.cyan("🔍 Starting quick audit..."))
    engine = AuditEngine()
    result = asyncio.run(engine.run_audit(request))

    if result.status == AuditStatus.FAILED:
        print(Colors.red(f"❌ Audit failed: {result.error}"))
        sys.exit(1)

    # Print colored summary
    print()
    print(Colors.bold("=" * 60))
    score_color = Colors.green if result.overall_score >= 80 else Colors.yellow if result.overall_score >= 60 else Colors.red
    print(f"  {Colors.bold('Overall Score:')} {score_color(str(result.overall_score) + '/100')}")
    print(f"  {Colors.bold('Trust Level:')}   {score_color(result.trust_level.upper())}")
    print(f"  {Colors.bold('Model:')}         {result.model}")
    print(f"  {Colors.bold('Duration:')}      {(result.completed_at - result.started_at).total_seconds():.1f}s")
    print(Colors.bold("=" * 60))
    print()

    print(Colors.bold("  Checks:"))
    for check in result.checks:
        icon = Colors.green("✅") if check.passed else Colors.red("❌")
        score = Colors.green(f"{check.score:.0f}") if check.score >= 70 else Colors.yellow(f"{check.score:.0f}") if check.score >= 40 else Colors.red(f"{check.score:.0f}")
        print(f"    {icon} {check.name}: {score}/100")
        print(f"       {Colors.gray(check.details)}")
    print()

    if result.recommendations:
        print(Colors.bold("  Recommendations:"))
        for rec in result.recommendations:
            print(f"    {Colors.cyan('→')} {rec}")
        print()

    # Export if requested
    if output:
        html = generate_html_report(result)
        Path(output).write_text(html, encoding="utf-8")
        print(f"  📄 Report exported to: {Colors.cyan(output)}")

    # JSON output
    if json_output:
        output_data = result.model_dump(mode="json")
        output_data["started_at"] = result.started_at.isoformat()
        if result.completed_at:
            output_data["completed_at"] = result.completed_at.isoformat()
        print(json.dumps(output_data, indent=2, ensure_ascii=False))

    return result


if __name__ == "__main__":
    main()
