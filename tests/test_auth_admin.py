"""Tests for AdminAuthManager - Anthropic Console authentication"""

import unittest
import os
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from claude_usage.console_mode.auth import AdminAuthManager


class TestAdminAuthManager(unittest.TestCase):
    """Test cases for AdminAuthManager class"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.credentials_path = Path(self.temp_dir) / ".credentials.json"

    def tearDown(self):
        """Clean up test fixtures"""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_load_from_env_var_takes_priority(self):
        """Test that ANTHROPIC_ADMIN_API_KEY environment variable is checked first"""
        # Set up environment variable
        env_key = "sk-ant-admin-test-env-key-12345"

        # Also create credentials file to verify env var takes priority
        credentials_data = {
            "anthropicConsole": {"adminApiKey": "sk-ant-admin-test-file-key-67890"}
        }
        with open(self.credentials_path, "w") as f:
            json.dump(credentials_data, f)

        with patch.dict(os.environ, {"ANTHROPIC_ADMIN_API_KEY": env_key}):
            manager = AdminAuthManager(self.credentials_path)
            key, source, error = manager.load_admin_credentials()

            self.assertEqual(key, env_key)
            self.assertEqual(source, "environment")
            self.assertIsNone(error)

    def test_load_from_credentials_file_when_no_env_var(self):
        """Test fallback to credentials.json when env var not set"""
        file_key = "sk-ant-admin-test-file-key-12345"
        credentials_data = {"anthropicConsole": {"adminApiKey": file_key}}
        with open(self.credentials_path, "w") as f:
            json.dump(credentials_data, f)

        # Ensure env var is not set
        with patch.dict(os.environ, {}, clear=True):
            manager = AdminAuthManager(self.credentials_path)
            key, source, error = manager.load_admin_credentials()

            self.assertEqual(key, file_key)
            self.assertEqual(source, "credentials_file")
            self.assertIsNone(error)

    def test_validate_admin_key_format_valid(self):
        """Test that Admin API key validation accepts keys starting with sk-ant-admin"""
        manager = AdminAuthManager(self.credentials_path)

        valid_key = "sk-ant-admin-test-key-12345"
        is_valid, error = manager.validate_admin_key(valid_key)

        self.assertTrue(is_valid)
        self.assertIsNone(error)

    def test_load_admin_credentials_validates_env_var_key_format(self):
        """Test that load_admin_credentials validates key format from env var"""
        invalid_key = "invalid-key-format"

        with patch.dict(os.environ, {"ANTHROPIC_ADMIN_API_KEY": invalid_key}):
            manager = AdminAuthManager(self.credentials_path)
            key, source, error = manager.load_admin_credentials()

            self.assertIsNone(key)
            self.assertIsNone(source)
            self.assertIsNotNone(error)
            self.assertIn("format", error.lower())

    def test_get_admin_headers_returns_required_headers(self):
        """Test that get_admin_headers returns all required headers for Console API"""
        admin_key = "sk-ant-admin-test-key-12345"
        manager = AdminAuthManager(self.credentials_path)

        headers = manager.get_admin_headers(admin_key)

        # Verify all required headers are present
        self.assertIn("x-api-key", headers)
        self.assertIn("anthropic-version", headers)
        self.assertIn("Content-Type", headers)

        # Verify header values
        self.assertEqual(headers["x-api-key"], admin_key)
        self.assertEqual(headers["anthropic-version"], "2023-06-01")
        self.assertEqual(headers["Content-Type"], "application/json")


# ---------------------------------------------------------------------------
# Clearly fake, non-credential-looking placeholders for ~/.claude.json tests
# ---------------------------------------------------------------------------
FAKE_PRIMARY_KEY = "fake-primary-api-key-for-testing"
FAKE_ADMIN_ENV_KEY = "sk-ant-admin-fake-env-key-for-testing"
FAKE_ADMIN_FILE_KEY = "sk-ant-admin-fake-file-key-for-testing"


def _write_claude_json(fake_home, data):
    """Write JSON data to fake ~/.claude.json inside fake_home."""
    claude_json = fake_home / ".claude.json"
    with open(claude_json, "w") as f:
        json.dump(data, f)


def _load_with_fake_home(credentials_path, fake_home):
    """Run load_admin_credentials() with Path.home() patched to fake_home."""
    with patch("claude_usage.console_mode.auth.Path.home", return_value=fake_home):
        manager = AdminAuthManager(credentials_path)
        return manager.load_admin_credentials()


class _ClaudeJsonFixture(unittest.TestCase):
    """Shared temp-dir and fake-home fixture — setUp + tearDown only."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.credentials_path = Path(self.temp_dir) / ".credentials.json"
        self.fake_home = Path(self.temp_dir) / "home"
        self.fake_home.mkdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)


