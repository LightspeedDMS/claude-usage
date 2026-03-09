"""Regression tests for error + usage coexistence.

Verifies that progress bars (5-hour, 7-day) ALWAYS render when usage data
is available, even when an error message is present (API throttle, backoff,
timeout, etc.).  This was a critical bug: error_message caused the renderer
to bail out before drawing progress bars.

Also tests the monitor-level logic that preserves last_usage during errors.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from rich.console import Group
from rich.text import Text

from claude_usage.code_mode.display import UsageRenderer

from tests.viz_regression_helpers import (
    _future_iso,
    _make_pacemaker_status,
    _make_profile,
    _make_usage,
    _render_to_str,
)


ARROW = "\u25b8"  # ▸


# ===========================================================================
# E1 — Error message + usage data: progress bars must render
# ===========================================================================


class TestErrorWithUsageProgressBars:
    """When both error_message and last_usage are provided, the renderer
    must show BOTH the error AND the progress bars."""

    def setup_method(self):
        self.r = UsageRenderer()

    def test_error_and_usage_returns_group(self):
        result = self.r.render(
            "API rate limited (429) after retries",
            _make_usage(),
            _make_profile(),
            datetime.now(timezone.utc),
        )
        assert isinstance(result, Group)

    def test_error_message_shown_when_usage_present(self):
        result = self.r.render(
            "API rate limited (429) after retries",
            _make_usage(),
            _make_profile(),
            datetime.now(timezone.utc),
        )
        text = _render_to_str(result)
        assert "API rate limited" in text

    def test_five_hour_bar_shown_with_error(self):
        result = self.r.render(
            "API rate limited (429) after retries",
            _make_usage(five_util=40.0),
            _make_profile(),
            datetime.now(timezone.utc),
        )
        text = _render_to_str(result)
        assert "5-Hour" in text
        assert "40" in text

    def test_seven_day_bar_shown_with_error(self):
        result = self.r.render(
            "API rate limited (429) after retries",
            _make_usage(seven_util=75.0),
            _make_profile(),
            datetime.now(timezone.utc),
        )
        text = _render_to_str(result)
        assert "7-Day" in text

    def test_profile_shown_with_error(self):
        result = self.r.render(
            "API rate limited (429) after retries",
            _make_usage(),
            _make_profile(display_name="TestUser"),
            datetime.now(timezone.utc),
        )
        text = _render_to_str(result)
        assert "TestUser" in text

    def test_backoff_error_with_usage_shows_both(self):
        result = self.r.render(
            "API backoff (pace-maker): 450s remaining",
            _make_usage(five_util=12.0, seven_util=60.0),
            _make_profile(),
            datetime.now(timezone.utc),
        )
        text = _render_to_str(result)
        assert "backoff" in text.lower()
        assert "5-Hour" in text
        assert "7-Day" in text

    def test_timeout_error_with_usage_shows_both(self):
        result = self.r.render(
            "Request timeout after 30s",
            _make_usage(five_util=5.0),
            _make_profile(),
            datetime.now(timezone.utc),
        )
        text = _render_to_str(result)
        assert "timeout" in text.lower()
        assert "5-Hour" in text

    def test_activity_line_shown_with_error_and_usage(self):
        events = [
            {"event_code": "IV", "status": "green"},
            {"event_code": "LF", "status": "blue"},
        ]
        result = self.r.render(
            "API error 500",
            _make_usage(),
            _make_profile(),
            datetime.now(timezone.utc),
            activity_events=events,
        )
        text = _render_to_str(result)
        assert ARROW in text
        assert "IV" in text

    def test_pacemaker_status_shown_with_error_and_usage(self):
        result = self.r.render(
            "API rate limited (429)",
            _make_usage(),
            _make_profile(),
            datetime.now(timezone.utc),
            pacemaker_status=_make_pacemaker_status(),
        )
        text = _render_to_str(result)
        assert "pace maker" in text.lower()


# ===========================================================================
# E2 — Error only (no usage data): graceful degradation
# ===========================================================================


class TestErrorOnlyNoUsage:
    """When error_message is present but no usage data, render what we can."""

    def setup_method(self):
        self.r = UsageRenderer()

    def test_error_only_returns_group_with_profile(self):
        result = self.r.render(
            "API rate limited (429)",
            None,
            _make_profile(),
            None,
        )
        assert isinstance(result, Group)

    def test_error_shown_without_usage(self):
        result = self.r.render(
            "Connection refused",
            None,
            _make_profile(),
            None,
        )
        text = _render_to_str(result)
        assert "Connection refused" in text

    def test_no_five_hour_bar_without_usage(self):
        result = self.r.render(
            "API error",
            None,
            _make_profile(),
            None,
        )
        text = _render_to_str(result)
        assert "5-Hour" not in text

    def test_profile_still_shown_without_usage(self):
        result = self.r.render(
            "API error",
            None,
            _make_profile(display_name="Bob"),
            None,
        )
        text = _render_to_str(result)
        assert "Bob" in text

    def test_activity_line_shown_even_without_usage(self):
        events = [{"event_code": "SE", "status": "green"}]
        result = self.r.render(
            "API error",
            None,
            _make_profile(),
            None,
            activity_events=events,
        )
        text = _render_to_str(result)
        assert ARROW in text


# ===========================================================================
# E3 — Error message ordering: error appears BEFORE progress bars
# ===========================================================================


class TestErrorMessageOrdering:
    """Error message must appear at the top, before profile and bars."""

    def setup_method(self):
        self.r = UsageRenderer()

    def test_error_precedes_profile_in_output(self):
        result = self.r.render(
            "API rate limited (429)",
            _make_usage(),
            _make_profile(display_name="Alice"),
            datetime.now(timezone.utc),
        )
        text = _render_to_str(result)
        error_pos = text.find("API rate limited")
        profile_pos = text.find("Alice")
        assert error_pos < profile_pos, "Error must appear before profile"

    def test_error_precedes_five_hour_bar(self):
        result = self.r.render(
            "API backoff: 300s",
            _make_usage(),
            _make_profile(),
            datetime.now(timezone.utc),
        )
        text = _render_to_str(result)
        error_pos = text.find("API backoff")
        bar_pos = text.find("5-Hour")
        assert error_pos < bar_pos, "Error must appear before 5-hour bar"

    def test_error_triangle_marker_present(self):
        result = self.r.render(
            "Some error",
            _make_usage(),
            _make_profile(),
            datetime.now(timezone.utc),
        )
        text = _render_to_str(result)
        assert "\u25b3" in text  # △ triangle marker


# ===========================================================================
# E4 — Stale usage data edge cases
# ===========================================================================


class TestStaleUsageEdgeCases:
    """Usage data with extreme or edge-case values must still render."""

    def setup_method(self):
        self.r = UsageRenderer()

    def test_zero_utilization_with_error_shows_bars(self):
        result = self.r.render(
            "Throttled",
            _make_usage(five_util=0.0, seven_util=0.0),
            _make_profile(),
            datetime.now(timezone.utc),
        )
        text = _render_to_str(result)
        assert "5-Hour" in text
        assert "7-Day" in text

    def test_100_percent_utilization_with_error_shows_bars(self):
        result = self.r.render(
            "Rate limited",
            _make_usage(five_util=100.0, seven_util=100.0),
            _make_profile(),
            datetime.now(timezone.utc),
        )
        text = _render_to_str(result)
        assert "5-Hour" in text
        assert "100" in text

    def test_empty_resets_at_with_error_shows_bars(self):
        result = self.r.render(
            "API error",
            _make_usage(five_resets="", seven_resets=""),
            _make_profile(),
            datetime.now(timezone.utc),
        )
        text = _render_to_str(result)
        assert "5-Hour" in text

    def test_past_resets_at_with_error_shows_bars(self):
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        result = self.r.render(
            "Stale data",
            _make_usage(five_resets=past, seven_resets=past),
            _make_profile(),
            datetime.now(timezone.utc),
        )
        text = _render_to_str(result)
        assert "5-Hour" in text

    def test_very_old_last_update_with_error_still_renders(self):
        old_time = datetime.now(timezone.utc) - timedelta(hours=2)
        result = self.r.render(
            "API timeout",
            _make_usage(),
            _make_profile(),
            old_time,
        )
        text = _render_to_str(result)
        assert "5-Hour" in text
        assert "7-Day" in text
