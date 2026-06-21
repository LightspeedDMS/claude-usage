"""Tests for agy reviewer tag display in governance event feed (Story #72)."""

import re

import pytest

from claude_usage.code_mode.display import (
    REVIEWER_TAGS,
    UsageRenderer,
    _REVIEWER_TAG_RE,
)


class TestAgyReviewerTagsPresent:
    """REVIEWER_TAGS must have entries for all agy model variants."""

    def test_agy_bare_in_reviewer_tags(self):
        assert "agy" in REVIEWER_TAGS

    def test_agy_flash_in_reviewer_tags(self):
        assert "agy-flash" in REVIEWER_TAGS

    def test_agy_flash_high_in_reviewer_tags(self):
        assert "agy-flash-high" in REVIEWER_TAGS

    def test_agy_flash_low_in_reviewer_tags(self):
        assert "agy-flash-low" in REVIEWER_TAGS

    def test_agy_flash_medium_in_reviewer_tags(self):
        assert "agy-flash-medium" in REVIEWER_TAGS

    def test_agy_pro_in_reviewer_tags(self):
        assert "agy-pro" in REVIEWER_TAGS

    def test_agy_pro_high_in_reviewer_tags(self):
        assert "agy-pro-high" in REVIEWER_TAGS

    def test_agy_pro_low_in_reviewer_tags(self):
        assert "agy-pro-low" in REVIEWER_TAGS

    def test_agy_gpt_oss_in_reviewer_tags(self):
        assert "agy-gpt-oss" in REVIEWER_TAGS

    def test_agy_sonnet_in_reviewer_tags(self):
        assert "agy-sonnet" in REVIEWER_TAGS

    def test_agy_opus_in_reviewer_tags(self):
        assert "agy-opus" in REVIEWER_TAGS


class TestAgyReviewerTagValues:
    """REVIEWER_TAGS entries for agy must have correct label and a color."""

    def test_agy_flash_high_label_is_agy(self):
        tag_label, tag_color = REVIEWER_TAGS["agy-flash-high"]
        assert tag_label == "[Agy]"

    def test_agy_flash_high_has_a_color(self):
        tag_label, tag_color = REVIEWER_TAGS["agy-flash-high"]
        assert tag_color  # must be non-empty string

    def test_agy_bare_label_is_agy(self):
        tag_label, tag_color = REVIEWER_TAGS["agy"]
        assert tag_label == "[Agy]"

    def test_agy_pro_label_is_agy(self):
        tag_label, tag_color = REVIEWER_TAGS["agy-pro"]
        assert tag_label == "[Agy]"

    def test_agy_gpt_oss_label_is_agy(self):
        tag_label, tag_color = REVIEWER_TAGS["agy-gpt-oss"]
        assert tag_label == "[Agy]"

    def test_agy_sonnet_label_is_agy(self):
        tag_label, tag_color = REVIEWER_TAGS["agy-sonnet"]
        assert tag_label == "[Agy]"

    def test_all_agy_entries_have_same_color(self):
        """All agy entries must share the same display color for visual consistency."""
        agy_keys = [k for k in REVIEWER_TAGS if k == "agy" or k.startswith("agy-")]
        colors = {REVIEWER_TAGS[k][1] for k in agy_keys}
        assert (
            len(colors) == 1
        ), f"Expected all agy tags to use same color, got: {colors}"


