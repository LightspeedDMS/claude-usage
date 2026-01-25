"""Tests for two-column layout in display module.

Story #23: Monitor Two-Column Layout with Blockage Dashboard
AC1: Two-Column Layout Structure
AC2: Column 1 - Status Indicators (Narrow)
AC3: Column 2 - Blockage Statistics
"""

import unittest
from io import StringIO
from unittest.mock import MagicMock, patch
from rich.console import Console
from claude_usage.code_mode.display import UsageRenderer
from claude_usage.code_mode.monitor import CodeMonitor


class TestTwoColumnLayout(unittest.TestCase):
    """Test cases for two-column layout rendering (AC1, AC2, AC3)"""

    def setUp(self):
        """Set up test fixtures"""
        self.renderer = UsageRenderer()

    def _render_to_text(self, panel, width=80):
        """Helper to render panel to plain text"""
        console = Console(file=StringIO(), width=width, force_terminal=True)
        with console.capture() as capture:
            console.print(panel)
        return capture.get()

    def test_render_bottom_section_returns_two_column_group(self):
        """Test that render_bottom_section returns a two-column layout (AC1)"""
        pacemaker_status = {
            "enabled": True,
            "has_data": True,
            "algorithm": "adaptive",
            "tempo_enabled": True,
            "intent_validation_enabled": False,
            "subagent_reminder_enabled": True,
        }
        blockage_stats = {
            "Intent Validation": 5,
            "Intent TDD": 2,
            "Pacing Tempo": 0,
            "Pacing Quota": 3,
            "Other": 0,
            "Total": 10,
        }
        result = self.renderer.render_bottom_section(pacemaker_status, blockage_stats)
        self.assertIsNotNone(result)

    def test_render_bottom_section_shows_status_indicators(self):
        """Test that left column shows pacing status indicators (AC2)"""
        pacemaker_status = {
            "enabled": True,
            "has_data": True,
            "algorithm": "adaptive",
            "tempo_enabled": True,
            "intent_validation_enabled": True,
            "subagent_reminder_enabled": False,
        }
        blockage_stats = {"Intent Validation": 0, "Total": 0}
        result = self.renderer.render_bottom_section(pacemaker_status, blockage_stats)
        output = self._render_to_text(result)
        self.assertIn("Algorithm", output)
        self.assertIn("Tempo", output)
        self.assertIn("Intent", output)

    def test_render_bottom_section_shows_blockage_stats(self):
        """Test that right column shows blockage statistics (AC3)"""
        pacemaker_status = {"enabled": True, "has_data": True}
        blockage_stats = {
            "Intent Validation": 5,
            "Intent TDD": 2,
            "Pacing Tempo": 1,
            "Pacing Quota": 3,
            "Other": 0,
            "Total": 11,
        }
        result = self.renderer.render_bottom_section(pacemaker_status, blockage_stats)
        output = self._render_to_text(result)
        self.assertIn("Intent Validation", output)
        self.assertIn("Total", output)


class TestBlockageStatsUnavailable(unittest.TestCase):
    """Test graceful degradation when blockage stats unavailable (AC5)"""

    def setUp(self):
        """Set up test fixtures"""
        self.renderer = UsageRenderer()

    def _render_to_text(self, panel, width=80):
        """Helper to render panel to plain text"""
        console = Console(file=StringIO(), width=width, force_terminal=True)
        with console.capture() as capture:
            console.print(panel)
        return capture.get()

    def test_render_bottom_section_shows_unavailable_when_stats_none(self):
        """Test that right column shows '(unavailable)' when blockage_stats is None (AC5)"""
        pacemaker_status = {"enabled": True, "has_data": True, "algorithm": "adaptive"}
        result = self.renderer.render_bottom_section(pacemaker_status, blockage_stats=None)
        output = self._render_to_text(result)
        self.assertIn("unavailable", output)
        # Left column should still work
        self.assertIn("Pacing Status", output)


class TestTerminalWidthHandling(unittest.TestCase):
    """Test cases for terminal width handling (AC6)"""

    def setUp(self):
        """Set up test fixtures"""
        self.renderer = UsageRenderer()

    def _render_to_text(self, panel, width=80):
        """Helper to render panel to plain text"""
        console = Console(file=StringIO(), width=width, force_terminal=True)
        with console.capture() as capture:
            console.print(panel)
        return capture.get()

    def test_wide_terminal_shows_two_columns(self):
        """Test that terminals >= 60 chars show two-column layout (AC6)"""
        pacemaker_status = {"enabled": True, "has_data": True, "algorithm": "adaptive"}
        blockage_stats = {"Intent Validation": 5, "Total": 5}
        result = self.renderer.render_bottom_section(pacemaker_status, blockage_stats)
        output = self._render_to_text(result, width=80)
        # Both columns should be visible in wide terminal
        self.assertIn("Pacing Status", output)
        self.assertIn("Blockages", output)

    def test_narrow_terminal_renders_without_error(self):
        """Test that narrow terminals render without crashing (AC6)"""
        pacemaker_status = {"enabled": True, "has_data": True}
        blockage_stats = {"Intent Validation": 2, "Total": 2}
        result = self.renderer.render_bottom_section(pacemaker_status, blockage_stats)
        # Should not crash at narrow width
        output = self._render_to_text(result, width=40)
        self.assertIsNotNone(output)


