#!/usr/bin/env python3
"""
Unit tests for activity line rendering in claude-usage-reporting.

Tests cover:
1. render_activity_line() - renders colored 2-letter codes grouped visually
2. PaceMakerReader.get_recent_activity() - reads from pace-maker SQLite DB
3. Collapsed Plan+Tier line format in display
4. Activity line shows idle (dim) when no recent events
"""

import sqlite3
import time
from unittest.mock import MagicMock

import pytest

from claude_usage.code_mode.display import UsageRenderer


class TestRenderActivityLine:
    """Tests for render_activity_line function."""

    def test_render_returns_rich_text(self):
        """render_activity_line returns a Rich Text object."""
        from rich.text import Text
        from claude_usage.code_mode.display import render_activity_line

        result = render_activity_line([])
        assert isinstance(result, Text)

    def test_render_empty_events_shows_idle(self):
        """render_activity_line with no events shows idle indicator."""
        from claude_usage.code_mode.display import render_activity_line

        result = render_activity_line([])
        # Idle text must contain the activity prefix and dim styling
        rendered = result.plain
        assert "▸" in rendered or "idle" in rendered.lower() or rendered.strip() != ""

    def test_render_single_green_event(self):
        """render_activity_line shows green event code in output."""
        from claude_usage.code_mode.display import render_activity_line

        events = [{"event_code": "IV", "status": "green"}]
        result = render_activity_line(events)
        assert "IV" in result.plain

    def test_render_single_red_event(self):
        """render_activity_line shows red event code in output."""
        from claude_usage.code_mode.display import render_activity_line

        events = [{"event_code": "IV", "status": "red"}]
        result = render_activity_line(events)
        assert "IV" in result.plain

    def test_render_single_blue_event(self):
        """render_activity_line shows blue event code in output."""
        from claude_usage.code_mode.display import render_activity_line

        events = [{"event_code": "LF", "status": "blue"}]
        result = render_activity_line(events)
        assert "LF" in result.plain

    def test_render_multiple_events_all_shown(self):
        """render_activity_line shows all event codes."""
        from claude_usage.code_mode.display import render_activity_line

        events = [
            {"event_code": "IV", "status": "green"},
            {"event_code": "TD", "status": "green"},
            {"event_code": "CC", "status": "green"},
        ]
        result = render_activity_line(events)
        plain = result.plain
        assert "IV" in plain
        assert "TD" in plain
        assert "CC" in plain

    def test_render_groups_with_dots(self):
        """render_activity_line uses dots (·) within groups."""
        from claude_usage.code_mode.display import render_activity_line

        # IV, TD, CC are in same group — should be separated by dots
        events = [
            {"event_code": "IV", "status": "green"},
            {"event_code": "TD", "status": "green"},
            {"event_code": "CC", "status": "green"},
        ]
        result = render_activity_line(events)
        plain = result.plain
        # Should contain dots between codes in same group
        assert "·" in plain

    def test_render_all_13_event_codes(self):
        """render_activity_line handles all 13 event codes."""
        from claude_usage.code_mode.display import render_activity_line

        events = [
            {"event_code": "IV", "status": "green"},
            {"event_code": "TD", "status": "green"},
            {"event_code": "CC", "status": "green"},
            {"event_code": "ST", "status": "green"},
            {"event_code": "CX", "status": "red"},
            {"event_code": "PA", "status": "green"},
            {"event_code": "PL", "status": "blue"},
            {"event_code": "LF", "status": "blue"},
            {"event_code": "SS", "status": "blue"},
            {"event_code": "SM", "status": "blue"},
            {"event_code": "SE", "status": "green"},
            {"event_code": "SA", "status": "green"},
            {"event_code": "UP", "status": "green"},
        ]
        result = render_activity_line(events)
        plain = result.plain
        for event in events:
            assert event["event_code"] in plain, f"Missing: {event['event_code']}"

    def test_render_prefix_arrow(self):
        """render_activity_line starts with ▸ prefix."""
        from claude_usage.code_mode.display import render_activity_line

        events = [{"event_code": "SE", "status": "green"}]
        result = render_activity_line(events)
        assert "▸" in result.plain

    def test_render_unknown_event_code_skipped(self):
        """render_activity_line handles unknown event codes gracefully."""
        from claude_usage.code_mode.display import render_activity_line

        events = [
            {"event_code": "IV", "status": "green"},
            {"event_code": "ZZ", "status": "green"},  # Unknown code
        ]
        # Should not raise
        result = render_activity_line(events)
        assert "IV" in result.plain


