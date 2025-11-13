"""Tests for ConsoleRenderer - MTD/YTD display with Rich UI"""

from datetime import datetime
from claude_usage.display import ConsoleRenderer
from rich.text import Text
from rich.panel import Panel
from rich.console import Group


class TestConsoleRendererHelpers:
    """Test helper formatting methods"""

    def test_format_tokens_handles_millions(self):
        """Format large token counts with M suffix"""
        renderer = ConsoleRenderer()

        result = renderer._format_tokens(1200000)

        assert result == "1.2M"

    def test_format_tokens_handles_thousands(self):
        """Format medium token counts with K suffix"""
        renderer = ConsoleRenderer()

        result = renderer._format_tokens(340000)

        assert result == "340K"

    def test_format_tokens_handles_small_numbers(self):
        """Format small token counts without suffix"""
        renderer = ConsoleRenderer()

        result = renderer._format_tokens(999)

        assert result == "999"

    def test_format_tokens_handles_zero(self):
        """Format zero tokens"""
        renderer = ConsoleRenderer()

        result = renderer._format_tokens(0)

        assert result == "0"

    def test_format_currency_formats_with_two_decimals(self):
        """Format currency with dollar sign and two decimals"""
        renderer = ConsoleRenderer()

        result = renderer._format_currency(123.456)

        assert result == "$123.46"

    def test_format_currency_handles_large_amounts(self):
        """Format large currency amounts with commas"""
        renderer = ConsoleRenderer()

        result = renderer._format_currency(1234.5)

        assert result == "$1,234.50"

    def test_format_currency_handles_zero(self):
        """Format zero currency"""
        renderer = ConsoleRenderer()

        result = renderer._format_currency(0)

        assert result == "$0.00"

    def test_get_color_style_green_for_low_utilization(self):
        """Return green for utilization < 50%"""
        renderer = ConsoleRenderer()

        result = renderer._get_color_style(30)

        assert result == "green"

    def test_get_color_style_yellow_for_medium_utilization(self):
        """Return yellow for utilization 50-80%"""
        renderer = ConsoleRenderer()

        result = renderer._get_color_style(65)

        assert result == "yellow"

    def test_get_color_style_bright_yellow_for_high_utilization(self):
        """Return bright_yellow for utilization 80-99%"""
        renderer = ConsoleRenderer()

        result = renderer._get_color_style(85)

        assert result == "bright_yellow"

    def test_get_color_style_red_for_overage(self):
        """Return red for utilization >= 100%"""
        renderer = ConsoleRenderer()

        result = renderer._get_color_style(105)

        assert result == "red"


class TestConsoleRendererOrganizationInfo:
    """Test organization info rendering"""

    def test_render_organization_info_returns_text_with_org_name(self):
        """Render organization name with building emoji"""
        renderer = ConsoleRenderer()
        org_data = {"name": "Acme Corp"}

        result = renderer._render_organization_info(org_data)

        # Should be a Text object with org name
        assert isinstance(result, Text)
        assert "Acme Corp" in str(result)


class TestConsoleRendererModelBreakdown:
    """Test model breakdown rendering"""

    def test_render_model_breakdown_formats_single_model(self):
        """Render a single model with cost and tokens"""
        renderer = ConsoleRenderer()
        models = {
            "claude-sonnet-4-5": {
                "input_tokens": 1200000,
                "output_tokens": 240000,
                "cost_usd": 67.89,
            }
        }

        result = renderer._render_model_breakdown(models, "MTD")

        # Should return list of Text objects
        assert isinstance(result, list)
        assert len(result) > 0
        # Check formatting includes model name, cost, and tokens
        result_str = str(result[0])
        assert "claude-sonnet-4-5" in result_str
        assert "67.89" in result_str


