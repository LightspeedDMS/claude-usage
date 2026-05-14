"""Tests for last_seen-based stale session detection in the activity panel.

Bug: When the pace-maker stop hook fails to call mark_agent_ended(), the agent row
stays with ended_at IS NULL and lingers as active for up to 20 minutes.

Fix: Root agents with ended_at IS NULL but last_seen older than AGENT_STALE_VISUAL_SECONDS
(3 min) are reclassified as ended_visible (dimmed) in _agent_build_tree().

Tests:
  1. test_recent_session_stays_active — last_seen within 3 min -> status "active"
  2. test_stale_session_becomes_ended — last_seen older than 3 min -> status "ended_visible"
  3. test_ended_session_not_affected — ended_at IS NOT NULL -> normal ended_visible, not changed
  4. test_stale_subagent_not_affected — subagents are not stale-checked (only root agents)
"""

from __future__ import annotations

import sqlite3
import time as _time
from contextlib import closing
from pathlib import Path


def _create_test_registry(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE agents ("
        "agent_id TEXT PRIMARY KEY, "
        "session_id TEXT NOT NULL, "
        "role TEXT NOT NULL, "
        "subagent_type TEXT, "
        "workspace_root TEXT NOT NULL, "
        "start_time REAL NOT NULL, "
        "last_seen REAL NOT NULL, "
        "ended_at REAL"
        ")"
    )
    conn.execute(
        "CREATE TABLE agent_actions ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "agent_id TEXT NOT NULL, "
        "tool_name TEXT NOT NULL, "
        "target TEXT NOT NULL DEFAULT '-', "
        "ts REAL NOT NULL"
        ")"
    )
    conn.commit()
    return conn


def _insert_agent(conn, agent_id, session_id, role, workspace_root,
                  subagent_type=None, last_seen=None, ended_at=None):
    now = _time.time()
    conn.execute(
        "INSERT INTO agents "
        "(agent_id, session_id, role, subagent_type, workspace_root, "
        "start_time, last_seen, ended_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (agent_id, session_id, role, subagent_type, workspace_root,
         now - 60, last_seen if last_seen is not None else now, ended_at),
    )
    conn.commit()


def _make_reader(tmp_path):
    from claude_usage.code_mode.pacemaker_integration import PaceMakerReader
    reader = PaceMakerReader.__new__(PaceMakerReader)
    reader.pm_dir = tmp_path
    return reader


class TestRecentSessionStaysActive:
    """Root agent with recent last_seen (within 3 min) stays active."""

    def test_recent_session_stays_active(self, tmp_path):
        from claude_usage.code_mode.pacemaker_integration import AGENT_STALE_VISUAL_SECONDS
        registry_path = tmp_path / "session_registry.db"
        now = _time.time()
        # last_seen 30 seconds ago — well within the 3-min threshold
        with closing(_create_test_registry(registry_path)) as conn:
            _insert_agent(conn, "root-recent", "sess-recent", "root", "/workspace/recent",
                          last_seen=now - 30)

        reader = _make_reader(tmp_path)
        result = reader.get_active_agent_tree()

        assert result is not None
        assert len(result) == 1
        assert result[0]["status"] == "active"


class TestStaleSessionBecomesEnded:
    """Root agent with last_seen older than AGENT_STALE_VISUAL_SECONDS gets ended_visible."""

    def test_stale_session_becomes_ended(self, tmp_path):
        from claude_usage.code_mode.pacemaker_integration import AGENT_STALE_VISUAL_SECONDS
        registry_path = tmp_path / "session_registry.db"
        now = _time.time()
        # last_seen 5 minutes ago — beyond the 3-min threshold but within 20-min SQL filter
        with closing(_create_test_registry(registry_path)) as conn:
            _insert_agent(conn, "root-stale", "sess-stale", "root", "/workspace/stale",
                          last_seen=now - (AGENT_STALE_VISUAL_SECONDS + 120))

        reader = _make_reader(tmp_path)
        result = reader.get_active_agent_tree()

        assert result is not None
        assert len(result) == 1
        assert result[0]["status"] == "ended_visible", (
            f"Expected ended_visible for stale session, got {result[0]['status']!r}"
        )


class TestEndedSessionNotAffected:
    """Session with ended_at set uses normal classification, not stale check."""

    def test_ended_session_not_affected(self, tmp_path):
        registry_path = tmp_path / "session_registry.db"
        now = _time.time()
        # ended_at set 10 seconds ago — should be ended_visible via normal path
        with closing(_create_test_registry(registry_path)) as conn:
            _insert_agent(conn, "root-ended", "sess-ended", "root", "/workspace/ended",
                          last_seen=now - 15, ended_at=now - 10)

        reader = _make_reader(tmp_path)
        result = reader.get_active_agent_tree()

        assert result is not None
        assert len(result) == 1
        assert result[0]["status"] == "ended_visible"


class TestStaleSubagentNotAffected:
    """Subagents are not stale-checked — only root agents get the visual stale treatment."""

    def test_stale_subagent_not_affected(self, tmp_path):
        from claude_usage.code_mode.pacemaker_integration import AGENT_STALE_VISUAL_SECONDS
        registry_path = tmp_path / "session_registry.db"
        now = _time.time()
        with closing(_create_test_registry(registry_path)) as conn:
            # Root agent is recent (active)
            _insert_agent(conn, "root-parent", "sess-parent", "root", "/workspace/parent",
                          last_seen=now - 10)
            # Subagent has stale last_seen — but should NOT be reclassified
            _insert_agent(conn, "sub-stale", "sess-parent", "subagent", "/workspace/parent",
                          subagent_type="tdd-engineer",
                          last_seen=now - (AGENT_STALE_VISUAL_SECONDS + 120))

        reader = _make_reader(tmp_path)
        result = reader.get_active_agent_tree()

        assert result is not None
        assert len(result) == 1
        root = result[0]
        assert root["status"] == "active"
        assert len(root["subagents"]) == 1
        # Subagent keeps its classify_status result (active since ended_at is NULL)
        assert root["subagents"][0]["status"] == "active", (
            f"Expected subagent to stay active (not stale-checked), got {root['subagents'][0]['status']!r}"
        )
