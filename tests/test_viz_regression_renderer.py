"""Regression tests for UsageRenderer.render() — Sections C and D.

Tests the real rendering code with no mocks.  All inputs are plain Python
dicts/lists built by the helper factories in viz_regression_helpers.py.
Output is inspected by rendering to a captured string via Console.
"""

from __future__ import annotations

from rich.console import Group
from rich.text import Text

from claude_usage.code_mode.display import UsageRenderer

from tests.viz_regression_helpers import (
    _future_iso,
    _make_pacemaker_status,
    _make_profile,
    _make_usage,
    _past_iso,
    _render_to_str,
)

ARROW = "\u25b8"  # ▸
TRIANGLE = "\u25b3"  # △


# ===========================================================================
# C1 — Return types
# ===========================================================================


class TestRendererRenderReturnTypes:
    def setup_method(self):
        self.r = UsageRenderer()

    def test_returns_text_when_no_usage_no_error(self):
        result = self.r.render(None, None, None, None)
        assert isinstance(result, Text)

    def test_returns_group_when_usage_present(self):
        result = self.r.render(None, _make_usage(), None, None)
        assert isinstance(result, Group)

    def test_returns_group_when_error_and_profile_no_usage(self):
        result = self.r.render("Something broke", None, _make_profile(), None)
        assert isinstance(result, Group)


# ===========================================================================
# C2 — Fetching state
# ===========================================================================


class TestRendererRenderFetchingState:
    def setup_method(self):
        self.r = UsageRenderer()

    def test_fetching_message_present_when_no_data(self):
        result = self.r.render(None, None, None, None)
        assert "Fetching usage data" in result.plain

    def test_fetching_message_absent_when_error_present(self):
        rendered = _render_to_str(self.r.render("Network error", None, None, None))
        assert "Fetching usage data" not in rendered


# ===========================================================================
# C3 — Error messages
# ===========================================================================


class TestRendererRenderErrorMessages:
    def setup_method(self):
        self.r = UsageRenderer()

    def test_error_shown_with_usage(self):
        rendered = _render_to_str(
            self.r.render("Rate limit exceeded", _make_usage(), None, None)
        )
        assert "Rate limit exceeded" in rendered

    def test_error_includes_triangle_indicator(self):
        rendered = _render_to_str(self.r.render("Bad token", _make_usage(), None, None))
        assert TRIANGLE in rendered

    def test_error_with_no_usage_shows_profile_name(self):
        rendered = _render_to_str(
            self.r.render("API down", None, _make_profile(), None)
        )
        assert "API down" in rendered
        assert "Alice" in rendered

    def test_no_error_no_triangle(self):
        rendered = _render_to_str(self.r.render(None, _make_usage(), None, None))
        assert TRIANGLE not in rendered


# ===========================================================================
# C4 — Profile section
# ===========================================================================


class TestRendererRenderProfileSection:
    def setup_method(self):
        self.r = UsageRenderer()

    def test_name_and_email_shown(self):
        rendered = _render_to_str(
            self.r.render(None, _make_usage(), _make_profile(), None)
        )
        assert "Alice" in rendered
        assert "alice@example.com" in rendered

    def test_org_name_shown(self):
        rendered = _render_to_str(
            self.r.render(
                None, _make_usage(), _make_profile(org_name="Acme Corp"), None
            )
        )
        assert "Acme Corp" in rendered

    def test_max_badge_shown(self):
        rendered = _render_to_str(
            self.r.render(None, _make_usage(), _make_profile(has_max=True), None)
        )
        assert "MAX" in rendered

    def test_enterprise_badge_shown(self):
        rendered = _render_to_str(
            self.r.render(
                None,
                _make_usage(),
                _make_profile(org_type="claude_enterprise", has_max=False),
                None,
            )
        )
        assert "ENTERPRISE" in rendered

    def test_no_profile_no_email_in_output(self):
        rendered = _render_to_str(self.r.render(None, _make_usage(), None, None))
        assert "alice@example.com" not in rendered

    def test_very_long_org_name_no_crash(self):
        rendered = _render_to_str(
            self.r.render(None, _make_usage(), _make_profile(org_name="A" * 200), None)
        )
        assert rendered  # must produce something

    def test_organization_word_stripped_from_display_name(self):
        profile = _make_profile(display_name="Organization Alice")
        rendered = _render_to_str(self.r.render(None, _make_usage(), profile, None))
        assert "Alice" in rendered


