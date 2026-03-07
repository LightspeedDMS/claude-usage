"""Tests for monitor behavior during API backoff when usage cache is available.

TDD: Tests written first. They define the expected behavior of the fix:

- During API backoff + cache exists: full display (return True with cached data)
- During API backoff + no cache + no previous data: error shown (return False)
- During API backoff + stale cache (older than CACHE_FRESHNESS_SECONDS): still use it
- fetch_profile() preserves last_profile during backoff instead of overwriting with None
"""

import json
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch


def _make_monitor():
    """Create a CodeMonitor with all dependencies mocked."""
    with (
        patch("claude_usage.code_mode.monitor.OAuthManager"),
        patch("claude_usage.code_mode.monitor.ClaudeAPIClient"),
        patch("claude_usage.code_mode.monitor.CodeStorage"),
        patch("claude_usage.code_mode.monitor.CodeAnalytics"),
        patch("claude_usage.code_mode.monitor.UsageRenderer"),
        patch("claude_usage.code_mode.monitor.PaceMakerReader"),
    ):
        from claude_usage.code_mode.monitor import CodeMonitor

        monitor = CodeMonitor.__new__(CodeMonitor)
        monitor.credentials = {
            "access_token": "test-token",
            "expires_at": 9999999999,
        }
        monitor.org_uuid = None
        monitor.account_uuid = None
        monitor.last_usage = None
        monitor.last_profile = None
        monitor.last_update = None
        monitor.error_message = None
        monitor.api_client = MagicMock()
        monitor.oauth_manager = MagicMock()
        monitor.pacemaker_reader = MagicMock()
        monitor.pacemaker_reader.is_installed.return_value = True
        monitor.oauth_manager.is_token_expired.return_value = False
        monitor.oauth_manager.get_auth_headers.return_value = {
            "Authorization": "Bearer test"
        }
        return monitor


_SAMPLE_USAGE = {
    "five_hour": {"utilization": 7.0, "resets_at": "2099-01-01T00:00:00"},
    "seven_day": {"utilization": 12.0, "resets_at": "2099-01-01T00:00:00"},
}


class TestFetchUsageBackoffWithFreshCache(unittest.TestCase):
    """When backoff is active AND a fresh cache exists, use the cache."""

    def _backoff_data(self, seconds_remaining=600):
        future = time.time() + seconds_remaining
        return json.dumps({"backoff_until": future, "consecutive_429s": 2})

    def _cache_data(self, age_seconds=30):
        ts = time.time() - age_seconds
        return json.dumps({"timestamp": ts, "response": _SAMPLE_USAGE})

    def test_returns_true_when_backoff_active_and_fresh_cache_exists(self):
        """fetch_usage must return True (full display) when backoff is on but cache is fresh."""
        monitor = _make_monitor()

        backoff_json = self._backoff_data()
        cache_json = self._cache_data(age_seconds=30)

        def path_exists(self_path):
            name = Path(self_path).name
            return name in ("api_backoff.json", "usage_cache.json")

        def path_read_text(self_path):
            name = Path(self_path).name
            if name == "api_backoff.json":
                return backoff_json
            if name == "usage_cache.json":
                return cache_json
            raise FileNotFoundError(name)

        with (
            patch.object(Path, "exists", path_exists),
            patch.object(Path, "read_text", path_read_text),
        ):
            result = monitor.fetch_usage()

        self.assertTrue(result)

    def test_last_usage_populated_from_cache_during_backoff(self):
        """last_usage must be set from cache data when backoff is active."""
        monitor = _make_monitor()

        backoff_json = self._backoff_data()
        cache_json = self._cache_data(age_seconds=30)

        def path_exists(self_path):
            return Path(self_path).name in ("api_backoff.json", "usage_cache.json")

        def path_read_text(self_path):
            name = Path(self_path).name
            if name == "api_backoff.json":
                return backoff_json
            if name == "usage_cache.json":
                return cache_json
            raise FileNotFoundError(name)

        with (
            patch.object(Path, "exists", path_exists),
            patch.object(Path, "read_text", path_read_text),
        ):
            monitor.fetch_usage()

        self.assertEqual(monitor.last_usage, _SAMPLE_USAGE)

    def test_last_update_set_from_cache_timestamp_during_backoff(self):
        """last_update must be set from the cache file timestamp when backoff is active."""
        monitor = _make_monitor()
        cache_ts = time.time() - 30

        backoff_json = self._backoff_data()
        cache_json = json.dumps({"timestamp": cache_ts, "response": _SAMPLE_USAGE})

        def path_exists(self_path):
            return Path(self_path).name in ("api_backoff.json", "usage_cache.json")

        def path_read_text(self_path):
            name = Path(self_path).name
            if name == "api_backoff.json":
                return backoff_json
            if name == "usage_cache.json":
                return cache_json
            raise FileNotFoundError(name)

        with (
            patch.object(Path, "exists", path_exists),
            patch.object(Path, "read_text", path_read_text),
        ):
            monitor.fetch_usage()

        expected_dt = datetime.fromtimestamp(cache_ts)
        self.assertIsNotNone(monitor.last_update)
        self.assertAlmostEqual(
            monitor.last_update.timestamp(), expected_dt.timestamp(), delta=1
        )

    def test_error_message_cleared_when_cache_used_during_backoff(self):
        """error_message must be None (not the backoff text) when cache is served."""
        monitor = _make_monitor()
        monitor.error_message = "previous error"

        backoff_json = self._backoff_data()
        cache_json = self._cache_data(age_seconds=30)

        def path_exists(self_path):
            return Path(self_path).name in ("api_backoff.json", "usage_cache.json")

        def path_read_text(self_path):
            name = Path(self_path).name
            if name == "api_backoff.json":
                return backoff_json
            if name == "usage_cache.json":
                return cache_json
            raise FileNotFoundError(name)

        with (
            patch.object(Path, "exists", path_exists),
            patch.object(Path, "read_text", path_read_text),
        ):
            monitor.fetch_usage()

        self.assertIsNone(monitor.error_message)

    def test_api_not_called_when_cache_satisfies_backoff_request(self):
        """API client must NOT be called when cache serves the request during backoff."""
        monitor = _make_monitor()

        backoff_json = self._backoff_data()
        cache_json = self._cache_data(age_seconds=30)

        def path_exists(self_path):
            return Path(self_path).name in ("api_backoff.json", "usage_cache.json")

        def path_read_text(self_path):
            name = Path(self_path).name
            if name == "api_backoff.json":
                return backoff_json
            if name == "usage_cache.json":
                return cache_json
            raise FileNotFoundError(name)

        with (
            patch.object(Path, "exists", path_exists),
            patch.object(Path, "read_text", path_read_text),
        ):
            monitor.fetch_usage()

        monitor.api_client.fetch_usage.assert_not_called()


