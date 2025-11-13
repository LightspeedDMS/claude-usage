"""Integration tests for mode resolution logic"""

import unittest
import os
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from claude_usage.monitor import ClaudeUsageMonitor


class TestModeResolution(unittest.TestCase):
    """Test cases for mode resolution (CLI override vs auto-detect)"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.credentials_path = Path(self.temp_dir) / ".credentials.json"

    def tearDown(self):
        """Clean up test fixtures"""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_resolve_mode_uses_cli_override_when_provided(self):
        """Test that CLI --mode argument overrides auto-detection"""
        # Create credentials file that would auto-detect as "console"
        credentials_data = {
            "anthropicConsole": {"adminApiKey": "sk-ant-admin-test-key"}
        }
        with open(self.credentials_path, "w") as f:
            json.dump(credentials_data, f)

        with patch.dict(os.environ, {}, clear=True):
            monitor = ClaudeUsageMonitor(credentials_path=self.credentials_path)

            # CLI override should take precedence
            mode = monitor.resolve_mode(cli_mode="code")
            self.assertEqual(mode, "code")

    def test_resolve_mode_auto_detects_when_no_cli_mode(self):
        """Test that resolve_mode falls back to auto-detection when no CLI mode"""
        # Create credentials file that will auto-detect as "console"
        credentials_data = {
            "anthropicConsole": {"adminApiKey": "sk-ant-admin-test-key"}
        }
        with open(self.credentials_path, "w") as f:
            json.dump(credentials_data, f)

        with patch.dict(os.environ, {}, clear=True):
            monitor = ClaudeUsageMonitor(credentials_path=self.credentials_path)

            # Should auto-detect as console
            mode = monitor.resolve_mode(cli_mode=None)
            self.assertEqual(mode, "console")


if __name__ == "__main__":
    unittest.main()
