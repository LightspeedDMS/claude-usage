"""Tests for exponential backoff in ClaudeAPIClient, CodeMonitor, and ConsoleAPIClient.

TDD: These tests define expected behavior. They will fail until implementation is added.
"""

import json
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

from claude_usage.code_mode.api import ClaudeAPIClient
from claude_usage.console_mode.api import ConsoleAPIClient


class TestClaudeAPIClientBackoffState(unittest.TestCase):
    """Tests for ClaudeAPIClient instance-level backoff state management."""

    def setUp(self):
        self.client = ClaudeAPIClient()

    def test_is_in_backoff_returns_false_initially(self):
        """Client should not be in backoff state when freshly created."""
        self.assertFalse(self.client.is_in_backoff())

    def test_record_429_sets_backoff_until_in_future(self):
        """After first 429, backoff_until should be in the future."""
        before = time.time()
        self.client._record_429()
        self.assertGreater(self.client._backoff_until, before)

    def test_is_in_backoff_returns_true_after_record_429(self):
        """Client should be in backoff after recording a 429."""
        self.client._record_429()
        self.assertTrue(self.client.is_in_backoff())

    def test_record_429_first_backoff_is_300_seconds(self):
        """First 429 should set backoff to 300 seconds (5 minutes)."""
        before = time.time()
        self.client._record_429()
        # First backoff: 300 * 2^1 = 600? No: formula is min(300 * 2^consecutive, 3600)
        # consecutive_429s starts at 0, after first _record_429 it becomes 1
        # backoff = min(300 * 2^1, 3600) = 600
        # Actually spec says: 5min, 10min, 20min, capped at 60min
        # 300 * 2^0 = 300 (first), 300 * 2^1 = 600 (second), etc.
        # Re-reading spec: "min(300 * 2^_consecutive_429s, 3600)"
        # _record_429() increments THEN computes: so first call: consecutive=1, backoff=300*2^1=600
        # But spec says "5min, 10min, 20min" which is 300, 600, 1200...
        # The spec says: consecutive starts at 0, _record_429 increments first
        # So: after 1st call: consecutive=1, backoff=300*2^1=600 (10min)?
        # But spec says "5min, 10min, 20min, capped at 60min"
        # This means first=5min=300. So formula must be 300 * 2^(consecutive-1) after increment
        # OR: increment happens AFTER computing: consecutive=0, backoff=300*2^0=300, then increment
        # Let's interpret as: backoff = min(300 * 2^_consecutive_429s_BEFORE_increment, 3600)
        # then increment. First call: backoff=300*2^0=300, consecutive becomes 1.
        # That gives 5min, 10min, 20min, 40min, capped at 60min. This matches spec.
        expected_backoff = 300  # 5 minutes = 300 seconds for first 429
        self.assertAlmostEqual(
            self.client._backoff_until - before, expected_backoff, delta=2
        )

    def test_record_429_second_call_doubles_backoff(self):
        """Second 429 should double the backoff (10 minutes)."""
        before = time.time()
        self.client._record_429()
        self.client._record_429()
        expected_backoff = 600  # 10 minutes
        self.assertAlmostEqual(
            self.client._backoff_until - before, expected_backoff, delta=2
        )

    def test_record_429_third_call_is_20_minutes(self):
        """Third 429 should result in 20-minute backoff."""
        before = time.time()
        self.client._record_429()
        self.client._record_429()
        self.client._record_429()
        expected_backoff = 1200  # 20 minutes
        self.assertAlmostEqual(
            self.client._backoff_until - before, expected_backoff, delta=2
        )

    def test_record_429_caps_at_3600_seconds(self):
        """Backoff should never exceed 3600 seconds (60 minutes)."""
        # Call many times to exceed the cap
        for _ in range(20):
            self.client._record_429()
        before_check = time.time()
        max_allowed = before_check + 3600 + 5  # 5 second tolerance
        self.assertLessEqual(self.client._backoff_until, max_allowed)
        # Also verify it IS at the cap (not zero or some small value)
        self.assertGreater(self.client._backoff_until, time.time() + 3590)

    def test_record_success_resets_consecutive_429s(self):
        """After success, consecutive_429s counter should reset to 0."""
        self.client._record_429()
        self.client._record_429()
        self.assertEqual(self.client._consecutive_429s, 2)
        self.client._record_success()
        self.assertEqual(self.client._consecutive_429s, 0)

    def test_record_success_clears_backoff_until(self):
        """After success, backoff_until should be cleared (set to 0)."""
        self.client._record_429()
        self.client._record_success()
        self.assertEqual(self.client._backoff_until, 0.0)

    def test_is_in_backoff_returns_false_after_record_success(self):
        """Client should not be in backoff after recording a success."""
        self.client._record_429()
        self.client._record_success()
        self.assertFalse(self.client.is_in_backoff())

    def test_get_backoff_remaining_seconds_returns_zero_when_not_in_backoff(self):
        """Should return 0 when not in backoff."""
        remaining = self.client.get_backoff_remaining_seconds()
        self.assertEqual(remaining, 0.0)

    def test_get_backoff_remaining_seconds_returns_positive_when_in_backoff(self):
        """Should return positive value when in backoff."""
        self.client._record_429()
        remaining = self.client.get_backoff_remaining_seconds()
        self.assertGreater(remaining, 0)

    def test_get_backoff_remaining_seconds_is_approximately_correct(self):
        """Remaining seconds should be close to expected backoff duration."""
        self.client._record_429()
        remaining = self.client.get_backoff_remaining_seconds()
        # First backoff is 300 seconds
        self.assertAlmostEqual(remaining, 300, delta=2)

    def test_consecutive_429s_initialized_to_zero(self):
        """New client should have consecutive_429s of 0."""
        self.assertEqual(self.client._consecutive_429s, 0)

    def test_backoff_until_initialized_to_zero(self):
        """New client should have backoff_until of 0.0."""
        self.assertEqual(self.client._backoff_until, 0.0)


