"""Tests verifying YTD functionality has been completely removed from Console mode"""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from claude_usage.monitor import ClaudeUsageMonitor


class TestYTDRemovalFromMonitor:
    """Test that monitor.py has no YTD state or logic"""

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

    def test_monitor_has_no_ytd_state_variables(self, console_credentials_file):
        """Monitor should not have ytd_usage or ytd_cost state variables"""
        import os

        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_ADMIN_API_KEY"}
        env["ANTHROPIC_ADMIN_API_KEY"] = "sk-ant-admin01-test-key"

        with patch.dict("os.environ", env, clear=True):
            monitor = ClaudeUsageMonitor(credentials_path=console_credentials_file)

            # Should NOT have ytd state variables
            assert not hasattr(
                monitor, "ytd_usage"
            ), "Monitor should not have ytd_usage attribute"
            assert not hasattr(
                monitor, "ytd_cost"
            ), "Monitor should not have ytd_cost attribute"

    def test_fetch_console_data_does_not_call_ytd_range_method(
        self, console_credentials_file
    ):
        """fetch_console_data should not call _calculate_ytd_range"""
        from unittest.mock import Mock

        import os

        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_ADMIN_API_KEY"}
        env["ANTHROPIC_ADMIN_API_KEY"] = "sk-ant-admin01-test-key"

        with patch.dict("os.environ", env, clear=True):
            monitor = ClaudeUsageMonitor(credentials_path=console_credentials_file)

            # Mock the console client
            mock_client = Mock()
            mock_client.fetch_organization.return_value = ({"name": "Test Org"}, None)
            mock_client.fetch_workspaces.return_value = ([], None)
            mock_client._calculate_mtd_range.return_value = ("2025-11-01", "2025-11-13")
            mock_client.fetch_usage_report.return_value = ({"by_model": {}}, None)
            mock_client.fetch_cost_report.return_value = (
                {"total_cost_usd": 100.0},
                None,
            )
            mock_client.fetch_claude_code_analytics.return_value = (None, None)
            monitor.console_client = mock_client

            # Fetch data
            monitor.fetch_console_data()

            # Should NOT have called _calculate_ytd_range
            assert (
                not mock_client._calculate_ytd_range.called
            ), "Should not call _calculate_ytd_range"

            # Should only fetch MTD reports once each
            assert (
                mock_client.fetch_usage_report.call_count == 1
            ), "Should fetch MTD usage report once"
            assert (
                mock_client.fetch_cost_report.call_count == 1
            ), "Should fetch MTD cost report once"


class TestYTDRemovalFromStorage:
    """Test that storage.py does not have YTD schema or logic"""

    def test_console_snapshots_table_has_no_ytd_column(self):
        """console_usage_snapshots table should not have ytd_cost column"""
        import tempfile
        import sqlite3
        from claude_usage.storage import UsageStorage

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            storage = UsageStorage(db_path)

            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(console_usage_snapshots)")
            columns = [row[1] for row in cursor.fetchall()]
            conn.close()

            # Should NOT have ytd_cost column
            assert (
                "ytd_cost" not in columns
            ), "console_usage_snapshots should not have ytd_cost column"


class TestYTDRemovalFromDisplay:
    """Test that display.py has no YTD rendering logic"""

    def test_console_renderer_render_does_not_accept_ytd_parameter(self):
        """ConsoleRenderer.render() should not accept ytd_data parameter"""
        import inspect
        from claude_usage.display import ConsoleRenderer

        renderer = ConsoleRenderer()
        sig = inspect.signature(renderer.render)
        params = list(sig.parameters.keys())

        # Should NOT have ytd_data parameter
        assert (
            "ytd_data" not in params
        ), "ConsoleRenderer.render() should not have ytd_data parameter"

    def test_console_renderer_has_no_ytd_section_method(self):
        """ConsoleRenderer should not have _render_ytd_section method"""
        from claude_usage.display import ConsoleRenderer

        renderer = ConsoleRenderer()

        # Should NOT have _render_ytd_section method
        assert not hasattr(
            renderer, "_render_ytd_section"
        ), "ConsoleRenderer should not have _render_ytd_section method"


class TestYTDRemovalFromMonitorDisplay:
    """Test that monitor.py doesn't pass YTD data to renderer"""

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

    def test_get_console_display_does_not_pass_ytd_to_renderer(
        self, console_credentials_file
    ):
        """get_console_display should not pass ytd_cost to renderer"""
        from unittest.mock import Mock
        import os

        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_ADMIN_API_KEY"}
        env["ANTHROPIC_ADMIN_API_KEY"] = "sk-ant-admin01-test-key"

        with patch.dict("os.environ", env, clear=True):
            monitor = ClaudeUsageMonitor(credentials_path=console_credentials_file)

            # Mock renderer
            mock_renderer = Mock()
            mock_renderer.render.return_value = "mock panel"
            monitor.console_renderer = mock_renderer

            # Set up some state
            monitor.console_org_data = {"name": "Test Org"}
            monitor.mtd_cost = {"total_cost_usd": 100.0}
            monitor.console_workspaces = []

            # Get display
            monitor.get_console_display()

            # Verify render was called WITHOUT ytd_cost
            assert mock_renderer.render.called, "render should have been called"
            call_kwargs = (
                mock_renderer.render.call_args[1]
                if mock_renderer.render.call_args[1]
                else {}
            )
            call_args = (
                mock_renderer.render.call_args[0]
                if mock_renderer.render.call_args[0]
                else []
            )

            # Should not have ytd_data in either positional or keyword args
            assert (
                "ytd_data" not in call_kwargs
            ), "Should not pass ytd_data as keyword argument"


class TestYTDRemovalFromAPI:
    """Test that api.py has no YTD logic"""

    def test_console_api_client_has_no_ytd_range_method(self):
        """ConsoleAPIClient should not have _calculate_ytd_range method"""
        from claude_usage.api import ConsoleAPIClient

        client = ConsoleAPIClient("test-key")

        # Should NOT have _calculate_ytd_range method
        assert not hasattr(
            client, "_calculate_ytd_range"
        ), "ConsoleAPIClient should not have _calculate_ytd_range method"
