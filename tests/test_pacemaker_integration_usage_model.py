#!/usr/bin/env python3
"""
Phase 8: Tests for PaceMakerReader._get_latest_usage() using UsageModel.

BUG-1 ROOT CAUSE: _get_latest_usage() reads synthetic_cache.json then falls
back to usage_snapshots. During API 429 outages, synthetic_cache.json may be
stale or absent, causing the monitor to display stale real-API values instead
of synthetic estimates.

FIX: Replace _get_latest_usage() body to use UsageModel.get_current_usage(),
which correctly returns synthetic values from fallback_state_v2 + accumulated_costs
during fallback, and real API values from api_cache otherwise.

Test strategy:
- BUG-1 test: seeds BOTH api_cache (52%) AND usage_snapshots (52%), enters fallback,
  then asserts result != 52.0. Old code returns 52.0 from usage_snapshots (bug).
  After fix, UsageModel returns synthetic value (not 52.0).
- Normal mode test: seeds api_cache only (35%). After fix, UsageModel reads api_cache
  and returns 35.0. No usage_snapshots row needed.
- is_fallback_active tests: verify delegation to UsageModel DB state (not JSON file).

These tests are written FIRST (TDD) and FAIL until the fix is implemented.

Story #42 Phase 8.
"""

import json
import sqlite3
import sys
import time
from pathlib import Path


# Add claude-usage src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Add pace-maker src to path so UsageModel is importable
_PM_SRC = Path(__file__).parent.parent.parent / "claude-pace-maker" / "src"
if str(_PM_SRC) not in sys.path:
    sys.path.insert(0, str(_PM_SRC))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pm_dir(tmp_path: Path) -> Path:
    """Create a minimal ~/.claude-pace-maker structure."""
    pm_dir = tmp_path / ".claude-pace-maker"
    pm_dir.mkdir()
    return pm_dir


def _write_config(pm_dir: Path, enabled: bool = True) -> None:
    """Write minimal config.json."""
    config = {
        "enabled": enabled,
        "weekly_limit_enabled": True,
        "five_hour_limit_enabled": True,
        "intent_validation_enabled": False,
        "tdd_enabled": True,
        "log_level": 2,
        "preferred_subagent_model": "auto",
    }
    (pm_dir / "config.json").write_text(json.dumps(config))


def _make_usage_model(db_path: str):
    """Instantiate UsageModel from pace-maker src."""
    from pacemaker.usage_model import UsageModel

    return UsageModel(db_path=db_path)


