"""Tests for display module"""

import unittest
from unittest.mock import patch, MagicMock
from claude_usage.display import UsageRenderer


class TestUsageRenderer(unittest.TestCase):
    """Test cases for UsageRenderer class"""

    def setUp(self):
        """Set up test fixtures"""
        self.renderer = UsageRenderer()

    def test_render_five_hour_limit_bar_column_style_parameters(self):
        """Test that BarColumn uses correct style parameters for progress bar

        The BarColumn should NOT set the 'style' parameter (which colors the
        incomplete portion) or should set it to a neutral color. Only
        complete_style and finished_style should be set to the bar_style
        (green/yellow/red) so that only the filled portion is colored.

        This ensures that:
        - 2% utilization shows small colored bar with remaining space neutral/dim
        - 50% utilization shows half colored bar with half remaining neutral
        - 100% utilization shows full colored bar
        """
        # Mock the Progress class to capture BarColumn initialization
        with patch("claude_usage.code_mode.display.Progress") as mock_progress_class:
            # Create a mock Progress instance
            mock_progress = MagicMock()
            mock_progress_class.return_value = mock_progress

            # Mock the add_task method to return a task ID
            mock_progress.add_task.return_value = 1

            # Test data with low utilization (2%)
            five_hour_data = {
                "utilization": 2,
                "resets_at": "2025-11-12T23:00:00+00:00",
            }

            content = []

            # Call the method that creates the progress bar
            self.renderer._render_five_hour_limit(content, five_hour_data)

            # Verify Progress was called
            self.assertTrue(mock_progress_class.called)

            # Get the BarColumn from the call arguments
            call_args = mock_progress_class.call_args
            columns = call_args[0] if call_args[0] else []

            # Find the BarColumn in the columns
            bar_column = None
            for col in columns:
                if col.__class__.__name__ == "BarColumn":
                    bar_column = col
                    break

            self.assertIsNotNone(bar_column, "BarColumn should be present in Progress")

            # The critical assertion: BarColumn should NOT have style parameter
            # set to the bar_style (green/yellow/red), or it should be None/neutral
            # We check the BarColumn's __dict__ or constructor parameters

            # Since we're mocking, we need to inspect the actual call
            # Let's verify the BarColumn initialization parameters
            bar_column_init_kwargs = {}
            for col in columns:
                if hasattr(col, "__class__") and col.__class__.__name__ == "BarColumn":
                    # Check if the column has a style attribute that's not neutral
                    if hasattr(col, "style"):
                        bar_column_init_kwargs["style"] = col.style
                    if hasattr(col, "complete_style"):
                        bar_column_init_kwargs["complete_style"] = col.complete_style
                    if hasattr(col, "finished_style"):
                        bar_column_init_kwargs["finished_style"] = col.finished_style

            # The test should FAIL initially because style=bar_style is set
            # After fix, style should be None, 'bar.back', or not set
            # This test verifies the bug exists
            if "style" in bar_column_init_kwargs:
                style_value = bar_column_init_kwargs.get("style")
                # Style should be None, 'bar.back', 'bar.complete', or similar neutral color
                # NOT 'bold green', 'bold yellow', 'bold bright_yellow', or 'bold red'
                self.assertNotIn(
                    style_value,
                    ["bold green", "bold yellow", "bold bright_yellow", "bold red"],
                    "BarColumn style parameter should not be set to bar_style colors. "
                    "This causes the entire bar to appear filled even at low utilization.",
                )

    def test_render_five_hour_limit_different_utilization_levels(self):
        """Test that different utilization levels produce appropriate bar styles

        Verify that:
        - Low utilization (< 51%) uses green
        - Medium utilization (51-80%) uses yellow
        - High utilization (81-99%) uses bright yellow
        - Full utilization (>= 100%) uses red
        """
        test_cases = [
            (2, "bold green"),
            (50, "bold green"),
            (51, "bold yellow"),
            (80, "bold yellow"),
            (81, "bold bright_yellow"),
            (99, "bold bright_yellow"),
            (100, "bold red"),
            (150, "bold red"),
        ]

        for utilization, expected_style in test_cases:
            with self.subTest(utilization=utilization):
                with patch("claude_usage.code_mode.display.Progress") as mock_progress_class:
                    mock_progress = MagicMock()
                    mock_progress_class.return_value = mock_progress
                    mock_progress.add_task.return_value = 1

                    five_hour_data = {
                        "utilization": utilization,
                        "resets_at": "2025-11-12T23:00:00+00:00",
                    }

                    content = []
                    self.renderer._render_five_hour_limit(content, five_hour_data)

                    # Verify the correct color style is being used for complete_style
                    # and finished_style (not for style parameter)
                    call_args = mock_progress_class.call_args
                    columns = call_args[0] if call_args[0] else []

                    # Find BarColumn and verify complete_style matches expected
                    for col in columns:
                        if (
                            hasattr(col, "__class__")
                            and col.__class__.__name__ == "BarColumn"
                        ):
                            if hasattr(col, "complete_style"):
                                self.assertEqual(
                                    col.complete_style,
                                    expected_style,
                                    f"At {utilization}% utilization, complete_style should be {expected_style}",
                                )
                            if hasattr(col, "finished_style"):
                                self.assertEqual(
                                    col.finished_style,
                                    expected_style,
                                    f"At {utilization}% utilization, finished_style should be {expected_style}",
                                )

    def test_render_five_hour_limit_creates_progress_bar(self):
        """Test that _render_five_hour_limit creates a progress bar with correct values"""
        five_hour_data = {"utilization": 75, "resets_at": "2025-11-12T23:00:00+00:00"}

        content = []
        self.renderer._render_five_hour_limit(content, five_hour_data)

        # Verify a Progress object was added to content
        self.assertEqual(len(content), 2)  # Progress bar + reset time text

        # First item should be a Progress instance
        from rich.progress import Progress

        self.assertIsInstance(content[0], Progress)


if __name__ == "__main__":
    unittest.main()