class TestFetchUsageBackoffWithStaleCache(unittest.TestCase):
    """During backoff, stale cache (older than CACHE_FRESHNESS_SECONDS) must still be used."""

    def _backoff_data(self):
        return json.dumps({"backoff_until": time.time() + 600, "consecutive_429s": 2})

    def test_returns_true_with_stale_cache_during_backoff(self):
        """Stale cache must still be accepted when backoff is active."""
        from claude_usage.code_mode.monitor import CodeMonitor

        monitor = _make_monitor()
        # Cache is far older than CACHE_FRESHNESS_SECONDS (360s)
        stale_ts = time.time() - (CodeMonitor.CACHE_FRESHNESS_SECONDS + 3600)
        backoff_json = self._backoff_data()
        cache_json = json.dumps({"timestamp": stale_ts, "response": _SAMPLE_USAGE})

        def path_exists(self_path):
            return Path(self_path).name in ("api_backoff.json", "usage_cache.json")

        def path_read_text(self_path):
            name = Path(self_path).name
            if name == "api_backoff.json":
                return backoff_json
            if name == "usage_cache.json":
                return cache_json
            raise FileNotFoundError(name)

        with (
            patch.object(Path, "exists", path_exists),
            patch.object(Path, "read_text", path_read_text),
        ):
            result = monitor.fetch_usage()

        self.assertTrue(result)
        self.assertEqual(monitor.last_usage, _SAMPLE_USAGE)

    def test_last_usage_set_from_stale_cache_during_backoff(self):
        """last_usage must be populated even from a stale cache during backoff."""
        from claude_usage.code_mode.monitor import CodeMonitor

        monitor = _make_monitor()
        stale_ts = time.time() - (CodeMonitor.CACHE_FRESHNESS_SECONDS + 7200)
        cache_json = json.dumps({"timestamp": stale_ts, "response": _SAMPLE_USAGE})
        backoff_json = self._backoff_data()

        def path_exists(self_path):
            return Path(self_path).name in ("api_backoff.json", "usage_cache.json")

        def path_read_text(self_path):
            name = Path(self_path).name
            if name == "api_backoff.json":
                return backoff_json
            if name == "usage_cache.json":
                return cache_json
            raise FileNotFoundError(name)

        with (
            patch.object(Path, "exists", path_exists),
            patch.object(Path, "read_text", path_read_text),
        ):
            monitor.fetch_usage()

        self.assertEqual(monitor.last_usage, _SAMPLE_USAGE)
        self.assertIsNone(monitor.error_message)


