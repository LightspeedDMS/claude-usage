"""Regression tests for render_activity_line() — Section A.

Tests the real rendering code with no mocks.  Input is a plain list of
event dicts; output is inspected via .plain and ._spans on the returned
Rich Text object.

Groups spec: IV·TD·CC ST·CX PA·PL LF SS·SM SE·SA·UP  (13 codes total)
"""

from __future__ import annotations

from rich.text import Text

from claude_usage.code_mode.display import render_activity_line

# Unicode constants used throughout
ARROW = "\u25b8"  # ▸
DOT = "\u00b7"  # ·

ALL_CODES = [
    "IV",
    "TD",
    "CC",
    "ST",
    "CX",
    "PA",
    "PL",
    "LF",
    "SS",
    "SM",
    "SE",
    "SA",
    "UP",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _span_styles_for(text_obj: Text, substring: str) -> list[str]:
    """Return styles of every span that fully covers *substring*."""
    plain = text_obj.plain
    start = plain.find(substring)
    if start == -1:
        return []
    end = start + len(substring)
    return [str(s.style) for s in text_obj._spans if s.start <= start and s.end >= end]


# ===========================================================================
# Return type
# ===========================================================================


class TestRenderActivityLineReturnType:
    def test_returns_rich_text_for_empty_list(self):
        assert isinstance(render_activity_line([]), Text)

    def test_returns_rich_text_for_non_empty_list(self):
        result = render_activity_line([{"event_code": "IV", "status": "green"}])
        assert isinstance(result, Text)


# ===========================================================================
# Prefix arrow
# ===========================================================================


class TestRenderActivityLinePrefix:
    def test_prefix_present_empty_events(self):
        assert ARROW in render_activity_line([]).plain

    def test_prefix_present_with_events(self):
        events = [{"event_code": "SE", "status": "green"}]
        assert ARROW in render_activity_line(events).plain

    def test_prefix_at_start(self):
        assert render_activity_line([]).plain.startswith(ARROW)


# ===========================================================================
# All 13 codes always appear
# ===========================================================================


class TestRenderActivityLineAllCodesPresent:
    def test_all_codes_present_when_no_events(self):
        plain = render_activity_line([]).plain
        for code in ALL_CODES:
            assert code in plain, f"Code {code!r} missing from empty-events output"

    def test_all_codes_present_when_all_active(self):
        events = [{"event_code": c, "status": "green"} for c in ALL_CODES]
        plain = render_activity_line(events).plain
        for code in ALL_CODES:
            assert code in plain, f"Code {code!r} missing from all-active output"


# ===========================================================================
# Single active events
# ===========================================================================


class TestRenderActivityLineSingleEvents:
    def test_single_green_iv(self):
        assert (
            "IV"
            in render_activity_line([{"event_code": "IV", "status": "green"}]).plain
        )

    def test_single_red_st(self):
        assert (
            "ST" in render_activity_line([{"event_code": "ST", "status": "red"}]).plain
        )

    def test_single_blue_lf(self):
        assert (
            "LF" in render_activity_line([{"event_code": "LF", "status": "blue"}]).plain
        )

    def test_inactive_codes_still_present_when_one_active(self):
        """When IV is active the other 12 codes still appear (dim)."""
        plain = render_activity_line([{"event_code": "IV", "status": "green"}]).plain
        inactive = [c for c in ALL_CODES if c != "IV"]
        for code in inactive:
            assert code in plain, f"Inactive code {code!r} should still appear"


# ===========================================================================
# Style assertions
# ===========================================================================


class TestRenderActivityLineStyles:
    def test_green_event_has_green_style(self):
        result = render_activity_line([{"event_code": "IV", "status": "green"}])
        styles = _span_styles_for(result, "IV")
        assert any("green" in s for s in styles), f"Expected green on IV, got: {styles}"

    def test_red_event_has_red_style(self):
        result = render_activity_line([{"event_code": "ST", "status": "red"}])
        styles = _span_styles_for(result, "ST")
        assert any("red" in s for s in styles), f"Expected red on ST, got: {styles}"

    def test_blue_event_has_blue_style(self):
        result = render_activity_line([{"event_code": "LF", "status": "blue"}])
        styles = _span_styles_for(result, "LF")
        assert any("blue" in s for s in styles), f"Expected blue on LF, got: {styles}"

    def test_inactive_code_not_colored(self):
        """With no events every code should be dim — no green/red/blue."""
        result = render_activity_line([])
        styles = _span_styles_for(result, "TD")
        assert not any(
            "green" in s or "red" in s or "blue" in s for s in styles
        ), f"Inactive code should be dim, not colored. Got: {styles}"

    def test_unknown_status_does_not_crash(self):
        """Unrecognised status falls back gracefully; IV still appears."""
        result = render_activity_line([{"event_code": "IV", "status": "purple"}])
        assert "IV" in result.plain


# ===========================================================================
# Group separators (dots within groups, spaces between groups)
# ===========================================================================


class TestRenderActivityLineGroupSeparators:
    def test_dots_within_groups(self):
        assert DOT in render_activity_line([]).plain

    def test_iv_td_cc_joined_by_dots(self):
        plain = render_activity_line([]).plain
        assert f"IV{DOT}TD{DOT}CC" in plain

    def test_st_cx_joined_by_dot(self):
        plain = render_activity_line([]).plain
        assert f"ST{DOT}CX" in plain

    def test_pa_pl_joined_by_dot(self):
        plain = render_activity_line([]).plain
        assert f"PA{DOT}PL" in plain

    def test_ss_sm_joined_by_dot(self):
        plain = render_activity_line([]).plain
        assert f"SS{DOT}SM" in plain

    def test_se_sa_up_joined_by_dots(self):
        plain = render_activity_line([]).plain
        assert f"SE{DOT}SA{DOT}UP" in plain

    def test_space_between_group_1_and_2(self):
        """After CC (end of group 1) there should be a space before ST."""
        assert "CC ST" in render_activity_line([]).plain

    def test_full_canonical_layout(self):
        expected = f"{ARROW} IV{DOT}TD{DOT}CC ST{DOT}CX PA{DOT}PL LF SS{DOT}SM SE{DOT}SA{DOT}UP"
        assert expected in render_activity_line([]).plain


# ===========================================================================
# Unknown / edge-case event codes
# ===========================================================================


class TestRenderActivityLineUnknownCodes:
    def test_unknown_code_zz_not_in_output(self):
        events = [
            {"event_code": "IV", "status": "green"},
            {"event_code": "ZZ", "status": "green"},
        ]
        plain = render_activity_line(events).plain
        assert "IV" in plain
        assert "ZZ" not in plain

    def test_only_unknown_codes_still_renders_all_known(self):
        events = [{"event_code": "XX", "status": "green"}]
        plain = render_activity_line(events).plain
        for code in ["IV", "TD", "CC", "ST", "CX"]:
            assert code in plain

    def test_empty_event_code_no_crash(self):
        result = render_activity_line([{"event_code": "", "status": "green"}])
        assert isinstance(result, Text)

    def test_duplicate_code_last_status_wins(self):
        """Dict update semantics: last occurrence overwrites earlier status."""
        events = [
            {"event_code": "IV", "status": "red"},
            {"event_code": "IV", "status": "green"},
        ]
        result = render_activity_line(events)
        plain = result.plain
        idx = plain.find("IV")
        styles = [str(s.style) for s in result._spans if s.start <= idx < s.end]
        assert any(
            "green" in s for s in styles
        ), f"Expected green after override, got: {styles}"


# ===========================================================================
# Mixed groups — multiple events across different groups
# ===========================================================================


class TestRenderActivityLineMixedGroups:
    def test_iv_td_green_cc_red_independent_styles(self):
        events = [
            {"event_code": "IV", "status": "green"},
            {"event_code": "TD", "status": "green"},
            {"event_code": "CC", "status": "red"},
        ]
        result = render_activity_line(events)
        plain = result.plain
        assert "IV" in plain and "TD" in plain and "CC" in plain
        idx = plain.find("CC")
        red_spans = [
            s for s in result._spans if s.start <= idx < s.end and "red" in str(s.style)
        ]
        assert red_spans, "CC should carry a red style"

    def test_all_13_active_mixed_statuses_all_codes_present(self):
        events = [
            {"event_code": "IV", "status": "green"},
            {"event_code": "TD", "status": "green"},
            {"event_code": "CC", "status": "red"},
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
        plain = render_activity_line(events).plain
        for e in events:
            assert e["event_code"] in plain
