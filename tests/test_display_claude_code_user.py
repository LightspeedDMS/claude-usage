"""Tests for per-user Claude Code display in ConsoleRenderer"""

import unittest
from claude_usage.display import ConsoleRenderer


class TestConsoleRendererUserClaudeCode(unittest.TestCase):
    """Test cases for per-user Claude Code rendering"""

    def test_render_mtd_with_user_claude_code_cost(self):
        """Test MTD section renders per-user Claude Code cost"""
        renderer = ConsoleRenderer()

        mtd_data = {
            "total_cost_usd": 1000.0,
            "period_label": "Nov 1-12",
            "claude_code_user_cost_usd": 50.25,
            "current_user_email": "test@example.com",
        }

        result = renderer._render_mtd_section(mtd_data, projection=None)

        # Convert renderables to strings and check content
        from rich.console import Group

        self.assertIsInstance(result, Group)
        renderables = list(result.renderables)
        all_text = " ".join(str(r) for r in renderables)

        # Verify per-user Claude Code cost is displayed
        self.assertIn("Your Claude Code Usage", all_text)
        self.assertIn("50.25", all_text)

    def test_render_mtd_without_org_wide_label(self):
        """Test MTD section does not show 'Organization-Wide' label"""
        renderer = ConsoleRenderer()

        mtd_data = {
            "total_cost_usd": 1000.0,
            "period_label": "Nov 1-12",
            "claude_code_user_cost_usd": 50.25,
            "current_user_email": "test@example.com",
        }

        result = renderer._render_mtd_section(mtd_data, projection=None)
        result_str = str(result)

        # Verify organization-wide label is NOT present
        self.assertNotIn("Organization-Wide", result_str)
        self.assertNotIn("Shows all organization usage", result_str)

    def test_render_mtd_without_user_claude_code_shows_nothing(self):
        """Test MTD section without user Claude Code data shows no Claude Code line"""
        renderer = ConsoleRenderer()

        mtd_data = {
            "total_cost_usd": 1000.0,
            "period_label": "Nov 1-12",
        }

        result = renderer._render_mtd_section(mtd_data, projection=None)
        result_str = str(result)

        # Verify no Claude Code line when data not available
        self.assertNotIn("Claude Code", result_str)

    def test_render_mtd_legacy_claude_code_fallback(self):
        """Test MTD section falls back to legacy Claude Code data if new data unavailable"""
        renderer = ConsoleRenderer()

        mtd_data = {
            "total_cost_usd": 1000.0,
            "period_label": "Nov 1-12",
            "claude_code": {"sessions": 10, "cost_usd": 75.0},
        }

        result = renderer._render_mtd_section(mtd_data, projection=None)

        # Convert renderables to strings and check content
        from rich.console import Group

        self.assertIsInstance(result, Group)
        renderables = list(result.renderables)
        all_text = " ".join(str(r) for r in renderables)

        # Verify legacy Claude Code format is shown
        self.assertIn("Claude Code", all_text)
        self.assertIn("10 sessions", all_text)
        self.assertIn("75.00", all_text)
        self.assertNotIn("Your Claude Code Usage", all_text)

    def test_render_mtd_user_zero_cost_shows_value(self):
        """Test MTD section shows $0.00 for user with no Claude Code usage"""
        renderer = ConsoleRenderer()

        mtd_data = {
            "total_cost_usd": 1000.0,
            "period_label": "Nov 1-12",
            "claude_code_user_cost_usd": 0.0,
            "current_user_email": "test@example.com",
        }

        result = renderer._render_mtd_section(mtd_data, projection=None)

        # Convert renderables to strings and check content
        from rich.console import Group

        self.assertIsInstance(result, Group)
        renderables = list(result.renderables)
        all_text = " ".join(str(r) for r in renderables)

        # Verify $0.00 is displayed for user
        self.assertIn("Your Claude Code Usage", all_text)
        self.assertIn("$0.00", all_text)


if __name__ == "__main__":
    unittest.main()