class TestFetchUsageBackoffNoCacheNoPreviousData(unittest.TestCase):
    """During backoff, when no cache AND no previous last_usage, show error."""

    def _backoff_data(self):
        return json.dumps({"backoff_until": time.time() + 600, "consecutive_429s": 2})

    def test_returns_false_when_backoff_active_and_no_cache_no_previous(self):
        """fetch_usage must return False when backoff is on and there's no data at all."""
        monitor = _make_monitor()
        monitor.last_usage = None

        backoff_json = self._backoff_data()

        def path_exists(self_path):
            name = Path(self_path).name
            # backoff file exists, cache file does NOT
            return name == "api_backoff.json"

        def path_read_text(self_path):
            name = Path(self_path).name
            if name == "api_backoff.json":
                return backoff_json
            raise FileNotFoundError(name)

        with (
            patch.object(Path, "exists", path_exists),
            patch.object(Path, "read_text", path_read_text),
        ):
            result = monitor.fetch_usage()

        self.assertFalse(result)

    def test_error_message_set_when_backoff_active_and_no_data(self):
        """error_message must be set to backoff text when no cache and no previous data."""
        monitor = _make_monitor()
        monitor.last_usage = None

        backoff_json = self._backoff_data()

        def path_exists(self_path):
            return Path(self_path).name == "api_backoff.json"

        def path_read_text(self_path):
            name = Path(self_path).name
            if name == "api_backoff.json":
                return backoff_json
            raise FileNotFoundError(name)

        with (
            patch.object(Path, "exists", path_exists),
            patch.object(Path, "read_text", path_read_text),
        ):
            monitor.fetch_usage()

        self.assertIsNotNone(monitor.error_message)
        self.assertIn("backoff", monitor.error_message.lower())

    def test_api_not_called_when_backoff_active_and_no_cache(self):
        """API client must NOT be called even when no cache — backoff prevents API."""
        monitor = _make_monitor()
        monitor.last_usage = None

        backoff_json = self._backoff_data()

        def path_exists(self_path):
            return Path(self_path).name == "api_backoff.json"

        def path_read_text(self_path):
            name = Path(self_path).name
            if name == "api_backoff.json":
                return backoff_json
            raise FileNotFoundError(name)

        with (
            patch.object(Path, "exists", path_exists),
            patch.object(Path, "read_text", path_read_text),
        ):
            monitor.fetch_usage()

        monitor.api_client.fetch_usage.assert_not_called()


class TestFetchUsageBackoffWithPreviousDataNoCacheFile(unittest.TestCase):
    """During backoff, when last_usage already populated but no cache file, keep it."""

    def _backoff_data(self):
        return json.dumps({"backoff_until": time.time() + 600, "consecutive_429s": 2})

    def test_returns_true_when_backoff_active_previous_data_no_cache_file(self):
        """When backoff is active and last_usage already set (but no cache file), return True."""
        monitor = _make_monitor()
        # Previous data from an earlier successful fetch
        monitor.last_usage = _SAMPLE_USAGE

        backoff_json = self._backoff_data()

        def path_exists(self_path):
            return Path(self_path).name == "api_backoff.json"

        def path_read_text(self_path):
            name = Path(self_path).name
            if name == "api_backoff.json":
                return backoff_json
            raise FileNotFoundError(name)

        with (
            patch.object(Path, "exists", path_exists),
            patch.object(Path, "read_text", path_read_text),
        ):
            result = monitor.fetch_usage()

        self.assertTrue(result)
        self.assertEqual(monitor.last_usage, _SAMPLE_USAGE)


