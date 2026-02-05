"""Tests for OAuthManager - Claude Code OAuth authentication with token expiry handling"""

import unittest
import json
import tempfile
import platform
from pathlib import Path
from unittest.mock import patch, MagicMock
from datetime import datetime
from claude_usage.code_mode.auth import OAuthManager


class TestOAuthManagerTokenExpiry(unittest.TestCase):
    """Test cases for OAuthManager token expiry handling"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.credentials_path = Path(self.temp_dir) / ".credentials.json"

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

    def tearDown(self):
        """Clean up test fixtures"""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_file_exists_with_valid_token_returns_file_token(self):
        """Test that valid token from file is returned without checking Keychain"""
        # Write valid token to file
        with open(self.credentials_path, "w") as f:
            json.dump(self.valid_token_data, f)

        manager = OAuthManager(self.credentials_path)

        # Mock Keychain to ensure it's not called
        with patch.object(manager, "extract_from_macos_keychain") as mock_keychain:
            credentials, error = manager.load_credentials()

        # Should return file token without calling Keychain
        self.assertIsNotNone(credentials)
        self.assertIsNone(error)
        self.assertEqual(credentials["accessToken"], "valid-access-token")
        mock_keychain.assert_not_called()

    @patch("platform.system", return_value="Darwin")
    def test_file_exists_with_expired_token_on_macos_extracts_from_keychain(
        self, mock_platform
    ):
        """Test that expired token on macOS triggers Keychain extraction"""
        # Write expired token to file
        with open(self.credentials_path, "w") as f:
            json.dump(self.expired_token_data, f)

        manager = OAuthManager(self.credentials_path)

        # Mock Keychain to return fresh token
        with patch.object(
            manager,
            "extract_from_macos_keychain",
            return_value=(self.fresh_keychain_data, None),
        ):
            credentials, error = manager.load_credentials()

        # Should return fresh Keychain token
        self.assertIsNotNone(credentials)
        self.assertIsNone(error)
        self.assertEqual(credentials["accessToken"], "fresh-keychain-token")

        # Verify fresh token was saved to file
        with open(self.credentials_path) as f:
            saved_data = json.load(f)
        self.assertEqual(
            saved_data["claudeAiOauth"]["accessToken"], "fresh-keychain-token"
        )

    @patch("platform.system", return_value="Darwin")
    def test_file_exists_with_expired_token_keychain_fails_returns_expired_with_error(
        self, mock_platform
    ):
        """Test that expired token with failed Keychain extraction returns expired token with error"""
        # Write expired token to file
        with open(self.credentials_path, "w") as f:
            json.dump(self.expired_token_data, f)

        manager = OAuthManager(self.credentials_path)

        # Mock Keychain to fail
        keychain_error = "Failed to extract from Keychain: security: SecKeychainSearchCopyNext: The specified item could not be found in the keychain."
        with patch.object(
            manager, "extract_from_macos_keychain", return_value=(None, keychain_error)
        ):
            credentials, error = manager.load_credentials()

        # Should return expired token with expiry error
        self.assertIsNotNone(credentials)
        self.assertIsNotNone(error)
        self.assertEqual(credentials["accessToken"], "expired-access-token")
        self.assertIn("expired", error.lower())

    @patch("platform.system", return_value="Linux")
    def test_file_exists_with_expired_token_on_linux_returns_expired_with_error(
        self, mock_platform
    ):
        """Test that expired token on Linux returns expired token with error (no Keychain)"""
        # Write expired token to file
        with open(self.credentials_path, "w") as f:
            json.dump(self.expired_token_data, f)

        manager = OAuthManager(self.credentials_path)

        # Mock Keychain to ensure it's not called (Linux doesn't have macOS Keychain)
        with patch.object(manager, "extract_from_macos_keychain") as mock_keychain:
            credentials, error = manager.load_credentials()

        # Should return expired token with error
        self.assertIsNotNone(credentials)
        self.assertIsNotNone(error)
        self.assertEqual(credentials["accessToken"], "expired-access-token")
        self.assertIn("expired", error.lower())
        mock_keychain.assert_not_called()

    @patch("platform.system", return_value="Darwin")
    def test_file_not_exists_on_macos_extracts_from_keychain(self, mock_platform):
        """Test existing behavior: file doesn't exist on macOS extracts from Keychain"""
        manager = OAuthManager(self.credentials_path)

        # Mock Keychain to return fresh token
        with patch.object(
            manager,
            "extract_from_macos_keychain",
            return_value=(self.fresh_keychain_data, None),
        ):
            credentials, error = manager.load_credentials()

        # Should return Keychain token
        self.assertIsNotNone(credentials)
        self.assertIsNone(error)
        self.assertEqual(credentials["accessToken"], "fresh-keychain-token")

        # Verify token was saved to file
        self.assertTrue(self.credentials_path.exists())
        with open(self.credentials_path) as f:
            saved_data = json.load(f)
        self.assertEqual(
            saved_data["claudeAiOauth"]["accessToken"], "fresh-keychain-token"
        )

    @patch("platform.system", return_value="Linux")
    def test_file_not_exists_on_linux_returns_error(self, mock_platform):
        """Test existing behavior: file doesn't exist on Linux returns error"""
        manager = OAuthManager(self.credentials_path)

        credentials, error = manager.load_credentials()

        # Should return error
        self.assertIsNone(credentials)
        self.assertIsNotNone(error)
        self.assertIn("not found", error.lower())

    @patch("platform.system", return_value="Darwin")
    def test_expired_token_keychain_extraction_saves_to_file(self, mock_platform):
        """Test that successful Keychain extraction for expired token saves to file"""
        # Write expired token to file
        with open(self.credentials_path, "w") as f:
            json.dump(self.expired_token_data, f)

        manager = OAuthManager(self.credentials_path)

        # Mock Keychain to return fresh token
        with patch.object(
            manager,
            "extract_from_macos_keychain",
            return_value=(self.fresh_keychain_data, None),
        ):
            credentials, error = manager.load_credentials()

        # Verify file was updated with fresh token
        with open(self.credentials_path) as f:
            saved_data = json.load(f)

        self.assertEqual(
            saved_data["claudeAiOauth"]["accessToken"], "fresh-keychain-token"
        )
        self.assertEqual(
            saved_data["claudeAiOauth"]["expiresAt"],
            self.fresh_keychain_data["claudeAiOauth"]["expiresAt"],
        )

    @patch("platform.system", return_value="Darwin")
    def test_expired_token_keychain_save_fails_returns_fresh_token_anyway(
        self, mock_platform
    ):
        """Test that Keychain token is returned even if file save fails"""
        # Write expired token to file
        with open(self.credentials_path, "w") as f:
            json.dump(self.expired_token_data, f)

        manager = OAuthManager(self.credentials_path)

        # Mock Keychain to return fresh token
        with patch.object(
            manager,
            "extract_from_macos_keychain",
            return_value=(self.fresh_keychain_data, None),
        ):
            # Mock save to fail
            with patch.object(
                manager,
                "save_credentials_file",
                return_value=(False, "Permission denied"),
            ):
                credentials, error = manager.load_credentials()

        # Should still return fresh Keychain token even though save failed
        self.assertIsNotNone(credentials)
        self.assertIsNone(error)
        self.assertEqual(credentials["accessToken"], "fresh-keychain-token")

    def test_token_considered_expired_with_less_than_5_minutes_remaining(self):
        """Test that token is considered expired when less than 5 minutes remain"""
        manager = OAuthManager(self.credentials_path)

        current_time = datetime.now().timestamp() * 1000

        # Token expiring in 4 minutes
        almost_expired_creds = {
            "accessToken": "almost-expired-token",
            "expiresAt": int(current_time + (4 * 60 * 1000)),  # 4 minutes from now
        }

        self.assertTrue(manager.is_token_expired(almost_expired_creds))

    def test_token_not_expired_with_more_than_5_minutes_remaining(self):
        """Test that token is not considered expired when more than 5 minutes remain"""
        manager = OAuthManager(self.credentials_path)

        current_time = datetime.now().timestamp() * 1000

        # Token expiring in 6 minutes
        valid_creds = {
            "accessToken": "valid-token",
            "expiresAt": int(current_time + (6 * 60 * 1000)),  # 6 minutes from now
        }

        self.assertFalse(manager.is_token_expired(valid_creds))


if __name__ == "__main__":
    unittest.main()
