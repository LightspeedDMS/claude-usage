"""Tests for ClaudeUsageMonitor mode detection and CLI integration"""

import unittest
import os
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from claude_usage.monitor import ClaudeUsageMonitor, detect_mode

# Clearly fake, non-credential-looking placeholders for test data
FAKE_PRIMARY_KEY = "fake-primary-api-key-for-testing"
FAKE_OAUTH_TOKEN = "fake-oauth-access-token"
FAKE_OAUTH_REFRESH = "fake-oauth-refresh-token"
FAKE_OAUTH_EXPIRES_AT = 9999999999000


class TestModeDetection(unittest.TestCase):
    """Test cases for mode detection logic"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.credentials_path = Path(self.temp_dir) / ".credentials.json"
        self.fake_home = Path(self.temp_dir) / "home"
        self.fake_home.mkdir()

    def tearDown(self):
        """Clean up test fixtures"""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _detect_mode_with_fake_home(self, credentials_path, home_path):
        """Run detect_mode with only Path.home() patched to home_path."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("claude_usage.monitor.Path.home", return_value=home_path):
                return detect_mode(credentials_path)

    def _write_claude_json(self, home_path, data):
        """Write fake ~/.claude.json into home_path directory."""
        claude_json = home_path / ".claude.json"
        with open(claude_json, "w") as f:
            json.dump(data, f)

    def test_detect_mode_console_when_claude_json_has_primary_api_key(self):
        """Console mode detected via ~/.claude.json primaryApiKey
        when credentials has only unrelated keys (e.g. mcpOAuth)"""
        credentials_data = {"mcpOAuth": {"token": "irrelevant-mcp-token"}}
        with open(self.credentials_path, "w") as f:
            json.dump(credentials_data, f)

        self._write_claude_json(self.fake_home, {"primaryApiKey": FAKE_PRIMARY_KEY})

        mode, error = self._detect_mode_with_fake_home(self.credentials_path, self.fake_home)

        self.assertEqual(mode, "console")
        self.assertIsNone(error)

    def test_detect_mode_code_when_oauth_in_credentials_overrides_claude_json_primary_key(self):
        """OAuth in credentials returns code mode even when ~/.claude.json has primaryApiKey"""
        credentials_data = {
            "claudeAiOauth": {
                "accessToken": FAKE_OAUTH_TOKEN,
                "refreshToken": FAKE_OAUTH_REFRESH,
                "expiresAt": FAKE_OAUTH_EXPIRES_AT,
            }
        }
        with open(self.credentials_path, "w") as f:
            json.dump(credentials_data, f)

        self._write_claude_json(self.fake_home, {"primaryApiKey": FAKE_PRIMARY_KEY})

        mode, error = self._detect_mode_with_fake_home(self.credentials_path, self.fake_home)

        self.assertEqual(mode, "code")
        self.assertIsNone(error)

    def test_detect_mode_no_credentials_regression(self):
        """Regression guard: no useful credentials anywhere returns exactly (None, 'No credentials found')"""
        credentials_data = {"mcpOAuth": {"token": "irrelevant-mcp-token"}}
        with open(self.credentials_path, "w") as f:
            json.dump(credentials_data, f)

        self._write_claude_json(self.fake_home, {"someOtherField": "no-key-here"})

        result = self._detect_mode_with_fake_home(self.credentials_path, self.fake_home)

        self.assertEqual(result, (None, "No credentials found"))

    def test_detect_mode_code_when_oauth_available_despite_admin_key_in_env(self):
        """Test that mode is 'code' when OAuth credentials take priority over env var"""
        # Create credentials file with OAuth but no admin key
        credentials_data = {
            "claudeCode": {"accessToken": "test-token", "refreshToken": "test-refresh"}
        }
        with open(self.credentials_path, "w") as f:
            json.dump(credentials_data, f)

        with patch.dict(
            os.environ, {"ANTHROPIC_ADMIN_API_KEY": "sk-ant-admin-test-key"}
        ):
            monitor = ClaudeUsageMonitor(credentials_path=self.credentials_path)
            mode = monitor.detect_mode()

            # Code mode takes priority over environment variable
            self.assertEqual(mode, "code")

    def test_detect_mode_code_when_oauth_available_despite_admin_key_in_file(self):
        """Test that mode is 'code' when OAuth credentials take priority over admin key in file"""
        credentials_data = {
            "claudeCode": {"accessToken": "test-token", "refreshToken": "test-refresh"},
            "anthropicConsole": {"adminApiKey": "sk-ant-admin-test-key"},
        }
        with open(self.credentials_path, "w") as f:
            json.dump(credentials_data, f)

        # Ensure env var is not set
        with patch.dict(os.environ, {}, clear=True):
            monitor = ClaudeUsageMonitor(credentials_path=self.credentials_path)
            mode = monitor.detect_mode()

            # Code mode takes priority over admin key in file
            self.assertEqual(mode, "code")

    def test_detect_mode_code_when_only_oauth_available(self):
        """Test that mode is 'code' when only OAuth credentials available"""
        credentials_data = {
            "claudeCode": {"accessToken": "test-token", "refreshToken": "test-refresh"}
        }
        with open(self.credentials_path, "w") as f:
            json.dump(credentials_data, f)

        # Ensure env var is not set
        with patch.dict(os.environ, {}, clear=True):
            monitor = ClaudeUsageMonitor(credentials_path=self.credentials_path)
            mode = monitor.detect_mode()

            self.assertEqual(mode, "code")

    def test_detect_mode_console_when_only_admin_key_in_file(self):
        """Test that mode is 'console' when only admin key in file (no OAuth)"""
        credentials_data = {
            "anthropicConsole": {"adminApiKey": "sk-ant-admin-test-key"},
        }
        with open(self.credentials_path, "w") as f:
            json.dump(credentials_data, f)

        with patch.dict(os.environ, {}, clear=True):
            monitor = ClaudeUsageMonitor(credentials_path=self.credentials_path)
            mode = monitor.detect_mode()

            self.assertEqual(mode, "console")

    def test_detect_mode_console_when_only_admin_key_in_env(self):
        """Test that mode is 'console' when only admin key in env (no OAuth)"""
        # Don't create credentials file with OAuth
        credentials_data = {}
        with open(self.credentials_path, "w") as f:
            json.dump(credentials_data, f)

        with patch.dict(
            os.environ, {"ANTHROPIC_ADMIN_API_KEY": "sk-ant-admin-test-key"}
        ):
            monitor = ClaudeUsageMonitor(credentials_path=self.credentials_path)
            mode = monitor.detect_mode()

            self.assertEqual(mode, "console")

    def test_detect_mode_error_when_no_credentials(self):
        """Test that mode detection returns error when no credentials found"""
        # Don't create credentials file and use empty fake home (no ~/.claude.json)
        with patch.dict(os.environ, {}, clear=True):
            with patch("claude_usage.monitor.Path.home", return_value=self.fake_home):
                monitor = ClaudeUsageMonitor(credentials_path=self.credentials_path)
                mode = monitor.detect_mode()

                self.assertIsNone(mode)
                self.assertIsNotNone(monitor.error_message)
                self.assertIn("No credentials", monitor.error_message)

    def test_mode_field_override_in_credentials_forces_console(self):
        """
        GIVEN credentials file has 'mode' field set to 'console'
        AND has both OAuth and Admin API credentials
        WHEN detect_mode is called
        THEN it should return 'console' (respecting the override)
        """
        credentials_data = {
            "mode": "console",
            "claudeAiOauth": {
                "accessToken": "test-token",
                "refreshToken": "test-refresh",
                "expiresAt": 9999999999000,
            },
            "anthropicConsole": {"adminApiKey": "sk-ant-admin-test-key"},
        }
        with open(self.credentials_path, "w") as f:
            json.dump(credentials_data, f)

        with patch.dict(os.environ, {}, clear=True):
            monitor = ClaudeUsageMonitor(credentials_path=self.credentials_path)
            mode = monitor.detect_mode()

            self.assertEqual(mode, "console")

    def test_mode_field_override_in_credentials_forces_code(self):
        """
        GIVEN credentials file has 'mode' field set to 'code'
        AND has both OAuth and Admin API credentials
        WHEN detect_mode is called
        THEN it should return 'code' (respecting the override)
        """
        credentials_data = {
            "mode": "code",
            "claudeAiOauth": {
                "accessToken": "test-token",
                "refreshToken": "test-refresh",
                "expiresAt": 9999999999000,
            },
            "anthropicConsole": {"adminApiKey": "sk-ant-admin-test-key"},
        }
        with open(self.credentials_path, "w") as f:
            json.dump(credentials_data, f)

        with patch.dict(os.environ, {}, clear=True):
            monitor = ClaudeUsageMonitor(credentials_path=self.credentials_path)
            mode = monitor.detect_mode()

            self.assertEqual(mode, "code")


if __name__ == "__main__":
    unittest.main()
