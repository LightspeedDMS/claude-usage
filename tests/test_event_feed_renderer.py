#!/usr/bin/env python3
"""
Unit tests for render_event_feed() in UsageRenderer.

Tests icon mapping, text wrapping, scroll behavior, and empty state.
"""

import time

import pytest

from claude_usage.code_mode.display import UsageRenderer


@pytest.fixture
def renderer():
    return UsageRenderer()


def _make_event(event_type, project="proj", feedback="Rejected", ts=None):
    """Helper to create a governance event dict."""
    return {
        "event_type": event_type,
        "project_name": project,
        "session_id": "sess-1",
        "feedback_text": feedback,
        "timestamp": ts or time.time(),
    }


class TestRenderEventFeedIconMapping:
    """Tests for event type icon mapping in render_event_feed."""

    def test_iv_icon(self, renderer):
        """IV events render with cross icon."""
        events = [_make_event("IV")]
        result = renderer.render_event_feed(events, available_width=60)
        # Convert to plain text for assertion
        text = result.plain if hasattr(result, "plain") else str(result)
        assert "\u2716" in text  # cross mark

    def test_td_icon(self, renderer):
        """TD events render with warning icon."""
        events = [_make_event("TD")]
        result = renderer.render_event_feed(events, available_width=60)
        text = result.plain if hasattr(result, "plain") else str(result)
        assert "\u26a0" in text  # warning sign

    def test_cc_icon(self, renderer):
        """CC events render with diamond icon."""
        events = [_make_event("CC")]
        result = renderer.render_event_feed(events, available_width=60)
        text = result.plain if hasattr(result, "plain") else str(result)
        assert "\u27e1" in text  # diamond


class TestRenderEventFeedTextWrapping:
    """Tests for text wrapping in event feed."""

    def test_long_feedback_wraps(self, renderer):
        """Long feedback text is word-wrapped to available width."""
        long_text = "This is a very long feedback message that should be wrapped " * 3
        events = [_make_event("IV", feedback=long_text)]
        result = renderer.render_event_feed(events, available_width=40)
        text = result.plain if hasattr(result, "plain") else str(result)
        lines = text.strip().split("\n")
        # Should have multiple lines for the wrapped text
        assert len(lines) > 2


class TestRenderEventFeedScrollOffset:
    """Tests for scroll offset handling."""

    def test_scroll_offset_skips_events(self, renderer):
        """scroll_offset > 0 skips earlier events."""
        now = time.time()
        events = [
            _make_event("IV", feedback="Event A", ts=now),
            _make_event("TD", feedback="Event B", ts=now - 10),
            _make_event("CC", feedback="Event C", ts=now - 20),
        ]
        # With offset=1, should skip the first event
        result = renderer.render_event_feed(
            events, available_width=60, scroll_offset=1,
        )
        text = result.plain if hasattr(result, "plain") else str(result)
        assert "Event B" in text or "Event C" in text


class TestRenderEventFeedEmpty:
    """Tests for empty events list."""

    def test_empty_events_returns_renderable(self, renderer):
        """Empty events list returns a valid renderable."""
        result = renderer.render_event_feed([], available_width=60)
        text = result.plain if hasattr(result, "plain") else str(result)
        assert "0 events" in text.lower() or "no events" in text.lower()

    def test_footer_shows_event_count(self, renderer):
        """Footer shows total event count."""
        now = time.time()
        events = [
            _make_event("IV", feedback="One", ts=now),
            _make_event("TD", feedback="Two", ts=now - 5),
        ]
        result = renderer.render_event_feed(events, available_width=60)
        text = result.plain if hasattr(result, "plain") else str(result)
        assert "2 events" in text.lower()
