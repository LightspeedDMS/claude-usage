"""Tests for AdminAuthManager - Anthropic Console authentication"""

import unittest
import os
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from claude_usage.auth import AdminAuthManager


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


if __name__ == "__main__":
    unittest.main()
