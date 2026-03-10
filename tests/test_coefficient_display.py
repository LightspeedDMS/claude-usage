"""Tests for coefficient display in pace-maker integration and renderer.

TDD test file — written before production code changes.

Covers:
1. PaceMakerReader.get_status() includes coefficients_5h and coefficients_7d
2. Display renders coefficient values next to limiter lines when present
3. Display works without coefficients (backward compat — None/missing)
4. Calibrated values replace defaults when available
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from claude_usage.code_mode.display import UsageRenderer

from tests.viz_regression_helpers import (
    _make_pacemaker_status,
    _make_usage,
    _render_to_str,
)


# ===========================================================================
# Helpers
# ===========================================================================


def _make_pm_status_with_coefficients(
    coeff_5h_5x: float = 0.0075,
    coeff_5h_20x: float = 0.001875,
    coeff_7d_5x: float = 0.0011,
    coeff_7d_20x: float = 0.000275,
    **kwargs,
) -> dict:
    """Extend _make_pacemaker_status with coefficient data."""
    status = _make_pacemaker_status(**kwargs)
    status["coefficients_5h"] = {"5x": coeff_5h_5x, "20x": coeff_5h_20x}
    status["coefficients_7d"] = {"5x": coeff_7d_5x, "20x": coeff_7d_20x}
    return status


def _make_mock_get_status_environment():
    """Build the shared mock objects needed for PaceMakerReader.get_status() tests.

    Returns a tuple: (mock_pacing_engine, mock_fallback, mock_usage_model_class)
    """
    mock_decision = {
        "five_hour": {"utilization": 40.0, "target": 60.0},
        "seven_day": {"utilization": 30.0, "target": 50.0},
        "constrained_window": "5-hour",
        "deviation_percent": -5.0,
        "should_throttle": False,
        "delay_seconds": 0,
        "algorithm": "adaptive",
        "strategy": "normal",
    }
    mock_pacing_engine = MagicMock()
    mock_pacing_engine.calculate_pacing_decision.return_value = mock_decision

    mock_fallback = MagicMock()
    mock_fallback._DEFAULT_TOKEN_COSTS = {
        "5x": {"coefficient_5h": 0.0075, "coefficient_7d": 0.0011},
        "20x": {"coefficient_5h": 0.001875, "coefficient_7d": 0.000275},
    }

    mock_usage_model_instance = MagicMock()
    mock_usage_model_instance._get_calibrated_coefficients.return_value = None
    mock_usage_model_class = MagicMock(return_value=mock_usage_model_instance)

    return mock_pacing_engine, mock_fallback, mock_usage_model_class


def _call_get_status_with_mocks(reader, mock_pacing_engine, mock_fallback, mock_usage_model_class):
    """Call reader.get_status() with all pacemaker modules mocked out."""
    import sys

    mock_pacemaker_pkg = MagicMock()
    mock_pacemaker_pkg.pacing_engine = mock_pacing_engine

    with patch.dict(
        sys.modules,
        {
            "pacemaker": mock_pacemaker_pkg,
            "pacemaker.pacing_engine": mock_pacing_engine,
            "pacemaker.fallback": mock_fallback,
            "pacemaker.usage_model": MagicMock(UsageModel=mock_usage_model_class),
        },
    ):
        return reader.get_status()


def _make_reader_with_data():
    """Create a PaceMakerReader pre-patched with installed state and usage data."""
    from claude_usage.code_mode.pacemaker_integration import PaceMakerReader

    reader = PaceMakerReader()
    return reader


_STANDARD_CONFIG = {
    "enabled": True,
    "threshold_percent": 0,
    "base_delay": 5,
    "max_delay": 350,
    "safety_buffer_pct": 95.0,
    "preload_hours": 12.0,
    "weekly_limit_enabled": True,
    "five_hour_limit_enabled": True,
}

_STANDARD_USAGE = {
    "timestamp": None,
    "five_hour_util": 40.0,
    "five_hour_resets_at": None,
    "seven_day_util": 30.0,
    "seven_day_resets_at": None,
}


# ===========================================================================
# Section 1: PaceMakerReader.get_status() returns coefficients
# ===========================================================================


class TestGetStatusIncludesCoefficients:
    """get_status() must include coefficients_5h and coefficients_7d in return dict."""

    def test_get_status_contains_coefficients_5h_key(self):
        """get_status() return dict must contain 'coefficients_5h' key."""
        reader = _make_reader_with_data()
        mock_pe, mock_fb, mock_umc = _make_mock_get_status_environment()

        with (
            patch.object(reader, "is_installed", return_value=True),
            patch.object(reader, "_read_config", return_value=_STANDARD_CONFIG),
            patch.object(reader, "_get_latest_usage", return_value=_STANDARD_USAGE),
            patch.object(reader, "is_fallback_active", return_value=False),
        ):
            result = _call_get_status_with_mocks(reader, mock_pe, mock_fb, mock_umc)

        assert result is not None
        assert "coefficients_5h" in result

    def test_get_status_contains_coefficients_7d_key(self):
        """get_status() return dict must contain 'coefficients_7d' key."""
        reader = _make_reader_with_data()
        mock_pe, mock_fb, mock_umc = _make_mock_get_status_environment()

        with (
            patch.object(reader, "is_installed", return_value=True),
            patch.object(reader, "_read_config", return_value=_STANDARD_CONFIG),
            patch.object(reader, "_get_latest_usage", return_value=_STANDARD_USAGE),
            patch.object(reader, "is_fallback_active", return_value=False),
        ):
            result = _call_get_status_with_mocks(reader, mock_pe, mock_fb, mock_umc)

        assert result is not None
        assert "coefficients_7d" in result

    def test_get_status_coefficients_use_defaults_when_no_calibration(self):
        """When _get_calibrated_coefficients returns None, defaults from _DEFAULT_TOKEN_COSTS are used."""
        reader = _make_reader_with_data()
        mock_pe, mock_fb, mock_umc = _make_mock_get_status_environment()
        # No calibration — instance already returns None by default

        with (
            patch.object(reader, "is_installed", return_value=True),
            patch.object(reader, "_read_config", return_value=_STANDARD_CONFIG),
            patch.object(reader, "_get_latest_usage", return_value=_STANDARD_USAGE),
            patch.object(reader, "is_fallback_active", return_value=False),
        ):
            result = _call_get_status_with_mocks(reader, mock_pe, mock_fb, mock_umc)

        assert result is not None
        assert result["coefficients_5h"]["5x"] == pytest.approx(0.0075)
        assert result["coefficients_5h"]["20x"] == pytest.approx(0.001875)
        assert result["coefficients_7d"]["5x"] == pytest.approx(0.0011)
        assert result["coefficients_7d"]["20x"] == pytest.approx(0.000275)

    def test_get_status_uses_calibrated_5x_when_available(self):
        """When calibrated coefficients exist for 5x tier, they replace defaults."""
        reader = _make_reader_with_data()
        mock_pe, mock_fb, mock_umc = _make_mock_get_status_environment()

        # Override calibration for 5x only
        mock_instance = mock_umc.return_value

        def calibrated_side_effect(tier):
            return (0.0088, 0.0013) if tier == "5x" else None

        mock_instance._get_calibrated_coefficients.side_effect = calibrated_side_effect

        with (
            patch.object(reader, "is_installed", return_value=True),
            patch.object(reader, "_read_config", return_value=_STANDARD_CONFIG),
            patch.object(reader, "_get_latest_usage", return_value=_STANDARD_USAGE),
            patch.object(reader, "is_fallback_active", return_value=False),
        ):
            result = _call_get_status_with_mocks(reader, mock_pe, mock_fb, mock_umc)

        assert result is not None
        assert result["coefficients_5h"]["5x"] == pytest.approx(0.0088)
        assert result["coefficients_7d"]["5x"] == pytest.approx(0.0013)
        # 20x stays at defaults
        assert result["coefficients_5h"]["20x"] == pytest.approx(0.001875)
        assert result["coefficients_7d"]["20x"] == pytest.approx(0.000275)

    def test_get_status_uses_calibrated_20x_when_available(self):
        """When calibrated coefficients exist for 20x tier, they replace defaults."""
        reader = _make_reader_with_data()
        mock_pe, mock_fb, mock_umc = _make_mock_get_status_environment()

        mock_instance = mock_umc.return_value

        def calibrated_side_effect(tier):
            return (0.0022, 0.00035) if tier == "20x" else None

        mock_instance._get_calibrated_coefficients.side_effect = calibrated_side_effect

        with (
            patch.object(reader, "is_installed", return_value=True),
            patch.object(reader, "_read_config", return_value=_STANDARD_CONFIG),
            patch.object(reader, "_get_latest_usage", return_value=_STANDARD_USAGE),
            patch.object(reader, "is_fallback_active", return_value=False),
        ):
            result = _call_get_status_with_mocks(reader, mock_pe, mock_fb, mock_umc)

        assert result is not None
        # 5x stays at defaults
        assert result["coefficients_5h"]["5x"] == pytest.approx(0.0075)
        # 20x uses calibrated
        assert result["coefficients_5h"]["20x"] == pytest.approx(0.0022)
        assert result["coefficients_7d"]["20x"] == pytest.approx(0.00035)

    def test_get_status_no_data_returns_none_coefficients(self):
        """When no usage data, get_status() still returns coefficient keys with None."""
        reader = _make_reader_with_data()

        with (
            patch.object(reader, "is_installed", return_value=True),
            patch.object(reader, "_read_config", return_value=_STANDARD_CONFIG),
            patch.object(reader, "_get_latest_usage", return_value=None),
        ):
            result = reader.get_status()

        assert result is not None
        assert "coefficients_5h" in result
        assert result["coefficients_5h"] is None
        assert "coefficients_7d" in result
        assert result["coefficients_7d"] is None


# ===========================================================================
# Section 2: Display renders coefficients next to limiter lines
# ===========================================================================


class TestFiveHourLimiterCoefficientsDisplay:
    """_render_five_hour_limit() shows coefficient values when present in pacemaker_status."""

    def setup_method(self):
        self.r = UsageRenderer()
        self.usage = _make_usage()

    def _render_with_pm(self, pm_status):
        return _render_to_str(
            self.r.render(
                error_message=None,
                last_usage=self.usage,
                last_profile=None,
                last_update=None,
                pacemaker_status=pm_status,
            )
        )

    def test_5h_coefficients_shown_when_enabled_and_present(self):
        """5-Hour Limiter line includes coefficient values when pacemaker_status has them."""
        pm = _make_pm_status_with_coefficients(
            coeff_5h_5x=0.0075,
            coeff_5h_20x=0.001875,
            five_hour_limit_enabled=True,
        )
        rendered = self._render_with_pm(pm)
        assert "5-Hour Limiter" in rendered
        assert "0.0075" in rendered
        assert "0.0019" in rendered  # 0.001875 formatted to 4 decimal places

    def test_5h_coefficients_shown_when_disabled_and_present(self):
        """5-Hour Limiter line includes coefficient values even when limiter is disabled."""
        pm = _make_pm_status_with_coefficients(
            coeff_5h_5x=0.0075,
            coeff_5h_20x=0.001875,
            five_hour_limit_enabled=False,
        )
        rendered = self._render_with_pm(pm)
        assert "5-Hour Limiter" in rendered
        assert "disabled" in rendered
        assert "0.0075" in rendered

    def test_5h_no_coefficients_key_backward_compatible(self):
        """When pacemaker_status has no coefficients_5h key, display still works."""
        pm = _make_pacemaker_status(five_hour_limit_enabled=True)
        # No coefficients keys — should not crash
        rendered = self._render_with_pm(pm)
        assert "5-Hour Limiter" in rendered
        assert "5x:" not in rendered

    def test_5h_none_coefficients_backward_compatible(self):
        """When coefficients_5h is None, display still works without coefficient text."""
        pm = _make_pacemaker_status(five_hour_limit_enabled=True)
        pm["coefficients_5h"] = None
        rendered = self._render_with_pm(pm)
        assert "5-Hour Limiter" in rendered
        assert "5x:" not in rendered

    def test_5h_coefficient_format_4_decimal_places(self):
        """Coefficients are formatted to 4 decimal places."""
        pm = _make_pm_status_with_coefficients(
            coeff_5h_5x=0.00751234,
            coeff_5h_20x=0.00187654,
        )
        rendered = self._render_with_pm(pm)
        # 0.00751234 → "0.0075", 0.00187654 → "0.0019"
        assert "0.0075" in rendered
        assert "0.0019" in rendered

    def test_5h_no_pacemaker_status_no_coefficients(self):
        """When pacemaker_status is None, no 5x: coefficient text appears."""
        rendered = self._render_with_pm(None)
        assert "5-Hour Usage" in rendered
        assert "5x:" not in rendered


class TestSevenDayLimiterCoefficientsDisplay:
    """_render_seven_day_limit() shows coefficient values when present in pacemaker_status."""

    def setup_method(self):
        self.r = UsageRenderer()
        self.usage = _make_usage()

    def _render_with_pm(self, pm_status, weekly_limit_enabled=True):
        return _render_to_str(
            self.r.render(
                error_message=None,
                last_usage=self.usage,
                last_profile=None,
                last_update=None,
                pacemaker_status=pm_status,
                weekly_limit_enabled=weekly_limit_enabled,
            )
        )

    def test_7d_limiter_always_shown_when_enabled(self):
        """7-Day Limiter: enabled line appears when weekly limit is enabled."""
        pm = _make_pm_status_with_coefficients(
            coeff_7d_5x=0.0011,
            coeff_7d_20x=0.000275,
        )
        rendered = self._render_with_pm(pm, weekly_limit_enabled=True)
        assert "7-Day Limiter" in rendered
        assert "enabled" in rendered

    def test_7d_coefficients_shown_when_enabled_and_present(self):
        """7-Day Limiter line includes coefficient values when pacemaker_status has them."""
        pm = _make_pm_status_with_coefficients(
            coeff_7d_5x=0.0011,
            coeff_7d_20x=0.000275,
        )
        rendered = self._render_with_pm(pm, weekly_limit_enabled=True)
        assert "7-Day Limiter" in rendered
        assert "0.0011" in rendered
        assert "0.0003" in rendered  # 0.000275 formatted to 4 decimal places

    def test_7d_coefficients_shown_when_disabled_and_present(self):
        """7-Day Limiter line includes coefficient values even when limiter is disabled."""
        pm = _make_pm_status_with_coefficients(
            coeff_7d_5x=0.0011,
            coeff_7d_20x=0.000275,
        )
        rendered = self._render_with_pm(pm, weekly_limit_enabled=False)
        assert "7-Day Limiter" in rendered
        assert "disabled" in rendered
        assert "0.0011" in rendered

    def test_7d_no_coefficients_key_backward_compatible(self):
        """When pacemaker_status has no coefficients_7d key, display still works."""
        pm = _make_pacemaker_status()
        rendered = self._render_with_pm(pm, weekly_limit_enabled=True)
        assert "7-Day Usage" in rendered

    def test_7d_none_coefficients_backward_compatible(self):
        """When coefficients_7d is None, display still works without coefficient text."""
        pm = _make_pacemaker_status()
        pm["coefficients_7d"] = None
        rendered = self._render_with_pm(pm, weekly_limit_enabled=True)
        assert "7-Day Usage" in rendered

    def test_7d_no_pacemaker_status_no_coefficients(self):
        """When pacemaker_status is None, no 5x: coefficient text appears in 7-day section."""
        rendered = self._render_with_pm(None, weekly_limit_enabled=True)
        assert "7-Day Usage" in rendered
        assert "5x:" not in rendered


# ===========================================================================
# Section 3: render() passes pacemaker_status through to both limiters
# ===========================================================================


class TestRenderPassesPacemakerStatusToLimiters:
    """render() passes pacemaker_status to both limiter render methods."""

    def setup_method(self):
        self.r = UsageRenderer()
        self.usage = _make_usage()

    def test_render_passes_5h_coefficients(self):
        """render() with pacemaker_status containing coefficients shows 5h coefficients."""
        pm = _make_pm_status_with_coefficients(
            coeff_5h_5x=0.0099,
            coeff_5h_20x=0.0024,
        )
        rendered = _render_to_str(
            self.r.render(
                error_message=None,
                last_usage=self.usage,
                last_profile=None,
                last_update=None,
                pacemaker_status=pm,
            )
        )
        assert "0.0099" in rendered

    def test_render_passes_7d_coefficients(self):
        """render() with pacemaker_status containing coefficients shows 7d coefficients."""
        pm = _make_pm_status_with_coefficients(
            coeff_7d_5x=0.0055,
            coeff_7d_20x=0.0014,
        )
        rendered = _render_to_str(
            self.r.render(
                error_message=None,
                last_usage=self.usage,
                last_profile=None,
                last_update=None,
                pacemaker_status=pm,
                weekly_limit_enabled=True,
            )
        )
        assert "0.0055" in rendered

    def test_render_without_pacemaker_status_no_coefficients(self):
        """When pacemaker_status is None, display renders without coefficients (no crash)."""
        rendered = _render_to_str(
            self.r.render(
                error_message=None,
                last_usage=self.usage,
                last_profile=None,
                last_update=None,
                pacemaker_status=None,
            )
        )
        assert "5-Hour Usage" in rendered
        assert "5x:" not in rendered


# ===========================================================================
# Helper for override-flag tests (Story #4)
# ===========================================================================


def _make_pm_status_with_override_flags(
    coeff_5h_5x: float = 0.0075,
    coeff_5h_20x: float = 0.001875,
    coeff_7d_5x: float = 0.0011,
    coeff_7d_20x: float = 0.000275,
    overridden_5x: bool = False,
    overridden_20x: bool = False,
    **kwargs,
) -> dict:
    """Build a pacemaker_status dict with both coefficients and override flags."""
    status = _make_pacemaker_status(**kwargs)
    status["coefficients_5h"] = {"5x": coeff_5h_5x, "20x": coeff_5h_20x}
    status["coefficients_7d"] = {"5x": coeff_7d_5x, "20x": coeff_7d_20x}
    status["coefficients_5x_overridden"] = overridden_5x
    status["coefficients_20x_overridden"] = overridden_20x
    return status


# ===========================================================================
# Section 4: get_status() returns override flags (Story #4)
# ===========================================================================


class TestGetStatusIncludesOverrideFlags:
    """get_status() must include coefficients_5x_overridden and coefficients_20x_overridden flags."""

    def test_override_flags_false_when_no_calibration(self):
        """Both override flags are False when no calibrated coefficients exist."""
        reader = _make_reader_with_data()
        mock_pe, mock_fb, mock_umc = _make_mock_get_status_environment()

        with (
            patch.object(reader, "is_installed", return_value=True),
            patch.object(reader, "_read_config", return_value=_STANDARD_CONFIG),
            patch.object(reader, "_get_latest_usage", return_value=_STANDARD_USAGE),
            patch.object(reader, "is_fallback_active", return_value=False),
        ):
            result = _call_get_status_with_mocks(reader, mock_pe, mock_fb, mock_umc)

        assert result is not None
        assert result["coefficients_5x_overridden"] is False
        assert result["coefficients_20x_overridden"] is False

    def test_5x_overridden_true_when_calibrated(self):
        """coefficients_5x_overridden is True when calibrated 5x coefficients exist."""
        reader = _make_reader_with_data()
        mock_pe, mock_fb, mock_umc = _make_mock_get_status_environment()

        mock_instance = mock_umc.return_value

        def calibrated_side_effect(tier):
            return (0.0088, 0.0013) if tier == "5x" else None

        mock_instance._get_calibrated_coefficients.side_effect = calibrated_side_effect

        with (
            patch.object(reader, "is_installed", return_value=True),
            patch.object(reader, "_read_config", return_value=_STANDARD_CONFIG),
            patch.object(reader, "_get_latest_usage", return_value=_STANDARD_USAGE),
            patch.object(reader, "is_fallback_active", return_value=False),
        ):
            result = _call_get_status_with_mocks(reader, mock_pe, mock_fb, mock_umc)

        assert result is not None
        assert result["coefficients_5x_overridden"] is True
        assert result["coefficients_20x_overridden"] is False

    def test_20x_overridden_true_when_calibrated(self):
        """coefficients_20x_overridden is True when calibrated 20x coefficients exist."""
        reader = _make_reader_with_data()
        mock_pe, mock_fb, mock_umc = _make_mock_get_status_environment()

        mock_instance = mock_umc.return_value

        def calibrated_side_effect(tier):
            return (0.0022, 0.00035) if tier == "20x" else None

        mock_instance._get_calibrated_coefficients.side_effect = calibrated_side_effect

        with (
            patch.object(reader, "is_installed", return_value=True),
            patch.object(reader, "_read_config", return_value=_STANDARD_CONFIG),
            patch.object(reader, "_get_latest_usage", return_value=_STANDARD_USAGE),
            patch.object(reader, "is_fallback_active", return_value=False),
        ):
            result = _call_get_status_with_mocks(reader, mock_pe, mock_fb, mock_umc)

        assert result is not None
        assert result["coefficients_5x_overridden"] is False
        assert result["coefficients_20x_overridden"] is True

    def test_override_flags_false_when_no_usage_data(self):
        """When no usage data, override flags are False in result dict."""
        reader = _make_reader_with_data()

        with (
            patch.object(reader, "is_installed", return_value=True),
            patch.object(reader, "_read_config", return_value=_STANDARD_CONFIG),
            patch.object(reader, "_get_latest_usage", return_value=None),
        ):
            result = reader.get_status()

        assert result is not None
        assert result.get("coefficients_5x_overridden") is False
        assert result.get("coefficients_20x_overridden") is False


# ===========================================================================
# Helper for display coloring tests (Story #4)
# ===========================================================================


def _render_display(r, pm_status, usage=None, **render_kwargs):
    """Render UsageRenderer to captured ANSI string for inspection.

    Uses force_terminal=True so Rich emits real ANSI escape codes (e.g. ESC[32m
    for green).  This differs from _render_to_str which strips all markup and is
    only suitable for plain-text content assertions.
    """
    from io import StringIO

    from rich.console import Console

    if usage is None:
        usage = _make_usage()
    buf = StringIO()
    console = Console(file=buf, width=120, force_terminal=True, highlight=False)
    rendered = r.render(
        error_message=None,
        last_usage=usage,
        last_profile=None,
        last_update=None,
        pacemaker_status=pm_status,
        **render_kwargs,
    )
    with console.capture() as capture:
        console.print(rendered)
    return capture.get()


# ===========================================================================
# Section 5: Display uses green for overridden 5-hour coefficients (Story #4)
# ===========================================================================


def _coeff_line(rendered: str, value: str) -> str:
    """Return the raw ANSI line that contains the given coefficient value string.

    Matches any limiter line that contains both the value and '5x:'.
    For limiter-specific matching use _coeff_line_7d.
    """
    for line in rendered.split("\n"):
        if value in line and "5x:" in line:
            return line
    return ""


def _coeff_line_7d(rendered: str, value: str) -> str:
    """Return the 7-Day Limiter ANSI line that contains the given coefficient value.

    Requires both '7-Day' and '5x:' on the line to avoid matching the 5-hour line
    when coefficient values happen to be identical.
    """
    for line in rendered.split("\n"):
        if value in line and "5x:" in line and "7-Day" in line:
            return line
    return ""


def _value_has_green(line: str, value: str) -> bool:
    """Return True iff a green ANSI code appears immediately before the value on this line.

    Rich renders [green] inside style="dim" as ESC[2;32m (combined dim+green),
    and bare [green] as ESC[32m.  Accept either form.
    """
    return f"\x1b[32m{value}" in line or f"\x1b[2;32m{value}" in line


class TestFiveHourLimiterOverrideColoring:
    """5-Hour Limiter coefficient values are green when overridden, plain when default."""

    def setup_method(self):
        self.r = UsageRenderer()

    def test_5h_overridden_5x_triggers_green_ansi(self):
        """When coefficients_5x_overridden=True, 5x value is wrapped in green ANSI."""
        pm = _make_pm_status_with_override_flags(
            coeff_5h_5x=0.0088, overridden_5x=True, overridden_20x=False
        )
        rendered = _render_display(self.r, pm)
        line = _coeff_line(rendered, "0.0088")
        assert line, "Coefficient line not found in rendered output"
        assert _value_has_green(line, "0.0088"), (
            f"Expected \\x1b[32m0.0088 in coefficient line, got: {repr(line)}"
        )

    def test_5h_non_overridden_5x_no_green_ansi_for_value(self):
        """When coefficients_5x_overridden=False, 5x value has no green ANSI wrapper."""
        pm = _make_pm_status_with_override_flags(
            coeff_5h_5x=0.0075, overridden_5x=False, overridden_20x=False
        )
        rendered = _render_display(self.r, pm)
        line = _coeff_line(rendered, "0.0075")
        assert line, "Coefficient line not found in rendered output"
        assert not _value_has_green(line, "0.0075"), (
            f"Expected no \\x1b[32m before 0.0075, got: {repr(line)}"
        )

    def test_5h_overridden_20x_triggers_green_ansi(self):
        """When coefficients_20x_overridden=True, 20x value is wrapped in green ANSI."""
        pm = _make_pm_status_with_override_flags(
            coeff_5h_20x=0.0022, overridden_5x=False, overridden_20x=True
        )
        rendered = _render_display(self.r, pm)
        line = _coeff_line(rendered, "0.0022")
        assert line, "Coefficient line not found in rendered output"
        assert _value_has_green(line, "0.0022"), (
            f"Expected \\x1b[32m0.0022 in coefficient line, got: {repr(line)}"
        )

    def test_5h_non_overridden_20x_no_green_ansi(self):
        """When coefficients_20x_overridden=False, 20x value has no green ANSI wrapper."""
        pm = _make_pm_status_with_override_flags(
            coeff_5h_20x=0.001875, overridden_5x=False, overridden_20x=False
        )
        rendered = _render_display(self.r, pm)
        line = _coeff_line(rendered, "0.0019")
        assert line, "Coefficient line not found in rendered output"
        assert not _value_has_green(line, "0.0019"), (
            f"Expected no \\x1b[32m before 0.0019, got: {repr(line)}"
        )


# ===========================================================================
# Section 6: Display uses green for overridden 7-day coefficients (Story #4)
# ===========================================================================


class TestSevenDayLimiterOverrideColoring:
    """7-Day Limiter coefficient values are green when overridden, plain when default."""

    def setup_method(self):
        self.r = UsageRenderer()

    def test_7d_overridden_5x_triggers_green_ansi(self):
        """When coefficients_5x_overridden=True, 7-day 5x value is wrapped in green ANSI."""
        pm = _make_pm_status_with_override_flags(
            coeff_7d_5x=0.0099, overridden_5x=True, overridden_20x=False
        )
        rendered = _render_display(self.r, pm)
        line = _coeff_line_7d(rendered, "0.0099")
        assert line, "7-Day coefficient line not found in rendered output"
        assert _value_has_green(line, "0.0099"), (
            f"Expected \\x1b[32m0.0099 in 7-day coefficient line, got: {repr(line)}"
        )

    def test_7d_non_overridden_5x_no_green_ansi_for_value(self):
        """When coefficients_5x_overridden=False, 7-day 5x value has no green ANSI wrapper."""
        pm = _make_pm_status_with_override_flags(
            coeff_7d_5x=0.0011, overridden_5x=False, overridden_20x=False
        )
        rendered = _render_display(self.r, pm)
        line = _coeff_line_7d(rendered, "0.0011")
        assert line, "7-Day coefficient line not found in rendered output"
        assert not _value_has_green(line, "0.0011"), (
            f"Expected no \\x1b[32m before 0.0011 on 7-day line, got: {repr(line)}"
        )
