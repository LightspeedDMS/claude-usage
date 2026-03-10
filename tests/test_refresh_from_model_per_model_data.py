#!/usr/bin/env python3
"""
TDD tests for _refresh_from_model() per-model data regression fix.

REGRESSION (commit cee8bbb, Mar 7 2026): _refresh_from_model() builds
self.last_usage with only five_hour/seven_day keys, dropping per-model
fields (seven_day_sonnet, seven_day_opus) from the raw API response.

FIX: After building the basic dict, read raw_response from get_api_cache()
and merge per-model fields into self.last_usage.

These tests are written FIRST (TDD red phase) and fail until the fix lands.
"""

import json
import sys
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

# Add claude-usage src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Add pace-maker src to path so UsageModel is importable
_PM_SRC = Path(__file__).parent.parent.parent / "claude-pace-maker" / "src"
if str(_PM_SRC) not in sys.path:
    sys.path.insert(0, str(_PM_SRC))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pm_dir(tmp_path: Path) -> Path:
    """Create a minimal ~/.claude-pace-maker structure."""
    pm_dir = tmp_path / ".claude-pace-maker"
    pm_dir.mkdir()
    return pm_dir


def _write_config(pm_dir: Path) -> None:
    """Write minimal config.json."""
    config = {
        "enabled": True,
        "weekly_limit_enabled": True,
        "five_hour_limit_enabled": True,
        "intent_validation_enabled": False,
        "tdd_enabled": True,
        "log_level": 2,
        "preferred_subagent_model": "auto",
    }
    (pm_dir / "config.json").write_text(json.dumps(config))


def _make_usage_model(db_path: str):
    """Instantiate UsageModel from pace-maker src."""
    from pacemaker.usage_model import UsageModel

    return UsageModel(db_path=db_path)


def _make_monitor(pm_dir: Path):
    """Create a CodeMonitor instance with all I/O stubbed out.

    Returns a CodeMonitor whose pacemaker_reader points at pm_dir
    so _refresh_from_model() reads the test DB.
    """
    from claude_usage.code_mode.monitor import CodeMonitor
    from claude_usage.code_mode.pacemaker_integration import PaceMakerReader

    with patch("claude_usage.code_mode.monitor.OAuthManager") as mock_oauth_cls, patch(
        "claude_usage.code_mode.monitor.ClaudeAPIClient"
    ), patch("claude_usage.code_mode.monitor.CodeStorage"), patch(
        "claude_usage.code_mode.monitor.CodeAnalytics"
    ), patch(
        "claude_usage.code_mode.monitor.UsageRenderer"
    ):
        mock_oauth = MagicMock()
        mock_oauth.load_credentials.return_value = (None, None)
        mock_oauth_cls.return_value = mock_oauth

        monitor = CodeMonitor.__new__(CodeMonitor)
        monitor.credentials = None
        monitor.org_uuid = None
        monitor.account_uuid = None
        monitor.last_usage = None
        monitor.last_profile = None
        monitor.last_update = None
        monitor.error_message = None
        monitor.CACHE_FRESHNESS_SECONDS = 360

        # Wire up a real PaceMakerReader pointing at our test pm_dir
        reader = PaceMakerReader()
        reader.pm_dir = pm_dir
        reader.config_path = pm_dir / "config.json"
        reader.db_path = pm_dir / "usage.db"
        reader.state_path = pm_dir / "state.json"
        monitor.pacemaker_reader = reader

        return monitor


