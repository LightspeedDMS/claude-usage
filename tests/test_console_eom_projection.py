"""Tests for Console mode end-of-month projection"""

import calendar
import sqlite3
import tempfile
from datetime import datetime, date
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from claude_usage.console_mode.storage import ConsoleStorage, ConsoleAnalytics
from claude_usage.console_mode.monitor import ConsoleMonitor
from claude_usage.console_mode.display import ConsoleRenderer


class TestConsoleEOMProjection:
    """Test end-of-month projection in Console monitor"""

    @pytest.fixture
    def temp_db(self):
        """Create temporary database for testing"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            yield db_path

    @pytest.fixture
    def temp_credentials(self):
        """Create temporary credentials file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            creds_path = Path(tmpdir) / ".credentials.json"
            # Don't create the file - let AdminAuthManager handle missing file
            yield creds_path

    def test_eom_projection_initialized_to_none(self, temp_credentials):
        """Test ConsoleMonitor initializes eom_projection to None"""
        monitor = ConsoleMonitor(credentials_path=temp_credentials)
        assert hasattr(monitor, 'eom_projection'), "ConsoleMonitor should have eom_projection attribute"
        assert monitor.eom_projection is None, "eom_projection should initialize to None"

    @patch('claude_usage.console_mode.monitor.ConsoleAPIClient')
    def test_eom_projection_calculated_when_rate_available(self, mock_client_class, temp_credentials, temp_db):
        """Test EOM projection is calculated when rate is available"""
        # Create monitor with mocked client
        monitor = ConsoleMonitor(credentials_path=temp_credentials)

        # Override storage with test database
        monitor.storage = ConsoleStorage(temp_db)
        monitor.analytics = ConsoleAnalytics(monitor.storage)

        # Insert historical data for rate calculation
        current_time = int(datetime.now().timestamp())
        thirty_min_ago = current_time - 1800

        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO console_usage_snapshots
            (timestamp, mtd_cost, workspace_costs_json)
            VALUES (?, ?, ?)
        """,
            (thirty_min_ago, 10.00, "[]"),
        )
        conn.commit()
        conn.close()

        # Set up mock client
        mock_client = Mock()
        mock_client.fetch_organization.return_value = ({"id": "org-123", "name": "Test Org"}, None)
        mock_client.fetch_workspaces.return_value = ([], None)
        mock_client._calculate_mtd_range.return_value = ("2025-01-01", "2025-01-15")
        mock_client.fetch_usage_report.return_value = ({}, None)
        mock_client.fetch_cost_report.return_value = ({"total_cost_usd": 20.00}, None)
        mock_client.fetch_claude_code_user_usage.return_value = (
            {"users": [{"email": "test@example.com", "cost_usd": 20.00}]},
            None
        )
        mock_client.get_current_user_email.return_value = ("test@example.com", None)
        mock_client.fetch_claude_code_analytics.return_value = (None, None)

        monitor.console_client = mock_client

        # Mock datetime and calendar functions to control "now" for EOM calculation
        # Use a specific date to avoid issues with real calendar
        mock_date = date(2025, 1, 15)

        with patch('claude_usage.console_mode.monitor.datetime') as mock_dt, \
             patch('claude_usage.console_mode.monitor.date') as mock_date_cls, \
             patch('calendar.monthrange', return_value=(3, 31)):  # January 2025: starts on Wed, has 31 days

            mock_now = datetime(2025, 1, 15, 12, 0, 0)
            mock_dt.now.return_value = mock_now
            mock_dt.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs) if args else mock_now
            mock_date_cls.today.return_value = mock_date

            # Fetch console data (should trigger EOM calculation)
            monitor.fetch_console_data()

        # Verify projection was calculated
        assert monitor.eom_projection is not None, "EOM projection should be calculated"
        assert "current_cost" in monitor.eom_projection
        assert "projected_cost" in monitor.eom_projection
        assert "rate_per_hour" in monitor.eom_projection
        assert "hours_until_eom" in monitor.eom_projection

        # Verify current cost
        assert monitor.eom_projection["current_cost"] == 20.00

        # Verify rate calculation (current: $20, old: $10, diff: $10 over 1800s = $20/hour)
        assert abs(monitor.eom_projection["rate_per_hour"] - 20.0) < 0.01

        # Verify hours calculation (Jan 15 12:00 to Jan 31 23:59)
        # ~16.5 days = ~396 hours
        assert monitor.eom_projection["hours_until_eom"] > 390
        assert monitor.eom_projection["hours_until_eom"] < 400

        # Verify projection ($20 + $20/hour * ~396 hours = ~$7940)
        assert monitor.eom_projection["projected_cost"] > 7900
        assert monitor.eom_projection["projected_cost"] < 8000

    @patch('claude_usage.console_mode.monitor.ConsoleAPIClient')
    def test_eom_projection_none_when_no_rate(self, mock_client_class, temp_credentials, temp_db):
        """Test EOM projection is None when no rate can be calculated"""
        monitor = ConsoleMonitor(credentials_path=temp_credentials)

        # Override storage with test database (empty - no historical data)
        monitor.storage = ConsoleStorage(temp_db)
        monitor.analytics = ConsoleAnalytics(monitor.storage)

        # Set up mock client
        mock_client = Mock()
        mock_client.fetch_organization.return_value = ({"id": "org-123", "name": "Test Org"}, None)
        mock_client.fetch_workspaces.return_value = ([], None)
        mock_client._calculate_mtd_range.return_value = ("2025-01-01", "2025-01-15")
        mock_client.fetch_usage_report.return_value = ({}, None)
        mock_client.fetch_cost_report.return_value = ({"total_cost_usd": 20.00}, None)
        mock_client.fetch_claude_code_user_usage.return_value = (
            {"users": [{"email": "test@example.com", "cost_usd": 20.00}]},
            None
        )
        mock_client.get_current_user_email.return_value = ("test@example.com", None)
        mock_client.fetch_claude_code_analytics.return_value = (None, None)

        monitor.console_client = mock_client

        # Fetch console data (no historical data for rate)
        monitor.fetch_console_data()

        # Verify projection is None
        assert monitor.eom_projection is None, "EOM projection should be None when no rate available"

    @patch('claude_usage.console_mode.monitor.ConsoleAPIClient')
    def test_eom_projection_none_when_no_mtd_cost(self, mock_client_class, temp_credentials, temp_db):
        """Test EOM projection is None when mtd_cost is None"""
        monitor = ConsoleMonitor(credentials_path=temp_credentials)

        # Override storage
        monitor.storage = ConsoleStorage(temp_db)
        monitor.analytics = ConsoleAnalytics(monitor.storage)

        # Set up mock client with None mtd_cost
        mock_client = Mock()
        mock_client.fetch_organization.return_value = ({"id": "org-123", "name": "Test Org"}, None)
        mock_client.fetch_workspaces.return_value = ([], None)
        mock_client._calculate_mtd_range.return_value = ("2025-01-01", "2025-01-15")
        mock_client.fetch_usage_report.return_value = ({}, None)
        mock_client.fetch_cost_report.return_value = (None, None)  # None mtd_cost
        mock_client.fetch_claude_code_user_usage.return_value = (None, None)
        mock_client.fetch_claude_code_analytics.return_value = (None, None)

        monitor.console_client = mock_client

        # Fetch console data
        monitor.fetch_console_data()

        # Verify projection is None
        assert monitor.eom_projection is None, "EOM projection should be None when mtd_cost is None"

    @patch('claude_usage.console_mode.monitor.ConsoleAPIClient')
    def test_get_display_passes_projection(self, mock_client_class, temp_credentials):
        """Test get_display() passes projection to renderer"""
        monitor = ConsoleMonitor(credentials_path=temp_credentials)

        # Set up mock renderer
        mock_renderer = Mock()
        mock_renderer.render.return_value = Mock()
        monitor.renderer = mock_renderer

        # Set eom_projection
        monitor.eom_projection = {
            "current_cost": 20.00,
            "projected_cost": 100.00,
            "rate_per_hour": 5.00,
            "hours_until_eom": 16.0
        }

        # Call get_display()
        monitor.get_display()

        # Verify renderer.render was called with projection
        mock_renderer.render.assert_called_once()
        call_kwargs = mock_renderer.render.call_args[1]
        assert 'projection' in call_kwargs or len(mock_renderer.render.call_args[0]) >= 5

        # Check if projection was passed (either as kwarg or positional arg)
        if 'projection' in call_kwargs:
            assert call_kwargs['projection'] == monitor.eom_projection
        else:
            # Check positional args (org, mtd, workspaces, last_update, projection)
            args = mock_renderer.render.call_args[0]
            if len(args) >= 5:
                assert args[4] == monitor.eom_projection


class TestConsoleEOMProjectionDisplay:
    """Test EOM projection display in ConsoleRenderer"""

    @pytest.fixture
    def renderer(self):
        """Create ConsoleRenderer instance"""
        return ConsoleRenderer()

    def test_render_projection_when_available(self, renderer):
        """Test renderer displays projection when available"""
        from rich.console import Console
        from io import StringIO

        org_data = {"name": "Test Org"}
        mtd_data = {
            "period_label": "Jan 1-15",
            "claude_code_user_cost_usd": 20.00,
            "current_user_email": "test@example.com"
        }
        projection = {
            "current_cost": 20.00,
            "projected_cost": 100.00,
            "rate_per_hour": 5.00,
            "hours_until_eom": 16.0
        }

        # Render with projection
        panel = renderer.render(org_data, mtd_data, [], None, projection=projection, error=None)

        # Convert panel to string using Rich console
        console = Console(file=StringIO(), force_terminal=True, width=120)
        with console.capture() as capture:
            console.print(panel)
        panel_str = capture.get()

        # Verify panel contains projection information
        assert "Projected by end of month" in panel_str or "projected" in panel_str.lower()
        assert "$100.00" in panel_str  # Projected cost
        assert "$5.00/hour" in panel_str or "5.00" in panel_str  # Rate

    def test_render_no_projection_when_none(self, renderer):
        """Test renderer doesn't show projection when None"""
        from rich.console import Console
        from io import StringIO

        org_data = {"name": "Test Org"}
        mtd_data = {
            "period_label": "Jan 1-15",
            "claude_code_user_cost_usd": 20.00,
            "current_user_email": "test@example.com"
        }

        # Render without projection
        panel = renderer.render(org_data, mtd_data, [], None, projection=None, error=None)

        # Convert panel to string using Rich console
        console = Console(file=StringIO(), force_terminal=True, width=120)
        with console.capture() as capture:
            console.print(panel)
        panel_str = capture.get()

        # Verify panel does NOT contain projection information
        # Should not have projection-specific text
        assert "Projected by end of month" not in panel_str

    def test_render_projection_format(self, renderer):
        """Test projection is formatted correctly with currency"""
        from rich.console import Console
        from io import StringIO

        org_data = {"name": "Test Org"}
        mtd_data = {
            "period_label": "Jan 1-15",
            "claude_code_user_cost_usd": 25.50,
            "current_user_email": "test@example.com"
        }
        projection = {
            "current_cost": 25.50,
            "projected_cost": 150.75,
            "rate_per_hour": 7.25,
            "hours_until_eom": 17.0
        }

        # Render with projection
        panel = renderer.render(org_data, mtd_data, [], None, projection=projection, error=None)

        # Convert panel to string using Rich console
        console = Console(file=StringIO(), force_terminal=True, width=120)
        with console.capture() as capture:
            console.print(panel)
        panel_str = capture.get()

        # Verify formatted values appear
        # Check for proper currency formatting (should have $ and decimals)
        assert "$150.75" in panel_str or "150.75" in panel_str
        assert "$125.25" in panel_str or "125.25" in panel_str  # Increase: $150.75 - $25.50
        assert "$7.25" in panel_str or "7.25" in panel_str  # Rate

    def test_render_projection_shows_increase(self, renderer):
        """Test projection displays the increase amount"""
        from rich.console import Console
        from io import StringIO

        org_data = {"name": "Test Org"}
        mtd_data = {
            "period_label": "Jan 1-15",
            "claude_code_user_cost_usd": 30.00,
            "current_user_email": "test@example.com"
        }
        projection = {
            "current_cost": 30.00,
            "projected_cost": 200.00,
            "rate_per_hour": 10.00,
            "hours_until_eom": 17.0
        }

        # Render with projection
        panel = renderer.render(org_data, mtd_data, [], None, projection=projection, error=None)

        # Convert panel to string using Rich console
        console = Console(file=StringIO(), force_terminal=True, width=120)
        with console.capture() as capture:
            console.print(panel)
        panel_str = capture.get()

        # Verify increase is shown (projected - current = $170.00)
        assert "$170.00" in panel_str or "170.00" in panel_str
        # Should show "+" prefix for increase
        assert "+$170.00" in panel_str or "+170.00" in panel_str
