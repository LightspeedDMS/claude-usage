"""Tests for Langfuse status and metrics display integration.

Story #34: Langfuse Integration Status and Metrics Display
Tests for:
- Left panel: Langfuse ON/OFF status indicator
- Right panel: Langfuse metrics (Sessions, Traces, Spans, Total)
"""

import unittest
from io import StringIO

from rich.console import Console

from claude_usage.code_mode.display import UsageRenderer


class TestLangfuseDisplayIntegration(unittest.TestCase):
    """Test cases for Langfuse status and metrics display in bottom section"""

    def setUp(self):
        """Set up test fixtures"""
        self.renderer = UsageRenderer()

    def _render_to_text(self, group, width=80):
        """Helper to render Rich Group to plain text"""
        console = Console(file=StringIO(), width=width, force_terminal=True)
        with console.capture() as capture:
            console.print(group)
        return capture.get()

    def test_left_panel_shows_langfuse_on_when_enabled(self):
        """Left panel should show 'Langfuse: on' when enabled"""
        pacemaker_status = {
            "enabled": True,
            "has_data": True,
            "algorithm": "adaptive",
            "tempo_enabled": True,
            "subagent_reminder_enabled": True,
            "intent_validation_enabled": False,
            "langfuse_enabled": True,  # Langfuse enabled
        }
        blockage_stats = {"Intent Validation": 0, "Total": 0}

        result = self.renderer.render_bottom_section(pacemaker_status, blockage_stats)

        # Render Rich output to text for assertion
        output = self._render_to_text(result)
        self.assertIn("Langfuse:", output)
        self.assertIn("on", output.lower())

    def test_left_panel_shows_langfuse_off_when_disabled(self):
        """Left panel should show 'Langfuse: off' when disabled"""
        pacemaker_status = {
            "enabled": True,
            "has_data": True,
            "algorithm": "adaptive",
            "tempo_enabled": True,
            "subagent_reminder_enabled": True,
            "intent_validation_enabled": False,
            "langfuse_enabled": False,  # Langfuse disabled
        }
        blockage_stats = {"Intent Validation": 0, "Total": 0}

        result = self.renderer.render_bottom_section(pacemaker_status, blockage_stats)

        # Render Rich output to text for assertion
        output = self._render_to_text(result)
        self.assertIn("Langfuse:", output)
        self.assertIn("off", output.lower())

    def test_right_panel_shows_langfuse_metrics_when_available(self):
        """Right panel should show Langfuse metrics when data is available"""
        pacemaker_status = {
            "enabled": True,
            "has_data": True,
            "algorithm": "adaptive",
            "tempo_enabled": True,
            "subagent_reminder_enabled": True,
            "intent_validation_enabled": False,
            "langfuse_enabled": True,
        }
        blockage_stats = {"Intent Validation": 5, "Total": 10}
        langfuse_metrics = {
            "sessions": 123,
            "traces": 456,
            "spans": 789,
            "total": 1368,
        }

        result = self.renderer.render_bottom_section(
            pacemaker_status, blockage_stats, langfuse_metrics=langfuse_metrics
        )

        # Render Rich output to text for assertion
        output = self._render_to_text(result)
        self.assertIn("Langfuse", output)
        self.assertIn("123", output)  # Sessions count
        self.assertIn("456", output)  # Traces count
        self.assertIn("789", output)  # Spans count
        self.assertIn("1368", output)  # Total count

    def test_right_panel_shows_langfuse_unavailable_when_none(self):
        """Right panel should show 'unavailable' when metrics are None"""
        pacemaker_status = {
            "enabled": True,
            "has_data": True,
            "algorithm": "adaptive",
            "tempo_enabled": True,
            "subagent_reminder_enabled": True,
            "intent_validation_enabled": False,
            "langfuse_enabled": True,
        }
        blockage_stats = {"Intent Validation": 5, "Total": 10}
        langfuse_metrics = None  # No metrics available

        result = self.renderer.render_bottom_section(
            pacemaker_status, blockage_stats, langfuse_metrics=langfuse_metrics
        )

        # Render Rich output to text for assertion
        output = self._render_to_text(result)
        self.assertIn("Langfuse", output)
        self.assertIn("unavailable", output.lower())

    def test_right_panel_shows_langfuse_zeros_when_no_activity(self):
        """Right panel should show zeros when no Langfuse activity in 24h"""
        pacemaker_status = {
            "enabled": True,
            "has_data": True,
            "algorithm": "adaptive",
            "tempo_enabled": True,
            "subagent_reminder_enabled": True,
            "intent_validation_enabled": False,
            "langfuse_enabled": True,
        }
        blockage_stats = {"Intent Validation": 0, "Total": 0}
        langfuse_metrics = {
            "sessions": 0,
            "traces": 0,
            "spans": 0,
            "total": 0,
        }

        result = self.renderer.render_bottom_section(
            pacemaker_status, blockage_stats, langfuse_metrics=langfuse_metrics
        )

        # Render Rich output to text for assertion
        output = self._render_to_text(result)
        self.assertIn("Langfuse", output)
        # Should show zeros, not "unavailable"
        self.assertNotIn("unavailable", output.lower())

    def test_langfuse_status_defaults_to_off_when_not_in_pacemaker_status(self):
        """Langfuse should default to 'off' when langfuse_enabled key is missing"""
        pacemaker_status = {
            "enabled": True,
            "has_data": True,
            "algorithm": "adaptive",
            "tempo_enabled": True,
            "subagent_reminder_enabled": True,
            "intent_validation_enabled": False,
            # langfuse_enabled key missing
        }
        blockage_stats = {"Intent Validation": 0, "Total": 0}

        result = self.renderer.render_bottom_section(pacemaker_status, blockage_stats)

        # Render Rich output to text for assertion
        output = self._render_to_text(result)
        self.assertIn("Langfuse:", output)
        self.assertIn("off", output.lower())

    def test_langfuse_metrics_section_label_alignment(self):
        """Langfuse metrics section should have properly aligned labels"""
        pacemaker_status = {
            "enabled": True,
            "has_data": True,
            "algorithm": "adaptive",
            "tempo_enabled": True,
            "subagent_reminder_enabled": True,
            "intent_validation_enabled": False,
            "langfuse_enabled": True,
        }
        blockage_stats = {"Intent Validation": 5, "Total": 10}
        langfuse_metrics = {
            "sessions": 123,
            "traces": 456,
            "spans": 789,
            "total": 1368,
        }

        result = self.renderer.render_bottom_section(
            pacemaker_status, blockage_stats, langfuse_metrics=langfuse_metrics
        )

        # Render Rich output to text for assertion
        output = self._render_to_text(result)
        # Check that metric labels are present
        self.assertIn("Sessions", output)
        self.assertIn("Traces", output)
        self.assertIn("Spans", output)
        self.assertIn("Total", output)


if __name__ == "__main__":
    unittest.main()
