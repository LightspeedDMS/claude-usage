"""Core data structures, parsing, and constants for token cost analysis."""

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Feature column layout: 4 token types x 3 model families = 12 features
FEATURE_NAMES = [
    "opus_input",
    "opus_output",
    "opus_cache_read",
    "opus_cache_create",
    "sonnet_input",
    "sonnet_output",
    "sonnet_cache_read",
    "sonnet_cache_create",
    "haiku_input",
    "haiku_output",
    "haiku_cache_read",
    "haiku_cache_create",
]
N_FEATURES = len(FEATURE_NAMES)

_COL_INPUT = 0
_COL_OUTPUT = 1
_COL_CACHE_READ = 2
_COL_CACHE_CREATE = 3

_FAMILY_OFFSET = {"opus": 0, "sonnet": 4, "haiku": 8}

# Near-zero threshold for safe division
NEAR_ZERO = 1e-10

# API pricing ($/MTok) — used to compute weighted cost units
API_PRICING = {
    "opus": {"input": 15.0, "output": 75.0, "cache_read": 1.50, "cache_create": 18.75},
    "sonnet": {"input": 3.0, "output": 15.0, "cache_read": 0.30, "cache_create": 3.75},
    "haiku": {"input": 0.80, "output": 4.0, "cache_read": 0.08, "cache_create": 1.00},
}

_PROGRESS_INTERVAL = 100


def classify_model(model_str: str) -> Optional[str]:
    """Return 'opus', 'sonnet', 'haiku', or None for unrecognized models."""
    lower = model_str.lower()
    if "opus" in lower:
        return "opus"
    if "sonnet" in lower:
        return "sonnet"
    if "haiku" in lower:
        return "haiku"
    return None


def parse_transcript_timestamp(ts: str) -> float:
    """Convert ISO 8601 timestamp string (UTC) to Unix epoch float."""
    ts = ts.rstrip("Z")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(ts, fmt).replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except ValueError:
            continue
    raise ValueError(f"Cannot parse timestamp: {ts!r}")


def parse_transcript_file(path: str) -> List[Dict]:
    """
    Parse a single JSONL transcript file and return token usage events.

    Consecutive duplicate usage entries are collapsed (Claude writes 2-4 per turn).
    """
    events: List[Dict] = []
    last_key = None

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                msg = obj.get("message")
                if not isinstance(msg, dict):
                    continue
                usage = msg.get("usage")
                if not isinstance(usage, dict):
                    continue

                family = classify_model(msg.get("model", ""))
                if family is None:
                    continue

                ts_str = obj.get("timestamp", "")
                if not ts_str:
                    continue

                inp = usage.get("input_tokens", 0) or 0
                out = usage.get("output_tokens", 0) or 0
                cr = usage.get("cache_read_input_tokens", 0) or 0
                cc = usage.get("cache_creation_input_tokens", 0) or 0

                key = (family, inp, out, cr, cc)
                if key == last_key:
                    continue
                last_key = key

                try:
                    epoch = parse_transcript_timestamp(ts_str)
                except ValueError:
                    continue

                events.append(
                    {
                        "timestamp": epoch,
                        "model_family": family,
                        "input_tokens": inp,
                        "output_tokens": out,
                        "cache_read_tokens": cr,
                        "cache_creation_tokens": cc,
                    }
                )
    except OSError as e:
        print(f"Warning: Could not read {path}: {e}", file=sys.stderr)

    return events


def load_snapshots(db_path: str) -> List[Tuple[int, float, float]]:
    """Load utilization snapshots sorted ascending by timestamp."""
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(
            "SELECT timestamp, five_hour_util, seven_day_util "
            "FROM usage_snapshots ORDER BY timestamp ASC"
        )
        return [(row[0], row[1], row[2]) for row in cur.fetchall()]
    finally:
        conn.close()


def collect_all_token_events(
    transcripts_dir: str,
    since_epoch: Optional[float] = None,
    verbose: bool = False,
) -> List[Dict]:
    """Walk all JSONL transcript files and return token events."""
    base = Path(transcripts_dir)
    patterns = ["*.jsonl", "*/*.jsonl", "*/*/*.jsonl"]
    files: set = set()
    for pattern in patterns:
        files.update(base.glob(pattern))

    all_events: List[Dict] = []
    processed = 0

    for path in sorted(files):
        if since_epoch is not None:
            try:
                if path.stat().st_mtime < since_epoch:
                    continue
            except OSError:
                continue

        events = parse_transcript_file(str(path))
        all_events.extend(events)
        processed += 1

        if processed % _PROGRESS_INTERVAL == 0:
            print(f"  Scanned {processed} files...", file=sys.stderr)

    if verbose:
        print(f"  Total files scanned: {processed}", file=sys.stderr)

    return all_events


def compute_weighted_cost(
    events: List[Dict],
    pricing: Optional[Dict] = None,
) -> List[Dict]:
    """Add 'api_cost' field (in $) to each event using API pricing ratios."""
    if pricing is None:
        pricing = API_PRICING

    result = []
    for ev in events:
        p = pricing.get(ev["model_family"])
        if p is None:
            continue
        cost = (
            ev["input_tokens"] / 1_000_000 * p["input"]
            + ev["output_tokens"] / 1_000_000 * p["output"]
            + ev["cache_read_tokens"] / 1_000_000 * p["cache_read"]
            + ev["cache_creation_tokens"] / 1_000_000 * p["cache_create"]
        )
        result.append({**ev, "api_cost": cost})
    return result


def total_tokens_for_events(events: List[Dict]) -> int:
    """Sum all token counts across events."""
    return sum(
        e["input_tokens"]
        + e["output_tokens"]
        + e["cache_read_tokens"]
        + e["cache_creation_tokens"]
        for e in events
    )
