"""Tests for per-user Claude Code usage tracking in monitor"""

import unittest
from unittest.mock import patch, Mock
from pathlib import Path
from claude_usage.monitor import ClaudeUsageMonitor


class TestMonitorClaudeCodeUserTracking(unittest.TestCase):
    """Test cases for monitor integration with per-user Claude Code tracking"""

    @patch("claude_usage.auth.AdminAuthManager")
    @patch("claude_usage.api.ConsoleAPIClient")
    def test_fetch_console_data_includes_user_claude_code_cost(
        self, mock_console_client_class, mock_auth_manager_class
    ):
        """Test that fetch_console_data fetches and stores per-user Claude Code cost"""
        # Setup mocks
        mock_auth_manager = Mock()
        mock_auth_manager.load_admin_credentials.return_value = (
            "sk-ant-admin-test",
            None,
            None,
        )
        mock_auth_manager_class.return_value = mock_auth_manager

        mock_console_client = Mock()
        mock_console_client._calculate_mtd_range.return_value = (
            "2025-11-01",
            "2025-11-12",
        )
        mock_console_client.fetch_organization.return_value = (
            {"id": "org_123", "name": "Test Org"},
            None,
        )
        mock_console_client.fetch_workspaces.return_value = ([], None)
        mock_console_client.fetch_usage_report.return_value = (
            {"by_model": {}},
            None,
        )
        mock_console_client.fetch_cost_report.return_value = (
            {"total_cost_usd": 100.0},
            None,
        )

        # Mock per-user Claude Code usage
        mock_console_client.fetch_claude_code_user_usage.return_value = (
            {
                "users": [
                    {"email": "user1@example.com", "cost_usd": 50.0},
                    {"email": "user2@example.com", "cost_usd": 30.0},
                ]
            },
            None,
        )
        mock_console_client.get_current_user_email.return_value = (
            "user1@example.com",
            None,
        )
        mock_console_client.fetch_claude_code_analytics.return_value = (None, None)

        mock_console_client_class.return_value = mock_console_client

        # Create monitor with mocked credentials path
        with patch("claude_usage.monitor.Path.home") as mock_home:
            mock_home.return_value = Path("/tmp")
            with patch("claude_usage.monitor.Path.mkdir"):
                with patch("builtins.open", create=True):
                    with patch("json.load") as mock_json_load:
                        with patch("claude_usage.monitor.UsageStorage") as mock_storage_class:
                            mock_storage = Mock()
                            mock_storage.store_console_snapshot = Mock()
                            mock_storage_class.return_value = mock_storage

                            mock_json_load.return_value = {
                                "anthropicConsole": {"adminApiKey": "sk-ant-admin-test"}
                            }
                            monitor = ClaudeUsageMonitor()
                            monitor.mode = "console"
                            monitor._initialize_mode_components()

                            # Execute
                            result = monitor.fetch_console_data()

                            # Verify per-user tracking was called
                            mock_console_client.fetch_claude_code_user_usage.assert_called_once_with(
                                "2025-11-01", "2025-11-12"
                            )
                            mock_console_client.get_current_user_email.assert_called_once()

                            # Verify mtd_cost contains user-specific data
                            self.assertTrue(result)
                            self.assertIsNotNone(monitor.mtd_cost)
                            self.assertEqual(monitor.mtd_cost["claude_code_user_cost_usd"], 50.0)
                            self.assertEqual(
                                monitor.mtd_cost["current_user_email"], "user1@example.com"
                            )

    @patch("claude_usage.auth.AdminAuthManager")
    @patch("claude_usage.api.ConsoleAPIClient")
    def test_fetch_console_data_handles_user_not_found(
        self, mock_console_client_class, mock_auth_manager_class
    ):
        """Test handling when current user not found in Claude Code usage"""
        # Setup mocks
        mock_auth_manager = Mock()
        mock_auth_manager.load_admin_credentials.return_value = (
            "sk-ant-admin-test",
            None,
            None,
        )
        mock_auth_manager_class.return_value = mock_auth_manager

        mock_console_client = Mock()
        mock_console_client._calculate_mtd_range.return_value = (
            "2025-11-01",
            "2025-11-12",
        )
        mock_console_client.fetch_organization.return_value = (
            {"id": "org_123", "name": "Test Org"},
            None,
        )
        mock_console_client.fetch_workspaces.return_value = ([], None)
        mock_console_client.fetch_usage_report.return_value = (
            {"by_model": {}},
            None,
        )
        mock_console_client.fetch_cost_report.return_value = (
            {"total_cost_usd": 100.0},
            None,
        )

        # Mock per-user Claude Code usage without current user
        mock_console_client.fetch_claude_code_user_usage.return_value = (
            {"users": [{"email": "user2@example.com", "cost_usd": 30.0}]},
            None,
        )
        mock_console_client.get_current_user_email.return_value = (
            "user1@example.com",
            None,
        )
        mock_console_client.fetch_claude_code_analytics.return_value = (None, None)

        mock_console_client_class.return_value = mock_console_client

        # Create monitor
        with patch("claude_usage.monitor.Path.home") as mock_home:
            mock_home.return_value = Path("/tmp")
            with patch("claude_usage.monitor.Path.mkdir"):
                with patch("builtins.open", create=True):
                    with patch("json.load") as mock_json_load:
                        with patch("claude_usage.monitor.UsageStorage") as mock_storage_class:
                            mock_storage = Mock()
                            mock_storage.store_console_snapshot = Mock()
                            mock_storage_class.return_value = mock_storage

                            mock_json_load.return_value = {
                                "anthropicConsole": {"adminApiKey": "sk-ant-admin-test"}
                            }
                            monitor = ClaudeUsageMonitor()
                            monitor.mode = "console"
                            monitor._initialize_mode_components()

                            # Execute
                            result = monitor.fetch_console_data()

                            # Verify user-specific data is 0.0 when user not found
                            self.assertTrue(result)
                            self.assertIsNotNone(monitor.mtd_cost)
                            self.assertEqual(monitor.mtd_cost["claude_code_user_cost_usd"], 0.0)
                            self.assertEqual(
                                monitor.mtd_cost["current_user_email"], "user1@example.com"
                            )


if __name__ == "__main__":
    unittest.main()
