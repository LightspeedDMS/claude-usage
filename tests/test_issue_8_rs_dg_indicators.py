"""Tests for issue #8: render pace-maker RS and DG events in the monitor.

pace-maker 2.36.x records two activity/governance event codes this monitor
did not know about yet:

- ``RS`` — Reasoning-Summary intent exception (issue #151): an APPROVED
  verdict reached via a reasoning-summary / visible-text intent source
  rather than a formal ``INTENT:`` declaration. Recorded with status
  ``"green"`` (pace-maker hook.py:2693).
- ``DG`` — Degraded review (issue #131): an APPROVED verdict where one or
  more verifiers failed to respond. Recorded with status ``"yellow"``
  (pace-maker hook.py:2651).

Before this fix:
- ``_ACTIVITY_GROUPS`` had no ``RS``/``DG`` entry, so neither ever appeared
  on the activity indicator line (``_get_all_known_codes()`` filters unknown
  codes out entirely).
- ``_STATUS_STYLES`` had no ``"yellow"`` entry, so even if the code were
  known, an active ``DG`` event would render with the dim/idle style instead
  of a distinct color.
- ``_ICON_MAP`` in ``render_event_feed`` had no ``"RS"``/``"DG"`` entry, so
  governance events of those types rendered with the fallback ``"?"`` icon.

These tests exercise the real rendering functions with no mocking.
"""

from __future__ import annotations

import time

from rich.text import Text

from claude_usage.code_mode.display import (
    UsageRenderer,
    render_activity_line,
    _ACTIVITY_GROUPS,
    _STATUS_STYLES,
    _get_all_known_codes,
)


def _make_governance_event(event_type, project="proj", feedback="Approved", ts=None):
    return {
        "event_type": event_type,
        "project_name": project,
        "session_id": "sess-1",
        "feedback_text": feedback,
        "timestamp": ts or time.time(),
    }


def _span_styles_for(text_obj: Text, substring: str) -> list:
    plain = text_obj.plain
    start = plain.find(substring)
    if start == -1:
        return []
    end = start + len(substring)
    return [str(s.style) for s in text_obj._spans if s.start <= start and s.end >= end]


class TestActivityGroupsKnowRSAndDG:
    """RS and DG must be registered as known activity codes."""

    def test_rs_is_a_known_code(self):
        assert "RS" in _get_all_known_codes()

    def test_dg_is_a_known_code(self):
        assert "DG" in _get_all_known_codes()

    def test_rs_and_dg_grouped_next_to_intent_validation_indicators(self):
        """RS/DG live in the same visual group as IV/TD/CC (PreToolUse review)."""
        iv_group = next(g for g in _ACTIVITY_GROUPS if "IV" in g)
        assert "RS" in iv_group
        assert "DG" in iv_group


class TestActivityLineRendersRSAndDG:
    """render_activity_line() must display RS and DG codes and colors."""

    def test_rs_appears_when_idle(self):
        plain = render_activity_line([]).plain
        assert "RS" in plain

    def test_dg_appears_when_idle(self):
        plain = render_activity_line([]).plain
        assert "DG" in plain

    def test_rs_active_green_style(self):
        result = render_activity_line([{"event_code": "RS", "status": "green"}])
        assert "RS" in result.plain
        styles = _span_styles_for(result, "RS")
        assert any("green" in s for s in styles), f"Expected green on RS, got: {styles}"

    def test_dg_active_yellow_style(self):
        result = render_activity_line([{"event_code": "DG", "status": "yellow"}])
        assert "DG" in result.plain
        styles = _span_styles_for(result, "DG")
        assert any(
            "yellow" in s for s in styles
        ), f"Expected yellow on DG, got: {styles}"

    def test_rs_inactive_is_dim_not_colored(self):
        result = render_activity_line([])
        styles = _span_styles_for(result, "RS")
        assert not any(
            "green" in s or "red" in s or "blue" in s or "yellow" in s for s in styles
        ), f"Inactive RS should be dim, not colored. Got: {styles}"

    def test_existing_iv_td_cc_unaffected_by_new_codes(self):
        """Adding RS/DG must not change IV/TD/CC's own color behavior."""
        events = [
            {"event_code": "IV", "status": "green"},
            {"event_code": "TD", "status": "green"},
            {"event_code": "CC", "status": "red"},
        ]
        result = render_activity_line(events)
        assert any("green" in s for s in _span_styles_for(result, "IV"))
        assert any("green" in s for s in _span_styles_for(result, "TD"))
        assert any("red" in s for s in _span_styles_for(result, "CC"))

    def test_status_styles_has_yellow_entry(self):
        assert "yellow" in _STATUS_STYLES
        assert "yellow" in _STATUS_STYLES["yellow"]


class TestGovernanceFeedRSAndDGIcons:
    """render_event_feed() must give RS/DG events a real icon, not '?'."""

    def test_rs_icon_is_not_question_mark(self):
        renderer = UsageRenderer()
        events = [_make_governance_event("RS")]
        result = renderer.render_event_feed(events, available_width=60)
        text = result.plain
        header_line = text.splitlines()[0]
        assert "RS" in header_line
        icon = header_line.split(" ", 1)[0]
        assert icon != "?"

    def test_dg_icon_is_not_question_mark(self):
        renderer = UsageRenderer()
        events = [_make_governance_event("DG", feedback="Degraded approval")]
        result = renderer.render_event_feed(events, available_width=60)
        text = result.plain
        header_line = text.splitlines()[0]
        assert "DG" in header_line
        icon = header_line.split(" ", 1)[0]
        assert icon != "?"

    def test_rs_and_dg_icons_are_distinct_from_each_other_and_existing(self):
        renderer = UsageRenderer()
        rs_result = renderer.render_event_feed(
            [_make_governance_event("RS")], available_width=60
        )
        dg_result = renderer.render_event_feed(
            [_make_governance_event("DG")], available_width=60
        )
        iv_result = renderer.render_event_feed(
            [_make_governance_event("IV")], available_width=60
        )
        rs_icon = rs_result.plain.splitlines()[0].split(" ", 1)[0]
        dg_icon = dg_result.plain.splitlines()[0].split(" ", 1)[0]
        iv_icon = iv_result.plain.splitlines()[0].split(" ", 1)[0]
        assert rs_icon != dg_icon
        assert rs_icon != iv_icon
        assert dg_icon != iv_icon

    def test_existing_iv_td_cc_icons_unchanged(self):
        """Adding RS/DG icons must not change the pre-existing icon mapping."""
        renderer = UsageRenderer()
        iv_text = renderer.render_event_feed(
            [_make_governance_event("IV")], available_width=60
        ).plain
        td_text = renderer.render_event_feed(
            [_make_governance_event("TD")], available_width=60
        ).plain
        cc_text = renderer.render_event_feed(
            [_make_governance_event("CC")], available_width=60
        ).plain
        assert "✖" in iv_text
        assert "⚠" in td_text
        assert "⟡" in cc_text