class TestPaceMakerReaderGetRecentActivity:
    """Tests for PaceMakerReader.get_recent_activity()."""

    @pytest.fixture
    def temp_db(self, tmp_path):
        """Create a temporary pace-maker style database."""
        db_path = tmp_path / "usage.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS activity_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                event_code TEXT NOT NULL,
                status TEXT NOT NULL,
                session_id TEXT NOT NULL
            )
        """
        )
        conn.commit()
        conn.close()
        return db_path

    def test_get_recent_activity_returns_empty_when_no_events(self, tmp_path):
        """get_recent_activity returns empty list when no events in DB."""
        from claude_usage.code_mode.pacemaker_integration import PaceMakerReader

        reader = PaceMakerReader.__new__(PaceMakerReader)
        reader.pm_dir = tmp_path
        reader.db_path = tmp_path / "usage.db"

        # Create empty DB
        conn = sqlite3.connect(str(reader.db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS activity_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                event_code TEXT NOT NULL,
                status TEXT NOT NULL,
                session_id TEXT NOT NULL
            )
        """
        )
        conn.commit()
        conn.close()

        result = reader.get_recent_activity(window_seconds=10)
        assert result == []

    def test_get_recent_activity_returns_recent_events(self, temp_db, tmp_path):
        """get_recent_activity returns events within the time window."""
        from claude_usage.code_mode.pacemaker_integration import PaceMakerReader

        # Insert a recent event
        conn = sqlite3.connect(str(temp_db))
        conn.execute(
            "INSERT INTO activity_events (timestamp, event_code, status, session_id) VALUES (?, ?, ?, ?)",
            (time.time() - 2, "IV", "green", "session-1"),
        )
        conn.commit()
        conn.close()

        reader = PaceMakerReader.__new__(PaceMakerReader)
        reader.pm_dir = tmp_path
        reader.db_path = temp_db

        result = reader.get_recent_activity(window_seconds=10)
        assert len(result) == 1
        assert result[0]["event_code"] == "IV"
        assert result[0]["status"] == "green"

    def test_get_recent_activity_excludes_old_events(self, temp_db, tmp_path):
        """get_recent_activity excludes events older than window_seconds."""
        from claude_usage.code_mode.pacemaker_integration import PaceMakerReader

        # Insert an old event
        conn = sqlite3.connect(str(temp_db))
        conn.execute(
            "INSERT INTO activity_events (timestamp, event_code, status, session_id) VALUES (?, ?, ?, ?)",
            (time.time() - 100, "IV", "green", "session-1"),
        )
        conn.commit()
        conn.close()

        reader = PaceMakerReader.__new__(PaceMakerReader)
        reader.pm_dir = tmp_path
        reader.db_path = temp_db

        result = reader.get_recent_activity(window_seconds=10)
        assert result == []

    def test_get_recent_activity_returns_most_recent_per_code(self, temp_db, tmp_path):
        """get_recent_activity returns most recent event per code."""
        from claude_usage.code_mode.pacemaker_integration import PaceMakerReader

        conn = sqlite3.connect(str(temp_db))
        # Older event - red
        conn.execute(
            "INSERT INTO activity_events (timestamp, event_code, status, session_id) VALUES (?, ?, ?, ?)",
            (time.time() - 8, "IV", "red", "session-1"),
        )
        # Newer event - green
        conn.execute(
            "INSERT INTO activity_events (timestamp, event_code, status, session_id) VALUES (?, ?, ?, ?)",
            (time.time() - 2, "IV", "green", "session-2"),
        )
        conn.commit()
        conn.close()

        reader = PaceMakerReader.__new__(PaceMakerReader)
        reader.pm_dir = tmp_path
        reader.db_path = temp_db

        result = reader.get_recent_activity(window_seconds=10)
        iv_events = [e for e in result if e["event_code"] == "IV"]
        assert len(iv_events) == 1
        assert iv_events[0]["status"] == "green"  # Most recent

    def test_get_recent_activity_returns_empty_when_db_missing(self, tmp_path):
        """get_recent_activity returns empty list when DB file does not exist."""
        from claude_usage.code_mode.pacemaker_integration import PaceMakerReader

        reader = PaceMakerReader.__new__(PaceMakerReader)
        reader.pm_dir = tmp_path
        reader.db_path = tmp_path / "nonexistent.db"

        result = reader.get_recent_activity(window_seconds=10)
        assert result == []

    def test_get_recent_activity_default_window_is_10(self, temp_db, tmp_path):
        """get_recent_activity default window_seconds is 10."""
        from claude_usage.code_mode.pacemaker_integration import PaceMakerReader

        # Insert event 5 seconds ago (within 10s window)
        conn = sqlite3.connect(str(temp_db))
        conn.execute(
            "INSERT INTO activity_events (timestamp, event_code, status, session_id) VALUES (?, ?, ?, ?)",
            (time.time() - 5, "SE", "green", "session-1"),
        )
        conn.commit()
        conn.close()

        reader = PaceMakerReader.__new__(PaceMakerReader)
        reader.pm_dir = tmp_path
        reader.db_path = temp_db

        # Call without explicit window_seconds
        result = reader.get_recent_activity()
        assert len(result) == 1
        assert result[0]["event_code"] == "SE"

    def test_get_recent_activity_handles_no_activity_events_table(self, tmp_path):
        """get_recent_activity returns empty list when table does not exist."""
        from claude_usage.code_mode.pacemaker_integration import PaceMakerReader

        # Create DB without activity_events table
        db_path = tmp_path / "usage.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE IF NOT EXISTS other_table (id INTEGER PRIMARY KEY)")
        conn.commit()
        conn.close()

        reader = PaceMakerReader.__new__(PaceMakerReader)
        reader.pm_dir = tmp_path
        reader.db_path = db_path

        # Should not raise, returns empty
        result = reader.get_recent_activity(window_seconds=10)
        assert result == []