class TestClaudeAPIClientFetchUsageBackoff(unittest.TestCase):
    """Tests for fetch_usage respecting backoff state."""

    def setUp(self):
        self.client = ClaudeAPIClient()
        self.auth_headers = {"Authorization": "Bearer test-token"}

    def test_fetch_usage_returns_backoff_message_when_in_backoff(self):
        """fetch_usage should return error message without API call when in backoff."""
        self.client._record_429()  # Put client in backoff

        with patch("requests.get") as mock_get:
            result, error = self.client.fetch_usage(self.auth_headers)

        mock_get.assert_not_called()
        self.assertIsNone(result)
        self.assertIn("backoff", error.lower())

    def test_fetch_usage_backoff_message_includes_remaining_seconds(self):
        """Backoff error message should include remaining seconds."""
        self.client._record_429()

        with patch("requests.get"):
            _, error = self.client.fetch_usage(self.auth_headers)

        self.assertIsNotNone(error)
        # Should contain something like "300s remaining" or similar
        self.assertRegex(error, r"\d+")

    def test_fetch_usage_calls_record_429_after_all_retries_fail(self):
        """fetch_usage should call _record_429 when all retries exhaust on 429."""
        mock_response = MagicMock()
        mock_response.status_code = 429

        with patch("requests.get", return_value=mock_response):
            with patch.object(self.client, "_record_429") as mock_record:
                with patch("time.sleep"):  # Speed up test
                    self.client.fetch_usage(self.auth_headers)

        mock_record.assert_called_once()

    def test_fetch_usage_calls_record_success_on_200(self):
        """fetch_usage should call _record_success when API returns 200."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"usage": "data"}

        with patch("requests.get", return_value=mock_response):
            with patch.object(self.client, "_record_success") as mock_success:
                result, error = self.client.fetch_usage(self.auth_headers)

        mock_success.assert_called_once()
        self.assertIsNotNone(result)
        self.assertIsNone(error)

    def test_fetch_usage_does_not_call_record_success_on_failure(self):
        """fetch_usage should NOT call _record_success on non-200 response."""
        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch("requests.get", return_value=mock_response):
            with patch.object(self.client, "_record_success") as mock_success:
                self.client.fetch_usage(self.auth_headers)

        mock_success.assert_not_called()

    def test_fetch_usage_retries_with_jitter_on_429(self):
        """fetch_usage should use time.sleep with delays including jitter on 429."""
        mock_429 = MagicMock()
        mock_429.status_code = 429
        mock_200 = MagicMock()
        mock_200.status_code = 200
        mock_200.json.return_value = {"usage": "data"}

        # First attempt 429, second succeeds
        with patch("requests.get", side_effect=[mock_429, mock_200]):
            with patch("time.sleep") as mock_sleep:
                result, error = self.client.fetch_usage(self.auth_headers)

        # Sleep should have been called at least once (for retry delay)
        mock_sleep.assert_called()
        # Sleep value should be >= 4 (base delay for first retry)
        sleep_arg = mock_sleep.call_args[0][0]
        self.assertGreaterEqual(sleep_arg, 4)

    def test_fetch_usage_not_in_backoff_makes_api_call(self):
        """fetch_usage should make API call when not in backoff."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"usage": "data"}

        with patch("requests.get", return_value=mock_response) as mock_get:
            result, error = self.client.fetch_usage(self.auth_headers)

        mock_get.assert_called_once()
        self.assertIsNotNone(result)