def _store_api_response_with_per_model(
    model,
    five_hour_util: float = 40.0,
    seven_day_util: float = 30.0,
    seven_day_sonnet: Optional[dict] = None,
    seven_day_opus: Optional[dict] = None,
) -> None:
    """Store an API response that includes per-model fields in raw_response."""
    response = {
        "five_hour": {
            "utilization": five_hour_util,
            "resets_at": "2099-01-01T12:00:00+00:00",
        },
        "seven_day": {
            "utilization": seven_day_util,
            "resets_at": "2099-01-07T12:00:00+00:00",
        },
    }
    if seven_day_sonnet is not None:
        response["seven_day_sonnet"] = seven_day_sonnet
    if seven_day_opus is not None:
        response["seven_day_opus"] = seven_day_opus

    model.store_api_response(response)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRefreshFromModelPerModelData:
    """_refresh_from_model() must include per-model fields from raw_response."""

    def test_seven_day_sonnet_present_when_raw_response_has_it(self, tmp_path):
        """When raw_response contains seven_day_sonnet, it must appear in self.last_usage.

        REGRESSION: Before fix, seven_day_sonnet was silently dropped.
        After fix, it should be merged from get_api_cache().raw_response.
        """
        pm_dir = _make_pm_dir(tmp_path)
        _write_config(pm_dir)

        model = _make_usage_model(str(pm_dir / "usage.db"))
        sonnet_data = {
            "utilization": 35.0,
            "resets_at": "2026-03-13T00:00:00+00:00",
        }
        _store_api_response_with_per_model(
            model,
            five_hour_util=40.0,
            seven_day_util=30.0,
            seven_day_sonnet=sonnet_data,
        )

        monitor = _make_monitor(pm_dir)
        result = monitor._refresh_from_model()

        assert (
            result is True
        ), "_refresh_from_model() must return True when data is available"
        assert monitor.last_usage is not None
        assert "seven_day_sonnet" in monitor.last_usage, (
            "REGRESSION: seven_day_sonnet missing from last_usage — "
            "raw_response per-model fields are not being merged"
        )
        assert monitor.last_usage["seven_day_sonnet"]["utilization"] == 35.0
        assert "resets_at" in monitor.last_usage["seven_day_sonnet"]

    def test_seven_day_opus_present_when_raw_response_has_it(self, tmp_path):
        """When raw_response contains seven_day_opus, it must appear in self.last_usage."""
        pm_dir = _make_pm_dir(tmp_path)
        _write_config(pm_dir)

        model = _make_usage_model(str(pm_dir / "usage.db"))
        opus_data = {
            "utilization": 12.5,
            "resets_at": "2026-03-13T00:00:00+00:00",
        }
        _store_api_response_with_per_model(
            model,
            five_hour_util=50.0,
            seven_day_util=45.0,
            seven_day_opus=opus_data,
        )

        monitor = _make_monitor(pm_dir)
        result = monitor._refresh_from_model()

        assert result is True
        assert monitor.last_usage is not None
        assert (
            "seven_day_opus" in monitor.last_usage
        ), "REGRESSION: seven_day_opus missing from last_usage"
        assert monitor.last_usage["seven_day_opus"]["utilization"] == 12.5

    def test_null_per_model_fields_not_included_in_last_usage(self, tmp_path):
        """Per-model fields that are null in raw_response must NOT be truthy in last_usage.

        The display code checks `if usage_data.get("seven_day_sonnet"):` so a null
        value would be treated as absent. We must not silently inject None values.
        """
        pm_dir = _make_pm_dir(tmp_path)
        _write_config(pm_dir)

        model = _make_usage_model(str(pm_dir / "usage.db"))
        # Store response with seven_day_opus explicitly null
        response = {
            "five_hour": {
                "utilization": 20.0,
                "resets_at": "2099-01-01T12:00:00+00:00",
            },
            "seven_day": {
                "utilization": 15.0,
                "resets_at": "2099-01-07T12:00:00+00:00",
            },
            "seven_day_sonnet": {
                "utilization": 10.0,
                "resets_at": "2099-01-07T12:00:00+00:00",
            },
            "seven_day_opus": None,
        }
        model.store_api_response(response)

        monitor = _make_monitor(pm_dir)
        result = monitor._refresh_from_model()

        assert result is True
        assert monitor.last_usage is not None
        # sonnet IS present (non-null) → must be in last_usage
        assert "seven_day_sonnet" in monitor.last_usage
        # opus IS null → must NOT be truthy in last_usage
        # The key requirement: display code `if usage_data.get("seven_day_opus"):` must be False
        assert not monitor.last_usage.get(
            "seven_day_opus"
        ), "seven_day_opus is null in raw_response — it must not be truthy in last_usage"

    def test_refresh_from_model_no_crash_when_get_api_cache_returns_none(
        self, tmp_path
    ):
        """_refresh_from_model() must not crash when get_api_cache() returns None.

        This happens when the UsageModel has a snapshot but api_cache is somehow
        empty. The basic five_hour/seven_day data should still be set.
        """
        pm_dir = _make_pm_dir(tmp_path)
        _write_config(pm_dir)

        model = _make_usage_model(str(pm_dir / "usage.db"))
        _store_api_response_with_per_model(
            model, five_hour_util=25.0, seven_day_util=18.0
        )

        monitor = _make_monitor(pm_dir)

        # Patch get_api_cache to return None only on 2nd+ call (1st call is
        # inside get_current_usage -> _get_api_snapshot which needs real data)
        original_get_api_cache = model.get_api_cache
        call_count = {"n": 0}

        def _get_api_cache_side_effect():
            call_count["n"] += 1
            if call_count["n"] <= 1:
                return original_get_api_cache()
            return None

        with patch(
            "pacemaker.usage_model.UsageModel.get_api_cache",
            side_effect=_get_api_cache_side_effect,
        ):
            result = monitor._refresh_from_model()

        # Must not crash and must still return True with basic data
        assert result is True
        assert monitor.last_usage is not None
        assert "five_hour" in monitor.last_usage
        assert "seven_day" in monitor.last_usage
        # No per-model keys should be injected when cache is None
        assert "seven_day_sonnet" not in monitor.last_usage
        assert "seven_day_opus" not in monitor.last_usage

    def test_refresh_from_model_no_crash_when_raw_response_missing(self, tmp_path):
        """_refresh_from_model() must not crash when cache has no raw_response key.

        Edge case: get_api_cache() returns a dict without 'raw_response'.
        """
        pm_dir = _make_pm_dir(tmp_path)
        _write_config(pm_dir)

        model = _make_usage_model(str(pm_dir / "usage.db"))
        _store_api_response_with_per_model(
            model, five_hour_util=22.0, seven_day_util=11.0
        )

        monitor = _make_monitor(pm_dir)

        # Patch get_api_cache to return a dict missing raw_response on 2nd call
        # (1st call is inside get_current_usage -> _get_api_snapshot)
        original_get_api_cache = model.get_api_cache
        call_count = {"n": 0}
        cache_without_raw = {
            "five_hour_util": 22.0,
            "seven_day_util": 11.0,
            # deliberately no 'raw_response' key
        }

        def _side_effect():
            call_count["n"] += 1
            if call_count["n"] <= 1:
                return original_get_api_cache()
            return cache_without_raw

        with patch(
            "pacemaker.usage_model.UsageModel.get_api_cache",
            side_effect=_side_effect,
        ):
            result = monitor._refresh_from_model()

        assert result is True
        assert monitor.last_usage is not None
        assert "five_hour" in monitor.last_usage
        assert "seven_day" in monitor.last_usage
        # No per-model keys — graceful absence
        assert "seven_day_sonnet" not in monitor.last_usage
        assert "seven_day_opus" not in monitor.last_usage

    def test_basic_five_hour_and_seven_day_still_populated(self, tmp_path):
        """Fix must not break existing five_hour/seven_day population in last_usage."""
        pm_dir = _make_pm_dir(tmp_path)
        _write_config(pm_dir)

        model = _make_usage_model(str(pm_dir / "usage.db"))
        _store_api_response_with_per_model(
            model,
            five_hour_util=60.0,
            seven_day_util=55.0,
            seven_day_sonnet={
                "utilization": 42.0,
                "resets_at": "2026-03-13T00:00:00+00:00",
            },
        )

        monitor = _make_monitor(pm_dir)
        result = monitor._refresh_from_model()

        assert result is True
        assert monitor.last_usage is not None
        # Basic keys still present
        assert "five_hour" in monitor.last_usage
        assert "seven_day" in monitor.last_usage
        assert abs(monitor.last_usage["five_hour"]["utilization"] - 60.0) < 0.01
        assert abs(monitor.last_usage["seven_day"]["utilization"] - 55.0) < 0.01
        # Per-model key also present
        assert "seven_day_sonnet" in monitor.last_usage
        assert abs(monitor.last_usage["seven_day_sonnet"]["utilization"] - 42.0) < 0.01
