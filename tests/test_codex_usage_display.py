"""
Unit tests for Codex GPT-5 usage color-coding in the Hook Model display.

All tests use real rendering via Console capture (no mocks).
Color thresholds:
  - <=50%  → green
  - 51-75% → yellow
  - 76-95% → orange (#ff8c00)
  - >95%   → red
  - auto   → cyan (unchanged)
  - non-GPT model → always green (no codex logic)

Uses max(primary_pct, secondary_pct) for threshold determination.

Rich outputs ANSI escape codes (not color names) when force_terminal=True:
  green  → \x1b[32m
  yellow → \x1b[33m
  red    → \x1b[31m
  orange → \x1b[38;2;255;140;0m  (from #ff8c00)
  cyan   → \x1b[36m
"""

from __future__ import annotations

from claude_usage.code_mode.display import UsageRenderer

from tests.viz_regression_helpers import _make_pacemaker_status, _render_to_str

# ANSI color codes emitted by Rich in terminal mode
ANSI_GREEN = "\x1b[32m"
ANSI_YELLOW = "\x1b[33m"
ANSI_RED = "\x1b[31m"
ANSI_ORANGE = "\x1b[38;2;255;140;0m"
ANSI_CYAN = "\x1b[36m"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _render_hook_model(
    hook_model: str,
    codex_primary_pct: float | None = None,
    codex_secondary_pct: float | None = None,
) -> str:
    """Render the bottom section with given hook model and codex usage."""
    pm = _make_pacemaker_status(hook_model=hook_model)
    pm["codex_primary_pct"] = codex_primary_pct
    pm["codex_secondary_pct"] = codex_secondary_pct
    r = UsageRenderer()
    return _render_to_str(r.render_bottom_section(pm, blockage_stats={}))


def _hook_model_color(rendered: str, model_name: str) -> str:
    """Extract the ANSI color code immediately preceding the model name."""
    idx = rendered.find(model_name)
    if idx < 0:
        return ""
    # Walk back to find the last ESC sequence before model_name
    prefix = rendered[:idx]
    esc_idx = prefix.rfind("\x1b[")
    if esc_idx < 0:
        return ""
    # Find end of escape sequence (letter terminates it)
    seq_end = esc_idx + 2
    while seq_end < len(prefix) and not prefix[seq_end].isalpha():
        seq_end += 1
    return prefix[esc_idx : seq_end + 1]


# ---------------------------------------------------------------------------
# Tests: color thresholds
# ---------------------------------------------------------------------------


class TestCodexColorThresholds:
    def test_color_green_at_30pct(self):
        """max(30, 20) = 30% → green"""
        rendered = _render_hook_model("gpt-5", codex_primary_pct=30.0, codex_secondary_pct=20.0)
        assert "gpt-5" in rendered
        assert _hook_model_color(rendered, "gpt-5") == ANSI_GREEN

    def test_color_green_at_50pct(self):
        """Boundary: exactly 50% → green (not yellow)"""
        rendered = _render_hook_model("gpt-5", codex_primary_pct=50.0, codex_secondary_pct=10.0)
        assert "gpt-5" in rendered
        assert _hook_model_color(rendered, "gpt-5") == ANSI_GREEN

    def test_color_yellow_at_51pct(self):
        """Boundary: 51% → yellow"""
        rendered = _render_hook_model("gpt-5", codex_primary_pct=51.0, codex_secondary_pct=10.0)
        assert "gpt-5" in rendered
        assert _hook_model_color(rendered, "gpt-5") == ANSI_YELLOW

    def test_color_yellow_at_75pct(self):
        """Boundary: exactly 75% → yellow (not orange)"""
        rendered = _render_hook_model("gpt-5", codex_primary_pct=75.0, codex_secondary_pct=10.0)
        assert "gpt-5" in rendered
        assert _hook_model_color(rendered, "gpt-5") == ANSI_YELLOW

    def test_color_orange_at_76pct(self):
        """Boundary: 76% → orange"""
        rendered = _render_hook_model("gpt-5", codex_primary_pct=76.0, codex_secondary_pct=10.0)
        assert "gpt-5" in rendered
        assert _hook_model_color(rendered, "gpt-5") == ANSI_ORANGE

    def test_color_orange_at_95pct(self):
        """Boundary: exactly 95% → orange (not red)"""
        rendered = _render_hook_model("gpt-5", codex_primary_pct=95.0, codex_secondary_pct=10.0)
        assert "gpt-5" in rendered
        assert _hook_model_color(rendered, "gpt-5") == ANSI_ORANGE

    def test_color_red_at_96pct(self):
        """Boundary: 96% → red"""
        rendered = _render_hook_model("gpt-5", codex_primary_pct=96.0, codex_secondary_pct=10.0)
        assert "gpt-5" in rendered
        assert _hook_model_color(rendered, "gpt-5") == ANSI_RED


