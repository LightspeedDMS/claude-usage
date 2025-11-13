"""Integration tests for Console mode in ClaudeUsageMonitor"""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from claude_usage.monitor import ClaudeUsageMonitor


class TestConsoleMonitorIntegration:
    """Integration tests for Console mode full workflow"""

    @pytest.fixture
    def console_credentials_file(self):
        """Create temporary credentials file with Admin API key"""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            credentials = {
                "anthropicConsole": {"adminApiKey": "sk-ant-admin01-test-key-12345"}
            }
            json.dump(credentials, f)
            path = Path(f.name)
        yield path
        path.unlink()

    def test_console_mode_initialization_creates_console_components(
        self, console_credentials_file
    ):
        """
        GIVEN Console mode credentials are present
        WHEN monitor is initialized in Console mode
        THEN it should create Console-specific components
        """
        import os

        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_ADMIN_API_KEY"}
        env["ANTHROPIC_ADMIN_API_KEY"] = "sk-ant-admin01-test-key"

        with patch.dict("os.environ", env, clear=True):
            monitor = ClaudeUsageMonitor(credentials_path=console_credentials_file)

            # Should detect console mode
            mode = monitor.detect_mode()
            assert mode == "console"

            # Should have console-specific components
            assert hasattr(
                monitor, "admin_auth_manager"
            ), "Should have admin_auth_manager"
            assert hasattr(monitor, "console_client"), "Should have console_client"
            assert hasattr(monitor, "renderer"), "Should have renderer"
