#!/usr/bin/env python3
"""
Unit tests for governance events retrieval from pace-maker database.

Tests get_governance_events() on PaceMakerReader using real SQLite (no mocking).
"""

import os
import sqlite3
import tempfile
import time
from pathlib import Path

import pytest

from claude_usage.code_mode.pacemaker_integration import PaceMakerReader


# Minimal schema for governance_events table
GOVERNANCE_SCHEMA = """
CREATE TABLE IF NOT EXISTS governance_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    event_type TEXT NOT NULL,
    project_name TEXT NOT NULL,
    session_id TEXT NOT NULL,
    feedback_text TEXT NOT NULL,
    created_at INTEGER DEFAULT (strftime('%s', 'now'))
);
"""


@pytest.fixture
def pm_reader(tmp_path):
    """Create PaceMakerReader with temp directory and initialized DB."""
    pm_dir = tmp_path / ".claude-pace-maker"
    pm_dir.mkdir()

    # Create minimal config
    config_path = pm_dir / "config.json"
    config_path.write_text('{"enabled": true}')

    # Create DB with governance_events table
    db_path = pm_dir / "usage.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(GOVERNANCE_SCHEMA)
    conn.close()

    reader = PaceMakerReader()
    reader.pm_dir = pm_dir
    reader.config_path = config_path
    reader.db_path = db_path
    return reader


def _insert_event(db_path, event_type, project_name, session_id, feedback_text, timestamp=None):
    """Helper to insert a governance event directly."""
    if timestamp is None:
        timestamp = time.time()
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO governance_events "
        "(timestamp, event_type, project_name, session_id, feedback_text) "
        "VALUES (?, ?, ?, ?, ?)",
        (timestamp, event_type, project_name, session_id, feedback_text),
    )
    conn.commit()
    conn.close()


class TestGetGovernanceEvents:
    """Tests for PaceMakerReader.get_governance_events()."""

    def test_get_governance_events_returns_recent(self, pm_reader):
        """Returns events within the time window."""
        _insert_event(pm_reader.db_path, "IV", "my-project", "sess-1", "Missing INTENT")
        events = pm_reader.get_governance_events(window_seconds=3600)
        assert len(events) == 1
        assert events[0]["event_type"] == "IV"
        assert events[0]["project_name"] == "my-project"
        assert events[0]["feedback_text"] == "Missing INTENT"

    def test_get_governance_events_excludes_old(self, pm_reader):
        """Excludes events older than the time window."""
        old_ts = time.time() - 7200  # 2 hours ago
        _insert_event(pm_reader.db_path, "IV", "proj", "sess", "old", timestamp=old_ts)
        events = pm_reader.get_governance_events(window_seconds=3600)
        assert len(events) == 0

    def test_get_governance_events_ordered_newest_first(self, pm_reader):
        """Events are returned newest first."""
        now = time.time()
        _insert_event(pm_reader.db_path, "IV", "proj", "s1", "first", timestamp=now - 60)
        _insert_event(pm_reader.db_path, "TD", "proj", "s2", "second", timestamp=now - 30)
        _insert_event(pm_reader.db_path, "CC", "proj", "s3", "third", timestamp=now)

        events = pm_reader.get_governance_events(window_seconds=3600)
        assert len(events) == 3
        assert events[0]["event_type"] == "CC"  # newest
        assert events[1]["event_type"] == "TD"
        assert events[2]["event_type"] == "IV"  # oldest

    def test_get_governance_events_empty_table(self, pm_reader):
        """Returns empty list when no events exist."""
        events = pm_reader.get_governance_events(window_seconds=3600)
        assert events == []

    def test_get_governance_events_db_missing(self, tmp_path):
        """Returns empty list when database file does not exist."""
        reader = PaceMakerReader()
        reader.pm_dir = tmp_path / ".claude-pace-maker"
        reader.pm_dir.mkdir()
        reader.config_path = reader.pm_dir / "config.json"
        reader.config_path.write_text('{"enabled": true}')
        reader.db_path = reader.pm_dir / "nonexistent.db"

        events = reader.get_governance_events(window_seconds=3600)
        assert events == []

    def test_get_governance_events_db_corrupted(self, pm_reader):
        """Returns empty list when database is corrupted/unreadable."""
        # Write garbage to the DB file to simulate corruption
        pm_reader.db_path.write_bytes(b"NOT A VALID SQLITE DATABASE FILE")

        # get_governance_events should handle the error gracefully
        events = pm_reader.get_governance_events(window_seconds=3600)
        assert events == []

    def test_get_governance_events_returns_all_fields(self, pm_reader):
        """Returned dicts contain all expected fields."""
        _insert_event(pm_reader.db_path, "TD", "my-proj", "sess-5", "TDD missing")
        events = pm_reader.get_governance_events(window_seconds=3600)
        assert len(events) == 1
        event = events[0]
        assert "event_type" in event
        assert "project_name" in event
        assert "session_id" in event
        assert "feedback_text" in event
        assert "timestamp" in event