class TestAgyTagRegexMatching:
    """Test that the tag regex correctly extracts agy reviewer ids from feedback text."""

    def test_regex_extracts_agy_flash_high_from_feedback(self):
        """Feedback '[agy-flash-high]APPROVED...' must yield reviewer_id='agy-flash-high'."""
        feedback = "[agy-flash-high]APPROVED - intent matches diff"
        match = _REVIEWER_TAG_RE.search(feedback)
        assert match is not None
        reviewer_id = match.group(1)
        assert reviewer_id == "agy-flash-high"
        assert reviewer_id in REVIEWER_TAGS

    def test_regex_extracts_agy_bare_from_feedback(self):
        feedback = "[agy]BLOCKED - missing intent"
        match = _REVIEWER_TAG_RE.search(feedback)
        assert match is not None
        assert match.group(1) == "agy"
        assert "agy" in REVIEWER_TAGS

    def test_regex_extracts_agy_pro_high_from_feedback(self):
        feedback = "[agy-pro-high]APPROVED"
        match = _REVIEWER_TAG_RE.search(feedback)
        assert match is not None
        assert match.group(1) == "agy-pro-high"
        assert "agy-pro-high" in REVIEWER_TAGS


class TestAgyTagRichRendering:
    """Reviewer tag labels must appear literally in event feed output.

    Bug: tag_label values like '[Agy]', '[Codex]', '[SDK]' are passed to
    Text.from_markup() without escaping. Rich interprets '[Agy]' as a style
    tag, silently swallows it (not a known Rich style), and the label never
    appears in plain text output.

    Fix: escape '[' to '\\[' in tag_label before building reviewer_markup.
    """

    def _make_event(self, feedback_text, event_type="IV"):
        return {
            "event_type": event_type,
            "timestamp": 1700000000,
            "project_name": "test-project",
            "feedback_text": feedback_text,
        }

    def test_agy_tag_label_appears_literally_in_event_feed_output(self):
        """'[Agy]' must appear in plain text after render_event_feed with agy reviewer."""
        renderer = UsageRenderer()
        events = [self._make_event("[agy-gpt-oss] APPROVED - intent matches diff")]
        result = renderer.render_event_feed(events, available_width=80)
        assert "[Agy]" in result.plain, (
            f"Expected '[Agy]' to appear literally in plain output, got: {result.plain!r}"
        )

    def test_codex_tag_label_appears_literally_in_event_feed_output(self):
        """'[Codex]' must appear in plain text after render_event_feed with codex reviewer."""
        renderer = UsageRenderer()
        events = [self._make_event("[codex-gpt5] APPROVED - looks good")]
        result = renderer.render_event_feed(events, available_width=80)
        assert "[Codex]" in result.plain, (
            f"Expected '[Codex]' to appear literally in plain output, got: {result.plain!r}"
        )

    def test_sdk_tag_label_appears_literally_in_event_feed_output(self):
        """'[SDK]' must appear in plain text after render_event_feed with sdk reviewer."""
        renderer = UsageRenderer()
        events = [self._make_event("[anthropic-sdk] APPROVED - safe operation")]
        result = renderer.render_event_feed(events, available_width=80)
        assert "[SDK]" in result.plain, (
            f"Expected '[SDK]' to appear literally in plain output, got: {result.plain!r}"
        )


class TestAgyHookModelColor:
    """Hook Model column in render_bottom_section must use bright_green for agy models."""

    def test_agy_hook_model_uses_bright_green(self):
        """render_bottom_section must pass bright_green markup to _fmt_kv for agy hook models.

        Monkeypatches _fmt_kv to capture the markup_value argument when the
        Hook Model key-value pair is rendered, then asserts bright_green is used.
        """
        renderer = UsageRenderer()
        captured = {}
        original_fmt_kv = renderer._fmt_kv

        def capturing_fmt_kv(label, value, markup_value, width):
            if label == "Hook Model:":
                captured["markup_value"] = markup_value
            return original_fmt_kv(label, value, markup_value, width)

        renderer._fmt_kv = capturing_fmt_kv
        renderer.render_bottom_section(
            pacemaker_status={"hook_model": "agy-flash-high"},
            blockage_stats={},
        )

        assert (
            "markup_value" in captured
        ), "Hook Model: _fmt_kv was never called — hook model block not reached"
        assert (
            "bright_green" in captured["markup_value"]
        ), f"Expected 'bright_green' in Hook Model markup, got: {captured['markup_value']!r}"
