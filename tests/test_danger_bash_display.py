"""Tests for Danger Bash rules display in usage monitor.

Story #58: Danger Bash Intent Validation — display integration.

Tests verify:
1. danger_bash_rules_count renders in left column (0, N, with breakdown)
2. danger_bash_enabled toggle renders "on"/"off" in Danger Bash line
3. Blockage stats include 'Danger Bash' label from get_blockage_stats_with_labels()
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import tempfile
import time
from pathlib import Path

from claude_usage.code_mode.display import UsageRenderer
from claude_usage.code_mode.pacemaker_integration import (
    DEFAULT_DANGER_BASH_RULES_COUNT,
    PaceMakerReader,
)
from tests.viz_regression_helpers import (
    _make_pacemaker_status,
    _render_to_str,
)

_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


# ---------------------------------------------------------------------------
# Helper: extend _make_pacemaker_status with danger bash fields
# ---------------------------------------------------------------------------


def _make_status_with_danger_bash(
    danger_bash_rules_count: int = DEFAULT_DANGER_BASH_RULES_COUNT,
    danger_bash_rules_breakdown=None,
    danger_bash_enabled: bool = True,
    **kwargs,
) -> dict:
    """Build a pacemaker_status dict that includes danger bash fields."""
    base = _make_pacemaker_status(**kwargs)
    base["danger_bash_rules_count"] = danger_bash_rules_count
    base["danger_bash_rules_breakdown"] = danger_bash_rules_breakdown
    base["danger_bash_enabled"] = danger_bash_enabled
    return base


def _render(pm: dict, blockage_stats: dict | None = None) -> str:
    renderer = UsageRenderer()
    stats = blockage_stats if blockage_stats is not None else {}
    return _render_to_str(renderer.render_bottom_section(pm, stats))


def _danger_bash_line(rendered: str) -> str:
    """Extract the first 'Danger Bash:' line (the on/off status line)."""
    for line in rendered.splitlines():
        if "Danger Bash:" in line:
            return line
    return ""


def _danger_bash_rules_line(rendered: str) -> str:
    """Extract the 'Danger Bash:' rules count line.

    Strips ANSI escape codes before the digit check so that color codes
    (e.g. \\x1b[32m) in the on/off status line are not mistaken for digits.
    """
    for line in rendered.splitlines():
        if "Danger Bash:" in line and any(
            c.isdigit() for c in _ANSI_ESCAPE.sub("", line)
        ):
            return line
    return ""


# ===========================================================================
# Left column — Danger Bash rules count
# ===========================================================================


class TestDangerBashRulesCountDisplay:
    def test_danger_bash_label_present(self):
        rendered = _render(
            _make_status_with_danger_bash(
                danger_bash_rules_count=DEFAULT_DANGER_BASH_RULES_COUNT
            )
        )
        assert "Danger Bash:" in rendered

    def test_danger_bash_count_shown(self):
        rendered = _render(
            _make_status_with_danger_bash(
                danger_bash_rules_count=DEFAULT_DANGER_BASH_RULES_COUNT
            )
        )
        assert str(DEFAULT_DANGER_BASH_RULES_COUNT) in rendered

    def test_danger_bash_zero_shows_zero(self):
        rendered = _render(_make_status_with_danger_bash(danger_bash_rules_count=0))
        assert "Danger Bash:" in rendered
        assert "0" in rendered

    def test_danger_bash_with_breakdown_shows_formula_with_operators(self):
        # total=57, defaults = 57 - custom(3) + deleted(1) = 55, custom=3, deleted=1
        custom_count = 3
        deleted_count = 1
        total = DEFAULT_DANGER_BASH_RULES_COUNT + custom_count - deleted_count
        breakdown = {"custom": custom_count, "deleted": deleted_count}
        rendered = _render(
            _make_status_with_danger_bash(
                danger_bash_rules_count=total,
                danger_bash_rules_breakdown=breakdown,
            )
        )
        # The formula may wrap across Rich cell lines because the column is narrow;
        # verify all components appear somewhere in the rendered section output.
        clean = _ANSI_ESCAPE.sub("", rendered)
        assert "Danger Bash:" in rendered, "Danger Bash label must appear"
        assert str(total) in clean, f"Total count {total} must appear in rendered output"
        assert str(DEFAULT_DANGER_BASH_RULES_COUNT) in clean, "Defaults portion must appear"
        assert f"+ {custom_count}" in clean, "Custom count with '+' operator must appear"
        assert f"- {deleted_count}" in clean, "Deleted count with '-' operator must appear"

    def test_danger_bash_no_breakdown_shows_plain_count_no_formula(self):
        rendered = _render(
            _make_status_with_danger_bash(
                danger_bash_rules_count=DEFAULT_DANGER_BASH_RULES_COUNT,
                danger_bash_rules_breakdown=None,
            )
        )
        line = _danger_bash_rules_line(rendered)
        assert line, "Expected a 'Danger Bash:' rules count line in rendered output"
        # Without breakdown the line must not contain formula operators
        assert "+" not in line


# ===========================================================================
# Left column — Danger Bash enabled toggle
# ===========================================================================


class TestDangerBashEnabledToggle:
    def test_danger_bash_enabled_shows_on(self):
        rendered = _render(_make_status_with_danger_bash(danger_bash_enabled=True))
        line = _danger_bash_line(rendered)
        assert line, "Expected a 'Danger Bash:' line in rendered output"
        assert "on" in line

    def test_danger_bash_disabled_shows_off(self):
        rendered = _render(_make_status_with_danger_bash(danger_bash_enabled=False))
        line = _danger_bash_line(rendered)
        assert line, "Expected a 'Danger Bash:' line in rendered output"
        assert "off" in line


# ===========================================================================
# Blockage stats — Danger Bash label from get_blockage_stats_with_labels()
# ===========================================================================


class TestDangerBashBlockageStats:
    """get_blockage_stats_with_labels() must include 'Danger Bash' label."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "usage.db")
        self.config_path = os.path.join(self.temp_dir, "config.json")
        self._init_db()
        self._create_config()
        self.reader = PaceMakerReader()
        self.reader.pm_dir = Path(self.temp_dir)
        self.reader.db_path = Path(self.db_path)
        self.reader.config_path = Path(self.config_path)

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS blockage_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp INTEGER NOT NULL,
                    category TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    hook_type TEXT NOT NULL,
                    session_id TEXT NOT NULL
                )"""
            )

    def _create_config(self):
        with open(self.config_path, "w") as f:
            json.dump({"enabled": True}, f)

    def _insert_event(self, category: str, minutes_ago: int = 0):
        ts = int(time.time()) - minutes_ago * 60
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO blockage_events "
                "(timestamp, category, reason, hook_type, session_id) "
                "VALUES (?, ?, 'test', 'pre_tool_use', 'sess')",
                (ts, category),
            )

    def test_danger_bash_label_in_blockage_stats_with_labels(self):
        result = self.reader.get_blockage_stats_with_labels()
        assert result is not None
        assert "Danger Bash" in result

    def test_danger_bash_count_zero_when_no_events(self):
        result = self.reader.get_blockage_stats_with_labels()
        assert result is not None
        assert result["Danger Bash"] == 0

    def test_danger_bash_count_increments_on_dangerbash_event(self):
        self._insert_event("intent_validation_dangerbash")
        self._insert_event("intent_validation_dangerbash")
        result = self.reader.get_blockage_stats_with_labels()
        assert result is not None
        assert result["Danger Bash"] == 2
