"""Tests for weekly_limit_enabled flag support in monitor integration"""

import unittest
from unittest.mock import MagicMock, patch
from claude_usage.code_mode.monitor import CodeMonitor


class TestMonitorWeeklyLimit(unittest.TestCase):
    """Test weekly_limit_enabled flag extraction and passing in CodeMonitor"""

    def setUp(self):
        """Set up test fixtures"""
        # Mock the storage path
        with patch("claude_usage.code_mode.monitor.Path"):
            self.monitor = CodeMonitor()

    def test_monitor_extracts_weekly_limit_enabled_from_pacemaker_status(self):
        """Test that monitor extracts weekly_limit_enabled from pacemaker status"""
        # Mock pacemaker reader
        mock_pacemaker_status = {
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

        self.monitor.pacemaker_reader.is_installed = MagicMock(return_value=True)
        self.monitor.pacemaker_reader.get_status = MagicMock(
            return_value=mock_pacemaker_status
        )

        # Mock renderer
        self.monitor.renderer.render = MagicMock()

        # Mock last_usage
        self.monitor.last_usage = {
            "five_hour": {
                "utilization": 65.0,
                "resets_at": "2025-11-12T23:00:00+00:00",
            },
        }

        # Get display
        self.monitor.get_display()

        # Verify renderer.render was called with weekly_limit_enabled=False
        self.monitor.renderer.render.assert_called_once()
        call_kwargs = self.monitor.renderer.render.call_args[1]

        self.assertIn("weekly_limit_enabled", call_kwargs)
        self.assertEqual(call_kwargs["weekly_limit_enabled"], False)

    def test_monitor_passes_weekly_limit_enabled_true(self):
        """Test that monitor passes weekly_limit_enabled=True when flag is True"""
        # Mock pacemaker reader
        mock_pacemaker_status = {
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

        self.monitor.pacemaker_reader.is_installed = MagicMock(return_value=True)
        self.monitor.pacemaker_reader.get_status = MagicMock(
            return_value=mock_pacemaker_status
        )

        # Mock renderer
        self.monitor.renderer.render = MagicMock()

        # Mock last_usage
        self.monitor.last_usage = {
            "five_hour": {
                "utilization": 65.0,
                "resets_at": "2025-11-12T23:00:00+00:00",
            },
            "seven_day": {
                "utilization": 78.0,
                "resets_at": "2025-11-16T12:00:00+00:00",
            },
        }

        # Get display
        self.monitor.get_display()

        # Verify renderer.render was called with weekly_limit_enabled=True
        self.monitor.renderer.render.assert_called_once()
        call_kwargs = self.monitor.renderer.render.call_args[1]

        self.assertIn("weekly_limit_enabled", call_kwargs)
        self.assertEqual(call_kwargs["weekly_limit_enabled"], True)

    def test_monitor_defaults_to_true_when_pacemaker_unavailable(self):
        """Test that monitor defaults weekly_limit_enabled=True when pacemaker unavailable"""
        # Mock pacemaker reader as not installed
        self.monitor.pacemaker_reader.is_installed = MagicMock(return_value=False)

        # Mock renderer
        self.monitor.renderer.render = MagicMock()

        # Mock last_usage
        self.monitor.last_usage = {
            "five_hour": {
                "utilization": 65.0,
                "resets_at": "2025-11-12T23:00:00+00:00",
            },
        }

        # Get display
        self.monitor.get_display()

        # Verify renderer.render was called with weekly_limit_enabled=True (default)
        self.monitor.renderer.render.assert_called_once()
        call_kwargs = self.monitor.renderer.render.call_args[1]

        self.assertIn("weekly_limit_enabled", call_kwargs)
        self.assertEqual(
            call_kwargs["weekly_limit_enabled"],
            True,
            "Should default to True when pacemaker unavailable",
        )


if __name__ == "__main__":
    unittest.main()