# ---------------------------------------------------------------------------
# Tests: max() uses secondary when it's higher
# ---------------------------------------------------------------------------


class TestCodexMaxUsesSecondary:
    def test_secondary_higher_than_primary(self):
        """primary=10, secondary=80 → max=80 → orange"""
        rendered = _render_hook_model("gpt-5", codex_primary_pct=10.0, codex_secondary_pct=80.0)
        assert "gpt-5" in rendered
        assert _hook_model_color(rendered, "gpt-5") == ANSI_ORANGE


# ---------------------------------------------------------------------------
# Tests: fallback when no codex data
# ---------------------------------------------------------------------------


class TestCodexNoData:
    def test_no_codex_data_defaults_green(self):
        """No codex_usage data (None) → defaults to green"""
        rendered = _render_hook_model("gpt-5", codex_primary_pct=None, codex_secondary_pct=None)
        assert "gpt-5" in rendered
        assert _hook_model_color(rendered, "gpt-5") == ANSI_GREEN

    def test_non_gpt_model_green(self):
        """hook_model without 'gpt' → always green regardless of codex pct"""
        rendered = _render_hook_model(
            "claude-sonnet", codex_primary_pct=99.0, codex_secondary_pct=99.0
        )
        assert "claude-sonnet" in rendered
        assert _hook_model_color(rendered, "claude-sonnet") == ANSI_GREEN


# ---------------------------------------------------------------------------
# Tests: auto model stays cyan
# ---------------------------------------------------------------------------


class TestAutoModelCyan:
    def test_auto_model_cyan(self):
        """hook_model='auto' → cyan (unchanged by codex logic)"""
        rendered = _render_hook_model("auto")
        assert "auto" in rendered
        assert ANSI_CYAN in rendered


# ---------------------------------------------------------------------------
# Tests: PAYG billing mode (limit_id='premium') → cyan
# ---------------------------------------------------------------------------


def _render_hook_model_with_billing(
    hook_model: str,
    codex_primary_pct: float | None = None,
    codex_secondary_pct: float | None = None,
    codex_limit_id: str | None = None,
    codex_plan_type: str | None = "team",
) -> str:
    """Render bottom section with billing mode fields in pacemaker_status."""
    pm = _make_pacemaker_status(hook_model=hook_model)
    pm["codex_primary_pct"] = codex_primary_pct
    pm["codex_secondary_pct"] = codex_secondary_pct
    pm["codex_limit_id"] = codex_limit_id
    pm["codex_plan_type"] = codex_plan_type
    r = UsageRenderer()
    return _render_to_str(r.render_bottom_section(pm, blockage_stats={}))


class TestPaygBillingMode:
    def test_payg_mode_shows_cyan(self):
        """limit_id='premium' at high pct → Hook Model color is cyan (not red)"""
        rendered = _render_hook_model_with_billing(
            "gpt-5",
            codex_primary_pct=96.0,
            codex_secondary_pct=96.0,
            codex_limit_id="premium",
            codex_plan_type=None,
        )
        assert "gpt-5" in rendered
        assert _hook_model_color(rendered, "gpt-5") == ANSI_CYAN

    def test_payg_mode_null_plan_type_shows_cyan(self):
        """limit_id='premium' AND plan_type=None at 0% → color is cyan (not green)"""
        rendered = _render_hook_model_with_billing(
            "gpt-5",
            codex_primary_pct=0.0,
            codex_secondary_pct=0.0,
            codex_limit_id="premium",
            codex_plan_type=None,
        )
        assert "gpt-5" in rendered
        assert _hook_model_color(rendered, "gpt-5") == ANSI_CYAN

    def test_subscription_mode_still_uses_thresholds(self):
        """limit_id='codex' → percentage thresholds apply normally (96% → red)"""
        rendered = _render_hook_model_with_billing(
            "gpt-5",
            codex_primary_pct=96.0,
            codex_secondary_pct=10.0,
            codex_limit_id="codex",
            codex_plan_type="team",
        )
        assert "gpt-5" in rendered
        assert _hook_model_color(rendered, "gpt-5") == ANSI_RED
