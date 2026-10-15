"""Tests for OAuthManager - Claude Code OAuth authentication with token expiry handling"""

import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
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

    @patch("platform.system", return_value="Linux")
    def test_file_exists_with_valid_token_returns_file_token(self, mock_platform):
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


def _oauth_blob(access, tier, subscription, expires_in_hours=4):
    """Credentials blob with FAKE tokens only."""
    expires = datetime.now().timestamp() * 1000 + expires_in_hours * 3600 * 1000
    return {
        "claudeAiOauth": {
            "accessToken": access,
            "refreshToken": f"refresh-{access}",
            "expiresAt": int(expires),
            "subscriptionType": subscription,
            "rateLimitTier": tier,
        },
        "mcpOAuth": {},
    }


class TestOAuthManagerKeychainPrecedence(unittest.TestCase):
    """Issue #10: on Darwin the Keychain is the source of truth, file is a cache.

    Only the `security` subprocess (OS boundary) and platform.system() are
    simulated; credentials files are real temp files.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.credentials_path = Path(self.temp_dir) / ".credentials.json"
        self.account_a = _oauth_blob(
            "fake-token-A", "default_claude_max_5x", "enterprise"
        )
        self.account_b = _oauth_blob("fake-token-B", "default_claude_max_20x", "max")

    def tearDown(self):
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _write_file(self, data):
        with open(self.credentials_path, "w") as f:
            json.dump(data, f)

    def _read_file(self):
        with open(self.credentials_path) as f:
            return json.load(f)

    def _security_returns(self, data):
        import subprocess

        return patch(
            "claude_usage.code_mode.auth.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0, json.dumps(data), ""),
        )

    def _security_fails(self):
        import subprocess

        return patch(
            "claude_usage.code_mode.auth.subprocess.run",
            side_effect=subprocess.CalledProcessError(
                44, "security", stderr="not found"
            ),
        )

    @patch("platform.system", return_value="Darwin")
    def test_unexpired_file_for_account_a_loses_to_keychain_account_b(self, _p):
        """Unexpired file token (A) + Keychain login (B) resolves to B and rewrites file"""
        self._write_file(self.account_a)
        manager = OAuthManager(self.credentials_path)

        with self._security_returns(self.account_b):
            credentials, error = manager.load_credentials()

        self.assertIsNone(error)
        self.assertEqual(credentials["accessToken"], "fake-token-B")
        self.assertEqual(credentials["rateLimitTier"], "default_claude_max_20x")
        saved = self._read_file()["claudeAiOauth"]
        self.assertEqual(saved["accessToken"], "fake-token-B")
        self.assertEqual(saved["subscriptionType"], "max")
        self.assertEqual(saved["rateLimitTier"], "default_claude_max_20x")

    @patch("platform.system", return_value="Darwin")
    def test_keychain_matching_file_does_not_rewrite_file(self, _p):
        """No rewrite when Keychain and file agree (file keeps its mtime)"""
        self._write_file(self.account_a)
        before = self.credentials_path.stat().st_mtime_ns
        manager = OAuthManager(self.credentials_path)

        with self._security_returns(self.account_a):
            credentials, error = manager.load_credentials()

        self.assertIsNone(error)
        self.assertEqual(credentials["accessToken"], "fake-token-A")
        self.assertEqual(self.credentials_path.stat().st_mtime_ns, before)

    @patch("platform.system", return_value="Darwin")
    def test_same_token_but_changed_tier_rewrites_file(self, _p):
        """subscriptionType/rateLimitTier drift alone triggers a rewrite"""
        self._write_file(self.account_a)
        upgraded = _oauth_blob("fake-token-A", "default_claude_max_20x", "max")
        manager = OAuthManager(self.credentials_path)

        with self._security_returns(upgraded):
            manager.load_credentials()

        saved = self._read_file()["claudeAiOauth"]
        self.assertEqual(saved["rateLimitTier"], "default_claude_max_20x")
        self.assertEqual(saved["subscriptionType"], "max")

    @patch("platform.system", return_value="Darwin")
    def test_unreadable_file_is_rewritten_from_keychain(self, _p):
        """Corrupt file is replaced by the Keychain value"""
        self.credentials_path.write_text("{not json")
        manager = OAuthManager(self.credentials_path)

        with self._security_returns(self.account_b):
            credentials, error = manager.load_credentials()

        self.assertIsNone(error)
        self.assertEqual(credentials["accessToken"], "fake-token-B")
        self.assertEqual(
            self._read_file()["claudeAiOauth"]["accessToken"], "fake-token-B"
        )

    @patch("platform.system", return_value="Darwin")
    def test_keychain_failure_falls_back_to_file_with_warning(self, _p):
        """Keychain failure -> unexpired file used, warning logged"""
        self._write_file(self.account_a)
        manager = OAuthManager(self.credentials_path)

        with self._security_fails():
            with self.assertLogs(
                "claude_usage.code_mode.auth", level="WARNING"
            ) as logs:
                credentials, error = manager.load_credentials()

        self.assertIsNone(error)
        self.assertEqual(credentials["accessToken"], "fake-token-A")
        self.assertTrue(any("Keychain" in line for line in logs.output))
        self.assertEqual(
            self._read_file()["claudeAiOauth"]["accessToken"], "fake-token-A"
        )

    @patch("platform.system", return_value="Darwin")
    def test_keychain_failure_and_no_file_reports_not_found(self, _p):
        manager = OAuthManager(self.credentials_path)

        with self._security_fails():
            with self.assertLogs("claude_usage.code_mode.auth", level="WARNING"):
                credentials, error = manager.load_credentials()

        self.assertIsNone(credentials)
        self.assertIn("Credentials not found", error)

    @patch("platform.system", return_value="Linux")
    def test_linux_never_calls_keychain(self, _p):
        """Linux behaviour unchanged: file only, security never invoked"""
        self._write_file(self.account_a)
        manager = OAuthManager(self.credentials_path)

        with patch("claude_usage.code_mode.auth.subprocess.run") as run:
            credentials, error = manager.load_credentials()

        run.assert_not_called()
        self.assertIsNone(error)
        self.assertEqual(credentials["accessToken"], "fake-token-A")

    @patch("platform.system", return_value="Darwin")
    def test_security_called_with_timeout(self, _p):
        from claude_usage.code_mode.auth import KEYCHAIN_TIMEOUT_SECONDS

        self.assertEqual(KEYCHAIN_TIMEOUT_SECONDS, 3)
        manager = OAuthManager(self.credentials_path)

        with self._security_returns(self.account_a) as run:
            manager.load_credentials()

        self.assertEqual(run.call_args.kwargs["timeout"], KEYCHAIN_TIMEOUT_SECONDS)

    @patch("platform.system", return_value="Darwin")
    def test_keychain_timeout_falls_back_to_file_with_warning(self, _p):
        import subprocess

        self._write_file(self.account_a)
        manager = OAuthManager(self.credentials_path)

        with patch(
            "claude_usage.code_mode.auth.subprocess.run",
            side_effect=subprocess.TimeoutExpired("security", 3),
        ):
            with self.assertLogs(
                "claude_usage.code_mode.auth", level="WARNING"
            ) as logs:
                credentials, error = manager.load_credentials()

        self.assertIsNone(error)
        self.assertEqual(credentials["accessToken"], "fake-token-A")
        self.assertTrue(any("timed out" in line for line in logs.output))

    @patch("platform.system", return_value="Darwin")
    def test_expired_keychain_token_returns_expired_error(self, _p):
        expired = _oauth_blob("fake-token-B", "default_claude_max_20x", "max", -2)
        manager = OAuthManager(self.credentials_path)

        with self._security_returns(expired):
            credentials, error = manager.load_credentials()

        self.assertEqual(credentials["accessToken"], "fake-token-B")
        self.assertEqual(error, "Token expired. Please run 'claude' to refresh.")

    @patch("platform.system", return_value="Darwin")
    def test_non_dict_keychain_oauth_is_a_keychain_failure(self, _p):
        self._write_file(self.account_a)

        for bad in (None, "text", ["x"]):
            manager = OAuthManager(self.credentials_path)
            with self._security_returns({"claudeAiOauth": bad}):
                with self.assertLogs("claude_usage.code_mode.auth", level="WARNING"):
                    credentials, error = manager.load_credentials()
            self.assertIsNone(error)
            self.assertEqual(credentials["accessToken"], "fake-token-A")

    @patch("platform.system", return_value="Darwin")
    def test_repeated_keychain_failure_warns_once_until_message_changes(self, _p):
        import subprocess

        self._write_file(self.account_a)
        manager = OAuthManager(self.credentials_path)

        with self._security_fails():
            with self.assertLogs(
                "claude_usage.code_mode.auth", level="WARNING"
            ) as logs:
                for _ in range(3):
                    manager.load_credentials()
        self.assertEqual(len(logs.output), 1)

        with patch(
            "claude_usage.code_mode.auth.subprocess.run",
            side_effect=subprocess.TimeoutExpired("security", 3),
        ):
            with self.assertLogs(
                "claude_usage.code_mode.auth", level="WARNING"
            ) as logs:
                manager.load_credentials()
                manager.load_credentials()
        self.assertEqual(len(logs.output), 1)

    @patch("platform.system", return_value="Darwin")
    def test_repeated_save_failure_warns_once(self, _p):
        blocker = Path(self.temp_dir) / "blocker"
        blocker.write_text("a file, not a directory")
        manager = OAuthManager(blocker / ".credentials.json")

        with self._security_returns(self.account_b):
            with self.assertLogs(
                "claude_usage.code_mode.auth", level="WARNING"
            ) as logs:
                for _ in range(3):
                    manager.load_credentials()

        self.assertEqual(len(logs.output), 1)
        self.assertIn("couldn't save", logs.output[0])

    def test_saved_file_is_mode_0600_even_over_existing_0644_file(self):
        import os
        import stat

        self._write_file(self.account_a)
        os.chmod(self.credentials_path, 0o644)
        manager = OAuthManager(self.credentials_path)

        ok, err = manager.save_credentials_file(self.account_b)

        self.assertTrue(ok, err)
        mode = stat.S_IMODE(self.credentials_path.stat().st_mode)
        self.assertEqual(mode, 0o600)
        self.assertEqual(
            self._read_file()["claudeAiOauth"]["accessToken"], "fake-token-B"
        )

    def test_save_creates_new_file_0600_and_leaves_no_temp_files(self):
        import stat

        manager = OAuthManager(self.credentials_path)

        ok, err = manager.save_credentials_file(self.account_b)

        self.assertTrue(ok, err)
        self.assertEqual(stat.S_IMODE(self.credentials_path.stat().st_mode), 0o600)
        self.assertEqual(
            [p.name for p in Path(self.temp_dir).iterdir()], [".credentials.json"]
        )

    def test_token_fingerprint_is_first_16_hex_of_sha256(self):
        import hashlib

        from claude_usage.code_mode.auth import token_fingerprint

        expected = hashlib.sha256(b"fake-token-A").hexdigest()[:16]
        self.assertEqual(token_fingerprint("fake-token-A"), expected)
        self.assertEqual(len(token_fingerprint("fake-token-A")), 16)


if __name__ == "__main__":
    unittest.main()