class TestAdminAuthClaudeJsonFallback(_ClaudeJsonFixture):
    """Positive + negative cases for the new ~/.claude.json primaryApiKey fallback."""

    def test_load_from_claude_json_primary_api_key_when_no_other_credentials(self):
        """primaryApiKey from ~/.claude.json is NOT used — returns not found."""
        with open(self.credentials_path, "w") as f:
            json.dump({"mcpOAuth": {"token": "irrelevant"}}, f)
        _write_claude_json(self.fake_home, {"primaryApiKey": FAKE_PRIMARY_KEY})

        with patch.dict(os.environ, {}, clear=True):
            key, source, error = _load_with_fake_home(self.credentials_path, self.fake_home)

        self.assertIsNone(key)
        self.assertIsNone(source)
        self.assertEqual(error, "Admin API key not found")

    def test_error_when_claude_json_has_no_primary_key(self):
        """Falls through to 'Admin API key not found' when ~/.claude.json lacks primaryApiKey."""
        with open(self.credentials_path, "w") as f:
            json.dump({"mcpOAuth": {"token": "irrelevant"}}, f)
        _write_claude_json(self.fake_home, {"someOtherField": "no-key-here"})

        with patch.dict(os.environ, {}, clear=True):
            key, source, error = _load_with_fake_home(self.credentials_path, self.fake_home)

        self.assertIsNone(key)
        self.assertIsNone(source)
        self.assertEqual(error, "Admin API key not found")


class TestAdminAuthClaudeJsonPrecedence(_ClaudeJsonFixture):
    """Regression guards: existing sources must win over ~/.claude.json primaryApiKey."""

    def test_env_var_wins_over_claude_json(self):
        """ANTHROPIC_ADMIN_API_KEY env var takes precedence over ~/.claude.json primaryApiKey."""
        with open(self.credentials_path, "w") as f:
            json.dump({"mcpOAuth": {"token": "irrelevant"}}, f)
        _write_claude_json(self.fake_home, {"primaryApiKey": FAKE_PRIMARY_KEY})

        with patch.dict(os.environ, {"ANTHROPIC_ADMIN_API_KEY": FAKE_ADMIN_ENV_KEY}):
            key, source, error = _load_with_fake_home(self.credentials_path, self.fake_home)

        self.assertEqual(source, "environment")
        self.assertIsNone(error)

    def test_credentials_file_wins_over_claude_json(self):
        """anthropicConsole.adminApiKey in credentials file wins over ~/.claude.json."""
        with open(self.credentials_path, "w") as f:
            json.dump({"anthropicConsole": {"adminApiKey": FAKE_ADMIN_FILE_KEY}}, f)
        _write_claude_json(self.fake_home, {"primaryApiKey": FAKE_PRIMARY_KEY})

        with patch.dict(os.environ, {}, clear=True):
            key, source, error = _load_with_fake_home(self.credentials_path, self.fake_home)

        self.assertEqual(source, "credentials_file")
        self.assertIsNone(error)


class TestAdminAuthNoFallback(unittest.TestCase):
    """Pins the corrected behavior: primaryApiKey is NOT an admin key source."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.credentials_path = Path(self.temp_dir) / ".credentials.json"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_load_admin_credentials_returns_not_found_when_only_claude_json_primary(self):
        """primaryApiKey in ~/.claude.json must NOT be used as admin key source.

        Credentials file has no anthropicConsole section; env var is absent.
        Even though the real ~/.claude.json may contain primaryApiKey, auth.py
        must not fall back to it — expected: (None, None, 'Admin API key not found').
        """
        with open(self.credentials_path, "w") as f:
            json.dump({"mcpOAuth": {"token": "irrelevant"}}, f)

        with patch.dict(os.environ, {}, clear=True):
            manager = AdminAuthManager(self.credentials_path)
            key, source, error = manager.load_admin_credentials()

        self.assertIsNone(key)
        self.assertIsNone(source)
        self.assertEqual(error, "Admin API key not found")


if __name__ == "__main__":
    unittest.main()