# ===========================================================================
# C5 — Activity line integration
# ===========================================================================


class TestRendererRenderActivityLine:
    def setup_method(self):
        self.r = UsageRenderer()

    def test_activity_line_present_when_events_provided(self):
        events = [{"event_code": "IV", "status": "green"}]
        rendered = _render_to_str(
            self.r.render(
                None, _make_usage(), _make_profile(), None, activity_events=events
            )
        )
        assert ARROW in rendered
        assert "IV" in rendered

    def test_activity_line_absent_when_events_is_none(self):
        rendered = _render_to_str(
            self.r.render(
                None, _make_usage(), _make_profile(), None, activity_events=None
            )
        )
        assert ARROW not in rendered

    def test_activity_line_shows_all_codes_for_empty_list(self):
        rendered = _render_to_str(
            self.r.render(
                None, _make_usage(), _make_profile(), None, activity_events=[]
            )
        )
        for code in ["IV", "TD", "CC", "ST", "CX"]:
            assert code in rendered

    def test_activity_line_after_profile_before_progress_bar(self):
        events = [{"event_code": "IV", "status": "green"}]
        rendered = _render_to_str(
            self.r.render(
                None, _make_usage(), _make_profile(), None, activity_events=events
            )
        )
        alice_pos = rendered.find("Alice")
        arrow_pos = rendered.find(ARROW)
        five_pos = rendered.find("5-Hour")
        assert alice_pos != -1 and arrow_pos != -1 and five_pos != -1
        assert (
            alice_pos < arrow_pos < five_pos
        ), f"Order wrong: Alice@{alice_pos} arrow@{arrow_pos} 5-Hour@{five_pos}"


# ===========================================================================
# C6 — Progress bars
# ===========================================================================


class TestRendererRenderProgressBars:
    def setup_method(self):
        self.r = UsageRenderer()

    def test_five_hour_label_present(self):
        rendered = _render_to_str(
            self.r.render(None, _make_usage(five_util=50), None, None)
        )
        assert "5-Hour" in rendered

    def test_seven_day_label_present(self):
        rendered = _render_to_str(
            self.r.render(None, _make_usage(seven_util=30), None, None)
        )
        assert "7-Day" in rendered

    def test_five_hour_percentage(self):
        rendered = _render_to_str(
            self.r.render(None, _make_usage(five_util=42), None, None)
        )
        assert "42%" in rendered

    def test_seven_day_percentage(self):
        rendered = _render_to_str(
            self.r.render(None, _make_usage(seven_util=77), None, None)
        )
        assert "77%" in rendered

    def test_zero_percent(self):
        rendered = _render_to_str(
            self.r.render(None, _make_usage(five_util=0), None, None)
        )
        assert "0%" in rendered

    def test_hundred_percent(self):
        rendered = _render_to_str(
            self.r.render(None, _make_usage(five_util=100), None, None)
        )
        assert "100%" in rendered

    def test_fractional_rounds(self):
        rendered = _render_to_str(
            self.r.render(None, _make_usage(five_util=50.5), None, None)
        )
        assert "51%" in rendered or "50%" in rendered

    def test_no_bars_when_no_usage(self):
        rendered = _render_to_str(self.r.render("Error", None, _make_profile(), None))
        assert "5-Hour" not in rendered
        assert "7-Day" not in rendered


# ===========================================================================
# C7 — Reset times
# ===========================================================================


class TestRendererRenderResetTimes:
    def setup_method(self):
        self.r = UsageRenderer()

    def test_resets_in_shown_for_future_five_hour(self):
        rendered = _render_to_str(
            self.r.render(None, _make_usage(five_resets=_future_iso(2.5)), None, None)
        )
        assert "Resets in" in rendered

    def test_resets_in_with_days_for_future_seven_day(self):
        rendered = _render_to_str(
            self.r.render(None, _make_usage(seven_resets=_future_iso(50)), None, None)
        )
        assert "Resets in" in rendered
        assert "d" in rendered

    def test_window_expired_for_past_reset(self):
        rendered = _render_to_str(
            self.r.render(None, _make_usage(five_resets=_past_iso(1)), None, None)
        )
        assert "Window expired" in rendered

    def test_no_countdown_when_resets_at_empty(self):
        usage = {"five_hour": {"utilization": 40, "resets_at": ""}}
        rendered = _render_to_str(self.r.render(None, usage, None, None))
        assert "Resets in" not in rendered