class TestClaudeAPIClientFetchProfileBackoff(unittest.TestCase):
    """Tests for fetch_profile respecting shared backoff state."""

    def setUp(self):
        self.client = ClaudeAPIClient()
        self.auth_headers = {"Authorization": "Bearer test-token"}

    def test_fetch_profile_respects_backoff_state(self):
        """fetch_profile should not make API call when client is in backoff."""
        self.client._record_429()  # Put client in backoff

        with patch("requests.get") as mock_get:
            result = self.client.fetch_profile(self.auth_headers)

        mock_get.assert_not_called()
        # Result should indicate error (4-tuple with last element as error message)
        self.assertIsNone(result[0])  # profile_data is None
        error = result[-1]
        self.assertIsNotNone(error)
        self.assertIn("backoff", error.lower())

    def test_fetch_profile_shared_backoff_with_fetch_usage(self):
        """Backoff state from fetch_usage failures should apply to fetch_profile."""
        mock_response = MagicMock()
        mock_response.status_code = 429

        # Exhaust retries in fetch_usage to trigger _record_429
        with patch("requests.get", return_value=mock_response):
            with patch("time.sleep"):
                self.client.fetch_usage(self.auth_headers)

        # Now fetch_profile should be in backoff too (same client instance)
        self.assertTrue(self.client.is_in_backoff())

        with patch("requests.get") as mock_get:
            self.client.fetch_profile(self.auth_headers)

        mock_get.assert_not_called()

    def test_fetch_profile_calls_record_success_on_200(self):
        """fetch_profile should call _record_success on successful response."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "organization": {"uuid": "org-uuid"},
            "account": {"uuid": "acc-uuid"},
        }

        with patch("requests.get", return_value=mock_response):
            with patch.object(self.client, "_record_success") as mock_success:
                self.client.fetch_profile(self.auth_headers)

        mock_success.assert_called_once()


class TestCodeMonitorPacemakerBackoff(unittest.TestCase):
    """Tests for CodeMonitor reading pace-maker backoff file."""

    def _make_monitor(self):
        """Create a CodeMonitor with all dependencies mocked."""
        with patch("claude_usage.code_mode.monitor.OAuthManager"), \
             patch("claude_usage.code_mode.monitor.ClaudeAPIClient"), \
             patch("claude_usage.code_mode.monitor.CodeStorage"), \
             patch("claude_usage.code_mode.monitor.CodeAnalytics"), \
             patch("claude_usage.code_mode.monitor.UsageRenderer"), \
             patch("claude_usage.code_mode.monitor.PaceMakerReader"):
            from claude_usage.code_mode.monitor import CodeMonitor
            monitor = CodeMonitor.__new__(CodeMonitor)
            monitor.credentials = {"access_token": "test-token", "expires_at": 9999999999}
            monitor.org_uuid = None
            monitor.account_uuid = None
            monitor.last_usage = None
            monitor.last_profile = None
            monitor.last_update = None
            monitor.error_message = None
            monitor.api_client = MagicMock()
            monitor.oauth_manager = MagicMock()
            monitor.pacemaker_reader = MagicMock()
            monitor.pacemaker_reader.is_installed.return_value = False
            monitor.oauth_manager.is_token_expired.return_value = False
            monitor.oauth_manager.get_auth_headers.return_value = {"Authorization": "Bearer test"}
            return monitor

    def test_code_monitor_poll_interval_is_300_seconds(self):
        """POLL_INTERVAL should be 300 seconds (5 minutes)."""
        from claude_usage.code_mode.monitor import CodeMonitor
        self.assertEqual(CodeMonitor.POLL_INTERVAL, 300)

    def test_code_monitor_cache_freshness_is_360_seconds(self):
        """CACHE_FRESHNESS_SECONDS should be 360 seconds."""
        from claude_usage.code_mode.monitor import CodeMonitor
        self.assertEqual(CodeMonitor.CACHE_FRESHNESS_SECONDS, 360)

    def test_fetch_usage_skips_api_when_pacemaker_in_backoff(self):
        """fetch_usage should skip API call when pace-maker backoff file indicates backoff."""
        monitor = self._make_monitor()

        # Simulate pace-maker backoff file with future backoff_until
        future_time = time.time() + 600  # 10 minutes from now
        backoff_data = json.dumps({"backoff_until": future_time, "consecutive_429s": 2})

        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.read_text", return_value=backoff_data):
            result = monitor.fetch_usage()

        # API should not have been called
        monitor.api_client.fetch_usage.assert_not_called()
        # Should return False (no data fetched)
        self.assertFalse(result)

    def test_fetch_usage_proceeds_when_pacemaker_backoff_expired(self):
        """fetch_usage should make API call when pace-maker backoff has expired."""
        monitor = self._make_monitor()

        # Simulate pace-maker backoff file with past backoff_until
        past_time = time.time() - 60  # expired 1 minute ago
        backoff_data = json.dumps({"backoff_until": past_time, "consecutive_429s": 1})

        mock_response_data = {"usage": "data"}
        monitor.api_client.fetch_usage.return_value = (mock_response_data, None)

        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.read_text", return_value=backoff_data):
            result = monitor.fetch_usage()

        monitor.api_client.fetch_usage.assert_called_once()

    def test_fetch_usage_handles_missing_pacemaker_backoff_file_gracefully(self):
        """fetch_usage should proceed normally when pace-maker backoff file doesn't exist."""
        monitor = self._make_monitor()
        mock_response_data = {"usage": "data"}
        monitor.api_client.fetch_usage.return_value = (mock_response_data, None)

        # Patch the specific backoff file path to not exist
        # The cache file may exist but the backoff file should not
        with patch("pathlib.Path.exists", return_value=False):
            result = monitor.fetch_usage()

        # Should still call API (no backoff file = no backoff)
        monitor.api_client.fetch_usage.assert_called_once()

    def test_fetch_usage_handles_corrupt_pacemaker_backoff_file_gracefully(self):
        """fetch_usage should proceed normally when pace-maker backoff file is corrupt."""
        monitor = self._make_monitor()
        mock_response_data = {"usage": "data"}
        monitor.api_client.fetch_usage.return_value = (mock_response_data, None)

        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.read_text", return_value="not-valid-json{{{"):
            result = monitor.fetch_usage()

        # Should still proceed (corrupt file = treat as no backoff)
        monitor.api_client.fetch_usage.assert_called_once()

    def test_fetch_usage_handles_backoff_file_with_no_backoff_until_key(self):
        """fetch_usage should proceed normally when backoff file lacks backoff_until key."""
        monitor = self._make_monitor()
        mock_response_data = {"usage": "data"}
        monitor.api_client.fetch_usage.return_value = (mock_response_data, None)

        backoff_data = json.dumps({"consecutive_429s": 0})  # No backoff_until

        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.read_text", return_value=backoff_data):
            result = monitor.fetch_usage()

        monitor.api_client.fetch_usage.assert_called_once()


class TestConsoleAPIClientBackoff(unittest.TestCase):
    """Tests for ConsoleAPIClient._handle_pagination retry logic on 429."""

    def setUp(self):
        self.client = ConsoleAPIClient(admin_key="test-admin-key")
        self.url = "https://api.anthropic.com/v1/test"
        self.params = {}
        self.headers = {"x-api-key": "test-admin-key"}

    def test_handle_pagination_retries_on_429(self):
        """_handle_pagination should retry when receiving 429 response."""
        mock_429 = MagicMock()
        mock_429.status_code = 429

        mock_200 = MagicMock()
        mock_200.status_code = 200
        mock_200.json.return_value = {"data": [{"item": 1}], "has_more": False}

        with patch("requests.get", side_effect=[mock_429, mock_200]) as mock_get:
            with patch("time.sleep"):
                result, error = self.client._handle_pagination(
                    self.url, self.params, self.headers
                )

        # Should succeed after retry
        self.assertIsNone(error)
        self.assertEqual(result, [{"item": 1}])
        self.assertEqual(mock_get.call_count, 2)

    def test_handle_pagination_retry_uses_exponential_delays(self):
        """_handle_pagination should use exponential delays (4s, 8s, 16s) on 429."""
        mock_429 = MagicMock()
        mock_429.status_code = 429

        mock_200 = MagicMock()
        mock_200.status_code = 200
        mock_200.json.return_value = {"data": [], "has_more": False}

        sleep_calls = []

        def capture_sleep(seconds):
            sleep_calls.append(seconds)

        # First call 429, second succeeds
        with patch("requests.get", side_effect=[mock_429, mock_200]):
            with patch("time.sleep", side_effect=capture_sleep):
                self.client._handle_pagination(self.url, self.params, self.headers)

        self.assertEqual(len(sleep_calls), 1)
        # First retry delay should be ~4s (plus jitter up to 2s)
        self.assertGreaterEqual(sleep_calls[0], 4)
        self.assertLessEqual(sleep_calls[0], 6 + 0.1)  # 4 + max_jitter(2) + epsilon

    def test_handle_pagination_retries_up_to_3_times_on_429(self):
        """_handle_pagination should retry at most 3 times before giving up on 429."""
        mock_429 = MagicMock()
        mock_429.status_code = 429

        with patch("requests.get", return_value=mock_429) as mock_get:
            with patch("time.sleep"):
                result, error = self.client._handle_pagination(
                    self.url, self.params, self.headers
                )

        # Should have tried 3 times (initial + 2 retries)
        self.assertEqual(mock_get.call_count, 3)
        self.assertIsNone(result)
        self.assertIsNotNone(error)
        self.assertIn("rate limit", error.lower())

    def test_handle_pagination_second_retry_uses_8_second_delay(self):
        """Second retry should use ~8s delay."""
        mock_429 = MagicMock()
        mock_429.status_code = 429
        mock_200 = MagicMock()
        mock_200.status_code = 200
        mock_200.json.return_value = {"data": [], "has_more": False}

        sleep_calls = []

        def capture_sleep(seconds):
            sleep_calls.append(seconds)

        # Two 429s then success
        with patch("requests.get", side_effect=[mock_429, mock_429, mock_200]):
            with patch("time.sleep", side_effect=capture_sleep):
                self.client._handle_pagination(self.url, self.params, self.headers)

        self.assertEqual(len(sleep_calls), 2)
        # Second retry delay should be ~8s (plus jitter)
        self.assertGreaterEqual(sleep_calls[1], 8)
        self.assertLessEqual(sleep_calls[1], 10 + 0.1)

    def test_handle_pagination_all_retries_produce_two_sleeps(self):
        """Three attempts produce 2 sleeps (between attempt 0->1 and 1->2)."""
        mock_429 = MagicMock()
        mock_429.status_code = 429

        sleep_calls = []

        def capture_sleep(seconds):
            sleep_calls.append(seconds)

        # Three 429s (all fail, client gives up after 3 attempts)
        with patch("requests.get", return_value=mock_429):
            with patch("time.sleep", side_effect=capture_sleep):
                self.client._handle_pagination(self.url, self.params, self.headers)

        # 3 attempts = 2 sleeps (no sleep after last attempt)
        self.assertEqual(len(sleep_calls), 2)
        # Second sleep should be ~8s (4 * 2^1 + jitter)
        self.assertGreaterEqual(sleep_calls[1], 8)
        self.assertLessEqual(sleep_calls[1], 10 + 0.1)

    def test_handle_pagination_returns_error_after_exhausting_retries(self):
        """_handle_pagination should return error tuple when all retries exhausted."""
        mock_429 = MagicMock()
        mock_429.status_code = 429

        with patch("requests.get", return_value=mock_429):
            with patch("time.sleep"):
                result, error = self.client._handle_pagination(
                    self.url, self.params, self.headers
                )

        self.assertIsNone(result)
        self.assertIsNotNone(error)

    def test_handle_pagination_non_429_error_not_retried(self):
        """_handle_pagination should NOT retry on non-429 errors."""
        mock_500 = MagicMock()
        mock_500.status_code = 500
        mock_500.text = "Internal Server Error"

        with patch("requests.get", return_value=mock_500) as mock_get:
            with patch("time.sleep") as mock_sleep:
                result, error = self.client._handle_pagination(
                    self.url, self.params, self.headers
                )

        # Should only be called once (no retries for non-429)
        self.assertEqual(mock_get.call_count, 1)
        mock_sleep.assert_not_called()
        self.assertIsNone(result)


class TestClaudeAPIClientJitterInRetries(unittest.TestCase):
    """Tests that jitter is applied to retry delays in ClaudeAPIClient."""

    def setUp(self):
        self.client = ClaudeAPIClient()
        self.auth_headers = {"Authorization": "Bearer test-token"}

    def test_fetch_usage_jitter_is_random(self):
        """Sleep calls should include random jitter (test by checking range)."""
        mock_429 = MagicMock()
        mock_429.status_code = 429
        mock_200 = MagicMock()
        mock_200.status_code = 200
        mock_200.json.return_value = {"data": "ok"}

        sleep_values = []

        def capture_sleep(val):
            sleep_values.append(val)

        # Run multiple times to verify jitter produces values in expected range
        for _ in range(5):
            client = ClaudeAPIClient()
            with patch("requests.get", side_effect=[mock_429, mock_200]):
                with patch("time.sleep", side_effect=capture_sleep):
                    client.fetch_usage(self.auth_headers)

        # All sleep values should be between 4.0 and 6.0 (4 base + 0-2 jitter)
        for val in sleep_values:
            self.assertGreaterEqual(val, 4.0)
            self.assertLessEqual(val, 6.0 + 0.01)


if __name__ == "__main__":
    unittest.main()