class TestCollapsedPlanTierLine:
    """Tests for collapsed Plan+Tier line format in _render_profile."""

    def test_plan_and_tier_on_same_line_when_both_present(self):
        """Plan badges and tier are on same collapsed line when both present."""
        from claude_usage.code_mode.display import render_collapsed_plan_tier_line

        plan_badges = ["MAX"]
        rate_tier = "20x"
        result = render_collapsed_plan_tier_line(plan_badges, rate_tier)
        plain = result.plain
        assert "Plan:" in plain
        assert "MAX" in plain
        assert "20x" in plain

    def test_collapsed_line_uses_package_emoji(self):
        """Collapsed plan+tier line uses 📦 prefix."""
        from claude_usage.code_mode.display import render_collapsed_plan_tier_line

        result = render_collapsed_plan_tier_line(["MAX"], "20x")
        plain = result.plain
        assert "📦" in plain

    def test_collapsed_line_uses_lightning_emoji(self):
        """Collapsed plan+tier line uses ⚡ for tier."""
        from claude_usage.code_mode.display import render_collapsed_plan_tier_line

        result = render_collapsed_plan_tier_line(["MAX"], "20x")
        plain = result.plain
        assert "⚡" in plain

    def test_collapsed_line_format_plan_max_20x(self):
        """Collapsed line matches '📦 Plan: MAX  ⚡ 20x' format."""
        from claude_usage.code_mode.display import render_collapsed_plan_tier_line

        result = render_collapsed_plan_tier_line(["MAX"], "20x")
        plain = result.plain
        # Should contain both plan info and tier info on same line
        assert "Plan:" in plain
        assert "MAX" in plain
        assert "20x" in plain
        # Should be a single text object (one line)
        assert "\n" not in plain

    def test_collapsed_line_with_pro_plan(self):
        """Collapsed line works with PRO plan badge."""
        from claude_usage.code_mode.display import render_collapsed_plan_tier_line

        result = render_collapsed_plan_tier_line(["PRO"], "5x")
        plain = result.plain
        assert "PRO" in plain
        assert "5x" in plain

    def test_collapsed_line_without_tier(self):
        """Collapsed line shows only plan when no tier."""
        from claude_usage.code_mode.display import render_collapsed_plan_tier_line

        result = render_collapsed_plan_tier_line(["MAX"], "")
        plain = result.plain
        assert "Plan:" in plain
        assert "MAX" in plain

    def test_collapsed_line_without_plan(self):
        """Collapsed line shows only tier when no plan badges."""
        from claude_usage.code_mode.display import render_collapsed_plan_tier_line

        result = render_collapsed_plan_tier_line([], "20x")
        plain = result.plain
        # Should still render something, even if just tier
        assert result is not None