# ===========================================================================
# C8 — Weekly limit / five-hour limiter disabled indicators
# ===========================================================================


class TestRendererRenderLimitIndicators:
    def setup_method(self):
        self.r = UsageRenderer()

    def test_weekly_limit_disabled_shows_disabled(self):
        rendered = _render_to_str(
            self.r.render(None, _make_usage(), None, None, weekly_limit_enabled=False)
        )
        assert "disabled" in rendered

    def test_five_hour_limiter_disabled_via_pacemaker(self):
        pm = _make_pacemaker_status(five_hour_limit_enabled=False)
        rendered = _render_to_str(
            self.r.render(None, _make_usage(), None, None, pacemaker_status=pm)
        )
        assert "disabled" in rendered


# ===========================================================================
# C9 — Pacemaker section
# ===========================================================================


class TestRendererRenderPacemakerSection:
    def setup_method(self):
        self.r = UsageRenderer()

    def test_on_pace_badge(self):
        rendered = _render_to_str(
            self.r.render(
                None,
                _make_usage(),
                None,
                None,
                pacemaker_status=_make_pacemaker_status(should_throttle=False),
            )
        )
        assert "Pace Maker" in rendered
        assert "ON PACE" in rendered

    def test_throttling_badge(self):
        rendered = _render_to_str(
            self.r.render(
                None,
                _make_usage(),
                None,
                None,
                pacemaker_status=_make_pacemaker_status(should_throttle=True),
            )
        )
        assert "THROTTLING" in rendered

    def test_delay_seconds_shown_when_throttling(self):
        pm = _make_pacemaker_status(should_throttle=True, delay_seconds=45)
        rendered = _render_to_str(
            self.r.render(None, _make_usage(), None, None, pacemaker_status=pm)
        )
        assert "45s" in rendered

    def test_disabled_shows_inactive(self):
        pm = _make_pacemaker_status(enabled=False)
        rendered = _render_to_str(
            self.r.render(None, _make_usage(), None, None, pacemaker_status=pm)
        )
        assert "INACTIVE" in rendered

    def test_no_data_shows_message(self):
        pm = _make_pacemaker_status(has_data=False)
        rendered = _render_to_str(
            self.r.render(None, _make_usage(), None, None, pacemaker_status=pm)
        )
        assert "No usage data yet" in rendered

    def test_none_pacemaker_skips_section(self):
        rendered = _render_to_str(
            self.r.render(None, _make_usage(), None, None, pacemaker_status=None)
        )
        assert "Pace Maker" not in rendered

    def test_empty_dict_pacemaker_no_crash(self):
        # An empty dict is falsy in Python, so the pacemaker section is skipped entirely.
        # The render should still produce progress-bar output without crashing.
        rendered = _render_to_str(
            self.r.render(None, _make_usage(), None, None, pacemaker_status={})
        )
        assert "5-Hour" in rendered  # progress bars still rendered
        assert "Pace Maker" not in rendered  # section skipped — empty dict is falsy

    def test_error_key_shows_error_badge(self):
        pm = {"error": "Database unavailable", "has_data": True}
        rendered = _render_to_str(
            self.r.render(None, _make_usage(), None, None, pacemaker_status=pm)
        )
        assert "ERROR" in rendered
        assert "Database unavailable" in rendered

    def test_deviation_under_budget(self):
        pm = _make_pacemaker_status(five_hour_target=80.0, constrained_window="5-hour")
        rendered = _render_to_str(
            self.r.render(
                None, _make_usage(five_util=40.0), None, None, pacemaker_status=pm
            )
        )
        assert "under budget" in rendered

    def test_deviation_over_budget(self):
        pm = _make_pacemaker_status(five_hour_target=20.0, constrained_window="5-hour")
        rendered = _render_to_str(
            self.r.render(
                None, _make_usage(five_util=90.0), None, None, pacemaker_status=pm
            )
        )
        assert "over budget" in rendered


