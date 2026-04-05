"""
Unit tests for reviewer identity tags in governance event feed display.

Tests verify that [REVIEWER:xxx] tags in feedback_text are parsed
and displayed as colored tags: [Codex] yellow, [SDK] green, [Gem] cyan.
Legacy events without tags display normally (backwards compatible).
"""

import time

from rich.console import Console

from claude_usage.code_mode.display import UsageRenderer

# Named ANSI escape code constants for color assertions
ANSI_YELLOW = "\x1b[33m"
ANSI_GREEN = "\x1b[32m"
ANSI_CYAN = "\x1b[36m"

# Default render width for all tests
RENDER_WIDTH = 80


def _render_event_feed(events):
    """Render governance events through the real display renderer."""
    display = UsageRenderer.__new__(UsageRenderer)
    result = display.render_event_feed(events, RENDER_WIDTH)
    console = Console(force_terminal=True, width=RENDER_WIDTH)
    with console.capture() as capture:
        console.print(result)
    return capture.get()


class TestReviewerTagDisplay:
    """Tests for reviewer tag parsing and colored display."""

    def test_codex_reviewer_shows_yellow_tag(self):
        """[REVIEWER:codex-gpt5] → [Codex] in yellow in event header."""
        events = [
            {
                "event_type": "CC",
                "project_name": "myproj",
                "session_id": "s1",
                "feedback_text": "[REVIEWER:codex-gpt5] Some code review feedback",
                "timestamp": time.time(),
            }
        ]
        rendered = _render_event_feed(events)
        assert "[Codex]" in rendered
        assert f"{ANSI_YELLOW}[Codex]" in rendered

    def test_sdk_reviewer_shows_green_tag(self):
        """[REVIEWER:anthropic-sdk] → [SDK] in green in event header."""
        events = [
            {
                "event_type": "IV",
                "project_name": "myproj",
                "session_id": "s1",
                "feedback_text": "[REVIEWER:anthropic-sdk] Intent validation failed",
                "timestamp": time.time(),
            }
        ]
        rendered = _render_event_feed(events)
        assert "[SDK]" in rendered
        assert f"{ANSI_GREEN}[SDK]" in rendered

    def test_gemini_reviewer_shows_cyan_tag(self):
        """[REVIEWER:gemini] → [Gem] in cyan in event header."""
        events = [
            {
                "event_type": "CC",
                "project_name": "myproj",
                "session_id": "s1",
                "feedback_text": "[REVIEWER:gemini] Clean code violation",
                "timestamp": time.time(),
            }
        ]
        rendered = _render_event_feed(events)
        assert "[Gem]" in rendered
        assert f"{ANSI_CYAN}[Gem]" in rendered

    def test_legacy_event_no_tag_displays_normally(self):
        """Events without [REVIEWER:...] tag show no reviewer label."""
        events = [
            {
                "event_type": "IV",
                "project_name": "myproj",
                "session_id": "s1",
                "feedback_text": "Intent declaration required",
                "timestamp": time.time(),
            }
        ]
        rendered = _render_event_feed(events)
        assert "Intent declaration required" in rendered
        assert "[Codex]" not in rendered
        assert "[SDK]" not in rendered
        assert "[Gem]" not in rendered

    def test_unknown_reviewer_leaves_feedback_unchanged(self):
        """[REVIEWER:unknown-thing] is not recognized — raw tag preserved."""
        events = [
            {
                "event_type": "IV",
                "project_name": "myproj",
                "session_id": "s1",
                "feedback_text": "[REVIEWER:unknown-thing] Some feedback",
                "timestamp": time.time(),
            }
        ]
        rendered = _render_event_feed(events)
        assert "Some feedback" in rendered
        assert "[REVIEWER:unknown-thing]" in rendered
        assert "[Codex]" not in rendered
        assert "[SDK]" not in rendered
        assert "[Gem]" not in rendered

    def test_recognized_tag_stripped_from_feedback(self):
        """When tag is recognized, it's stripped from displayed feedback."""
        events = [
            {
                "event_type": "CC",
                "project_name": "myproj",
                "session_id": "s1",
                "feedback_text": "[REVIEWER:codex-gpt5] Actual feedback here",
                "timestamp": time.time(),
            }
        ]
        rendered = _render_event_feed(events)
        assert "Actual feedback here" in rendered
        assert "[REVIEWER:codex-gpt5]" not in rendered
