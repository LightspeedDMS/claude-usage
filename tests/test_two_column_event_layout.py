#!/usr/bin/env python3
"""
Unit tests for two-column layout with governance event feed.

Tests that render() produces a two-column layout when terminal width >= 85
and a single-column layout when < 85.
"""

import time

import pytest
from rich.console import Console
from rich.text import Text
from rich.table import Table

from claude_usage.code_mode.display import UsageRenderer


@pytest.fixture
def renderer():
    return UsageRenderer()


@pytest.fixture
def sample_events():
    """Sample governance events for testing."""
    now = time.time()
    return [
        {
            "event_type": "IV",
            "project_name": "my-project",
            "session_id": "sess-1",
            "feedback_text": "Missing INTENT: marker",
            "timestamp": now,
        },
        {
            "event_type": "TD",
            "project_name": "my-project",
            "session_id": "sess-2",
            "feedback_text": "TDD declaration missing",
            "timestamp": now - 30,
        },
    ]


class TestResponsiveLayoutWideTerminal:
    """Tests for two-column layout at width >= 85."""

    def test_wide_terminal_returns_grid(self, renderer, sample_events):
        """At >= 85 cols, render_with_event_feed returns a Table grid."""
        result = renderer.render_with_event_feed(
            main_content=Text("Main content here"),
            events=sample_events,
            terminal_width=120,
        )
        # Should contain a grid table (two columns)
        # The result should be renderable - verify it doesn't raise
        console = Console(width=120, force_terminal=True)
        with console.capture() as capture:
            console.print(result)
        output = capture.get()
        assert "Main content" in output
        assert "IV" in output  # Event type visible

    def test_wide_terminal_shows_event_feed(self, renderer, sample_events):
        """At >= 85 cols, event feed content is visible."""
        result = renderer.render_with_event_feed(
            main_content=Text("Dashboard"),
            events=sample_events,
            terminal_width=100,
        )
        console = Console(width=100, force_terminal=True)
        with console.capture() as capture:
            console.print(result)
        output = capture.get()
        assert "Missing INTENT" in output or "events" in output.lower()

    def test_exactly_85_cols_shows_feed(self, renderer, sample_events):
        """At exactly 85 cols, event feed is shown."""
        result = renderer.render_with_event_feed(
            main_content=Text("Dashboard"),
            events=sample_events,
            terminal_width=85,
        )
        console = Console(width=85, force_terminal=True)
        with console.capture() as capture:
            console.print(result)
        output = capture.get()
        # Should have event content
        assert "events" in output.lower()


class TestResponsiveLayoutNarrowTerminal:
    """Tests for single-column layout at width < 85."""

    def test_narrow_terminal_returns_main_only(self, renderer, sample_events):
        """At < 85 cols, render_with_event_feed returns just main content."""
        result = renderer.render_with_event_feed(
            main_content=Text("Main content only"),
            events=sample_events,
            terminal_width=80,
        )
        console = Console(width=80, force_terminal=True)
        with console.capture() as capture:
            console.print(result)
        output = capture.get()
        assert "Main content only" in output

    def test_narrow_terminal_hides_event_feed(self, renderer, sample_events):
        """At < 85 cols, event feed is not shown."""
        result = renderer.render_with_event_feed(
            main_content=Text("Narrow"),
            events=sample_events,
            terminal_width=60,
        )
        console = Console(width=60, force_terminal=True)
        with console.capture() as capture:
            console.print(result)
        output = capture.get()
        # Should NOT contain event details
        assert "Missing INTENT" not in output

    def test_empty_events_wide_terminal(self, renderer):
        """Wide terminal with no events shows empty feed."""
        result = renderer.render_with_event_feed(
            main_content=Text("Dashboard"),
            events=[],
            terminal_width=120,
        )
        console = Console(width=120, force_terminal=True)
        with console.capture() as capture:
            console.print(result)
        output = capture.get()
        assert "0 events" in output.lower()
