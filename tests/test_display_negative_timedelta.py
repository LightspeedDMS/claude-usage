"""Tests for negative timedelta display bug fix in UsageRenderer.

When resets_at is in the past, time_until is a negative timedelta.
Python represents negative timedeltas as timedelta(days=-1, seconds=N)
where .seconds is always positive — producing nonsensical countdown values.
The fix checks total_seconds() > 0 and shows "Window expired" instead.
"""

from datetime import datetime, timedelta, timezone

import pytest

from claude_usage.code_mode.display import UsageRenderer


def _past_iso(hours_ago=1):
    """Return an ISO 8601 UTC string for a time in the past."""
    dt = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return dt.isoformat().replace("+00:00", "+00:00")


def _future_iso(hours_from_now=2):
    """Return an ISO 8601 UTC string for a time in the future."""
    dt = datetime.now(timezone.utc) + timedelta(hours=hours_from_now)
    return dt.isoformat().replace("+00:00", "+00:00")


def _text_strings(content):
    """Extract plain string values from a list of Rich Text objects."""
    result = []
    for item in content:
        # Rich Text objects have a plain attribute
        if hasattr(item, "plain"):
            result.append(item.plain)
        else:
            result.append(str(item))
    return result


class TestFiveHourLimitExpired:
    def test_expired_resets_at_shows_window_expired(self):
        renderer = UsageRenderer()
        content = []
        five_hour_data = {
            "utilization": 75,
            "resets_at": _past_iso(hours_ago=1),
        }
        renderer._render_five_hour_limit(content, five_hour_data)
        texts = _text_strings(content)
        assert any("Window expired" in t for t in texts), (
            f"Expected 'Window expired' in output, got: {texts}"
        )

    def test_expired_resets_at_does_not_show_nonsensical_hours(self):
        renderer = UsageRenderer()
        content = []
        five_hour_data = {
            "utilization": 75,
            "resets_at": _past_iso(hours_ago=1),
        }
        renderer._render_five_hour_limit(content, five_hour_data)
        texts = _text_strings(content)
        # Must not show "Resets in: 19h" or similar nonsensical value
        assert not any("Resets in:" in t for t in texts), (
            f"Expected no 'Resets in:' countdown for expired window, got: {texts}"
        )

    def test_future_resets_at_shows_countdown(self):
        renderer = UsageRenderer()
        content = []
        five_hour_data = {
            "utilization": 50,
            "resets_at": _future_iso(hours_from_now=2),
        }
        renderer._render_five_hour_limit(content, five_hour_data)
        texts = _text_strings(content)
        assert any("Resets in:" in t for t in texts), (
            f"Expected countdown for future window, got: {texts}"
        )

    def test_no_resets_at_renders_without_countdown(self):
        renderer = UsageRenderer()
        content = []
        five_hour_data = {"utilization": 50, "resets_at": ""}
        renderer._render_five_hour_limit(content, five_hour_data)
        texts = _text_strings(content)
        assert not any("Resets in:" in t for t in texts)
        assert not any("Window expired" in t for t in texts)


class TestSevenDayLimitExpired:
    def test_expired_resets_at_shows_window_expired(self):
        renderer = UsageRenderer()
        content = []
        seven_day_data = {
            "utilization": 60,
            "resets_at": _past_iso(hours_ago=3),
        }
        renderer._render_seven_day_limit(content, seven_day_data)
        texts = _text_strings(content)
        assert any("Window expired" in t for t in texts), (
            f"Expected 'Window expired' in output, got: {texts}"
        )

    def test_expired_resets_at_does_not_show_nonsensical_hours(self):
        renderer = UsageRenderer()
        content = []
        seven_day_data = {
            "utilization": 60,
            "resets_at": _past_iso(hours_ago=3),
        }
        renderer._render_seven_day_limit(content, seven_day_data)
        texts = _text_strings(content)
        assert not any("Resets in:" in t for t in texts), (
            f"Expected no countdown for expired window, got: {texts}"
        )

    def test_future_resets_at_shows_countdown(self):
        renderer = UsageRenderer()
        content = []
        seven_day_data = {
            "utilization": 30,
            "resets_at": _future_iso(hours_from_now=48),
        }
        renderer._render_seven_day_limit(content, seven_day_data)
        texts = _text_strings(content)
        assert any("Resets in:" in t for t in texts), (
            f"Expected countdown for future window, got: {texts}"
        )


class TestModelLimitExpired:
    def test_expired_resets_at_shows_window_expired(self):
        renderer = UsageRenderer()
        content = []
        model_data = {
            "utilization": 80,
            "resets_at": _past_iso(hours_ago=2),
        }
        renderer._render_model_limit(content, model_data, "Sonnet")
        texts = _text_strings(content)
        assert any("Window expired" in t for t in texts), (
            f"Expected 'Window expired' in output, got: {texts}"
        )

    def test_expired_resets_at_does_not_show_nonsensical_hours(self):
        renderer = UsageRenderer()
        content = []
        model_data = {
            "utilization": 80,
            "resets_at": _past_iso(hours_ago=2),
        }
        renderer._render_model_limit(content, model_data, "Opus")
        texts = _text_strings(content)
        assert not any("Resets in:" in t for t in texts), (
            f"Expected no countdown for expired window, got: {texts}"
        )

    def test_future_resets_at_shows_countdown(self):
        renderer = UsageRenderer()
        content = []
        model_data = {
            "utilization": 45,
            "resets_at": _future_iso(hours_from_now=72),
        }
        renderer._render_model_limit(content, model_data, "Sonnet")
        texts = _text_strings(content)
        assert any("Resets in:" in t for t in texts), (
            f"Expected countdown for future window, got: {texts}"
        )

    def test_opus_model_expired(self):
        renderer = UsageRenderer()
        content = []
        model_data = {
            "utilization": 100,
            "resets_at": _past_iso(hours_ago=5),
        }
        renderer._render_model_limit(content, model_data, "Opus")
        texts = _text_strings(content)
        assert any("Window expired" in t for t in texts), (
            f"Expected 'Window expired' for expired Opus window, got: {texts}"
        )
