"""Unit tests for agent activity reader (Part 1) and display functions (Part 2).

Tests cover:
  1. get_active_agent_tree — DB missing, empty, single root, subagents, orphans,
     action ordering, caching TTL (7 classes, 8 methods)
  2. format_action, format_trail, render_agent_line, render_activity_panel
     (4 classes, 18 methods)

Total: 26 test methods.
"""

from __future__ import annotations

import re
import sqlite3
import time as _time
from contextlib import closing
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers — in-process SQLite registry for reader tests
# ---------------------------------------------------------------------------


def _create_test_registry(path: Path) -> sqlite3.Connection:
    """Create session_registry.db and return an OPEN connection.

    Callers must use ``with closing(_create_test_registry(p)) as conn:``
    to ensure the connection is released even on failure.
    """
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS agents ("
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
        "CREATE TABLE IF NOT EXISTS agent_actions ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "agent_id TEXT NOT NULL, "
        "tool_name TEXT NOT NULL, "
        "target TEXT NOT NULL, "
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
        (
            agent_id,
            session_id,
            role,
            subagent_type,
            workspace_root,
            now - 60,
            last_seen if last_seen is not None else now,
            ended_at,
        ),
    )
    conn.commit()


def _insert_action(conn, agent_id, tool_name, target, ts=None):
    conn.execute(
        "INSERT INTO agent_actions (agent_id, tool_name, target, ts) VALUES (?,?,?,?)",
        (agent_id, tool_name, target, ts if ts is not None else _time.time()),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Part 1 — Reader tests  (PaceMakerReader.get_active_agent_tree)
# ---------------------------------------------------------------------------


class TestGetActiveAgentTreeDbMissing:
    """Returns None when registry DB doesn't exist."""

    def test_returns_none_when_db_missing(self, tmp_path):
        from claude_usage.code_mode.pacemaker_integration import PaceMakerReader

        reader = PaceMakerReader.__new__(PaceMakerReader)
        reader.pm_dir = tmp_path  # no session_registry.db here

        assert reader.get_active_agent_tree() is None


class TestGetActiveAgentTreeEmptyDb:
    """Returns [] when tables exist but no rows."""

    def test_returns_empty_list_when_no_rows(self, tmp_path):
        from claude_usage.code_mode.pacemaker_integration import PaceMakerReader

        registry_path = tmp_path / "session_registry.db"
        with closing(_create_test_registry(registry_path)):
            pass  # create schema then close

        reader = PaceMakerReader.__new__(PaceMakerReader)
        reader.pm_dir = tmp_path

        assert reader.get_active_agent_tree() == []


class TestGetActiveAgentTreeSingleRoot:
    """Returns one root node with correct fields."""

    def test_single_root_fields(self, tmp_path):
        from claude_usage.code_mode.pacemaker_integration import PaceMakerReader

        registry_path = tmp_path / "session_registry.db"
        with closing(_create_test_registry(registry_path)) as conn:
            _insert_agent(conn, "a1", "s1", "root", "/home/user/myproject")

        reader = PaceMakerReader.__new__(PaceMakerReader)
        reader.pm_dir = tmp_path

        result = reader.get_active_agent_tree()

        assert result is not None
        assert len(result) == 1
        root = result[0]
        assert root["agent_id"] == "a1"
        assert root["workspace_root"] == "/home/user/myproject"
        assert root["status"] == "active"
        assert root["subagents"] == []
        assert isinstance(root["actions"], list)


class TestGetActiveAgentTreeWithSubagents:
    """Returns root node with nested subagents."""

    def test_root_with_two_subagents(self, tmp_path):
        from claude_usage.code_mode.pacemaker_integration import PaceMakerReader

        registry_path = tmp_path / "session_registry.db"
        with closing(_create_test_registry(registry_path)) as conn:
            _insert_agent(conn, "root1", "sess1", "root", "/workspace/proj")
            _insert_agent(conn, "sub1", "sess1", "subagent", "/workspace/proj",
                          subagent_type="tdd-engineer")
            _insert_agent(conn, "sub2", "sess1", "subagent", "/workspace/proj",
                          subagent_type="code-reviewer")

        reader = PaceMakerReader.__new__(PaceMakerReader)
        reader.pm_dir = tmp_path

        result = reader.get_active_agent_tree()

        assert len(result) == 1
        root = result[0]
        assert len(root["subagents"]) == 2
        subtypes = {s["subagent_type"] for s in root["subagents"]}
        assert subtypes == {"tdd-engineer", "code-reviewer"}


class TestGetActiveAgentTreeOrphan:
    """Subagent without matching root appears under "(parent ended)"."""

    def test_orphan_subagent_appears_under_parent_ended_group(self, tmp_path):
        from claude_usage.code_mode.pacemaker_integration import PaceMakerReader

        registry_path = tmp_path / "session_registry.db"
        with closing(_create_test_registry(registry_path)) as conn:
            # No matching root for session "orphan_sess"
            _insert_agent(conn, "orph1", "orphan_sess", "subagent", "/some/path",
                          subagent_type="code-surgeon")

        reader = PaceMakerReader.__new__(PaceMakerReader)
        reader.pm_dir = tmp_path

        result = reader.get_active_agent_tree()

        assert result is not None
        orphan_group = next(
            (r for r in result if r.get("label") == "(parent ended)"), None
        )
        assert orphan_group is not None
        assert len(orphan_group["subagents"]) == 1
        assert orphan_group["subagents"][0]["agent_id"] == "orph1"


class TestGetActiveAgentTreeActionsOrder:
    """Actions are returned oldest-to-newest (ascending timestamp)."""

    def test_actions_order_oldest_to_newest(self, tmp_path):
        from claude_usage.code_mode.pacemaker_integration import PaceMakerReader

        registry_path = tmp_path / "session_registry.db"
        now = _time.time()
        with closing(_create_test_registry(registry_path)) as conn:
            _insert_agent(conn, "a1", "s1", "root", "/proj")
            # Insert newest first — result should still be oldest-first
            _insert_action(conn, "a1", "Write", "file3.py", ts=now + 3)
            _insert_action(conn, "a1", "Edit",  "file2.py", ts=now + 2)
            _insert_action(conn, "a1", "Read",  "file1.py", ts=now + 1)

        reader = PaceMakerReader.__new__(PaceMakerReader)
        reader.pm_dir = tmp_path

        result = reader.get_active_agent_tree()

        actions = result[0]["actions"]
        assert len(actions) == 3
        assert actions[0]["tool_name"] == "Read"
        assert actions[1]["tool_name"] == "Edit"
        assert actions[2]["tool_name"] == "Write"


class TestGetActiveAgentTreeCachedTtl:
    """Cached value is returned within 2 s TTL; fresh fetch occurs after expiry."""

    def test_cached_within_ttl(self, tmp_path):
        from claude_usage.code_mode.pacemaker_integration import PaceMakerReader

        registry_path = tmp_path / "session_registry.db"
        with closing(_create_test_registry(registry_path)) as conn:
            _insert_agent(conn, "a1", "s1", "root", "/proj")

        reader = PaceMakerReader.__new__(PaceMakerReader)
        reader.pm_dir = tmp_path

        first = reader.get_active_agent_tree_cached()
        # Remove DB — second call must return the same cached object
        registry_path.unlink()
        second = reader.get_active_agent_tree_cached()

        assert first is not None
        assert second is not None
        assert second is first  # Same list object served from cache

    def test_cache_expires_after_ttl(self, tmp_path):
        from claude_usage.code_mode.pacemaker_integration import PaceMakerReader

        registry_path = tmp_path / "session_registry.db"
        with closing(_create_test_registry(registry_path)) as conn:
            _insert_agent(conn, "a1", "s1", "root", "/proj")

        reader = PaceMakerReader.__new__(PaceMakerReader)
        reader.pm_dir = tmp_path

        first = reader.get_active_agent_tree_cached()
        # Backdate cache timestamp to simulate TTL expiry (10 s > 2 s TTL)
        reader._agent_tree_cache_time = _time.time() - 10
        # Remove DB so fresh call returns None (proves fresh fetch was attempted)
        registry_path.unlink()
        second = reader.get_active_agent_tree_cached()

        assert first is not None
        assert second is None  # Fresh fetch returned None because DB is gone


# ---------------------------------------------------------------------------
# Part 2 — Display function tests
# ---------------------------------------------------------------------------


class TestFormatAction:
    """format_action produces 'ABBREV:target' strings."""

    def test_edit_abbreviation(self):
        from claude_usage.code_mode.display import format_action

        assert format_action({"tool_name": "Edit", "target": "foo.py"}) == "E:foo.py"

    def test_write_abbreviation(self):
        from claude_usage.code_mode.display import format_action

        assert format_action({"tool_name": "Write", "target": "bar.py"}) == "W:bar.py"

    def test_unknown_tool_uses_first_char(self):
        from claude_usage.code_mode.display import format_action

        assert format_action({"tool_name": "Xyzzy", "target": "t"}) == "X:t"

    def test_target_truncated_when_too_long(self):
        from claude_usage.code_mode.display import format_action

        result = format_action(
            {"tool_name": "Read", "target": "very_long_path_name.py"},
            max_target_len=8,
        )
        assert result.endswith("…")
        assert len(result) <= 10  # "R:" + 8 chars

    def test_missing_target_defaults_to_dash(self):
        from claude_usage.code_mode.display import format_action

        assert format_action({"tool_name": "Bash"}) == "B:-"


class TestFormatTrail:
    """format_trail joins action summaries with ' → ' separator."""

    def test_three_actions_joined_with_arrow(self):
        from claude_usage.code_mode.display import format_trail

        actions = [
            {"tool_name": "Read",  "target": "a"},
            {"tool_name": "Edit",  "target": "b"},
            {"tool_name": "Bash",  "target": "c"},
        ]
        result = format_trail(actions)
        assert "→" in result
        assert "R:a" in result
        assert "E:b" in result
        assert "B:c" in result

    def test_empty_returns_idle(self):
        from claude_usage.code_mode.display import format_trail

        assert format_trail([]) == "(idle)"

    def test_single_action_no_separator(self):
        from claude_usage.code_mode.display import format_trail

        result = format_trail([{"tool_name": "Write", "target": "f"}])
        assert "→" not in result
        assert "W:f" in result

    def test_trail_fits_within_budget(self):
        from claude_usage.code_mode.display import format_trail

        actions = [
            {"tool_name": "Edit", "target": "x"},
            {"tool_name": "Bash", "target": "y"},
        ]
        result = format_trail(actions, width_budget=20)
        # Strip Rich markup tags for plain-text length check
        plain = re.sub(r"\[.*?\]", "", result)
        assert len(plain) <= 21  # budget + 1 for possible ellipsis


class TestRenderAgentLine:
    """render_agent_line renders root, subagent, ended, and label nodes."""

    def test_root_line_starts_with_tree_arrow(self):
        from claude_usage.code_mode.display import render_agent_line

        node = {
            "workspace_root": "myproject",
            "actions": [{"tool_name": "Edit", "target": "foo.py"}],
            "status": "active",
            "subagents": [],
        }
        result = render_agent_line(node)
        assert result.startswith("▸")
        assert "myproject" in result

    def test_subagent_line_contains_indent_and_type(self):
        from claude_usage.code_mode.display import render_agent_line

        node = {
            "subagent_type": "tdd-engineer",
            "actions": [{"tool_name": "Write", "target": "test.py"}],
            "status": "active",
        }
        result = render_agent_line(node)
        assert "↳" in result
        assert "tdd-engineer" in result

    def test_ended_line_wrapped_in_dim_markup(self):
        from claude_usage.code_mode.display import render_agent_line

        node = {
            "workspace_root": "proj",
            "actions": [],
            "status": "ended_visible",
            "subagents": [],
        }
        result = render_agent_line(node)
        assert "[dim]" in result

    def test_label_node_renders_label_text(self):
        from claude_usage.code_mode.display import render_agent_line

        node = {
            "label": "(parent ended)",
            "workspace_root": "",
            "status": "ended_visible",
            "subagents": [],
        }
        result = render_agent_line(node)
        assert "(parent ended)" in result


class TestRenderActivityPanel:
    """render_activity_panel handles empty, None, normal, and overflow inputs."""

    def test_empty_tree_returns_no_active_agents(self):
        from claude_usage.code_mode.display import render_activity_panel

        assert render_activity_panel([]) == ["(no active agents)"]

    def test_none_tree_returns_registry_unavailable(self):
        from claude_usage.code_mode.display import render_activity_panel

        assert render_activity_panel(None) == ["(registry unavailable)"]

    def test_single_root_renders_one_line(self):
        from claude_usage.code_mode.display import render_activity_panel

        tree = [
            {
                "workspace_root": "proj",
                "actions": [],
                "status": "active",
                "subagents": [],
            }
        ]
        lines = render_activity_panel(tree)
        assert len(lines) >= 1
        assert any("proj" in line for line in lines)

    def test_overflow_shows_more_agents_line(self):
        from claude_usage.code_mode.display import render_activity_panel

        tree = [
            {
                "workspace_root": f"proj{i}",
                "actions": [],
                "status": "active",
                "subagents": [],
            }
            for i in range(6)
        ]
        lines = render_activity_panel(tree, max_rows=3)
        assert any("more agents" in line for line in lines)

    def test_panel_respects_max_rows(self):
        from claude_usage.code_mode.display import render_activity_panel

        tree = [
            {
                "workspace_root": f"proj{i}",
                "actions": [],
                "status": "active",
                "subagents": [],
            }
            for i in range(20)
        ]
        lines = render_activity_panel(tree, max_rows=5)
        assert len(lines) <= 5