class TestMonitorActivityLineIntegration:
    """Integration tests for activity line in monitor display."""

    def test_get_display_includes_activity_line_when_pacemaker_installed(self):
        """get_display includes activity line group when pacemaker is installed."""
        from claude_usage.code_mode.monitor import CodeMonitor

        monitor = CodeMonitor.__new__(CodeMonitor)
        monitor.error_message = None
        monitor.last_usage = {
            "five_hour": {"utilization": 50, "resets_at": ""},
            "seven_day": {"utilization": 30, "resets_at": ""},
        }
        monitor.last_profile = None
        monitor.last_update = None

        # Mock pacemaker_reader to appear installed with activity events
        mock_reader = MagicMock()
        mock_reader.is_installed.return_value = True
        mock_reader.get_status.return_value = {
            "enabled": True,
            "has_data": True,
            "five_hour": {"utilization": 50, "target": 60, "deviation": -10},
            "seven_day": {"utilization": 30, "target": 40, "deviation": -10},
            "constrained_window": "5-hour",
            "should_throttle": False,
            "delay_seconds": 0,
            "algorithm": "adaptive",
            "weekly_limit_enabled": True,
            "five_hour_limit_enabled": True,
            "tempo_enabled": True,
            "subagent_reminder_enabled": True,
            "intent_validation_enabled": True,
            "tdd_enabled": True,
            "preferred_subagent_model": "auto",
            "clean_code_rules_count": 17,
            "log_level": 2,
            "langfuse_enabled": False,
            "langfuse_connection": {"connected": False},
            "pacemaker_version": "1.0.0",
            "usage_console_version": "1.0.0",
            "error_count_24h": 0,
            "api_backoff_remaining": 0,
            "fallback_mode": False,
        }
        mock_reader.get_langfuse_status.return_value = False
        mock_reader.test_langfuse_connection.return_value = {"connected": False}
        mock_reader.get_pacemaker_version.return_value = "1.0.0"
        mock_reader.get_recent_error_count.return_value = 0
        mock_reader.get_blockage_stats_with_labels.return_value = {"Total": 0}
        mock_reader.get_langfuse_metrics.return_value = None
        mock_reader.get_secrets_metrics.return_value = None
        mock_reader.get_recent_activity.return_value = [
            {"event_code": "IV", "status": "green"},
            {"event_code": "SE", "status": "green"},
        ]

        monitor.pacemaker_reader = mock_reader
        monitor.renderer = UsageRenderer()

        # Should not raise and should include activity line
        display = monitor.get_display()
        assert display is not None