class TestConsoleRendererMTDSection:
    """Test MTD section rendering"""

    def test_render_mtd_with_limit_and_progress_bar(self):
        """Render MTD section with monthly limit showing progress bar"""
        renderer = ConsoleRenderer()
        mtd_data = {
            "period_label": "November 2025",
            "total_cost_usd": 123.45,
            "monthly_limit_usd": 1000.00,
            "by_model": {},
        }
        projection = None

        result = renderer._render_mtd_section(mtd_data, projection)

        # Should return a Group
        assert isinstance(result, Group)
        # Check renderables contain expected content
        renderables = list(result.renderables)
        assert len(renderables) >= 3  # header, cost, progress bar
        # First item should be header with period label
        header_str = str(renderables[0])
        assert "November 2025" in header_str
        # Should contain cost
        all_text = " ".join(str(r) for r in renderables)
        assert "123.45" in all_text
        # Should have a Progress bar (third element)
        from rich.progress import Progress

        assert isinstance(renderables[2], Progress)

    def test_render_mtd_without_limit_no_progress_bar(self):
        """Render MTD section without monthly limit - no progress bar"""
        renderer = ConsoleRenderer()
        mtd_data = {
            "period_label": "November 2025",
            "total_cost_usd": 123.45,
            "by_model": {},
        }
        projection = None

        result = renderer._render_mtd_section(mtd_data, projection)

        # Should return a Group
        assert isinstance(result, Group)
        renderables = list(result.renderables)
        # Should have header and cost, but no progress bar
        assert len(renderables) == 2
        # Verify no Progress object
        from rich.progress import Progress

        assert not any(isinstance(r, Progress) for r in renderables)

    def test_render_mtd_with_claude_code_data(self):
        """Render MTD section with claude_code data showing sessions and cost"""
        renderer = ConsoleRenderer()
        mtd_data = {
            "period_label": "November 2025",
            "total_cost_usd": 123.45,
            "by_model": {},
            "claude_code": {"sessions": 42, "cost_usd": 23.45},
        }
        projection = None

        result = renderer._render_mtd_section(mtd_data, projection)

        renderables = list(result.renderables)
        all_text = " ".join(str(r) for r in renderables)
        # Should contain Claude Code sessions and cost
        assert "Claude Code" in all_text
        assert "42" in all_text
        assert "23.45" in all_text

    def test_render_mtd_with_projection(self):
        """Render MTD section with projection showing EOM estimate"""
        renderer = ConsoleRenderer()
        mtd_data = {
            "period_label": "November 2025",
            "total_cost_usd": 123.45,
            "by_model": {},
        }
        projection = {"projected_eom_usd": 389.50, "rate_per_hour": 8.50}

        result = renderer._render_mtd_section(mtd_data, projection)

        renderables = list(result.renderables)
        all_text = " ".join(str(r) for r in renderables)
        # Should contain projection
        assert "Projected EOM" in all_text
        assert "389.50" in all_text
        assert "8.50" in all_text


class TestConsoleRendererYTDSection:
    """Test YTD section rendering"""

    def test_render_ytd_complete_data_with_models(self):
        """Render YTD section with complete data"""
        renderer = ConsoleRenderer()
        ytd_data = {
            "period_label": "2025",
            "total_cost_usd": 2456.78,
            "by_model": {
                "claude-sonnet-4-5": {
                    "input_tokens": 5000000,
                    "output_tokens": 1000000,
                    "cost_usd": 1200.00,
                }
            },
            "claude_code": {"sessions": 150, "cost_usd": 100.50},
        }

        result = renderer._render_ytd_section(ytd_data)

        # Should return a Group
        assert isinstance(result, Group)
        renderables = list(result.renderables)
        assert len(renderables) > 0
        # Should contain year in header
        all_text = " ".join(str(r) for r in renderables)
        assert "2025" in all_text
        assert "2,456.78" in all_text
        assert "claude-sonnet-4-5" in all_text
        assert "Claude Code" in all_text

    def test_render_ytd_without_claude_code(self):
        """Render YTD section without claude_code data"""
        renderer = ConsoleRenderer()
        ytd_data = {
            "period_label": "2025",
            "total_cost_usd": 1500.00,
            "by_model": {},
        }

        result = renderer._render_ytd_section(ytd_data)

        renderables = list(result.renderables)
        all_text = " ".join(str(r) for r in renderables)
        # Should NOT contain Claude Code mention
        assert "Claude Code" not in all_text
        # Should still have cost
        assert "1,500.00" in all_text


class TestConsoleRendererWorkspaces:
    """Test workspace rendering"""

    def test_render_workspaces_single_workspace(self):
        """Render a single workspace with spend and limit"""
        renderer = ConsoleRenderer()
        workspaces = [
            {
                "name": "Claude Code",
                "spend_usd": 123.45,
                "limit_usd": 1000.00,
                "utilization": 12.3,
            }
        ]

        result = renderer._render_workspaces(workspaces)

        # Should return list of Text objects
        assert isinstance(result, list)
        assert len(result) > 0
        # Check content
        all_text = " ".join(str(r) for r in result)
        assert "Claude Code" in all_text
        assert "123.45" in all_text
        assert "1,000.00" in all_text


class TestConsoleRendererMainRender:
    """Test main render method"""

    def test_render_returns_panel_with_all_data(self):
        """Main render method returns a Rich Panel"""
        renderer = ConsoleRenderer()
        org_data = {"name": "Acme Corp"}
        mtd_data = {
            "period_label": "November 2025",
            "total_cost_usd": 123.45,
            "monthly_limit_usd": 1000.00,
            "by_model": {},
        }
        ytd_data = {"period_label": "2025", "total_cost_usd": 500.00, "by_model": {}}
        workspaces = []
        last_update = datetime(2025, 11, 12, 10, 30, 0)
        projection = None

        result = renderer.render(
            org_data, mtd_data, ytd_data, workspaces, last_update, projection
        )

        # Should return a Panel
        assert isinstance(result, Panel)
