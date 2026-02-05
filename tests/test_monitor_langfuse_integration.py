"""Integration tests for CodeMonitor Langfuse data fetching.

Story #34: Langfuse Integration Status and Metrics Display
CRITICAL-1: Tests that monitor layer fetches Langfuse data from PaceMakerReader
and passes it to the renderer.

This file tests the CRITICAL bug: CodeMonitor.get_display() never calls
get_langfuse_status() or get_langfuse_metrics(), causing display to always
show "off" and "unavailable".
"""

import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

from claude_usage.code_mode.monitor import CodeMonitor


class TestMonitorLangfuseIntegration(unittest.TestCase):
    """Test CodeMonitor fetches and passes Langfuse data correctly"""

    def setUp(self):
        """Set up test fixtures"""
        self.credentials_path = Path("/tmp/test_credentials.json")

    @patch("claude_usage.code_mode.monitor.PaceMakerReader")
    @patch("claude_usage.code_mode.monitor.UsageRenderer")
    def test_get_display_fetches_langfuse_status_when_pacemaker_installed(
        self, mock_renderer_class, mock_reader_class
    ):
        """CRITICAL-1a: get_display() should call get_langfuse_status() when pace-maker installed"""
        # Setup mock PaceMakerReader
        mock_reader = MagicMock()
        mock_reader.is_installed.return_value = True
        mock_reader.get_status.return_value = {
            "enabled": True,
            "has_data": True,
            "algorithm": "adaptive",
        }
        mock_reader.get_langfuse_status.return_value = True  # Langfuse enabled
        mock_reader.get_langfuse_metrics.return_value = {
            "sessions": 10,
            "traces": 20,
            "spans": 30,
            "total": 60,
        }
        mock_reader_class.return_value = mock_reader

        # Setup mock renderer
        mock_renderer = MagicMock()
        mock_renderer.render.return_value = MagicMock()
        mock_renderer.render_bottom_section.return_value = MagicMock()
        mock_renderer_class.return_value = mock_renderer

        # Create monitor and call get_display()
        monitor = CodeMonitor(self.credentials_path)
        monitor.get_display()

        # ASSERT: get_langfuse_status() should be called
        mock_reader.get_langfuse_status.assert_called_once()

    @patch("claude_usage.code_mode.monitor.PaceMakerReader")
    @patch("claude_usage.code_mode.monitor.UsageRenderer")
    def test_get_display_fetches_langfuse_metrics_when_pacemaker_installed(
        self, mock_renderer_class, mock_reader_class
    ):
        """CRITICAL-1b: get_display() should call get_langfuse_metrics() when pace-maker installed"""
        # Setup mock PaceMakerReader
        mock_reader = MagicMock()
        mock_reader.is_installed.return_value = True
        mock_reader.get_status.return_value = {
            "enabled": True,
            "has_data": True,
            "algorithm": "adaptive",
        }
        mock_reader.get_langfuse_status.return_value = True
        mock_reader.get_langfuse_metrics.return_value = {
            "sessions": 10,
            "traces": 20,
            "spans": 30,
            "total": 60,
        }
        mock_reader_class.return_value = mock_reader

        # Setup mock renderer
        mock_renderer = MagicMock()
        mock_renderer.render.return_value = MagicMock()
        mock_renderer.render_bottom_section.return_value = MagicMock()
        mock_renderer_class.return_value = mock_renderer

        # Create monitor and call get_display()
        monitor = CodeMonitor(self.credentials_path)
        monitor.get_display()

        # ASSERT: get_langfuse_metrics() should be called
        mock_reader.get_langfuse_metrics.assert_called_once()

    @patch("claude_usage.code_mode.monitor.PaceMakerReader")
    @patch("claude_usage.code_mode.monitor.UsageRenderer")
    def test_get_display_injects_langfuse_enabled_into_pacemaker_status(
        self, mock_renderer_class, mock_reader_class
    ):
        """CRITICAL-1c: get_display() should inject langfuse_enabled into pacemaker_status dict"""
        # Setup mock PaceMakerReader
        mock_reader = MagicMock()
        mock_reader.is_installed.return_value = True
        mock_reader.get_status.return_value = {
            "enabled": True,
            "has_data": True,
            "algorithm": "adaptive",
        }
        mock_reader.get_langfuse_status.return_value = True  # Langfuse enabled
        mock_reader.get_langfuse_metrics.return_value = None
        mock_reader_class.return_value = mock_reader

        # Setup mock renderer
        mock_renderer = MagicMock()
        mock_renderer.render.return_value = MagicMock()
        mock_renderer.render_bottom_section.return_value = MagicMock()
        mock_renderer_class.return_value = mock_renderer

        # Create monitor and call get_display()
        monitor = CodeMonitor(self.credentials_path)
        monitor.get_display()

        # ASSERT: render_bottom_section() should be called with langfuse_enabled=True in pacemaker_status
        # First verify the method was called
        mock_renderer.render_bottom_section.assert_called()

        # Now safely access call arguments
        call_args = mock_renderer.render_bottom_section.call_args
        pacemaker_status_arg = call_args[0][0]  # First positional arg
        self.assertIn(
            "langfuse_enabled",
            pacemaker_status_arg,
            "pacemaker_status should contain langfuse_enabled key",
        )
        self.assertTrue(
            pacemaker_status_arg["langfuse_enabled"],
            "langfuse_enabled should be True",
        )

    @patch("claude_usage.code_mode.monitor.PaceMakerReader")
    @patch("claude_usage.code_mode.monitor.UsageRenderer")
    def test_get_display_passes_langfuse_metrics_to_render_bottom_section(
        self, mock_renderer_class, mock_reader_class
    ):
        """CRITICAL-1d: get_display() should pass langfuse_metrics parameter to render_bottom_section()"""
        # Setup mock PaceMakerReader
        mock_reader = MagicMock()
        mock_reader.is_installed.return_value = True
        mock_reader.get_status.return_value = {
            "enabled": True,
            "has_data": True,
            "algorithm": "adaptive",
        }
        mock_reader.get_langfuse_status.return_value = False
        expected_metrics = {
            "sessions": 123,
            "traces": 456,
            "spans": 789,
            "total": 1368,
        }
        mock_reader.get_langfuse_metrics.return_value = expected_metrics
        mock_reader_class.return_value = mock_reader

        # Setup mock renderer
        mock_renderer = MagicMock()
        mock_renderer.render.return_value = MagicMock()
        mock_renderer.render_bottom_section.return_value = MagicMock()
        mock_renderer_class.return_value = mock_renderer

        # Create monitor and call get_display()
        monitor = CodeMonitor(self.credentials_path)
        monitor.get_display()

        # ASSERT: render_bottom_section() should be called with langfuse_metrics kwarg
        # First verify the method was called
        mock_renderer.render_bottom_section.assert_called()

        # Now safely access call kwargs
        call_kwargs = mock_renderer.render_bottom_section.call_args.kwargs
        self.assertIn(
            "langfuse_metrics",
            call_kwargs,
            "render_bottom_section should receive langfuse_metrics keyword argument",
        )
        self.assertEqual(
            call_kwargs["langfuse_metrics"],
            expected_metrics,
            "langfuse_metrics should match what get_langfuse_metrics() returned",
        )

    @patch("claude_usage.code_mode.monitor.PaceMakerReader")
    @patch("claude_usage.code_mode.monitor.UsageRenderer")
    def test_get_display_skips_langfuse_when_pacemaker_not_installed(
        self, mock_renderer_class, mock_reader_class
    ):
        """When pace-maker not installed, Langfuse methods should not be called"""
        # Setup mock PaceMakerReader - NOT installed
        mock_reader = MagicMock()
        mock_reader.is_installed.return_value = False
        mock_reader_class.return_value = mock_reader

        # Setup mock renderer
        mock_renderer = MagicMock()
        mock_renderer.render.return_value = MagicMock()
        mock_renderer_class.return_value = mock_renderer

        # Create monitor and call get_display()
        monitor = CodeMonitor(self.credentials_path)
        monitor.get_display()

        # ASSERT: Langfuse methods should NOT be called
        mock_reader.get_langfuse_status.assert_not_called()
        mock_reader.get_langfuse_metrics.assert_not_called()

    @patch("claude_usage.code_mode.monitor.PaceMakerReader")
    @patch("claude_usage.code_mode.monitor.UsageRenderer")
    def test_get_display_handles_none_langfuse_metrics_gracefully(
        self, mock_renderer_class, mock_reader_class
    ):
        """When get_langfuse_metrics() returns None, should pass None to renderer"""
        # Setup mock PaceMakerReader
        mock_reader = MagicMock()
        mock_reader.is_installed.return_value = True
        mock_reader.get_status.return_value = {
            "enabled": True,
            "has_data": True,
            "algorithm": "adaptive",
        }
        mock_reader.get_langfuse_status.return_value = False
        mock_reader.get_langfuse_metrics.return_value = None  # No metrics available
        mock_reader_class.return_value = mock_reader

        # Setup mock renderer
        mock_renderer = MagicMock()
        mock_renderer.render.return_value = MagicMock()
        mock_renderer.render_bottom_section.return_value = MagicMock()
        mock_renderer_class.return_value = mock_renderer

        # Create monitor and call get_display()
        monitor = CodeMonitor(self.credentials_path)
        monitor.get_display()

        # ASSERT: render_bottom_section() should receive langfuse_metrics=None
        # First verify the method was called
        mock_renderer.render_bottom_section.assert_called()

        # Now safely access call kwargs
        call_kwargs = mock_renderer.render_bottom_section.call_args.kwargs
        self.assertIn("langfuse_metrics", call_kwargs)
        self.assertIsNone(call_kwargs["langfuse_metrics"])


if __name__ == "__main__":
    unittest.main()
