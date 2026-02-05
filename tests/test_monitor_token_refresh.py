"""Tests for CodeMonitor token expiry and refresh handling

Tests verify that the monitor properly reloads credentials when tokens expire,
using the existing load_credentials() functionality instead of the placeholder
refresh_token() method.
"""

import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from datetime import datetime
from claude_usage.code_mode.monitor import CodeMonitor


class TestCodeMonitorTokenRefresh(unittest.TestCase):
    """Test cases for token expiry handling in CodeMonitor.fetch_usage()"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.credentials_path = Path(self.temp_dir) / ".credentials.json"
        self.db_path = Path(self.temp_dir) / "usage_history.db"

        # Current time in milliseconds
        current_time = datetime.now().timestamp() * 1000

        # Valid token (expires in 4 hours)
        self.valid_token_data = {
            "claudeAiOauth": {
                "accessToken": "valid-access-token",
                "refreshToken": "valid-refresh-token",
                "expiresAt": int(
                    current_time + (4 * 60 * 60 * 1000)
                ),  # 4 hours from now
            }
        }

        # Expired token (expired 2 days ago)
        self.expired_token_data = {
            "claudeAiOauth": {
                "accessToken": "expired-access-token",
                "refreshToken": "expired-refresh-token",
                "expiresAt": int(
                    current_time - (2 * 24 * 60 * 60 * 1000)
                ),  # 2 days ago
            }
        }

        # Fresh token from Keychain (expires in 5 hours)
        self.fresh_keychain_data = {
            "claudeAiOauth": {
                "accessToken": "fresh-keychain-token",
                "refreshToken": "fresh-keychain-refresh",
                "expiresAt": int(
                    current_time + (5 * 60 * 60 * 1000)
                ),  # 5 hours from now
            }
        }

        # Mock usage API response
        self.mock_usage_response = {
            "usage": {
                "daily_limit": 1000,
                "daily_used": 500,
                "reset_at": int(current_time + (3 * 60 * 60 * 1000)),
            }
        }

    def tearDown(self):
        """Clean up test fixtures"""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("platform.system", return_value="Darwin")
    def test_fetch_usage_with_expired_token_reloads_from_file_valid_token(
        self, mock_platform
    ):
        """Test that expired token triggers reload from file with valid token"""
        # Write expired token to file initially
        with open(self.credentials_path, "w") as f:
            json.dump(self.expired_token_data, f)

        # Mock Keychain during init to prevent it from loading real credentials
        with patch(
            "claude_usage.code_mode.auth.OAuthManager.extract_from_macos_keychain"
        ) as mock_keychain_init:
            mock_keychain_init.return_value = (None, "Not found")
            monitor = CodeMonitor(credentials_path=self.credentials_path)

        # Verify initial credentials are expired
        self.assertIsNotNone(monitor.credentials)
        self.assertEqual(monitor.credentials["accessToken"], "expired-access-token")

        # Update file with valid token (simulating external refresh)
        with open(self.credentials_path, "w") as f:
            json.dump(self.valid_token_data, f)

        # Mock API client to succeed with fresh token
        with patch.object(monitor.api_client, "fetch_usage") as mock_fetch:
            mock_fetch.return_value = (self.mock_usage_response, None)

            # Mock Keychain to ensure it's not called (file has valid token)
            with patch.object(
                monitor.oauth_manager, "extract_from_macos_keychain"
            ) as mock_keychain:
                success = monitor.fetch_usage()

            mock_keychain.assert_not_called()

        # Should succeed after reloading from file
        self.assertTrue(success)
        self.assertIsNone(monitor.error_message)
        self.assertEqual(monitor.credentials["accessToken"], "valid-access-token")
        self.assertIsNotNone(monitor.last_usage)

    @patch("platform.system", return_value="Darwin")
    def test_fetch_usage_with_expired_token_reloads_from_keychain(self, mock_platform):
        """Test that expired token triggers reload from Keychain when file also expired"""
        # Write expired token to file
        with open(self.credentials_path, "w") as f:
            json.dump(self.expired_token_data, f)

        # Mock Keychain during init
        with patch(
            "claude_usage.code_mode.auth.OAuthManager.extract_from_macos_keychain"
        ) as mock_keychain_init:
            mock_keychain_init.return_value = (None, "Not found")
            monitor = CodeMonitor(credentials_path=self.credentials_path)

        # Verify initial credentials are expired
        self.assertIsNotNone(monitor.credentials)
        self.assertEqual(monitor.credentials["accessToken"], "expired-access-token")

        # Mock Keychain to return fresh token
        with patch.object(
            monitor.oauth_manager, "extract_from_macos_keychain"
        ) as mock_keychain:
            mock_keychain.return_value = (self.fresh_keychain_data, None)

            # Mock API client to succeed with fresh token
            with patch.object(monitor.api_client, "fetch_usage") as mock_fetch:
                mock_fetch.return_value = (self.mock_usage_response, None)

                success = monitor.fetch_usage()

            # Keychain should be called once during reload
            mock_keychain.assert_called_once()

        # Should succeed after reloading from Keychain
        self.assertTrue(success)
        self.assertIsNone(monitor.error_message)
        self.assertEqual(monitor.credentials["accessToken"], "fresh-keychain-token")
        self.assertIsNotNone(monitor.last_usage)

    @patch("platform.system", return_value="Darwin")
    def test_fetch_usage_with_expired_token_keychain_fails_shows_error(
        self, mock_platform
    ):
        """Test that expired token with failed Keychain extraction shows error"""
        # Write expired token to file
        with open(self.credentials_path, "w") as f:
            json.dump(self.expired_token_data, f)

        # Mock Keychain during init
        with patch(
            "claude_usage.code_mode.auth.OAuthManager.extract_from_macos_keychain"
        ) as mock_keychain_init:
            mock_keychain_init.return_value = (None, "Not found")
            monitor = CodeMonitor(credentials_path=self.credentials_path)

        # Mock Keychain to fail
        with patch.object(
            monitor.oauth_manager, "extract_from_macos_keychain"
        ) as mock_keychain:
            mock_keychain.return_value = (
                None,
                "Failed to extract from Keychain: security error",
            )

            # Mock API client (should not be called)
            with patch.object(monitor.api_client, "fetch_usage") as mock_fetch:
                success = monitor.fetch_usage()

            mock_fetch.assert_not_called()

        # Should fail with error message
        self.assertFalse(success)
        self.assertIsNotNone(monitor.error_message)
        self.assertIn("expired", monitor.error_message.lower())

    @patch("platform.system", return_value="Linux")
    def test_fetch_usage_with_expired_token_on_linux_shows_error(self, mock_platform):
        """Test that expired token on Linux shows error (no Keychain available)"""
        # Write expired token to file
        with open(self.credentials_path, "w") as f:
            json.dump(self.expired_token_data, f)

        # On Linux, no Keychain to mock during init, so file credentials are used directly
        monitor = CodeMonitor(credentials_path=self.credentials_path)

        # Mock API client (should not be called)
        with patch.object(monitor.api_client, "fetch_usage") as mock_fetch:
            success = monitor.fetch_usage()

        mock_fetch.assert_not_called()

        # Should fail with error message
        self.assertFalse(success)
        self.assertIsNotNone(monitor.error_message)
        self.assertIn("expired", monitor.error_message.lower())

    @patch("claude_usage.code_mode.auth.OAuthManager.extract_from_macos_keychain")
    def test_fetch_usage_with_valid_token_succeeds_without_reload(
        self, mock_keychain_init
    ):
        """Test that valid token proceeds directly to API call without reload"""
        # Write valid token to file
        with open(self.credentials_path, "w") as f:
            json.dump(self.valid_token_data, f)

        # Mock Keychain during init (won't be called since file token is valid)
        mock_keychain_init.return_value = (None, "Not found")
        monitor = CodeMonitor(credentials_path=self.credentials_path)

        # Track load_credentials calls
        original_load = monitor._load_credentials
        load_call_count = [0]

        def tracked_load():
            load_call_count[0] += 1
            return original_load()

        monitor._load_credentials = tracked_load

        # Mock API client to succeed
        with patch.object(monitor.api_client, "fetch_usage") as mock_fetch:
            mock_fetch.return_value = (self.mock_usage_response, None)

            success = monitor.fetch_usage()

        # Should succeed without additional credential reload
        self.assertTrue(success)
        self.assertIsNone(monitor.error_message)
        self.assertEqual(monitor.credentials["accessToken"], "valid-access-token")
        self.assertIsNotNone(monitor.last_usage)
        # Only initial load in __init__, no reload during fetch_usage
        self.assertEqual(load_call_count[0], 0)

    @patch("platform.system", return_value="Darwin")
    def test_fetch_usage_updates_credentials_in_memory_after_reload(
        self, mock_platform
    ):
        """Test that credentials object in monitor is updated after successful reload"""
        # Write expired token to file
        with open(self.credentials_path, "w") as f:
            json.dump(self.expired_token_data, f)

        # Mock Keychain during init
        with patch(
            "claude_usage.code_mode.auth.OAuthManager.extract_from_macos_keychain"
        ) as mock_keychain_init:
            mock_keychain_init.return_value = (None, "Not found")
            monitor = CodeMonitor(credentials_path=self.credentials_path)

        # Verify initial expired token
        initial_token = monitor.credentials["accessToken"]
        self.assertEqual(initial_token, "expired-access-token")

        # Mock Keychain to return fresh token
        with patch.object(
            monitor.oauth_manager, "extract_from_macos_keychain"
        ) as mock_keychain:
            mock_keychain.return_value = (self.fresh_keychain_data, None)

            # Mock API client
            with patch.object(monitor.api_client, "fetch_usage") as mock_fetch:
                mock_fetch.return_value = (self.mock_usage_response, None)

                monitor.fetch_usage()

        # Verify credentials were updated in memory
        self.assertEqual(monitor.credentials["accessToken"], "fresh-keychain-token")
        self.assertNotEqual(monitor.credentials["accessToken"], initial_token)

    @patch("platform.system", return_value="Darwin")
    def test_fetch_usage_saves_reloaded_token_to_file(self, mock_platform):
        """Test that successfully reloaded token from Keychain is saved to file"""
        # Write expired token to file
        with open(self.credentials_path, "w") as f:
            json.dump(self.expired_token_data, f)

        # Mock Keychain during init
        with patch(
            "claude_usage.code_mode.auth.OAuthManager.extract_from_macos_keychain"
        ) as mock_keychain_init:
            mock_keychain_init.return_value = (None, "Not found")
            monitor = CodeMonitor(credentials_path=self.credentials_path)

        # Mock Keychain to return fresh token
        with patch.object(
            monitor.oauth_manager, "extract_from_macos_keychain"
        ) as mock_keychain:
            mock_keychain.return_value = (self.fresh_keychain_data, None)

            # Mock API client
            with patch.object(monitor.api_client, "fetch_usage") as mock_fetch:
                mock_fetch.return_value = (self.mock_usage_response, None)

                monitor.fetch_usage()

        # Verify file was updated with fresh token
        with open(self.credentials_path) as f:
            saved_data = json.load(f)

        self.assertEqual(
            saved_data["claudeAiOauth"]["accessToken"], "fresh-keychain-token"
        )

    @patch("claude_usage.code_mode.auth.OAuthManager.extract_from_macos_keychain")
    def test_fetch_usage_with_no_credentials_loads_on_first_call(
        self, mock_keychain_init
    ):
        """Test that missing credentials trigger load on first fetch_usage call"""
        # Don't create credentials file initially
        # Mock Keychain during init to return no credentials
        mock_keychain_init.return_value = (None, "Credentials not found")
        monitor = CodeMonitor(credentials_path=self.credentials_path)

        # Credentials should be None after init (file doesn't exist)
        self.assertIsNone(monitor.credentials)
        self.assertIsNotNone(monitor.error_message)

        # Create valid credentials file
        with open(self.credentials_path, "w") as f:
            json.dump(self.valid_token_data, f)

        # Mock API client
        with patch.object(monitor.api_client, "fetch_usage") as mock_fetch:
            mock_fetch.return_value = (self.mock_usage_response, None)

            success = monitor.fetch_usage()

        # Should succeed after loading credentials
        self.assertTrue(success)
        self.assertIsNone(monitor.error_message)
        self.assertEqual(monitor.credentials["accessToken"], "valid-access-token")

    @patch("platform.system", return_value="Darwin")
    def test_multiple_fetch_usage_calls_only_reload_once_for_expired_token(
        self, mock_platform
    ):
        """Test that multiple fetch_usage calls with expired token only reload once"""
        # Write expired token to file
        with open(self.credentials_path, "w") as f:
            json.dump(self.expired_token_data, f)

        # Mock Keychain during init
        with patch(
            "claude_usage.code_mode.auth.OAuthManager.extract_from_macos_keychain"
        ) as mock_keychain_init:
            mock_keychain_init.return_value = (None, "Not found")
            monitor = CodeMonitor(credentials_path=self.credentials_path)

        # Mock Keychain to return fresh token
        with patch.object(
            monitor.oauth_manager, "extract_from_macos_keychain"
        ) as mock_keychain:
            mock_keychain.return_value = (self.fresh_keychain_data, None)

            # Mock API client
            with patch.object(monitor.api_client, "fetch_usage") as mock_fetch:
                mock_fetch.return_value = (self.mock_usage_response, None)

                # First call - should reload from Keychain
                success1 = monitor.fetch_usage()
                # Second call - should use reloaded token without calling Keychain again
                success2 = monitor.fetch_usage()

            # Keychain should only be called once (during first reload)
            self.assertEqual(mock_keychain.call_count, 1)

        # Both calls should succeed
        self.assertTrue(success1)
        self.assertTrue(success2)


if __name__ == "__main__":
    unittest.main()
