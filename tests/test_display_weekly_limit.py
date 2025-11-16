"""Tests for weekly_limit_enabled flag support in display module"""

import unittest
from io import StringIO
from unittest.mock import MagicMock
from claude_usage.code_mode.display import UsageRenderer
from rich.console import Console
from rich.text import Text


class TestDisplayWeeklyLimit(unittest.TestCase):
    """Test weekly_limit_enabled conditional rendering in UsageRenderer"""

    def setUp(self):
        """Set up test fixtures"""
        self.renderer = UsageRenderer()

    def test_render_includes_7day_section_when_weekly_limit_enabled_true(self):
        """Test that 7-day section is rendered when weekly_limit_enabled=True"""
        usage_data = {
            "five_hour": {
                "utilization": 65.0,
                "resets_at": "2025-11-12T23:00:00+00:00",
            },
            "seven_day": {
                "utilization": 78.0,
                "resets_at": "2025-11-16T12:00:00+00:00",
            },
        }

        pacemaker_status = {
            "enabled": True,
            "has_data": True,
            "weekly_limit_enabled": True,
            "five_hour": {
                "utilization": 65.0,
                "target": 50.0,
                "time_elapsed_pct": 40.0,
            },
            "seven_day": {
                "utilization": 78.0,
                "target": 45.0,
                "time_elapsed_pct": 65.0,
            },
            "constrained_window": "7-day",
            "deviation_percent": 33.0,
            "should_throttle": True,
            "delay_seconds": 10,
            "algorithm": "adaptive",
            "strategy": "weekend",
        }

        panel = self.renderer.render(
            error_message=None,
            last_usage=usage_data,
            last_profile=None,
            last_overage=None,
            last_update=None,
            projection=None,
            pacemaker_status=pacemaker_status,
            weekly_limit_enabled=True,
        )

        # Render panel to string
        console = Console(file=StringIO(), force_terminal=True, width=120)
        console.print(panel)
        panel_str = console.file.getvalue()

        # Verify 7-day section is present
        self.assertIn("7-Day", panel_str)

    def test_render_shows_7day_section_with_throttling_disabled_note(self):
        """Test that 7-day section is shown with '(throttling disabled)' note when weekly_limit_enabled=False"""
        usage_data = {
            "five_hour": {
                "utilization": 65.0,
                "resets_at": "2025-11-12T23:00:00+00:00",
            },
            "seven_day": {
                "utilization": 78.0,
                "resets_at": "2025-11-16T12:00:00+00:00",
            },
        }

        pacemaker_status = {
            "enabled": True,
            "has_data": True,
            "weekly_limit_enabled": False,
            "five_hour": {
                "utilization": 65.0,
                "target": 50.0,
                "time_elapsed_pct": 40.0,
            },
            "seven_day": {
                "utilization": 78.0,
                "target": 45.0,
                "time_elapsed_pct": 65.0,
            },
            "constrained_window": "5-hour",
            "deviation_percent": 15.0,
            "should_throttle": True,
            "delay_seconds": 10,
            "algorithm": "adaptive",
            "strategy": "preload",
        }

        panel = self.renderer.render(
            error_message=None,
            last_usage=usage_data,
            last_profile=None,
            last_overage=None,
            last_update=None,
            projection=None,
            pacemaker_status=pacemaker_status,
            weekly_limit_enabled=False,
        )

        # Render panel to string
        console = Console(file=StringIO(), force_terminal=True, width=120)
        console.print(panel)
        panel_str = console.file.getvalue()

        # Verify 7-day section IS present (usage still reported)
        self.assertIn("7-Day", panel_str)
        # Verify it shows throttling disabled note
        self.assertIn("throttling disabled", panel_str)
        # Verify 5-hour section IS present
        self.assertIn("5-Hour", panel_str)

    def test_pacemaker_status_shows_correct_message_when_weekly_disabled(self):
        """Test pace-maker status shows appropriate message when weekly throttling disabled"""
        usage_data = {
            "five_hour": {
                "utilization": 65.0,
                "resets_at": "2025-11-12T23:00:00+00:00",
            },
        }

        pacemaker_status = {
            "enabled": True,
            "has_data": True,
            "weekly_limit_enabled": False,
            "five_hour": {
                "utilization": 65.0,
                "target": 50.0,
                "time_elapsed_pct": 40.0,
            },
            "constrained_window": "5-hour",
            "deviation_percent": 15.0,
            "should_throttle": False,
            "delay_seconds": 0,
            "algorithm": "adaptive",
            "strategy": "preload",
        }

        panel = self.renderer.render(
            error_message=None,
            last_usage=usage_data,
            last_profile=None,
            last_overage=None,
            last_update=None,
            projection=None,
            pacemaker_status=pacemaker_status,
            weekly_limit_enabled=False,
        )

        # Render panel to string
        console = Console(file=StringIO(), force_terminal=True, width=120)
        console.print(panel)
        panel_str = console.file.getvalue()

        # Verify appropriate messaging is present
        self.assertIn("Pace Maker", panel_str)
        # Should show 5-hour target (not 7-day target)
        self.assertIn("5-Hour Target", panel_str)
        self.assertNotIn("7-Day Target", panel_str)

    def test_render_handles_missing_7day_data_gracefully(self):
        """Test render handles missing 7-day data gracefully (still doesn't show if no data)"""
        usage_data = {
            "five_hour": {
                "utilization": 65.0,
                "resets_at": "2025-11-12T23:00:00+00:00",
            },
            # No seven_day data
        }

        pacemaker_status = {
            "enabled": True,
            "has_data": True,
            "weekly_limit_enabled": False,
            "five_hour": {
                "utilization": 65.0,
                "target": 50.0,
                "time_elapsed_pct": 40.0,
            },
            "constrained_window": "5-hour",
            "deviation_percent": 15.0,
            "should_throttle": False,
            "delay_seconds": 0,
            "algorithm": "adaptive",
            "strategy": "preload",
        }

        # Should not raise exception
        panel = self.renderer.render(
            error_message=None,
            last_usage=usage_data,
            last_profile=None,
            last_overage=None,
            last_update=None,
            projection=None,
            pacemaker_status=pacemaker_status,
            weekly_limit_enabled=False,
        )

        # Verify panel is created
        self.assertIsNotNone(panel)

        # Render panel to string
        console = Console(file=StringIO(), force_terminal=True, width=120)
        console.print(panel)
        panel_str = console.file.getvalue()

        # Verify 5-hour section is present
        self.assertIn("5-Hour", panel_str)
        # Verify 7-day section is NOT present when there's no data (regardless of throttling setting)
        self.assertNotIn("7-Day", panel_str)


if __name__ == "__main__":
    unittest.main()
