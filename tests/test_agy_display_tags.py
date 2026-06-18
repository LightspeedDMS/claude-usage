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