# ===========================================================================
# C10 — Layout order
# ===========================================================================


class TestRendererRenderLayoutOrder:
    def setup_method(self):
        self.r = UsageRenderer()

    def test_error_before_profile(self):
        rendered = _render_to_str(
            self.r.render("Boom", _make_usage(), _make_profile(), None)
        )
        assert rendered.find("Boom") < rendered.find("Alice")

    def test_profile_before_five_hour_bar(self):
        rendered = _render_to_str(
            self.r.render(None, _make_usage(), _make_profile(), None)
        )
        assert rendered.find("Alice") < rendered.find("5-Hour")

    def test_five_hour_before_seven_day(self):
        rendered = _render_to_str(self.r.render(None, _make_usage(), None, None))
        assert rendered.find("5-Hour") < rendered.find("7-Day")

    def test_seven_day_before_pacemaker(self):
        pm = _make_pacemaker_status()
        rendered = _render_to_str(
            self.r.render(None, _make_usage(), None, None, pacemaker_status=pm)
        )
        assert rendered.find("7-Day") < rendered.find("Pace Maker")

    def test_full_order_all_sections(self):
        events = [{"event_code": "IV", "status": "green"}]
        pm = _make_pacemaker_status()
        rendered = _render_to_str(
            self.r.render(
                "Warn",
                _make_usage(),
                _make_profile(),
                None,
                pacemaker_status=pm,
                activity_events=events,
            )
        )
        pos = {
            "error": rendered.find("Warn"),
            "profile": rendered.find("Alice"),
            "activity": rendered.find(ARROW),
            "5h": rendered.find("5-Hour"),
            "7d": rendered.find("7-Day"),
            "pace": rendered.find("Pace Maker"),
        }
        assert all(v != -1 for v in pos.values()), f"Missing sections: {pos}"
        assert (
            pos["error"]
            < pos["profile"]
            < pos["activity"]
            < pos["5h"]
            < pos["7d"]
            < pos["pace"]
        ), f"Order violated: {pos}"


# ===========================================================================
# D — Edge cases
# ===========================================================================


class TestRendererRenderEdgeCases:
    def setup_method(self):
        self.r = UsageRenderer()

    def test_missing_utilization_defaults_to_zero(self):
        usage = {"five_hour": {"resets_at": _future_iso()}}
        rendered = _render_to_str(self.r.render(None, usage, None, None))
        assert "0%" in rendered

    def test_missing_resets_at_no_countdown(self):
        usage = {"five_hour": {"utilization": 50}}
        rendered = _render_to_str(self.r.render(None, usage, None, None))
        assert "Resets in" not in rendered

    def test_no_five_hour_key_skips_bar(self):
        usage = {"seven_day": {"utilization": 30, "resets_at": _future_iso(48)}}
        rendered = _render_to_str(self.r.render(None, usage, None, None))
        assert "5-Hour" not in rendered
        assert "7-Day" in rendered

    def test_no_seven_day_key_skips_bar(self):
        usage = {"five_hour": {"utilization": 40, "resets_at": _future_iso(2)}}
        rendered = _render_to_str(self.r.render(None, usage, None, None))
        assert "7-Day" not in rendered
        assert "5-Hour" in rendered

    def test_partial_pacemaker_dict_no_crash(self):
        pm = {"enabled": True, "has_data": True}
        rendered = _render_to_str(
            self.r.render(None, _make_usage(), None, None, pacemaker_status=pm)
        )
        assert "Pace Maker" in rendered

    def test_empty_profile_fields_no_crash(self):
        profile = {"account": {}, "organization": {}}
        rendered = _render_to_str(self.r.render(None, _make_usage(), profile, None))
        assert rendered

    def test_sonnet_model_limit_rendered(self):
        usage = dict(_make_usage())
        usage["seven_day_sonnet"] = {"utilization": 55, "resets_at": _future_iso(24)}
        rendered = _render_to_str(self.r.render(None, usage, None, None))
        assert "Sonnet" in rendered

    def test_opus_model_limit_rendered(self):
        usage = dict(_make_usage())
        usage["seven_day_opus"] = {"utilization": 20, "resets_at": _future_iso(24)}
        rendered = _render_to_str(self.r.render(None, usage, None, None))
        assert "Opus" in rendered
