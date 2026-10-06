"""Contribution moderation CLI (N2).

Public ranking rows are NOT written by the anonymous ``POST /api/contribute``
endpoint anymore: every submitted audit lands in a moderation queue with
``status = pending``. An operator reviews the queue and runs this tool to
approve (write to the public ranking) or reject each item. There is no
unauthenticated HTTP approval endpoint.

Usage (run from ``backend/``):

    python -m app.moderation list [--status pending]
    python -m app.moderation approve <contribution_id>
    python -m app.moderation reject <contribution_id>
"""
import argparse
import logging
import sys
from datetime import datetime

from .core.contributor_reputation import ContributorReputationSystem
from .database import upsert_ranking
from .models import RankingEntry

logger = logging.getLogger(__name__)


def _build_ranking_entry(content: dict) -> RankingEntry | None:
    """Best-effort build of a public RankingEntry from stored contribution content.

    Returns None if essential fields are unusable.
    """
    try:
        relay_name = (
            content.get("relay_name")
            or (content.get("base_url", "") or "").split("//")[-1].split("/")[0]
            or "unknown"
        )
        token_cmp = content.get("token_comparison") or {}
        latency = content.get("latency") or {}
        fp = content.get("fingerprint") or {}
        return RankingEntry(
            relay_name=str(relay_name),
            base_url=str(content.get("base_url", "")),
            model=str(content.get("model", "")),
            avg_trust_score=float(content.get("overall_score", 0)),
            audit_count=1,
            last_audited=datetime.now(),
            token_inflation_avg=float(token_cmp.get("prompt_inflation_pct", 0) or 0),
            model_authenticity_rate=1.0 if fp.get("family_match", True) else 0.0,
            avg_latency_ms=float(latency.get("avg_latency_ms", 0) or 0),
            uptime_rate=1.0,
            notes=(content.get("notes") or "")[:500],
        )
    except (TypeError, ValueError, AttributeError):
        return None


def _print_summary(contrib):
    content = contrib.content or {}
    print(
        f"{contrib.id}  [{contrib.status:8}]  "
        f"model={content.get('model', '?')}  "
        f"score={content.get('overall_score', '?')}  "
        f"base_url={content.get('base_url', '?')}  "
        f"by={contrib.contributor_id}  "
        f"at={contrib.created_at.isoformat(timespec='seconds')}"
    )


def cmd_list(args) -> int:
    sys_ = ContributorReputationSystem()
    items = sys_.list_contributions(status=args.status)
    if not items:
        print("(no contributions)")
        return 0
    for c in items:
        _print_summary(c)
    print(f"\n{len(items)} contribution(s)")
    return 0


def cmd_approve(args) -> int:
    sys_ = ContributorReputationSystem()
    contrib = sys_.get_contribution(args.id)
    if contrib is None:
        print(f"contribution not found: {args.id}", file=sys.stderr)
        return 1
    if contrib.status == "approved":
        print(f"{args.id} already approved")
        return 0

    entry = _build_ranking_entry(contrib.content or {})
    if entry is None or not entry.base_url or not entry.model:
        print(
            f"refusing to approve {args.id}: missing base_url/model; "
            "inspect content with `list` and fix or reject it.",
            file=sys.stderr,
        )
        return 2

    sys_.set_contribution_status(args.id, "approved", reviewer="cli")
    # audit_count accumulates in the SQL upsert (read old value +1).
    upsert_ranking(entry)
    print(f"approved {args.id} -> ranking[{entry.base_url} / {entry.model}]")
    return 0


def cmd_reject(args) -> int:
    sys_ = ContributorReputationSystem()
    contrib = sys_.get_contribution(args.id)
    if contrib is None:
        print(f"contribution not found: {args.id}", file=sys.stderr)
        return 1
    sys_.set_contribution_status(args.id, "rejected", reviewer="cli")
    print(f"rejected {args.id}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Moderate pending contributions.")
    sub = p.add_subparsers(dest="cmd", required=True)

    pl = sub.add_parser("list", help="list contributions (default: pending)")
    pl.add_argument("--status", default=None,
                    help="filter by status: pending|approved|rejected (default: all pending when omitted? see note)")
    pl.set_defaults(func=cmd_list)

    pa = sub.add_parser("approve", help="approve a contribution and write it to the public ranking")
    pa.add_argument("id")
    pa.set_defaults(func=cmd_approve)

    pr = sub.add_parser("reject", help="reject a contribution")
    pr.add_argument("id")
    pr.set_defaults(func=cmd_reject)
    return p


def main(argv=None) -> int:
    logging.basicConfig(level=logging.WARNING)
    parser = build_parser()
    args = parser.parse_args(argv)
    # `list` with no explicit status defaults to pending, which is what operators
    # usually want; --status all lists everything.
    if args.cmd == "list" and getattr(args, "status", None) in (None, "all"):
        args.status = None if getattr(args, "status", None) == "all" else "pending"
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
