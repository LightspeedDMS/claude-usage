"""Regression tests for monitor behavior during API 429 / backoff.

Tests the full pipeline: UsageModel returns naive timestamps → monitor's
_refresh_from_model() populates last_usage → get_display() renders a
complete frame with error banner AND progress bars.

Mocks: UsageModel (external dependency), PaceMakerReader (external),
       OAuthManager/credentials (external).
Real:  _refresh_from_model() logic, UsageRenderer (the visualization).
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from io import StringIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from claude_usage.code_mode.monitor import CodeMonitor


def _render_frame_to_str(display, width: int = 120) -> str:
    """Render a Rich display object to plain string."""
    from rich.console import Console

    console = Console(file=StringIO(), width=width, force_terminal=True)
    with console.capture() as capture:
        console.print(display)
    return capture.get()


def _make_naive_snapshot(
    five_util: float = 25.0,
    seven_util: float = 60.0,
    age_seconds: float = 30.0,
) -> SimpleNamespace:
    """Create a UsageSnapshot-like object with NAIVE timestamps (no tzinfo).

    This is what UsageModel actually returns — the root cause of the bug.
    Uses datetime.now(timezone.utc).replace(tzinfo=None) instead of the
    deprecated datetime.utcnow().
    """
    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    ts = now_naive - timedelta(seconds=age_seconds)
    return SimpleNamespace(
        five_hour_util=five_util,
        five_hour_resets_at=now_naive + timedelta(hours=3),
        seven_day_util=seven_util,
        seven_day_resets_at=now_naive + timedelta(days=5),
        is_synthetic=False,
        timestamp=ts,
    )


def _make_aware_snapshot(
    five_util: float = 25.0,
    seven_util: float = 60.0,
    age_seconds: float = 30.0,
) -> SimpleNamespace:
    """Create a UsageSnapshot-like object with AWARE timestamps."""
    now_aware = datetime.now(timezone.utc)
    ts = now_aware - timedelta(seconds=age_seconds)
    return SimpleNamespace(
        five_hour_util=five_util,
        five_hour_resets_at=now_aware + timedelta(hours=3),
        seven_day_util=seven_util,
        seven_day_resets_at=now_aware + timedelta(days=5),
        is_synthetic=False,
        timestamp=ts,
    )


def _make_profile(name: str = "TestUser", org: str = "TestOrg") -> dict:
    return {
        "account": {
            "display_name": name,
            "email": f"{name.lower()}@test.com",
            "has_claude_pro": False,
            "has_claude_max": True,
        },
        "organization": {
            "name": org,
            "organization_type": "",
            "rate_limit_tier": "20x",
        },
    }


@pytest.fixture
def monitor_no_io(tmp_path):
    """Create a CodeMonitor with all I/O mocked out."""
    creds_path = tmp_path / "creds.json"
    creds_path.write_text("{}")

    with patch(
        "claude_usage.code_mode.monitor.OAuthManager"
    ) as mock_oauth, patch(
        "claude_usage.code_mode.monitor.ClaudeAPIClient"
    ), patch(
        "claude_usage.code_mode.monitor.CodeStorage"
    ), patch(
        "claude_usage.code_mode.monitor.CodeAnalytics"
    ), patch(
        "claude_usage.code_mode.monitor.PaceMakerReader"
    ) as mock_pm_cls:
        mock_oauth.return_value.load_credentials.return_value = (None, None)

        mock_pm = mock_pm_cls.return_value
        mock_pm.is_installed.return_value = True
        mock_pm._get_pacemaker_src_path.return_value = "/fake/src"

        m = CodeMonitor(credentials_path=creds_path)
        yield m


# ===========================================================================
# F1 — _refresh_from_model() actually called with naive timestamps
# ===========================================================================


class TestRefreshFromModelNaiveTimestamps:
    """Actually call _refresh_from_model() with mocked UsageModel returning
    naive timestamps — verifies the fix works end-to-end."""

    def test_naive_snapshot_populates_last_usage(self, monitor_no_io):
        """_refresh_from_model() must handle naive timestamps without crashing."""
        snapshot = _make_naive_snapshot(five_util=12.0, seven_util=75.0)

        mock_usage_model_cls = MagicMock()
        mock_usage_model_cls.return_value.get_current_usage.return_value = snapshot

        mock_module = MagicMock()
        mock_module.UsageModel = mock_usage_model_cls

        with patch.dict(sys.modules, {"pacemaker.usage_model": mock_module}):
            result = monitor_no_io._refresh_from_model()

        assert result is True, "_refresh_from_model should return True"
        assert monitor_no_io.last_usage is not None
        assert monitor_no_io.last_usage["five_hour"]["utilization"] == 12.0
        assert monitor_no_io.last_usage["seven_day"]["utilization"] == 75.0
        assert monitor_no_io.last_update is not None
        assert monitor_no_io.last_update.tzinfo is not None, (
            "last_update must be timezone-aware"
        )

    def test_aware_snapshot_also_works(self, monitor_no_io):
        """Aware timestamps should still work (no regression)."""
        snapshot = _make_aware_snapshot(five_util=50.0, seven_util=30.0)

        mock_usage_model_cls = MagicMock()
        mock_usage_model_cls.return_value.get_current_usage.return_value = snapshot

        mock_module = MagicMock()
        mock_module.UsageModel = mock_usage_model_cls

        with patch.dict(sys.modules, {"pacemaker.usage_model": mock_module}):
            result = monitor_no_io._refresh_from_model()

        assert result is True
        assert monitor_no_io.last_usage is not None
        assert monitor_no_io.last_usage["five_hour"]["utilization"] == 50.0
        assert monitor_no_io.last_update.tzinfo is not None

    def test_stale_naive_snapshot_accepted_when_no_prior_data(self, monitor_no_io):
        """When last_usage is None, accept stale data beyond freshness window."""
        # age_seconds=500 > CACHE_FRESHNESS_SECONDS=360
        snapshot = _make_naive_snapshot(five_util=8.0, seven_util=90.0, age_seconds=500)

        mock_usage_model_cls = MagicMock()
        mock_usage_model_cls.return_value.get_current_usage.return_value = snapshot

        mock_module = MagicMock()
        mock_module.UsageModel = mock_usage_model_cls

        assert monitor_no_io.last_usage is None  # No prior data

        with patch.dict(sys.modules, {"pacemaker.usage_model": mock_module}):
            result = monitor_no_io._refresh_from_model()

        assert result is True, "Stale data must be accepted when no prior data exists"
        assert monitor_no_io.last_usage["five_hour"]["utilization"] == 8.0

    def test_stale_naive_snapshot_rejected_when_prior_data_exists(self, monitor_no_io):
        """When last_usage exists, stale data beyond freshness is rejected."""
        # Pre-populate with existing data
        monitor_no_io.last_usage = {"five_hour": {"utilization": 20.0, "resets_at": ""}}
        monitor_no_io.last_update = datetime.now(timezone.utc)

        # age_seconds=500 > CACHE_FRESHNESS_SECONDS=360
        snapshot = _make_naive_snapshot(five_util=8.0, seven_util=90.0, age_seconds=500)

        mock_usage_model_cls = MagicMock()
        mock_usage_model_cls.return_value.get_current_usage.return_value = snapshot

        mock_module = MagicMock()
        mock_module.UsageModel = mock_usage_model_cls

        with patch.dict(sys.modules, {"pacemaker.usage_model": mock_module}):
            result = monitor_no_io._refresh_from_model()

        assert result is False, "Stale data should be rejected when fresh data exists"
        # Original data preserved
        assert monitor_no_io.last_usage["five_hour"]["utilization"] == 20.0

    def test_none_snapshot_returns_false(self, monitor_no_io):
        """No snapshot available returns False."""
        mock_usage_model_cls = MagicMock()
        mock_usage_model_cls.return_value.get_current_usage.return_value = None

        mock_module = MagicMock()
        mock_module.UsageModel = mock_usage_model_cls

        with patch.dict(sys.modules, {"pacemaker.usage_model": mock_module}):
            result = monitor_no_io._refresh_from_model()

        assert result is False


# ===========================================================================
# F2 — Full frame rendering during 429 backoff
# ===========================================================================


class TestMonitor429FrameRendering:
    """Full frame rendering during 429 backoff — error + progress bars."""

    def test_429_with_stale_usage_renders_error_and_bars(self, monitor_no_io):
        """Simulate: API returned 429, but we have stale usage data."""
        monitor_no_io.last_usage = {
            "five_hour": {
                "utilization": 12.0,
                "resets_at": (
                    datetime.now(timezone.utc) + timedelta(hours=2)
                ).isoformat(),
            },
            "seven_day": {
                "utilization": 75.0,
                "resets_at": (
                    datetime.now(timezone.utc) + timedelta(days=3)
                ).isoformat(),
            },
        }
        monitor_no_io.last_update = datetime.now(timezone.utc) - timedelta(minutes=5)
        monitor_no_io.error_message = "API rate limited (429) after retries"
        monitor_no_io.last_profile = _make_profile()
        monitor_no_io.pacemaker_reader.is_installed.return_value = False

        display = monitor_no_io.get_display()
        frame = _render_frame_to_str(display)

        assert "429" in frame
        assert "API rate limited" in frame
        assert "TestUser" in frame
        assert "5-Hour" in frame, "5-hour bar missing during 429!"
        assert "7-Day" in frame, "7-day bar missing during 429!"

    def test_429_no_prior_usage_shows_error_only(self, monitor_no_io):
        """No prior data → error + profile, no bars."""
        monitor_no_io.last_usage = None
        monitor_no_io.error_message = "API rate limited (429) after retries"
        monitor_no_io.last_profile = _make_profile()
        monitor_no_io.pacemaker_reader.is_installed.return_value = False

        display = monitor_no_io.get_display()
        frame = _render_frame_to_str(display)

        assert "429" in frame
        assert "TestUser" in frame
        assert "5-Hour" not in frame

    def test_backoff_error_with_stale_data_renders_full_ui(self, monitor_no_io):
        """Pace-maker backoff error with stale data shows everything."""
        monitor_no_io.last_usage = {
            "five_hour": {
                "utilization": 40.0,
                "resets_at": (
                    datetime.now(timezone.utc) + timedelta(hours=1)
                ).isoformat(),
            },
            "seven_day": {
                "utilization": 55.0,
                "resets_at": (
                    datetime.now(timezone.utc) + timedelta(days=2)
                ).isoformat(),
            },
        }
        monitor_no_io.last_update = datetime.now(timezone.utc) - timedelta(minutes=10)
        monitor_no_io.error_message = "API backoff (pace-maker): 450s remaining"
        monitor_no_io.last_profile = _make_profile("Alice", "Acme")
        monitor_no_io.pacemaker_reader.is_installed.return_value = False

        display = monitor_no_io.get_display()
        frame = _render_frame_to_str(display)

        assert "backoff" in frame.lower()
        assert "Alice" in frame
        assert "5-Hour" in frame
        assert "7-Day" in frame

    def test_error_appears_before_bars_in_frame(self, monitor_no_io):
        """Error banner must be at the top, before progress bars."""
        monitor_no_io.last_usage = {
            "five_hour": {
                "utilization": 20.0,
                "resets_at": (
                    datetime.now(timezone.utc) + timedelta(hours=2)
                ).isoformat(),
            },
            "seven_day": {
                "utilization": 50.0,
                "resets_at": (
                    datetime.now(timezone.utc) + timedelta(days=1)
                ).isoformat(),
            },
        }
        monitor_no_io.last_update = datetime.now(timezone.utc)
        monitor_no_io.error_message = "Rate limited"
        monitor_no_io.last_profile = _make_profile("X", "O")
        monitor_no_io.pacemaker_reader.is_installed.return_value = False

        display = monitor_no_io.get_display()
        frame = _render_frame_to_str(display)

        error_pos = frame.lower().find("rate limited")
        bar_pos = frame.find("5-Hour")
        assert error_pos >= 0, "Error message not found in frame"
        assert bar_pos >= 0, "5-Hour bar not found in frame"
        assert error_pos < bar_pos, "Error must appear before progress bars"

    def test_naive_snapshot_to_full_frame(self, monitor_no_io):
        """End-to-end: _refresh_from_model() with naive snapshot → frame has bars."""
        snapshot = _make_naive_snapshot(five_util=7.0, seven_util=82.0, age_seconds=10)

        mock_usage_model_cls = MagicMock()
        mock_usage_model_cls.return_value.get_current_usage.return_value = snapshot

        mock_module = MagicMock()
        mock_module.UsageModel = mock_usage_model_cls

        with patch.dict(sys.modules, {"pacemaker.usage_model": mock_module}):
            result = monitor_no_io._refresh_from_model()
        assert result is True

        # Now simulate 429 error arriving after we got the data
        monitor_no_io.error_message = "API rate limited (429) after retries"
        monitor_no_io.last_profile = _make_profile("Seba", "LightspeedDMS")
        monitor_no_io.pacemaker_reader.is_installed.return_value = False

        display = monitor_no_io.get_display()
        frame = _render_frame_to_str(display)

        assert "429" in frame
        assert "Seba" in frame
        assert "MAX" in frame
        assert "5-Hour" in frame, "5-hour bar missing from naive snapshot data!"
        assert "7-Day" in frame, "7-day bar missing from naive snapshot data!"
