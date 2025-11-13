"""End-to-end tests for main() function"""

import unittest
import os
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestMainE2E(unittest.TestCase):
    """End-to-end test cases for main() function"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.credentials_path = Path(self.temp_dir) / ".credentials.json"

    def tearDown(self):
        """Clean up test fixtures"""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_main_calls_parse_args_on_startup(self):
        """Test that main() calls parse_args() to get CLI arguments"""
        # Create minimal credentials
        credentials_data = {
            "anthropicConsole": {"adminApiKey": "sk-ant-admin-test-key"}
        }
        with open(self.credentials_path, "w") as f:
            json.dump(credentials_data, f)

        # Mock everything except parse_args to test it gets called
        with patch("sys.argv", ["monitor.py", "--mode", "console"]):
            with patch.dict(os.environ, {}, clear=True):
                with patch("claude_usage.ClaudeUsageMonitor") as MockMonitor:
                    with patch("claude_usage.console_mode.monitor.Live") as MockLive:
                        with patch("claude_usage.monitor.console"):
                            # Setup mocks
                            mock_monitor = MockMonitor.return_value
                            mock_monitor.credentials_path = self.credentials_path
                            mock_monitor.resolve_mode.return_value = "console"
                            mock_monitor.error_message = None
                            mock_monitor.firefox_manager.extract_session_key.return_value = (
                                None
                            )

                            # Make Live context manager raise KeyboardInterrupt to exit loop
                            MockLive.return_value.__enter__.return_value = MagicMock()
                            MockLive.return_value.__enter__.side_effect = (
                                KeyboardInterrupt()
                            )

                            # Import and run main
                            from claude_usage.monitor import main

                            try:
                                main()
                            except KeyboardInterrupt:
                                pass

                            # Verify resolve_mode was called with "console" from CLI
                            mock_monitor.resolve_mode.assert_called_once_with(
                                cli_mode="console"
                            )

    def test_main_console_mode_no_firefox_manager_access(self):
        """Test that main() doesn't access firefox_manager in console mode"""
        # Create admin credentials for console mode
        credentials_data = {
            "anthropicConsole": {"adminApiKey": "sk-ant-admin-test-key"}
        }
        with open(self.credentials_path, "w") as f:
            json.dump(credentials_data, f)

        with patch("sys.argv", ["monitor.py"]):
            with patch.dict(
                os.environ,
                {"ANTHROPIC_ADMIN_API_KEY": "sk-ant-admin-env-key"},
                clear=True,
            ):
                with patch("claude_usage.console_mode.monitor.Live") as MockLive:
                    with patch("claude_usage.monitor.console"):
                        # Make Live context manager raise KeyboardInterrupt to exit loop
                        MockLive.return_value.__enter__.return_value = MagicMock()
                        MockLive.return_value.__enter__.side_effect = (
                            KeyboardInterrupt()
                        )

                        # Import and run main with real ClaudeUsageMonitor
                        from claude_usage.monitor import main

                        try:
                            main()
                        except KeyboardInterrupt:
                            pass
                        # Test passes if no AttributeError about firefox_manager


if __name__ == "__main__":
    unittest.main()
