"""CLI entry point for token cost analysis."""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Optional

import numpy as np

from .core import (
    N_FEATURES,
    collect_all_token_events,
    compute_weighted_cost,
    load_snapshots,
    total_tokens_for_events,
)
from .intervals import build_intervals, build_weighted_intervals
from .regression import (
    format_raw_results,
    format_weighted_results,
    run_regression,
)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Reverse-engineer Claude subscription token costs via regression."
    )
    p.add_argument(
        "--db-path", default=os.path.expanduser("~/.claude-pace-maker/usage.db")
    )
    p.add_argument(
        "--transcripts-dir", default=os.path.expanduser("~/.claude/projects")
    )
    p.add_argument(
        "--window", choices=["five_hour", "seven_day", "both"], default="both"
    )
    p.add_argument("--min-intervals", type=int, default=20)
    p.add_argument(
        "--since", default=None, help="YYYY-MM-DD filter for transcript files"
    )
    p.add_argument(
        "--mode",
        choices=["weighted", "raw", "both"],
        default="weighted",
        help="weighted (API pricing collapse), raw (12-feature), or both",
    )
    p.add_argument(
        "--tier",
        choices=["5x", "20x", "unknown"],
        default="unknown",
        help="Subscription tier (5x=Pro, 20x=Max/Team). Run separately per tier for accurate results.",
    )
    p.add_argument(
        "--aggregate-hours",
        type=int,
        default=1,
        help="Bucket size in hours (weighted mode)",
    )
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--output-json", action="store_true")
    return p.parse_args()


def _load_events(args) -> tuple:
    """Load snapshots and token events, return (snapshots, events, meta_dates)."""
    since_epoch: Optional[float] = None
    if args.since:
        try:
            since_epoch = (
                datetime.strptime(args.since, "%Y-%m-%d")
                .replace(tzinfo=timezone.utc)
                .timestamp()
            )
        except ValueError:
            print(f"ERROR: Invalid --since date: {args.since!r}", file=sys.stderr)
            sys.exit(1)

    print("Loading utilization snapshots...", file=sys.stderr)
    snapshots = load_snapshots(args.db_path)
    if not snapshots:
        print("ERROR: No snapshots found.", file=sys.stderr)
        sys.exit(1)

    print(
        f"Loaded {len(snapshots):,} snapshots. Scanning transcripts...", file=sys.stderr
    )
    events = collect_all_token_events(
        args.transcripts_dir,
        since_epoch=since_epoch,
        verbose=args.verbose,
    )
    if not events:
        print("ERROR: No token events found.", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(events):,} events.", file=sys.stderr)
    return snapshots, events


def _date_range(events):
    ts_all = [e["timestamp"] for e in events]
    ds = datetime.fromtimestamp(min(ts_all), tz=timezone.utc).strftime("%Y-%m-%d")
    de = datetime.fromtimestamp(max(ts_all), tz=timezone.utc).strftime("%Y-%m-%d")
    return ds, de


def _run_raw(args, snapshots, events):
    """Run 12-feature raw regression."""
    print("Building raw intervals...", file=sys.stderr)
    X5, y5, X7, y7 = build_intervals(snapshots, events)
    n5, n7 = X5.shape[0], X7.shape[0]

    dummy = np.zeros(N_FEATURES)
    c5, r5 = dummy.copy(), 0.0
    c7, r7 = dummy.copy(), 0.0

    if n5 >= args.min_intervals:
        print(f"Running raw 5h regression ({n5} intervals)...", file=sys.stderr)
        c5, r5 = run_regression(X5, y5)
    if n7 >= args.min_intervals:
        print(f"Running raw 7d regression ({n7} intervals)...", file=sys.stderr)
        c7, r7 = run_regression(X7, y7)

    meta = {
        "date_range": _date_range(events),
        "tier": args.tier,
        "n_intervals_5h": n5,
        "n_intervals_7d": n7,
        "total_tokens": total_tokens_for_events(events),
    }
    print(format_raw_results(c5, c7, r5, r7, meta))


def _run_weighted(args, snapshots, events):
    """Run weighted API-cost regression."""
    print("Computing API-equivalent costs...", file=sys.stderr)
    costed = compute_weighted_cost(events)
    total_cost = sum(e["api_cost"] for e in costed)

    print(f"Building weighted intervals ({args.aggregate_hours}h)...", file=sys.stderr)
    X5, y5, X7, y7 = build_weighted_intervals(
        snapshots,
        costed,
        aggregate_hours=args.aggregate_hours,
    )
    n5, n7 = X5.shape[0], X7.shape[0]

    dummy = np.zeros(4)
    c5, r5 = dummy.copy(), 0.0
    c7, r7 = dummy.copy(), 0.0

    if n5 >= args.min_intervals:
        print(f"Running weighted 5h regression ({n5} intervals)...", file=sys.stderr)
        c5, r5 = run_regression(X5, y5)
    if n7 >= args.min_intervals:
        print(f"Running weighted 7d regression ({n7} intervals)...", file=sys.stderr)
        c7, r7 = run_regression(X7, y7)

    meta = {
        "date_range": _date_range(events),
        "tier": args.tier,
        "n_intervals_5h": n5,
        "n_intervals_7d": n7,
        "total_tokens": total_tokens_for_events(events),
        "total_api_cost": total_cost,
        "aggregate_hours": args.aggregate_hours,
    }

    if args.output_json:
        print(
            json.dumps(
                {
                    "mode": "weighted",
                    "tier": args.tier,
                    "five_hour": {"coefficients": c5.tolist(), "r2": r5},
                    "seven_day": {"coefficients": c7.tolist(), "r2": r7},
                    "feature_names": [
                        "total_api_cost",
                        "opus_cost",
                        "sonnet_cost",
                        "haiku_cost",
                    ],
                    "metadata": {**meta, "date_range": list(meta["date_range"])},
                },
                indent=2,
            )
        )
    else:
        print(format_weighted_results(c5, c7, r5, r7, meta))


def main() -> None:
    args = _parse_args()
    snapshots, events = _load_events(args)

    if args.tier == "unknown":
        print(
            "NOTE: No --tier specified. If you switch between 5x and 20x accounts,\n"
            "      run separately with --tier 5x --since <date> and --tier 20x --since <date>\n"
            "      for each account period. Different tiers have different allowances.\n",
            file=sys.stderr,
        )

    if args.mode in ("raw", "both"):
        _run_raw(args, snapshots, events)
        if args.mode == "both":
            print("\n" + "=" * 60 + "\n")

    if args.mode in ("weighted", "both"):
        _run_weighted(args, snapshots, events)