class TestFetchProfilePreservesLastProfileDuringBackoff(unittest.TestCase):
    """fetch_profile() must preserve last_profile when the API would fail due to backoff."""

    def _make_monitor_with_profile(self, profile_data):
        """Make monitor with last_profile pre-populated."""
        monitor = _make_monitor()
        monitor.last_profile = profile_data
        return monitor

    def test_last_profile_preserved_when_api_client_returns_backoff_error(self):
        """When api_client.fetch_profile returns None (backoff), last_profile is kept."""
        existing_profile = {
            "account": {"uuid": "acc-123"},
            "organization": {"uuid": "org-456"},
        }
        monitor = self._make_monitor_with_profile(existing_profile)

        # Simulate api_client.fetch_profile returning backoff error
        monitor.api_client.fetch_profile.return_value = (
            None,
            None,
            None,
            "API backoff: 300s remaining",
        )

        result = monitor.fetch_profile()

        # last_profile must not be overwritten with None
        self.assertEqual(monitor.last_profile, existing_profile)

    def test_fetch_profile_returns_true_when_preserving_existing_profile(self):
        """fetch_profile returns True when it preserves an existing profile (data available)."""
        existing_profile = {
            "account": {"uuid": "acc-123"},
            "organization": {"uuid": "org-456"},
        }
        monitor = self._make_monitor_with_profile(existing_profile)

        monitor.api_client.fetch_profile.return_value = (
            None,
            None,
            None,
            "API backoff: 300s remaining",
        )

        result = monitor.fetch_profile()

        # Should return True because we still have profile data
        self.assertTrue(result)

    def test_fetch_profile_returns_false_when_no_previous_profile_and_backoff(self):
        """fetch_profile returns False when last_profile is None and API is in backoff."""
        monitor = _make_monitor()
        monitor.last_profile = None

        monitor.api_client.fetch_profile.return_value = (
            None,
            None,
            None,
            "API backoff: 300s remaining",
        )

        result = monitor.fetch_profile()

        self.assertFalse(result)
        self.assertIsNone(monitor.last_profile)

    def test_fetch_profile_updates_when_api_succeeds_despite_previous_data(self):
        """fetch_profile updates last_profile when API call succeeds."""
        old_profile = {"account": {"uuid": "old-acc"}}
        new_profile = {
            "account": {"uuid": "new-acc"},
            "organization": {"uuid": "org-789"},
        }
        monitor = self._make_monitor_with_profile(old_profile)

        monitor.api_client.fetch_profile.return_value = (
            new_profile,
            "org-789",
            "new-acc",
            None,
        )

        result = monitor.fetch_profile()

        self.assertTrue(result)
        self.assertEqual(monitor.last_profile, new_profile)


class TestNonBackoffBehaviorUnchanged(unittest.TestCase):
    """Verify normal (non-backoff) cache and API behavior is unchanged."""

    def test_fresh_cache_used_when_no_backoff(self):
        """When no backoff, fresh cache is still used (existing behavior preserved)."""
        monitor = _make_monitor()
        cache_ts = time.time() - 30
        cache_json = json.dumps({"timestamp": cache_ts, "response": _SAMPLE_USAGE})

        def path_exists(self_path):
            name = Path(self_path).name
            # No backoff file, but cache exists
            return name == "usage_cache.json"

        def path_read_text(self_path):
            name = Path(self_path).name
            if name == "usage_cache.json":
                return cache_json
            raise FileNotFoundError(name)

        with (
            patch.object(Path, "exists", path_exists),
            patch.object(Path, "read_text", path_read_text),
        ):
            result = monitor.fetch_usage()

        self.assertTrue(result)
        self.assertEqual(monitor.last_usage, _SAMPLE_USAGE)
        monitor.api_client.fetch_usage.assert_not_called()

    def test_stale_cache_falls_through_to_api_when_no_backoff(self):
        """When no backoff, stale cache is skipped and API is called (existing behavior)."""
        from claude_usage.code_mode.monitor import CodeMonitor

        monitor = _make_monitor()
        stale_ts = time.time() - (CodeMonitor.CACHE_FRESHNESS_SECONDS + 3600)
        cache_json = json.dumps({"timestamp": stale_ts, "response": _SAMPLE_USAGE})
        api_response = {"five_hour": {"utilization": 50.0}}
        monitor.api_client.fetch_usage.return_value = (api_response, None)

        def path_exists(self_path):
            name = Path(self_path).name
            return name == "usage_cache.json"

        def path_read_text(self_path):
            name = Path(self_path).name
            if name == "usage_cache.json":
                return cache_json
            raise FileNotFoundError(name)

        with (
            patch.object(Path, "exists", path_exists),
            patch.object(Path, "read_text", path_read_text),
        ):
            result = monitor.fetch_usage()

        self.assertTrue(result)
        monitor.api_client.fetch_usage.assert_called_once()
        self.assertEqual(monitor.last_usage, api_response)


if __name__ == "__main__":
    unittest.main()
