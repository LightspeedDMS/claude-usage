"""Tests for mode-aware polling loop integration in monitor.py"""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, Mock
from datetime import datetime
from claude_usage.monitor import ClaudeUsageMonitor


class TestFetchConsoleData:
    """Tests for fetch_console_data() method"""

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

    def test_fetch_console_data_fetches_all_required_data(
        self, console_credentials_file
    ):
        """
        GIVEN monitor initialized in console mode
        WHEN fetch_console_data() is called
        THEN it should fetch organization, workspaces, and MTD data
        """
        with patch.dict(
            "os.environ", {"ANTHROPIC_ADMIN_API_KEY": "sk-ant-admin01-test-key"}
        ):
            monitor = ClaudeUsageMonitor(credentials_path=console_credentials_file)

            # Mock console client methods
            monitor.console_client.fetch_organization = Mock(
                return_value=({"id": "org_123", "name": "Test Org"}, None)
            )
            monitor.console_client.fetch_workspaces = Mock(
                return_value=([{"id": "ws_1", "name": "Workspace 1"}], None)
            )

            # Mock date range calculations
            monitor.console_client._calculate_mtd_range = Mock(
                return_value=("2025-11-01", "2025-11-15")
            )

            # Mock report fetches (only MTD now)
            monitor.console_client.fetch_usage_report = Mock(
                return_value=({"total_tokens": 1000000}, None)  # MTD usage
            )
            monitor.console_client.fetch_cost_report = Mock(
                return_value=({"total_cost_usd": 50.00}, None)  # MTD cost
            )

            # Mock per-user Claude Code usage
            monitor.console_client.fetch_claude_code_user_usage = Mock(
                return_value=({"users": []}, None)
            )
            monitor.console_client.get_current_user_email = Mock(
                return_value=(None, "No users found")
            )

            # Mock optional analytics
            monitor.console_client.fetch_claude_code_analytics = Mock(
                return_value=({"code_sessions": 100}, None)
            )

            # Mock storage
            monitor.storage.store_console_snapshot = Mock()

            # Execute
            result = monitor.fetch_console_data()

            # Verify
            assert result is True
            assert monitor.console_org_data == {"id": "org_123", "name": "Test Org"}
            assert monitor.console_workspaces == [{"id": "ws_1", "name": "Workspace 1"}]
            assert monitor.mtd_usage == {"total_tokens": 1000000}
            assert monitor.mtd_cost["total_cost_usd"] == 50.00
            assert "claude_code_users" in monitor.mtd_cost
            # YTD data should NOT exist
            assert not hasattr(monitor, "ytd_usage")
            assert not hasattr(monitor, "ytd_cost")
            assert monitor.console_code_analytics == {"code_sessions": 100}
            assert monitor.last_update is not None
            monitor.storage.store_console_snapshot.assert_called_once()

    def test_fetch_console_data_handles_missing_console_client(self):
        """
        GIVEN monitor initialized in code mode (no console_client)
        WHEN fetch_console_data() is called
        THEN it should return False gracefully
        """
        # Create code mode credentials
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            credentials = {
                "claudeAiOauth": {
                    "accessToken": "test_token",
                    "refreshToken": "test_refresh",
                    "expiresAt": 9999999999000,
                }
            }
            json.dump(credentials, f)
            code_creds_path = Path(f.name)

        try:
            # Ensure no Admin API key in environment
            import os

            env_without_admin_key = {
                k: v for k, v in os.environ.items() if k != "ANTHROPIC_ADMIN_API_KEY"
            }

            with patch.dict("os.environ", env_without_admin_key, clear=True):
                monitor = ClaudeUsageMonitor(credentials_path=code_creds_path)

                # Execute
                result = monitor.fetch_console_data()

                # Verify
                assert result is False
                assert not hasattr(monitor, "console_client")
        finally:
            code_creds_path.unlink()

    def test_fetch_console_data_handles_organization_fetch_error(
        self, console_credentials_file
    ):
        """
        GIVEN monitor initialized in console mode
        WHEN fetch_organization() returns an error
        THEN fetch_console_data() should return False and set error_message
        """
        with patch.dict(
            "os.environ", {"ANTHROPIC_ADMIN_API_KEY": "sk-ant-admin01-test-key"}
        ):
            monitor = ClaudeUsageMonitor(credentials_path=console_credentials_file)

            # Mock console client with error
            monitor.console_client.fetch_organization = Mock(
                return_value=(None, "API Error: Unauthorized")
            )

            # Execute
            result = monitor.fetch_console_data()

            # Verify
            assert result is False
            assert monitor.error_message == "API Error: Unauthorized"