def _write_usage_snapshot(
    pm_dir: Path,
    five_hour_util: float,
    seven_day_util: float,
    future_str: str = "2099-12-31T23:59:59",
) -> None:
    """Write a row into usage_snapshots — what the CURRENT (buggy) _get_latest_usage() reads.

    Used in BUG-1 test to prove old code would have returned the stale value.
    """
    db_path = pm_dir / "usage.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    # Create table if not already created by UsageModel init
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS usage_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL,
            five_hour_util REAL,
            five_hour_resets_at TEXT,
            seven_day_util REAL,
            seven_day_resets_at TEXT,
            session_id TEXT,
            created_at INTEGER DEFAULT (strftime('%s', 'now'))
        )
    """
    )
    conn.execute(
        "INSERT INTO usage_snapshots (timestamp, five_hour_util, five_hour_resets_at, "
        "seven_day_util, seven_day_resets_at, session_id) VALUES (?, ?, ?, ?, ?, ?)",
        (
            time.time(),
            five_hour_util,
            future_str,
            seven_day_util,
            future_str,
            "test-session",
        ),
    )
    conn.commit()
    conn.close()


def _make_reader(pm_dir: Path):
    """Create PaceMakerReader pointing at test pm_dir."""
    from claude_usage.code_mode.pacemaker_integration import PaceMakerReader

    reader = PaceMakerReader()
    reader.pm_dir = pm_dir
    reader.config_path = pm_dir / "config.json"
    reader.db_path = pm_dir / "usage.db"
    reader.state_path = pm_dir / "state.json"
    return reader


# ---------------------------------------------------------------------------
# Phase 8: _get_latest_usage() uses UsageModel
# ---------------------------------------------------------------------------


class TestGetLatestUsageUsesUsageModel:
    """_get_latest_usage() must use UsageModel.get_current_usage() as its data source.

    CURRENT BEHAVIOR (buggy): reads usage_snapshots, ignores fallback state.
    EXPECTED BEHAVIOR (fix): delegates to UsageModel.get_current_usage() which
    returns synthetic values during fallback and real api_cache values otherwise.
    """

    def test_get_latest_usage_returns_synthetic_during_fallback(self, tmp_path):
        """BUG-1: During fallback, _get_latest_usage() must return synthetic values,
        not stale real-API data from usage_snapshots.

        Setup: DB has stale real data (52%) in BOTH api_cache AND usage_snapshots,
        so both old and new code paths would see 52.0 in normal mode.
        Then fallback is entered with baseline=30%.
        Expected: _get_latest_usage() returns synthetic value (NOT 52.0).
        Old code: reads usage_snapshots → returns 52.0 (BUG).
        New code: calls UsageModel.get_current_usage() → returns synthetic (~30.0).
        """
        pm_dir = _make_pm_dir(tmp_path)
        _write_config(pm_dir)

        # Initialize DB with full UsageModel schema
        model = _make_usage_model(str(pm_dir / "usage.db"))

        # Store real API data in api_cache (simulates last known value before 429)
        model.store_api_response(
            {
                "five_hour": {
                    "utilization": 52.0,
                    "resets_at": "2099-01-01T12:00:00+00:00",
                },
                "seven_day": {
                    "utilization": 40.0,
                    "resets_at": "2099-01-07T12:00:00+00:00",
                },
            }
        )

        # Also write to usage_snapshots so old code path would return 52.0 too
        _write_usage_snapshot(pm_dir, five_hour_util=52.0, seven_day_util=40.0)

        # Enter fallback (simulates API returning 429) — sets state to FALLBACK
        # with baseline snapshotted from api_cache (52% → baseline_5h=52, baseline_7d=40)
        # Wait — actually enter_fallback snapshots the api_cache values as baselines.
        # So synthetic_5h starts at 52.0 too. Let us re-enter with lower baselines by
        # storing a lower api_response first then entering fallback.
        model.store_api_response(
            {
                "five_hour": {
                    "utilization": 30.0,
                    "resets_at": "2099-01-01T12:00:00+00:00",
                },
                "seven_day": {
                    "utilization": 20.0,
                    "resets_at": "2099-01-07T12:00:00+00:00",
                },
            }
        )
        model.enter_fallback()

        # Now update usage_snapshots to still show the stale 52.0 (simulates race condition
        # where usage_snapshots was written from a real API call before the 429 started)
        _write_usage_snapshot(pm_dir, five_hour_util=52.0, seven_day_util=40.0)

        # Create reader pointing at same DB
        reader = _make_reader(pm_dir)

        # BUG-1 test: _get_latest_usage() must NOT return 52.0 (stale usage_snapshot value)
        # After fix: UsageModel.get_current_usage() detects fallback and returns synthetic.
        result = reader._get_latest_usage()

        assert (
            result is not None
        ), "_get_latest_usage() must not return None during fallback"
        # Old code reads usage_snapshots → 52.0 (BUG)
        # New code uses UsageModel → synthetic value starting at baseline 30.0
        assert result["five_hour_util"] != 52.0, (
            "BUG-1: _get_latest_usage() returned stale API value 52.0 instead of "
            "synthetic value during fallback"
        )

    def test_get_latest_usage_returns_normal_data_when_not_in_fallback(self, tmp_path):
        """Normal mode: _get_latest_usage() returns real API values from UsageModel api_cache."""
        pm_dir = _make_pm_dir(tmp_path)
        _write_config(pm_dir)

        # Set up UsageModel with API response in api_cache (no fallback entered)
        model = _make_usage_model(str(pm_dir / "usage.db"))
        model.store_api_response(
            {
                "five_hour": {
                    "utilization": 35.0,
                    "resets_at": "2099-01-01T12:00:00+00:00",
                },
                "seven_day": {
                    "utilization": 20.0,
                    "resets_at": "2099-01-07T12:00:00+00:00",
                },
            }
        )

        reader = _make_reader(pm_dir)
        result = reader._get_latest_usage()

        assert result is not None
        assert abs(result["five_hour_util"] - 35.0) < 0.01
        assert abs(result["seven_day_util"] - 20.0) < 0.01

    def test_get_latest_usage_returns_none_when_no_data(self, tmp_path):
        """No data at all → _get_latest_usage() returns None."""
        pm_dir = _make_pm_dir(tmp_path)
        _write_config(pm_dir)

        # Create empty UsageModel DB (no data stored)
        _make_usage_model(str(pm_dir / "usage.db"))

        reader = _make_reader(pm_dir)
        result = reader._get_latest_usage()

        assert (
            result is None
        ), "_get_latest_usage() must return None when no data available"

    def test_get_latest_usage_result_has_required_keys(self, tmp_path):
        """Returned dict must have all keys that get_status() depends on."""
        pm_dir = _make_pm_dir(tmp_path)
        _write_config(pm_dir)

        model = _make_usage_model(str(pm_dir / "usage.db"))
        model.store_api_response(
            {
                "five_hour": {
                    "utilization": 25.0,
                    "resets_at": "2099-01-01T12:00:00+00:00",
                },
                "seven_day": {
                    "utilization": 12.0,
                    "resets_at": "2099-01-07T12:00:00+00:00",
                },
            }
        )

        reader = _make_reader(pm_dir)
        result = reader._get_latest_usage()

        assert result is not None
        # These keys are consumed by get_status() → calculate_pacing_decision()
        required_keys = {
            "timestamp",
            "five_hour_util",
            "five_hour_resets_at",
            "seven_day_util",
            "seven_day_resets_at",
        }
        assert required_keys.issubset(
            result.keys()
        ), f"Missing keys: {required_keys - result.keys()}"


class TestIsFallbackActiveUsesUsageModel:
    """is_fallback_active() should delegate to UsageModel.is_fallback_active() (DB state).

    Current implementation reads fallback_state.json — after fix it reads
    fallback_state_v2 table via UsageModel.
    """

    def test_is_fallback_active_returns_false_when_normal(self, tmp_path):
        """Normal mode in DB → is_fallback_active() returns False."""
        pm_dir = _make_pm_dir(tmp_path)

        # Initialize DB with normal state (no fallback entered, no fallback_state.json)
        model = _make_usage_model(str(pm_dir / "usage.db"))
        model.store_api_response(
            {
                "five_hour": {
                    "utilization": 10.0,
                    "resets_at": "2099-01-01T12:00:00+00:00",
                },
                "seven_day": {
                    "utilization": 5.0,
                    "resets_at": "2099-01-07T12:00:00+00:00",
                },
            }
        )

        reader = _make_reader(pm_dir)
        assert reader.is_fallback_active() is False

    def test_is_fallback_active_returns_true_when_fallback_in_db(self, tmp_path):
        """Fallback active in DB (fallback_state_v2) → is_fallback_active() returns True.

        After fix: reads UsageModel DB state (not fallback_state.json).
        This test does NOT write fallback_state.json, only uses UsageModel.enter_fallback().
        """
        pm_dir = _make_pm_dir(tmp_path)

        model = _make_usage_model(str(pm_dir / "usage.db"))
        model.store_api_response(
            {
                "five_hour": {
                    "utilization": 30.0,
                    "resets_at": "2099-01-01T12:00:00+00:00",
                },
                "seven_day": {
                    "utilization": 15.0,
                    "resets_at": "2099-01-07T12:00:00+00:00",
                },
            }
        )
        model.enter_fallback()

        # No fallback_state.json written — only DB state set
        assert not (
            pm_dir / "fallback_state.json"
        ).exists(), "Precondition: test must NOT write fallback_state.json so we verify DB delegation"

        reader = _make_reader(pm_dir)
        assert reader.is_fallback_active() is True
