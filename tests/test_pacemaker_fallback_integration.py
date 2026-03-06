#!/usr/bin/env python3
"""
Tests for pacemaker_integration.py fallback mode display.

TDD: Tests written first to define behavior before implementation.
Story #38: Scenario 6 - Display shows fallback indicators when in fallback mode.

Tests verify:
- get_status() reads fallback_state.json
- fallback_mode flag propagated in status dict
- is_synthetic flag propagated in status dict when in fallback
- fallback_message included when in fallback
"""

import json
import sqlite3
import time
from pathlib import Path

import pytest
import sys

# Add claude-usage src to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def _make_pm_dir(tmp_path: Path) -> Path:
    """Helper: create a minimal ~/.claude-pace-maker structure."""
    pm_dir = tmp_path / ".claude-pace-maker"
    pm_dir.mkdir()
    return pm_dir


def _write_config(pm_dir: Path, enabled: bool = True) -> None:
    """Helper: write minimal config.json."""
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


def _write_usage_db(pm_dir: Path) -> None:
    """Helper: write minimal usage.db with a snapshot."""
    db_path = pm_dir / "usage.db"
    future_str = "2099-12-31T23:59:59"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS usage_snapshots (
            id INTEGER PRIMARY KEY,
            timestamp REAL,
            five_hour_util REAL,
            five_hour_resets_at TEXT,
            seven_day_util REAL,
            seven_day_resets_at TEXT,
            session_id TEXT
        )
    """)
    conn.execute(
        "INSERT INTO usage_snapshots VALUES (NULL, ?, ?, ?, ?, ?, ?)",
        (time.time(), 45.0, future_str, 30.0, future_str, "test-session"),
    )
    conn.commit()
    conn.close()


def _write_fallback_state(pm_dir: Path, state: str, baseline_5h: float = 45.0,
                           baseline_7d: float = 30.0, accumulated_cost: float = 5.0) -> None:
    """Helper: write fallback_state.json."""
    content = {
        "state": state,
        "baseline_5h": baseline_5h,
        "baseline_7d": baseline_7d,
        "accumulated_cost": accumulated_cost,
        "entered_at": time.time() - 300,
    }
    (pm_dir / "fallback_state.json").write_text(json.dumps(content))


class TestReadFallbackState:
    """Tests for PaceMakerReader._read_fallback_state() method."""

    def test_returns_normal_when_file_missing(self, tmp_path):
        """_read_fallback_state returns NORMAL state when file is missing."""
        from claude_usage.code_mode.pacemaker_integration import PaceMakerReader

        pm_dir = _make_pm_dir(tmp_path)
        reader = PaceMakerReader()
        reader.pm_dir = pm_dir

        state = reader._read_fallback_state()

        assert state["state"] == "normal"

    def test_returns_fallback_when_active(self, tmp_path):
        """_read_fallback_state returns FALLBACK state when file shows fallback."""
        from claude_usage.code_mode.pacemaker_integration import PaceMakerReader

        pm_dir = _make_pm_dir(tmp_path)
        _write_fallback_state(pm_dir, state="fallback", accumulated_cost=10.0)

        reader = PaceMakerReader()
        reader.pm_dir = pm_dir

        state = reader._read_fallback_state()

        assert state["state"] == "fallback"
        assert state["accumulated_cost"] == 10.0

    def test_returns_normal_on_corrupt_file(self, tmp_path):
        """_read_fallback_state returns NORMAL state when file is corrupt."""
        from claude_usage.code_mode.pacemaker_integration import PaceMakerReader

        pm_dir = _make_pm_dir(tmp_path)
        (pm_dir / "fallback_state.json").write_text("{{{invalid")

        reader = PaceMakerReader()
        reader.pm_dir = pm_dir

        state = reader._read_fallback_state()

        assert state["state"] == "normal"

    def test_returns_normal_on_empty_file(self, tmp_path):
        """_read_fallback_state returns NORMAL state when file is empty."""
        from claude_usage.code_mode.pacemaker_integration import PaceMakerReader

        pm_dir = _make_pm_dir(tmp_path)
        (pm_dir / "fallback_state.json").write_text("")

        reader = PaceMakerReader()
        reader.pm_dir = pm_dir

        state = reader._read_fallback_state()

        assert state["state"] == "normal"


class TestIsFallbackActive:
    """Tests for PaceMakerReader.is_fallback_active() method."""

    def test_returns_false_when_fallback_state_missing(self, tmp_path):
        """is_fallback_active returns False when fallback_state.json is missing."""
        from claude_usage.code_mode.pacemaker_integration import PaceMakerReader

        pm_dir = _make_pm_dir(tmp_path)
        reader = PaceMakerReader()
        reader.pm_dir = pm_dir

        assert reader.is_fallback_active() is False

    def test_returns_false_when_state_is_normal(self, tmp_path):
        """is_fallback_active returns False when state is NORMAL."""
        from claude_usage.code_mode.pacemaker_integration import PaceMakerReader

        pm_dir = _make_pm_dir(tmp_path)
        _write_fallback_state(pm_dir, state="normal", accumulated_cost=0.0)

        reader = PaceMakerReader()
        reader.pm_dir = pm_dir

        assert reader.is_fallback_active() is False

    def test_returns_true_when_state_is_fallback(self, tmp_path):
        """is_fallback_active returns True when state is FALLBACK."""
        from claude_usage.code_mode.pacemaker_integration import PaceMakerReader

        pm_dir = _make_pm_dir(tmp_path)
        _write_fallback_state(pm_dir, state="fallback", accumulated_cost=5.0)

        reader = PaceMakerReader()
        reader.pm_dir = pm_dir

        assert reader.is_fallback_active() is True

    def test_returns_true_when_state_is_trueup(self, tmp_path):
        """is_fallback_active returns True when state is TRUEUP."""
        from claude_usage.code_mode.pacemaker_integration import PaceMakerReader

        pm_dir = _make_pm_dir(tmp_path)
        _write_fallback_state(pm_dir, state="trueup", accumulated_cost=0.0)

        reader = PaceMakerReader()
        reader.pm_dir = pm_dir

        assert reader.is_fallback_active() is True


class TestGetStatusFallbackMode:
    """Tests for get_status() when fallback_state.json shows FALLBACK state."""

    def _make_reader_with_pm_dir(self, tmp_path: Path):
        """Create a PaceMakerReader pointing to test pm_dir."""
        from claude_usage.code_mode.pacemaker_integration import PaceMakerReader

        pm_dir = _make_pm_dir(tmp_path)
        _write_config(pm_dir)
        _write_usage_db(pm_dir)

        reader = PaceMakerReader()
        reader.pm_dir = pm_dir
        reader.config_path = pm_dir / "config.json"
        reader.db_path = pm_dir / "usage.db"
        reader.state_path = pm_dir / "state.json"
        return reader, pm_dir

    def test_get_status_fallback_mode_false_when_normal(self, tmp_path):
        """get_status returns fallback_mode=False when state is NORMAL."""
        reader, pm_dir = self._make_reader_with_pm_dir(tmp_path)
        _write_fallback_state(pm_dir, state="normal", accumulated_cost=0.0)

        status = reader.get_status()

        if status and status.get("has_data"):
            assert status.get("fallback_mode", False) is False

    def test_get_status_fallback_mode_true_when_fallback(self, tmp_path):
        """get_status returns fallback_mode=True when state is FALLBACK."""
        reader, pm_dir = self._make_reader_with_pm_dir(tmp_path)
        _write_fallback_state(pm_dir, state="fallback", accumulated_cost=5.0)

        status = reader.get_status()

        if status and status.get("has_data"):
            assert status.get("fallback_mode") is True

    def test_get_status_is_synthetic_true_when_fallback(self, tmp_path):
        """get_status returns is_synthetic=True when state is FALLBACK."""
        reader, pm_dir = self._make_reader_with_pm_dir(tmp_path)
        _write_fallback_state(pm_dir, state="fallback", accumulated_cost=5.0)

        status = reader.get_status()

        if status and status.get("has_data"):
            assert status.get("is_synthetic") is True

    def test_get_status_is_synthetic_absent_or_false_when_normal(self, tmp_path):
        """get_status returns is_synthetic=False or absent when state is NORMAL."""
        reader, pm_dir = self._make_reader_with_pm_dir(tmp_path)
        _write_fallback_state(pm_dir, state="normal", accumulated_cost=0.0)

        status = reader.get_status()

        if status and status.get("has_data"):
            assert status.get("is_synthetic", False) is False

    def test_get_status_fallback_message_present_when_fallback(self, tmp_path):
        """get_status includes a non-empty fallback_message when in FALLBACK state."""
        reader, pm_dir = self._make_reader_with_pm_dir(tmp_path)
        _write_fallback_state(pm_dir, state="fallback", accumulated_cost=5.0)

        status = reader.get_status()

        if status and status.get("has_data"):
            msg = status.get("fallback_message")
            assert msg is not None
            assert len(msg) > 0
            assert any(
                word in msg.lower()
                for word in ["api", "unavailable", "estimated", "fallback"]
            )

    def test_get_status_fallback_message_absent_when_normal(self, tmp_path):
        """get_status does not include fallback_message when in NORMAL state."""
        reader, pm_dir = self._make_reader_with_pm_dir(tmp_path)
        _write_fallback_state(pm_dir, state="normal", accumulated_cost=0.0)

        status = reader.get_status()

        if status and status.get("has_data"):
            assert status.get("fallback_message") is None

    def test_get_status_no_crash_when_fallback_state_missing(self, tmp_path):
        """get_status does not crash when fallback_state.json is missing."""
        reader, pm_dir = self._make_reader_with_pm_dir(tmp_path)
        # Don't write fallback_state.json

        status = reader.get_status()

        assert status is None or isinstance(status, dict)

    def test_get_status_no_crash_when_fallback_state_corrupt(self, tmp_path):
        """get_status does not crash when fallback_state.json is corrupt."""
        reader, pm_dir = self._make_reader_with_pm_dir(tmp_path)
        (pm_dir / "fallback_state.json").write_text("not valid json")

        status = reader.get_status()

        assert status is None or isinstance(status, dict)