class TestGetConsoleDisplay:
    """Tests for get_console_display() method"""

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

    def test_get_console_display_returns_rich_panel(self, console_credentials_file):
        """
        GIVEN monitor initialized in console mode with data
        WHEN get_console_display() is called
        THEN it should return a Rich Panel object
        """
        from rich.panel import Panel
        from unittest.mock import MagicMock

        with patch.dict(
            "os.environ", {"ANTHROPIC_ADMIN_API_KEY": "sk-ant-admin01-test-key"}
        ):
            monitor = ClaudeUsageMonitor(credentials_path=console_credentials_file)

            # Mock data
            monitor.console_org_data = {"id": "org_123", "name": "Test Org"}
            monitor.mtd_cost = {"total_cost_usd": 50.00}
            monitor.console_workspaces = [{"id": "ws_1", "name": "Workspace 1"}]
            monitor.last_update = datetime.now()

            # Mock analytics to return no rate (no projection)
            monitor.analytics.calculate_console_mtd_rate = Mock(return_value=None)

            # Mock renderer
            mock_panel = MagicMock(spec=Panel)
            monitor.console_renderer.render = Mock(return_value=mock_panel)

            # Execute
            result = monitor.get_console_display()

            # Verify
            assert result == mock_panel
            monitor.console_renderer.render.assert_called_once_with(
                monitor.console_org_data,
                monitor.mtd_cost,
                monitor.console_workspaces,
                monitor.last_update,
                None,  # No projection
                error=None,
            )

    def test_get_console_display_includes_projection_when_rate_available(
        self, console_credentials_file
    ):
        """
        GIVEN monitor initialized in console mode with positive spending rate
        WHEN get_console_display() is called
        THEN it should calculate and include projection
        """
        from rich.panel import Panel
        from unittest.mock import MagicMock

        with patch.dict(
            "os.environ", {"ANTHROPIC_ADMIN_API_KEY": "sk-ant-admin01-test-key"}
        ):
            with patch("claude_usage.monitor.datetime") as mock_datetime_class:
                # Mock current time to mid-month
                mock_now = datetime(2025, 11, 15, 14, 30)
                mock_datetime_class.now.return_value = mock_now

                monitor = ClaudeUsageMonitor(credentials_path=console_credentials_file)

                # Mock data
                monitor.console_org_data = {"id": "org_123", "name": "Test Org"}
                monitor.mtd_cost = {"total_cost_usd": 50.00}
                monitor.console_workspaces = [{"id": "ws_1", "name": "Workspace 1"}]
                monitor.last_update = mock_now

                # Mock analytics to return positive rate
                monitor.analytics.calculate_console_mtd_rate = Mock(
                    return_value=2.5
                )  # $2.50/hour
                monitor.analytics.project_console_eom_cost = Mock(return_value=150.00)

                # Mock renderer
                mock_panel = MagicMock(spec=Panel)
                monitor.console_renderer.render = Mock(return_value=mock_panel)

                # Execute
                monitor.get_console_display()

                # Verify analytics calls
                monitor.analytics.calculate_console_mtd_rate.assert_called_once_with(
                    50.00
                )
                monitor.analytics.project_console_eom_cost.assert_called_once()

                # Verify renderer called with projection
                call_args = monitor.console_renderer.render.call_args[0]
                projection = call_args[4]
                assert projection is not None
                assert projection["projected_eom_cost"] == 150.00
                assert projection["rate_per_hour"] == 2.5


class TestGetDisplayRouting:
    """Tests for get_display() routing based on mode"""

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

    def test_get_display_routes_to_console_display_in_console_mode(
        self, console_credentials_file
    ):
        """
        GIVEN monitor initialized in console mode
        WHEN get_display() is called
        THEN it should route to get_console_display()
        """
        from unittest.mock import MagicMock

        with patch.dict(
            "os.environ", {"ANTHROPIC_ADMIN_API_KEY": "sk-ant-admin01-test-key"}
        ):
            monitor = ClaudeUsageMonitor(credentials_path=console_credentials_file)

            # Store mode for verification
            monitor.mode = monitor.detect_mode()
            assert monitor.mode == "console"

            # Mock get_console_display
            mock_panel = MagicMock()
            monitor.get_console_display = Mock(return_value=mock_panel)

            # Execute
            result = monitor.get_display()

            # Verify
            monitor.get_console_display.assert_called_once()
            assert result == mock_panel

    def test_get_display_routes_to_code_display_in_code_mode(self):
        """
        GIVEN monitor initialized in code mode
        WHEN get_display() is called
        THEN it should route to existing renderer (code mode display)
        """
        from unittest.mock import MagicMock
        import os

        # Create code mode credentials
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            credentials = {
                "claudeAiOauth": {
                    "accessToken": "test_token",
                    "refreshToken": "test_refresh",
                    "expiresAt": 9999999999000,
                }
            }
            json.dump(credentials, f)
            code_creds_path = Path(f.name)

        try:
            # Ensure no Admin API key in environment
            env_without_admin_key = {
                k: v for k, v in os.environ.items() if k != "ANTHROPIC_ADMIN_API_KEY"
            }

            with patch.dict("os.environ", env_without_admin_key, clear=True):
                monitor = ClaudeUsageMonitor(credentials_path=code_creds_path)

                # Store mode for verification
                monitor.mode = monitor.detect_mode()
                assert monitor.mode == "code"

                # Mock the existing renderer
                mock_panel = MagicMock()
                monitor.renderer.render = Mock(return_value=mock_panel)

                # Execute existing get_display() - should use renderer.render
                result = monitor.get_display()

                # Verify it called the code renderer
                monitor.renderer.render.assert_called_once()
                assert result == mock_panel
        finally:
            code_creds_path.unlink()
