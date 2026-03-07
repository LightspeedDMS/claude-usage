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
                content.append(Text.from_markup("📦 Plan: " + " ".join(badges)))
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
                bar_width=26,
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

            if time_until.total_seconds() > 0:
                hours = time_until.seconds // 3600
                minutes = (time_until.seconds % 3600) // 60
                content.append(Text(f"⏰ Resets in: {hours}h {minutes}m", style="cyan"))
            else:
                content.append(Text("⏰ Window expired", style="cyan"))

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
                bar_width=26,
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
            content.append(
                Text.from_markup(
                    "7-Day Limiter: [yellow]disabled[/yellow]", style="dim"
                )
            )

        if resets_at:
            reset_time = datetime.fromisoformat(resets_at.replace("+00:00", ""))
            now = datetime.utcnow()
            time_until = reset_time - now

            if time_until.total_seconds() > 0:
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
                    content.append(
                        Text(f"⏰ Resets in: {hours}h {minutes}m", style="cyan")
                    )
            else:
                content.append(Text("⏰ Window expired", style="cyan"))

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
                bar_width=26,
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

            if time_until.total_seconds() > 0:
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
                    content.append(
                        Text(f"⏰ Resets in: {hours}h {minutes}m", style="cyan")
                    )
            else:
                content.append(Text("⏰ Window expired", style="cyan"))

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
            content.append(
                Text.from_markup("🎯 Pace Maker: [bold yellow]ERROR[/bold yellow]")
            )
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

        # Get window data — prefer constrained window, but always show
        # informational data even when limits are disabled
        constrained = pm_status.get("constrained_window")
        if constrained == "5-hour":
            window_data = pm_status.get("five_hour", {})
            window_label = "5-Hour"
        elif constrained == "7-day":
            window_data = pm_status.get("seven_day", {})
            window_label = "7-Day"
        else:
            # No constrained window (limits disabled) — pick best available
            # for informational display
            five_h = pm_status.get("five_hour", {})
            seven_d = pm_status.get("seven_day", {})
            if five_h.get("target", 0) > 0:
                window_data = five_h
                window_label = "5-Hour"
                constrained = "5-hour"
            elif seven_d.get("target", 0) > 0:
                window_data = seven_d
                window_label = "7-Day"
                constrained = "7-day"
            else:
                content.append(Text("No active windows", style="dim"))
                return

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
                bar_width=26,
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

    def _fmt_kv(self, label, value, markup_value, width):
        """Format a key-value pair with label left-aligned and value right-aligned.

        Args:
            label: Plain text label (e.g., "Algorithm:")
            value: Plain text value for width calculation (e.g., "legacy")
            markup_value: Rich markup value for display (e.g., "[green]legacy[/green]")
            width: Total column width to right-align value within

        Returns:
            Formatted string with label and right-aligned markup value
        """
        padding = width - len(label) - len(value)
        if padding < 1:
            padding = 1
        return f"{label}{' ' * padding}{markup_value}"

    def render_bottom_section(
        self,
        pacemaker_status,
        blockage_stats,
        last_update=None,
        langfuse_metrics=None,
        secrets_metrics=None,
    ):
        """Render two-column bottom section with status and blockage stats.

        Args:
            pacemaker_status: Dict with pace-maker status info
            blockage_stats: Dict with human-readable blockage category labels and counts
            last_update: Optional datetime of last data update
            langfuse_metrics: Optional dict with Langfuse metrics (sessions, traces, spans, total)
            secrets_metrics: Optional dict with secrets metrics (secrets_masked)

        Returns:
            Rich renderable Group with two-column layout
        """
        # Layout constants
        status_col_width = 22
        blockage_col_width = 21  # Matches blockage separator width
        status_separator = "-" * 18
        blockage_separator = "-" * 21  # 1 char longer than "Blockages (last hour)"
        langfuse_separator = "-" * 21  # Same width as blockage separator

        # Create two-column table
        table = Table.grid(padding=(0, 2))
        table.add_column("status", width=status_col_width)
        table.add_column("blockage", ratio=1)

        # Build left column - Status indicators
        left_lines = []
        left_lines.append("[bold]Pacing Status[/bold]")
        left_lines.append(status_separator)

        # Fallback mode indicator (only when active)
        if pacemaker_status.get("fallback_mode"):
            left_lines.append(
                self._fmt_kv(
                    "API:",
                    "fallback (est)",
                    "[yellow]fallback (est)[/yellow]",
                    status_col_width,
                )
            )

        # Algorithm status
        algorithm = pacemaker_status.get("algorithm", "unknown")
        enabled = pacemaker_status.get("enabled", False)
        if enabled:
            left_lines.append(
                self._fmt_kv(
                    "Algorithm:",
                    algorithm,
                    f"[green]{algorithm}[/green]",
                    status_col_width,
                )
            )
        else:
            left_lines.append(
                self._fmt_kv(
                    "Algorithm:", "inactive", "[dim]inactive[/dim]", status_col_width
                )
            )

        # Tempo status
        tempo_enabled = pacemaker_status.get("tempo_enabled", True)
        if tempo_enabled:
            left_lines.append(
                self._fmt_kv("Tempo:", "on", "[green]on[/green]", status_col_width)
            )
        else:
            left_lines.append(
                self._fmt_kv("Tempo:", "off", "[yellow]off[/yellow]", status_col_width)
            )

        # Subagent status
        subagent_enabled = pacemaker_status.get("subagent_reminder_enabled", True)
        if subagent_enabled:
            left_lines.append(
                self._fmt_kv("Subagent:", "on", "[green]on[/green]", status_col_width)
            )
        else:
            left_lines.append(
                self._fmt_kv("Subagent:", "idle", "[dim]idle[/dim]", status_col_width)
            )

        # Intent validation status
        intent_enabled = pacemaker_status.get("intent_validation_enabled", False)
        if intent_enabled:
            left_lines.append(
                self._fmt_kv("Intent Val:", "on", "[green]on[/green]", status_col_width)
            )
        else:
            left_lines.append(
                self._fmt_kv(
                    "Intent Val:", "off", "[yellow]off[/yellow]", status_col_width
                )
            )

        # Langfuse status
        langfuse_enabled = pacemaker_status.get("langfuse_enabled", False)
        if langfuse_enabled:
            left_lines.append(
                self._fmt_kv("Langfuse:", "on", "[green]on[/green]", status_col_width)
            )
            # Add connectivity status (indented - NOT reformatted)
            langfuse_conn = pacemaker_status.get("langfuse_connection", {})
            if langfuse_conn.get("connected"):
                left_lines.append("  [green]✓ Connected[/green]")
            else:
                msg = langfuse_conn.get("message", "Unknown error")
                left_lines.append(f"  [red]✗ {msg}[/red]")
        else:
            left_lines.append(
                self._fmt_kv(
                    "Langfuse:", "off", "[yellow]off[/yellow]", status_col_width
                )
            )

        # TDD status
        tdd_enabled = pacemaker_status.get("tdd_enabled", False)
        if tdd_enabled:
            left_lines.append(
                self._fmt_kv("TDD:", "on", "[green]on[/green]", status_col_width)
            )
        else:
            left_lines.append(
                self._fmt_kv("TDD:", "off", "[yellow]off[/yellow]", status_col_width)
            )

        # Model preference status
        preferred_model = pacemaker_status.get("preferred_subagent_model", "auto")
        if preferred_model == "auto":
            left_lines.append(
                self._fmt_kv("Model:", "auto", "[cyan]auto[/cyan]", status_col_width)
            )
        else:
            left_lines.append(
                self._fmt_kv(
                    "Model:",
                    preferred_model,
                    f"[green]{preferred_model}[/green]",
                    status_col_width,
                )
            )

        # Log level (0=CRITICAL, 1=ERROR, 2=WARNING, 3=INFO, 4=DEBUG)
        log_level = pacemaker_status.get("log_level", 2)
        log_level_names = {
            0: "CRITICAL",
            1: "ERROR",
            2: "WARNING",
            3: "INFO",
            4: "DEBUG",
        }
        log_level_name = log_level_names.get(log_level, f"L{log_level}")
        if log_level <= 2:
            left_lines.append(
                self._fmt_kv(
                    "Log:",
                    log_level_name,
                    f"[green]{log_level_name}[/green]",
                    status_col_width,
                )
            )
        elif log_level == 3:
            left_lines.append(
                self._fmt_kv(
                    "Log:",
                    log_level_name,
                    f"[yellow]{log_level_name}[/yellow]",
                    status_col_width,
                )
            )
        else:
            left_lines.append(
                self._fmt_kv(
                    "Log:",
                    log_level_name,
                    f"[red]{log_level_name}[/red]",
                    status_col_width,
                )
            )

        # Clean code rules count
        rules_count = pacemaker_status.get("clean_code_rules_count", 0)
        if rules_count > 0:
            left_lines.append(
                self._fmt_kv(
                    "Rules:",
                    str(rules_count),
                    f"[green]{rules_count}[/green]",
                    status_col_width,
                )
            )
        else:
            left_lines.append(
                self._fmt_kv("Rules:", "0", "[yellow]0[/yellow]", status_col_width)
            )

        # Version info
        pm_version = pacemaker_status.get("pacemaker_version", "unknown")
        uc_version = pacemaker_status.get("usage_console_version", "unknown")
        left_lines.append(
            self._fmt_kv(
                "PM:",
                f"v{pm_version}",
                f"[green]v{pm_version}[/green]",
                status_col_width,
            )
        )
        left_lines.append(
            self._fmt_kv(
                "UC:",
                f"v{uc_version}",
                f"[green]v{uc_version}[/green]",
                status_col_width,
            )
        )

        # Error count (24h)
        error_count = pacemaker_status.get("error_count_24h", 0)
        if error_count == -1:
            left_lines.append(
                self._fmt_kv(
                    "Errors 24h:",
                    "(log large)",
                    "[yellow](log large)[/yellow]",
                    status_col_width,
                )
            )
        elif error_count == 0:
            left_lines.append(
                self._fmt_kv(
                    "Errors 24h:",
                    str(error_count),
                    f"[green]{error_count}[/green]",
                    status_col_width,
                )
            )
        elif error_count <= 10:
            left_lines.append(
                self._fmt_kv(
                    "Errors 24h:",
                    str(error_count),
                    f"[yellow]{error_count}[/yellow]",
                    status_col_width,
                )
            )
        else:
            left_lines.append(
                self._fmt_kv(
                    "Errors 24h:",
                    str(error_count),
                    f"[red]{error_count}[/red]",
                    status_col_width,
                )
            )

        # Last update time (no blank line - compact layout)
        if last_update:
            update_str = last_update.strftime("%H:%M:%S")
            left_lines.append(
                self._fmt_kv(
                    "Updated:", update_str, f"[dim]{update_str}[/dim]", status_col_width
                )
            )

        left_content = Text.from_markup("\n".join(left_lines))

        # Build right column - Blockage statistics and Langfuse metrics
        right_lines = []
        right_lines.append("[bold]Blockages (last hour)[/bold]")
        right_lines.append(blockage_separator)

        if blockage_stats:
            # Get categories from stats (excluding Total)
            for category, count in blockage_stats.items():
                if category != "Total":
                    right_lines.append(
                        self._fmt_kv(
                            f"{category}:", str(count), str(count), blockage_col_width
                        )
                    )

            total = blockage_stats.get("Total", 0)
            right_lines.append(
                self._fmt_kv(
                    "Total:", str(total), f"[bold]{total}[/bold]", blockage_col_width
                )
            )
        else:
            right_lines.append("(unavailable)")

        # Add Langfuse metrics section
        right_lines.append("[bold]Langfuse (last 24hrs)[/bold]")
        right_lines.append(langfuse_separator)

        if langfuse_metrics is not None:
            # Display metrics with alignment
            sessions = langfuse_metrics.get("sessions", 0)
            traces = langfuse_metrics.get("traces", 0)
            spans = langfuse_metrics.get("spans", 0)
            total = langfuse_metrics.get("total", 0)

            right_lines.append(
                self._fmt_kv(
                    "Sessions:", str(sessions), str(sessions), blockage_col_width
                )
            )
            right_lines.append(
                self._fmt_kv("Traces:", str(traces), str(traces), blockage_col_width)
            )
            right_lines.append(
                self._fmt_kv("Spans:", str(spans), str(spans), blockage_col_width)
            )
            right_lines.append(
                self._fmt_kv(
                    "Total:", str(total), f"[bold]{total}[/bold]", blockage_col_width
                )
            )
        else:
            right_lines.append("(unavailable)")

        # Add Secrets metrics section
        secrets_separator = "-" * 21  # Same width as langfuse separator
        right_lines.append("[bold]Secrets (last 24hrs)[/bold]")
        right_lines.append(secrets_separator)

        if secrets_metrics is not None:
            # Display secrets masked count
            masked = secrets_metrics.get("secrets_masked", 0)
            right_lines.append(
                self._fmt_kv("Masked:", str(masked), str(masked), blockage_col_width)
            )
            # Display stored secrets count
            stored = secrets_metrics.get("secrets_stored", 0)
            right_lines.append(
                self._fmt_kv("Stored:", str(stored), str(stored), blockage_col_width)
            )
        else:
            right_lines.append("(unavailable)")

        right_content = Text.from_markup("\n".join(right_lines))

        # Add row to table
        table.add_row(left_content, right_content)

        return Group(table)