class TestMonitorIntegration(unittest.TestCase):
    """Test that monitor.get_display() integrates blockage stats (Issue 2)"""

    def _render_to_text(self, panel, width=80):
        """Helper to render panel to plain text"""
        console = Console(file=StringIO(), width=width, force_terminal=True)
        with console.capture() as capture:
            console.print(panel)
        return capture.get()

    def test_get_display_includes_bottom_section_with_blockage_stats(self):
        """Test that get_display output includes bottom section with blockage stats (Issue 2)"""
        # Create monitor with mocked dependencies
        with patch(
            "claude_usage.code_mode.monitor.OAuthManager"
        ) as mock_oauth, patch(
            "claude_usage.code_mode.monitor.ClaudeAPIClient"
        ), patch(
            "claude_usage.code_mode.monitor.CodeStorage"
        ), patch(
            "claude_usage.code_mode.monitor.CodeAnalytics"
        ), patch(
            "claude_usage.code_mode.monitor.PaceMakerReader"
        ) as mock_pacemaker_class:
            # Setup mocks
            mock_oauth.return_value.load_credentials.return_value = (None, None)
            mock_pacemaker = MagicMock()
            mock_pacemaker_class.return_value = mock_pacemaker
            mock_pacemaker.is_installed.return_value = True
            mock_pacemaker.get_status.return_value = {
                "enabled": True,
                "has_data": True,
                "algorithm": "adaptive",
                "tempo_enabled": True,
                "intent_validation_enabled": False,
                "subagent_reminder_enabled": True,
                "five_hour": {"utilization": 50.0, "target": 60.0},
                "seven_day": {"utilization": 45.0, "target": 50.0},
                "constrained_window": "7-day",
                "should_throttle": False,
                "delay_seconds": 0,
            }
            mock_pacemaker.get_blockage_stats_with_labels.return_value = {
                "Intent Validation": 5,
                "Intent TDD": 2,
                "Pacing Tempo": 0,
                "Pacing Quota": 3,
                "Other": 0,
                "Total": 10,
            }

            monitor = CodeMonitor()

            # Provide usage data
            monitor.last_usage = {
                "five_hour": {"utilization": 50.0, "resets_at": "2024-01-15T10:00:00+00:00"},
                "seven_day": {"utilization": 45.0, "resets_at": "2024-01-20T10:00:00+00:00"},
            }
            monitor.last_profile = None
            monitor.error_message = None

            # Get display
            display = monitor.get_display()
            output = self._render_to_text(display)

            # Verify blockage stats are included in the output
            self.assertIn("Blockages", output, "Bottom section with blockages should be included")
            self.assertIn("Intent Validation", output, "Blockage stats should show categories")

    def test_get_display_gracefully_degrades_without_blockage_stats(self):
        """Test that get_display works when blockage stats are unavailable"""
        # Create monitor with mocked dependencies
        with patch(
            "claude_usage.code_mode.monitor.OAuthManager"
        ) as mock_oauth, patch(
            "claude_usage.code_mode.monitor.ClaudeAPIClient"
        ), patch(
            "claude_usage.code_mode.monitor.CodeStorage"
        ), patch(
            "claude_usage.code_mode.monitor.CodeAnalytics"
        ), patch(
            "claude_usage.code_mode.monitor.PaceMakerReader"
        ) as mock_pacemaker_class:
            # Setup mocks
            mock_oauth.return_value.load_credentials.return_value = (None, None)
            mock_pacemaker = MagicMock()
            mock_pacemaker_class.return_value = mock_pacemaker
            mock_pacemaker.is_installed.return_value = True
            mock_pacemaker.get_status.return_value = {
                "enabled": True,
                "has_data": True,
                "algorithm": "adaptive",
                "five_hour": {"utilization": 50.0, "target": 60.0},
                "seven_day": {"utilization": 45.0, "target": 50.0},
                "constrained_window": "7-day",
                "should_throttle": False,
                "delay_seconds": 0,
            }
            # Blockage stats unavailable
            mock_pacemaker.get_blockage_stats_with_labels.return_value = None

            monitor = CodeMonitor()
            monitor.last_usage = {
                "five_hour": {"utilization": 50.0, "resets_at": "2024-01-15T10:00:00+00:00"},
                "seven_day": {"utilization": 45.0, "resets_at": "2024-01-20T10:00:00+00:00"},
            }
            monitor.last_profile = None
            monitor.error_message = None

            # Get display - should not crash
            display = monitor.get_display()
            output = self._render_to_text(display)

            # Should still show basic output and unavailable message
            self.assertIn("5-Hour", output)
            self.assertIn("unavailable", output)


if __name__ == "__main__":
    unittest.main()
