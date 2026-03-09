"""Regression tests for render_collapsed_plan_tier_line() — Section B.

Tests the real rendering code with no mocks.  Input is plain Python lists
and strings; output is inspected via .plain and ._spans on the Rich Text.

Format spec: '📦 Plan: MAX  ⚡ 20x'
"""

from __future__ import annotations

from rich.text import Text

from claude_usage.code_mode.display import render_collapsed_plan_tier_line

# Unicode constants
PACKAGE_EMOJI = "\U0001f4e6"  # 📦
LIGHTNING_EMOJI = "\u26a1"  # ⚡


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _badge_style(text_obj: Text, badge: str) -> str | None:
    """Return the first span style that covers *badge*, or None."""
    plain = text_obj.plain
    idx = plain.find(badge)
    if idx == -1:
        return None
    for span in text_obj._spans:
        if span.start <= idx < span.end:
            return str(span.style)
    return None


# ===========================================================================
# Return type
# ===========================================================================


class TestCollapsedPlanTierReturnType:
    def test_returns_rich_text_for_max_20x(self):
        assert isinstance(render_collapsed_plan_tier_line(["MAX"], "20x"), Text)

    def test_returns_rich_text_for_empty_inputs(self):
        assert isinstance(render_collapsed_plan_tier_line([], ""), Text)


# ===========================================================================
# Plain-text content
# ===========================================================================


class TestCollapsedPlanTierContent:
    def test_max_plan_20x_tier(self):
        plain = render_collapsed_plan_tier_line(["MAX"], "20x").plain
        assert "Plan:" in plain
        assert "MAX" in plain
        assert "20x" in plain

    def test_pro_plan_5x_tier(self):
        plain = render_collapsed_plan_tier_line(["PRO"], "5x").plain
        assert "PRO" in plain
        assert "5x" in plain

    def test_enterprise_plan_10x_tier(self):
        plain = render_collapsed_plan_tier_line(["ENTERPRISE"], "10x").plain
        assert "ENTERPRISE" in plain
        assert "10x" in plain

    def test_package_emoji_present_with_plan(self):
        plain = render_collapsed_plan_tier_line(["MAX"], "20x").plain
        assert PACKAGE_EMOJI in plain

    def test_lightning_emoji_present_with_tier(self):
        plain = render_collapsed_plan_tier_line(["MAX"], "20x").plain
        assert LIGHTNING_EMOJI in plain

    def test_single_line_no_newline(self):
        plain = render_collapsed_plan_tier_line(["MAX"], "20x").plain
        assert "\n" not in plain

    def test_plan_only_no_tier(self):
        plain = render_collapsed_plan_tier_line(["MAX"], "").plain
        assert "MAX" in plain
        assert "Plan:" in plain
        assert LIGHTNING_EMOJI not in plain

    def test_tier_only_no_plan(self):
        plain = render_collapsed_plan_tier_line([], "20x").plain
        assert "20x" in plain
        assert PACKAGE_EMOJI not in plain
        assert "Plan:" not in plain

    def test_empty_badges_empty_tier_returns_empty(self):
        assert render_collapsed_plan_tier_line([], "").plain == ""

    def test_multiple_badges_both_shown(self):
        plain = render_collapsed_plan_tier_line(["PRO", "MAX"], "20x").plain
        assert "PRO" in plain
        assert "MAX" in plain


# ===========================================================================
# Badge colour styles
# ===========================================================================


class TestCollapsedPlanTierBadgeColors:
    def test_max_badge_bold_yellow(self):
        result = render_collapsed_plan_tier_line(["MAX"], "")
        style = _badge_style(result, "MAX")
        assert style is not None, "MAX badge should have a style"
        assert "yellow" in style, f"MAX should be yellow, got: {style}"
        assert "bold" in style, f"MAX should be bold, got: {style}"

    def test_pro_badge_bold_magenta(self):
        result = render_collapsed_plan_tier_line(["PRO"], "")
        style = _badge_style(result, "PRO")
        assert style is not None, "PRO badge should have a style"
        assert "magenta" in style, f"PRO should be magenta, got: {style}"
        assert "bold" in style, f"PRO should be bold, got: {style}"

    def test_enterprise_badge_bold_blue(self):
        result = render_collapsed_plan_tier_line(["ENTERPRISE"], "")
        style = _badge_style(result, "ENTERPRISE")
        assert style is not None, "ENTERPRISE badge should have a style"
        assert "blue" in style, f"ENTERPRISE should be blue, got: {style}"
        assert "bold" in style, f"ENTERPRISE should be bold, got: {style}"

    def test_unknown_badge_falls_back_to_bold(self):
        result = render_collapsed_plan_tier_line(["CUSTOM"], "")
        style = _badge_style(result, "CUSTOM")
        assert style is not None, "Custom badge should have a style"
        assert "bold" in style, f"Custom badge should at least be bold, got: {style}"
