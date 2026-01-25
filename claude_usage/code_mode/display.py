"""UI rendering for Code mode usage monitor"""

from datetime import datetime
from rich.progress import BarColumn, Progress, TextColumn
from rich.table import Table
from rich.text import Text
from rich.console import Group


class UsageRenderer:
    """Renders usage data using Rich library"""

    def render(
        self,
        error_message,
        last_usage,
        last_profile,
        last_update,
        pacemaker_status=None,
        weekly_limit_enabled=True,
    ):
        """Generate rich display for current usage"""

        if error_message:
            return Text(f"[red]⚠ {error_message}[/red]")

        if not last_usage:
            return Text("[yellow]Fetching usage data...[/yellow]")

        # Build display content
        content = []

        # Profile information (at top)
        if last_profile:
            self._render_profile(content, last_profile)

        # Five-hour limit
        if last_usage.get("five_hour"):
            five_hour_limit_enabled = True
            if pacemaker_status:
                five_hour_limit_enabled = pacemaker_status.get(
                    "five_hour_limit_enabled", True
                )
            self._render_five_hour_limit(
                content, last_usage["five_hour"], five_hour_limit_enabled
            )

        # Seven-day limit (always show if data available)
        if last_usage.get("seven_day"):
            self._render_seven_day_limit(
                content, last_usage["seven_day"], weekly_limit_enabled
            )

        # Model-specific 7-day limits (Sonnet, Opus) if available
        self._render_model_specific_limits(content, last_usage)

        # Pace-maker status (if available)
        if pacemaker_status:
            self._render_pacemaker(
                content, pacemaker_status, last_usage, weekly_limit_enabled
            )

        # Combine content (Updated time moved to bottom section)
        return Group(*content)

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

        # Strip "Organization" word entirely if present (Claude API sometimes includes it)
        if display_name:
            display_name = display_name.replace("Organization", "").strip()
        if org_name:
            # Remove "Organization" from anywhere in the string
            org_name = org_name.replace("Organization", "").strip()
            # If empty after removal, don't display
            if not org_name:
                org_name = ""

        if display_name and email:
            content.append(Text(f"👤 {display_name} ({email})", style="bold cyan"))
        if org_name:
            # Show org name on one line (no "Org:" label, just icon and name)
            content.append(Text(f"🏢 {org_name}", style="bold"))
            # Show plan badges on separate line if present
            if badges:
                content.append(Text.from_markup("   Plan: " + " ".join(badges)))
        if rate_tier:
            content.append(Text(f"⚡ Tier: {rate_tier}", style="dim"))

        if content:
            content.append(Text(""))  # spacing

    def _render_five_hour_limit(self, content, five_hour, five_hour_limit_enabled=True):
        """Render five-hour usage display

        Args:
            content: List to append rendered content to
            five_hour: Five-hour usage data
            five_hour_limit_enabled: Whether five-hour throttling is enabled (affects display note only)
        """
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
            TextColumn("[bold]5-Hour Usage:  [/bold]"),
            BarColumn(
                bar_width=14,
                complete_style=bar_style,
                finished_style=bar_style,
            ),
            TextColumn("[bold]{task.percentage:>3.0f}%[/bold]"),
        )
        _ = progress.add_task("usage", total=100, completed=utilization)

        content.append(progress)

        # 5-Hour limiter status (always shown, like other status indicators)
        if five_hour_limit_enabled:
            content.append(
                Text.from_markup("5-Hour Limiter: [green]enabled[/green]", style="dim")
            )
        else:
            content.append(
                Text.from_markup(
                    "5-Hour Limiter: [yellow]disabled[/yellow]", style="dim"
                )
            )

        if resets_at:
            reset_time = datetime.fromisoformat(resets_at.replace("+00:00", ""))
            now = datetime.utcnow()
            time_until = reset_time - now

            hours = time_until.seconds // 3600
            minutes = (time_until.seconds % 3600) // 60

            content.append(Text(f"⏰ Resets in: {hours}h {minutes}m", style="cyan"))

    def _render_seven_day_limit(self, content, seven_day, weekly_limit_enabled=True):
        """Render seven-day usage display

        Args:
            content: List to append rendered content to
            seven_day: Seven-day usage data
            weekly_limit_enabled: Whether weekly throttling is enabled (affects display note only)
        """
        utilization = seven_day.get("utilization", 0)
        resets_at = seven_day.get("resets_at", "")

        # Determine color based on utilization (same logic as 5-hour)
        if utilization >= 100:
            bar_style = "bold red"
        elif utilization >= 81:
            bar_style = "bold bright_yellow"  # Orange-ish
        elif utilization >= 51:
            bar_style = "bold yellow"
        else:
            bar_style = "bold green"

        # Progress bar (without throttling note in label)
        progress = Progress(
            TextColumn("[bold]7-Day Usage:   [/bold]"),
            BarColumn(
                bar_width=14,
                complete_style=bar_style,
                finished_style=bar_style,
            ),
            TextColumn("[bold]{task.percentage:>3.0f}%[/bold]"),
        )
        _ = progress.add_task("usage", total=100, completed=utilization)
        content.append(Text(""))  # spacing
        content.append(progress)

        # Throttling disabled note below progress bar
        if not weekly_limit_enabled:
            content.append(Text("(throttling disabled)", style="dim"))

        if resets_at:
            reset_time = datetime.fromisoformat(resets_at.replace("+00:00", ""))
            now = datetime.utcnow()
            time_until = reset_time - now

            # Calculate days, hours, and minutes
            days = time_until.days
            hours = time_until.seconds // 3600
            minutes = (time_until.seconds % 3600) // 60

            # Format the countdown message
            if days > 0:
                content.append(
                    Text(f"⏰ Resets in: {days}d {hours}h {minutes}m", style="cyan")
                )
            else:
                content.append(Text(f"⏰ Resets in: {hours}h {minutes}m", style="cyan"))

    def _render_model_specific_limits(self, content, usage_data):
        """Render model-specific 7-day usage limits (Sonnet, Opus) if available

        Args:
            content: List to append rendered content to
            usage_data: Usage data dict that may contain seven_day_sonnet and seven_day_opus
        """
        # Check and render Sonnet limit
        if usage_data.get("seven_day_sonnet"):
            self._render_model_limit(content, usage_data["seven_day_sonnet"], "Sonnet")

        # Check and render Opus limit
        if usage_data.get("seven_day_opus"):
            self._render_model_limit(content, usage_data["seven_day_opus"], "Opus")

    def _render_model_limit(self, content, model_data, model_name):
        """Render a single model-specific 7-day limit

        Args:
            content: List to append rendered content to
            model_data: Model-specific usage data (utilization, resets_at)
            model_name: Display name for the model (e.g., "Sonnet", "Opus")
        """
        utilization = model_data.get("utilization", 0)
        resets_at = model_data.get("resets_at", "")

        # Determine color based on utilization (same logic as other limits)
        if utilization >= 100:
            bar_style = "bold red"
        elif utilization >= 81:
            bar_style = "bold bright_yellow"
        elif utilization >= 51:
            bar_style = "bold yellow"
        else:
            bar_style = "bold green"

        # Create label padded to 15 chars for alignment
        # "7-Day Sonnet:" = 13 chars, "7-Day Opus:" = 11 chars
        label = f"7-Day {model_name}:"
        padding = " " * (15 - len(label))

        # Progress bar
        progress = Progress(
            TextColumn(f"[bold]{label}{padding}[/bold]"),
            BarColumn(
                bar_width=14,
                complete_style=bar_style,
                finished_style=bar_style,
            ),
            TextColumn("[bold]{task.percentage:>3.0f}%[/bold]"),
        )
        _ = progress.add_task("usage", total=100, completed=utilization)

        content.append(Text(""))  # spacing
        content.append(progress)

        if resets_at:
            reset_time = datetime.fromisoformat(resets_at.replace("+00:00", ""))
            now = datetime.utcnow()
            time_until = reset_time - now

            # Calculate days, hours, and minutes
            days = time_until.days
            hours = time_until.seconds // 3600
            minutes = (time_until.seconds % 3600) // 60

            # Format the countdown message
            if days > 0:
                content.append(
                    Text(f"⏰ Resets in: {days}d {hours}h {minutes}m", style="cyan")
                )
            else:
                content.append(Text(f"⏰ Resets in: {hours}h {minutes}m", style="cyan"))

    def _render_pacemaker(
        self, content, pm_status, last_usage, weekly_limit_enabled=True
    ):
        """Render pace-maker status and throttling information

        Args:
            content: List to append rendered content to
            pm_status: Pace-maker status from integration module
            last_usage: Fresh usage data from API (for fresh utilization)
            weekly_limit_enabled: Whether weekly limit is enabled
        """
        content.append(Text(""))  # spacing

        # Status header
        enabled = pm_status.get("enabled", False)
        has_data = pm_status.get("has_data", False)

        if not has_data:
            # Pace-maker installed but no data yet
            status_line = "🎯 Pace Maker: " + (
                "[bold green]ACTIVE[/bold green]" if enabled else "[dim]INACTIVE[/dim]"
            )
            content.append(Text.from_markup(status_line))
            content.append(Text("No usage data yet", style="dim"))
            return

        # Check for errors
        if "error" in pm_status:
            content.append(Text("🎯 Pace Maker: [yellow]ERROR[/yellow]", style="bold"))
            content.append(Text(f"{pm_status['error']}", style="dim"))
            return

        # Full status display
        should_throttle = pm_status.get("should_throttle", False)
        delay_seconds = pm_status.get("delay_seconds", 0)

        # Status line with badge
        if not enabled:
            status_badge = "[dim]INACTIVE[/dim]"
        elif should_throttle:
            status_badge = "[bold yellow]⚠️ THROTTLING[/bold yellow]"
        else:
            status_badge = "[bold green]✓ ON PACE[/bold green]"

        content.append(Text.from_markup(f"🎯 Pace Maker: {status_badge}"))

        # Get window data
        constrained = pm_status.get("constrained_window")
        if not constrained:
            content.append(Text("No active windows", style="dim"))
            return

        # Select which window to display (the constrained one)
        if constrained == "5-hour":
            window_data = pm_status.get("five_hour", {})
            window_label = "5-Hour"
        else:
            window_data = pm_status.get("seven_day", {})
            window_label = "7-Day"

        target = window_data.get("target", 0)

        # FIX 1: Calculate deviation from safe_allowance, not target
        # Use fresh utilization from last_usage, not stale pm_status
        actual_util = 0.0
        if last_usage:
            if constrained == "5-hour" and last_usage.get("five_hour"):
                actual_util = last_usage["five_hour"].get("utilization", 0)
            elif constrained == "7-day" and last_usage.get("seven_day"):
                actual_util = last_usage["seven_day"].get("utilization", 0)

        # Calculate safe_allowance = target × safety_buffer_pct
        # Default safety buffer is 95% (5% margin)
        safety_buffer_pct = 95.0  # TODO: Get from config if available
        safe_allowance = target * (safety_buffer_pct / 100.0)

        # Deviation = actual_util - safe_allowance (NOT target!)
        deviation = actual_util - safe_allowance

        # Target pace progress bar (pad label to align with other progress bars)
        # "5-Hour Target:" = 14 chars, "7-Day Target:" = 13 chars
        # Pad to 15 chars total to match other progress bars
        target_label = f"{window_label} Target:"
        padding = " " * (15 - len(target_label))
        target_progress = Progress(
            TextColumn(f"[bold]{target_label}{padding}[/bold]"),
            BarColumn(
                bar_width=14,
                complete_style="cyan",
                finished_style="cyan",
            ),
            TextColumn("[bold]{task.percentage:>3.0f}%[/bold]"),
        )
        _ = target_progress.add_task("target", total=100, completed=target)
        content.append(target_progress)

        # Deviation display
        if deviation < 0:
            # Under budget (good - using less than target)
            dev_style = "green"
            dev_text = "under budget"
        elif deviation <= 5:
            # Slightly over budget
            dev_style = "bright_yellow"
            dev_text = "over budget"
        else:
            # Significantly over budget
            dev_style = "red"
            dev_text = "over budget"

        content.append(
            Text.from_markup(
                f"Deviation: [{dev_style}]{deviation:+.1f}% ({dev_text})[/{dev_style}]"
            )
        )

        # Throttling info
        if should_throttle and delay_seconds > 0:
            content.append(
                Text(
                    f"⏱️  Next delay: {delay_seconds}s per tool use",
                    style="yellow",
                )
            )

        # Note: Status indicators (Algorithm, Tempo, Subagent, Intent Validation)
        # are now displayed in the two-column bottom section via render_bottom_section()

    def render_bottom_section(self, pacemaker_status, blockage_stats, last_update=None):
        """Render two-column bottom section with status and blockage stats.

        Args:
            pacemaker_status: Dict with pace-maker status info
            blockage_stats: Dict with human-readable blockage category labels and counts
            last_update: Optional datetime of last data update

        Returns:
            Rich renderable Group with two-column layout
        """
        # Layout constants
        status_col_width = 22
        status_separator = "-" * 18
        blockage_separator = "-" * 21  # 1 char longer than "Blockages (last hour)"
        count_width = 4

        # Create two-column table
        table = Table.grid(padding=(0, 2))
        table.add_column("status", width=status_col_width)
        table.add_column("blockage", ratio=1)

        # Build left column - Status indicators
        left_lines = []
        left_lines.append("[bold]Pacing Status[/bold]")
        left_lines.append(status_separator)

        # Algorithm status
        algorithm = pacemaker_status.get("algorithm", "unknown")
        enabled = pacemaker_status.get("enabled", False)
        if enabled:
            left_lines.append(f"Algorithm: [green]{algorithm}[/green]")
        else:
            left_lines.append("Algorithm: [dim]inactive[/dim]")

        # Tempo status
        tempo_enabled = pacemaker_status.get("tempo_enabled", True)
        if tempo_enabled:
            left_lines.append("Tempo: [green]on[/green]")
        else:
            left_lines.append("Tempo: [yellow]off[/yellow]")

        # Subagent status
        subagent_enabled = pacemaker_status.get("subagent_reminder_enabled", True)
        if subagent_enabled:
            left_lines.append("Subagent: [green]on[/green]")
        else:
            left_lines.append("Subagent: [dim]idle[/dim]")

        # Intent validation status
        intent_enabled = pacemaker_status.get("intent_validation_enabled", False)
        if intent_enabled:
            left_lines.append("Intent Val: [green]on[/green]")
        else:
            left_lines.append("Intent Val: [yellow]off[/yellow]")

        # Last update time (no blank line - compact layout)
        if last_update:
            update_str = last_update.strftime("%H:%M:%S")
            left_lines.append(f"[dim]Updated: {update_str}[/dim]")

        left_content = Text.from_markup("\n".join(left_lines))

        # Build right column - Blockage statistics
        right_lines = []
        right_lines.append("[bold]Blockages (last hour)[/bold]")
        right_lines.append(blockage_separator)

        if blockage_stats:
            # Get categories from stats (excluding Total)
            for category, count in blockage_stats.items():
                if category != "Total":
                    right_lines.append(f"{category}:{count:>{count_width}}")

            total = blockage_stats.get("Total", 0)
            right_lines.append(f"[bold]Total:{total:>{count_width}}[/bold]")
        else:
            right_lines.append("(unavailable)")

        right_content = Text.from_markup("\n".join(right_lines))

        # Add row to table
        table.add_row(left_content, right_content)

        return Group(table)
