"""UI rendering for Console mode usage monitor"""

from rich.panel import Panel
from rich.text import Text
from rich.console import Group


class ConsoleRenderer:
    """Renders Console API usage data with MTD display"""

    def render(
        self,
        org_data,
        mtd_data,
        workspaces,
        last_update,
        projection,
        error=None,
    ):
        """Generate rich display for Console API usage"""
        content = []

        # Organization info
        if org_data:
            org_text = self._render_organization_info(org_data)
            content.append(org_text)

        # MTD section - ONLY current user's Claude Code usage
        if mtd_data and not error:
            content.append(Text(""))
            mtd_content = self._render_mtd_section(mtd_data, projection, last_update)
            content.append(mtd_content)

        # Show errors prominently
        if error:
            content.append(Text(""))
            content.append(Text(f"⚠️  {error}", style="bold red"))
            content.append(Text(""))

        # Show loading message if no content yet
        if not content:
            content.append(Text("Loading...", style="dim"))

        # Combine content
        display = Group(*content)
        border_color = "red" if error else "green"
        return Panel(display, title="Console Usage", border_style=border_color)

    def _format_tokens(self, count):
        """Format token count with K/M suffix"""
        if count >= 1_000_000:
            return f"{count / 1_000_000:.1f}M"
        elif count >= 1_000:
            return f"{int(count / 1_000)}K"
        return str(count)

    def _format_currency(self, amount):
        """Format currency with dollar sign and two decimals"""
        return f"${amount:,.2f}"

    def _get_color_style(self, utilization):
        """Get color style based on utilization percentage"""
        if utilization < 50:
            return "green"
        elif utilization < 80:
            return "yellow"
        elif utilization < 100:
            return "bright_yellow"
        return "red"

    def _render_organization_info(self, org_data):
        """Render organization information"""
        org_name = org_data.get("name", "")
        return Text(f"🏢 {org_name}")

    def _render_model_breakdown(self, models, period):
        """Render per-model cost and token breakdown"""
        result = []
        for model_name, data in models.items():
            cost = data.get("cost_usd", 0)
            input_tokens = data.get("input_tokens", 0)
            output_tokens = data.get("output_tokens", 0)

            # Format: "• model-name    $X.XX  (Xin / Xout)"
            cost_str = self._format_currency(cost)
            input_str = self._format_tokens(input_tokens)
            output_str = self._format_tokens(output_tokens)

            line = Text(
                f"• {model_name}    {cost_str}  ({input_str} in / {output_str} out)"
            )
            result.append(line)

        return result

    def _render_mtd_section(self, mtd_data, projection, last_update=None):
        """Render month-to-date section showing ONLY current user's Claude Code usage"""
        content = []

        # Section header with period label
        period_label = mtd_data.get("period_label", "")
        content.append(Text(f"═══ Month-to-Date ({period_label}) ═══", style="bold"))

        # Show ONLY current user's Claude Code cost
        claude_code_user_cost = mtd_data.get("claude_code_user_cost_usd")
        current_user_email = mtd_data.get("current_user_email")

        if claude_code_user_cost is not None and current_user_email:
            # Show current user's cost prominently
            content.append(
                Text(
                    f"Your Claude Code Usage: {self._format_currency(claude_code_user_cost)}",
                    style="bold cyan",
                )
            )
            content.append(Text(f"({current_user_email})", style="dim"))
        else:
            # Error case - couldn't identify user
            content.append(
                Text(
                    "Could not identify current user for usage tracking",
                    style="yellow",
                )
            )

        # Add projection display (after current cost, before last update timestamp)
        if projection and projection.get("projected_cost"):
            content.append(Text(""))  # spacing

            current = projection["current_cost"]
            projected = projection["projected_cost"]
            rate = projection["rate_per_hour"]
            increase = projected - current

            content.append(
                Text(
                    f"Projected by end of month: {self._format_currency(projected)} "
                    f"(+{self._format_currency(increase)})",
                    style="cyan",
                )
            )
            content.append(
                Text(f"Rate: {self._format_currency(rate)}/hour", style="dim")
            )

        # Last update timestamp
        if last_update:
            update_str = last_update.strftime("%H:%M:%S")
            content.append(Text(""))  # spacing
            content.append(Text(f"Updated: {update_str}", style="dim"))

        return Group(*content)

    def _render_workspaces(self, workspaces):
        """Render workspace spend and limits with progress bars"""
        result = []
        result.append(Text("Workspaces:", style="bold"))

        for workspace in workspaces:
            name = workspace.get("name", "")
            spend = workspace.get("spend_usd", 0)
            limit = workspace.get("limit_usd")

            spend_str = self._format_currency(spend)
            if limit:
                limit_str = self._format_currency(limit)
                result.append(Text(f"• {name}    {spend_str} / {limit_str}"))
            else:
                result.append(Text(f"• {name}    {spend_str}"))

        return result
