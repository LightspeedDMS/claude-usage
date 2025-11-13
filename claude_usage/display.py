"""UI rendering for Claude Code usage monitor"""

from datetime import datetime
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn
from rich.text import Text
from rich.console import Group


class UsageRenderer:
    """Renders usage data using Rich library"""

    def render(
        self,
        error_message,
        last_usage,
        last_profile,
        last_overage,
        last_update,
        projection,
    ):
        """Generate rich display for current usage"""

        if error_message:
            return Panel(
                f"[red]⚠ {error_message}[/red]",
                title="Claude Code Usage",
                border_style="red",
            )

        if not last_usage:
            return Panel(
                "[yellow]Fetching usage data...[/yellow]",
                title="Claude Code Usage",
                border_style="yellow",
            )

        # Build display content
        content = []

        # Profile information (at top)
        if last_profile:
            self._render_profile(content, last_profile)

        # Five-hour limit
        if last_usage.get("five_hour"):
            self._render_five_hour_limit(content, last_usage["five_hour"])

        # Seven-day limit
        if last_usage.get("seven_day"):
            self._render_seven_day_limit(content, last_usage["seven_day"])

        # Overage credits
        if last_overage:
            # Get current utilization to check if in overage
            utilization = 0
            if last_usage and last_usage.get("five_hour"):
                utilization = last_usage["five_hour"].get("utilization", 0)

            self._render_overage(content, last_overage, projection, utilization)

        # Last update time
        if last_update:
            update_str = last_update.strftime("%H:%M:%S")
            content.append(Text(""))  # spacing
            content.append(Text(f"Updated: {update_str}", style="dim"))

        # Combine content
        display = Group(*content)

        return Panel(display, title="Claude Code Usage", border_style="green")

    def _render_profile(self, content, profile):
        """Render profile information"""
        account = profile.get("account", {})
        org = profile.get("organization", {})

        # Account badges
        badges = []
        org_type = org.get("organization_type", "")
        if org_type == "claude_enterprise":
            badges.append("[bold blue]ENTERPRISE[/bold blue]")
        if account.get("has_claude_pro"):
            badges.append("[bold magenta]PRO[/bold magenta]")
        if account.get("has_claude_max"):
            badges.append("[bold yellow]MAX[/bold yellow]")

        # User and org info
        display_name = account.get("display_name", "")
        email = account.get("email", "")
        org_name = org.get("name", "")
        rate_tier = org.get("rate_limit_tier", "")

        if display_name and email:
            content.append(Text(f"👤 {display_name} ({email})", style="bold cyan"))
        if org_name:
            org_text = f"🏢 {org_name}"
            if badges:
                org_text += " " + " ".join(badges)
            content.append(Text.from_markup(org_text))
        if rate_tier:
            content.append(Text(f"⚡ Tier: {rate_tier}", style="dim"))

        if content:
            content.append(Text(""))  # spacing

    def _render_five_hour_limit(self, content, five_hour):
        """Render five-hour limit display"""
        utilization = five_hour.get("utilization", 0)
        resets_at = five_hour.get("resets_at", "")

        # Determine color based on utilization
        if utilization >= 100:
            bar_style = "bold red"
        elif utilization >= 81:
            bar_style = "bold bright_yellow"  # Orange-ish
        elif utilization >= 51:
            bar_style = "bold yellow"
        else:
            bar_style = "bold green"

        # Progress bar
        progress = Progress(
            TextColumn("[bold]5-Hour Limit:[/bold]"),
            BarColumn(
                bar_width=20,
                complete_style=bar_style,
                finished_style=bar_style,
            ),
            TextColumn("[bold]{task.percentage:>3.0f}%[/bold]"),
        )
        _ = progress.add_task("usage", total=100, completed=utilization)

        content.append(progress)

        if resets_at:
            reset_time = datetime.fromisoformat(resets_at.replace("+00:00", ""))
            now = datetime.utcnow()
            time_until = reset_time - now

            hours = time_until.seconds // 3600
            minutes = (time_until.seconds % 3600) // 60

            content.append(Text(f"⏰ Resets in: {hours}h {minutes}m", style="cyan"))

    def _render_seven_day_limit(self, content, seven_day):
        """Render seven-day limit display"""
        utilization = seven_day.get("utilization", 0)

        progress = Progress(
            TextColumn("[bold]7-Day Limit:[/bold]"),
            BarColumn(bar_width=20),
            TextColumn("[bold]{task.percentage:>3.0f}%[/bold]"),
        )
        _ = progress.add_task("usage", total=100, completed=utilization)
        content.append(Text(""))  # spacing
        content.append(progress)

    def _render_overage(self, content, overage, projection, utilization):
        """Render overage and projection display"""
        used_credits = overage.get("used_credits", 0)
        monthly_limit = overage.get("monthly_credit_limit")

        if used_credits > 0 or monthly_limit:
            content.append(Text(""))  # spacing

            # Convert credits to dollars (1 credit = $0.01)
            used_dollars = used_credits / 100

            if monthly_limit:
                # Show progress bar if there's a limit
                limit_dollars = monthly_limit / 100
                progress = Progress(
                    TextColumn("[bold]Overage:[/bold]"),
                    BarColumn(bar_width=20),
                    TextColumn("[bold]${task.completed:.2f}/${task.total:.2f}[/bold]"),
                )
                _ = progress.add_task(
                    "overage", total=limit_dollars, completed=used_dollars
                )
                content.append(progress)
            else:
                # No limit, just show used dollars
                content.append(
                    Text(f"💳 Overage: ${used_dollars:.2f}", style="bold yellow")
                )

            # Projection display - only show when currently in overage (utilization >= 100)
            if projection and utilization >= 100:
                current_dollars = projection["current_credits"] / 100
                projected_dollars = projection["projected_credits"] / 100
                rate_dollars = projection["rate_per_hour"] / 100
                increase = projected_dollars - current_dollars

                content.append(
                    Text(
                        f"📊 Projected by reset: ${projected_dollars:.2f} (+${increase:.2f})",
                        style="cyan",
                    )
                )
                content.append(Text(f"📈 Rate: ${rate_dollars:.2f}/hour", style="dim"))


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
            mtd_content = self._render_mtd_section(mtd_data, projection)
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

    def _render_mtd_section(self, mtd_data, projection):
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
