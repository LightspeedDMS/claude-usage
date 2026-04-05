"""UI rendering for Code mode usage monitor"""

import re
import textwrap
import time
from datetime import datetime, timezone
from rich.progress import BarColumn, Progress, TextColumn
from rich.table import Table
from rich.text import Text
from rich.console import Group


# Codex usage color thresholds (used_percent > threshold → that color)
CODEX_RED_THRESHOLD = 95  # >95% → red
CODEX_ORANGE_THRESHOLD = 75  # >75% → orange
CODEX_YELLOW_THRESHOLD = 50  # >50% → yellow
COLOR_ORANGE = "#ff8c00"  # Rich markup color for orange tier

# Reviewer identity tags for governance event feed display
REVIEWER_TAGS = {
    "codex-gpt5": ("[Codex]", "yellow"),
    "anthropic-sdk": ("[SDK]", "green"),
    "gemini": ("[Gem]", "cyan"),
}
_REVIEWER_TAG_RE = re.compile(r"\[REVIEWER:([^\]]+)\]")


def _md_to_rich(text):
    """Convert basic markdown formatting to Rich markup for event feed."""
    # Escape literal brackets so Rich doesn't misinterpret them
    text = text.replace("[", "\\[")
    # Bold: **text** → [bold]text[/bold]
    text = re.sub(r"\*\*(.+?)\*\*", r"[bold]\1[/bold]", text)
    # Inline code: `text` → [cyan]text[/cyan]
    text = re.sub(r"`([^`]+)`", r"[cyan]\1[/cyan]", text)
    return text


def _format_feedback_lines(feedback, wrap_width):
    """Wrap feedback text and apply markdown-to-Rich-markup styling."""
    if not feedback:
        return []
    if wrap_width < 10:
        wrap_width = 10

    lines = []
    in_code_block = False

    for raw_line in feedback.split("\n"):
        stripped = raw_line.strip()

        # Toggle code fence blocks
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue

        if in_code_block:
            escaped = stripped.replace("[", "\\[")
            lines.append(f"  [dim cyan]{escaped}[/dim cyan]")
            continue

        # Bullet points
        if stripped.startswith("- "):
            wrapped = textwrap.wrap(stripped[2:], width=wrap_width - 4)
            if wrapped:
                lines.append(f"  [dim]•[/dim] {_md_to_rich(wrapped[0])}")
                for cont in wrapped[1:]:
                    lines.append(f"    {_md_to_rich(cont)}")
            continue

        # Regular text with markdown conversion
        if not stripped:
            continue
        wrapped = textwrap.wrap(stripped, width=wrap_width - 2)
        for w in wrapped:
            lines.append(f"  {_md_to_rich(w)}")

    return lines


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
        activity_events=None,
    ):
        """Generate rich display for current usage"""

        if not last_usage and not error_message:
            return Text("[yellow]Fetching usage data...[/yellow]")

        # Build display content
        content = []

        if error_message:
            content.append(Text.from_markup(f"[red]△ {error_message}[/red]"))

        # Profile information (at top)
        if last_profile:
            self._render_profile(content, last_profile)

        # Activity line right below profile (Plan/Tier)
        if activity_events is not None:
            try:
                activity_line = render_activity_line(activity_events)
                content.append(activity_line)
            except Exception as e:
                import logging

                logging.debug("Activity line render failed: %s", e)

        if not last_usage:
            return Group(*content) if content else Text("")

        # Five-hour limit
        if last_usage.get("five_hour"):
            five_hour_limit_enabled = True
            if pacemaker_status:
                five_hour_limit_enabled = pacemaker_status.get(
                    "five_hour_limit_enabled", True
                )
            self._render_five_hour_limit(
                content,
                last_usage["five_hour"],
                five_hour_limit_enabled,
                pacemaker_status,
            )

        # Seven-day limit (always show if data available)
        if last_usage.get("seven_day"):
            self._render_seven_day_limit(
                content, last_usage["seven_day"], weekly_limit_enabled, pacemaker_status
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
        raw_badges = []
        org_type = org.get("organization_type", "")
        if org_type == "claude_enterprise":
            badges.append("[bold blue]ENTERPRISE[/bold blue]")
            raw_badges.append("ENTERPRISE")
        if account.get("has_claude_pro"):
            badges.append("[bold magenta]PRO[/bold magenta]")
            raw_badges.append("PRO")
        if account.get("has_claude_max"):
            badges.append("[bold yellow]MAX[/bold yellow]")
            raw_badges.append("MAX")

        # User and org info
        display_name = account.get("display_name", "")
        email = account.get("email", "")
        org_name = org.get("name", "")
        rate_tier = org.get("rate_limit_tier", "")
        _KNOWN_TIERS = {"default_claude_max_5x": "5x", "default_claude_max_20x": "20x"}
        rate_tier = _KNOWN_TIERS.get(rate_tier, rate_tier)

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
        if raw_badges or rate_tier:
            content.append(render_collapsed_plan_tier_line(raw_badges, rate_tier))

        if content:
            content.append(Text(""))  # spacing

    def _render_five_hour_limit(
        self, content, five_hour, five_hour_limit_enabled=True, pacemaker_status=None
    ):
        """Render five-hour usage display

        Args:
            content: List to append rendered content to
            five_hour: Five-hour usage data
            five_hour_limit_enabled: Whether five-hour throttling is enabled (affects display note only)
            pacemaker_status: Optional pace-maker status dict (for coefficient display)
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
        coeffs = ""
        if pacemaker_status:
            c5h = pacemaker_status.get("coefficients_5h")
            if c5h:
                overridden_5x = pacemaker_status.get(
                    "coefficients_5x_overridden", False
                )
                overridden_20x = pacemaker_status.get(
                    "coefficients_20x_overridden", False
                )
                val_5x = (
                    f"[green]{c5h['5x']:.4f}[/green]"
                    if overridden_5x
                    else f"{c5h['5x']:.4f}"
                )
                val_20x = (
                    f"[green]{c5h['20x']:.4f}[/green]"
                    if overridden_20x
                    else f"{c5h['20x']:.4f}"
                )
                coeffs = f" (5x:{val_5x} 20x:{val_20x})"
        if five_hour_limit_enabled:
            content.append(
                Text.from_markup(
                    f"5-Hour Limiter: [green]enabled[/green]{coeffs}", style="dim"
                )
            )
        else:
            content.append(
                Text.from_markup(
                    f"5-Hour Limiter: [yellow]disabled[/yellow]{coeffs}", style="dim"
                )
            )

        if resets_at:
            reset_time = datetime.fromisoformat(resets_at)
            now = datetime.now(timezone.utc)
            time_until = reset_time - now

            if time_until.total_seconds() > 0:
                hours = time_until.seconds // 3600
                minutes = (time_until.seconds % 3600) // 60
                content.append(Text(f"⏰ Resets in: {hours}h {minutes}m", style="cyan"))
            else:
                content.append(Text("⏰ Window expired", style="cyan"))

    def _render_seven_day_limit(
        self, content, seven_day, weekly_limit_enabled=True, pacemaker_status=None
    ):
        """Render seven-day usage display

        Args:
            content: List to append rendered content to
            seven_day: Seven-day usage data
            weekly_limit_enabled: Whether weekly throttling is enabled (affects display note only)
            pacemaker_status: Optional pace-maker status dict (for coefficient display)
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

        # 7-Day limiter status (always shown, matching 5-hour pattern)
        coeffs = ""
        if pacemaker_status:
            c7d = pacemaker_status.get("coefficients_7d")
            if c7d:
                overridden_5x = pacemaker_status.get(
                    "coefficients_5x_overridden", False
                )
                overridden_20x = pacemaker_status.get(
                    "coefficients_20x_overridden", False
                )
                val_5x = (
                    f"[green]{c7d['5x']:.4f}[/green]"
                    if overridden_5x
                    else f"{c7d['5x']:.4f}"
                )
                val_20x = (
                    f"[green]{c7d['20x']:.4f}[/green]"
                    if overridden_20x
                    else f"{c7d['20x']:.4f}"
                )
                coeffs = f" (5x:{val_5x} 20x:{val_20x})"
        if weekly_limit_enabled:
            content.append(
                Text.from_markup(
                    f"7-Day Limiter: [green]enabled[/green]{coeffs}", style="dim"
                )
            )
        else:
            content.append(
                Text.from_markup(
                    f"7-Day Limiter: [yellow]disabled[/yellow]{coeffs}", style="dim"
                )
            )

        if resets_at:
            reset_time = datetime.fromisoformat(resets_at)
            now = datetime.now(timezone.utc)
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
            reset_time = datetime.fromisoformat(resets_at)
            now = datetime.now(timezone.utc)
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
            # API backoff countdown right below fallback indicator
            api_backoff = pacemaker_status.get("api_backoff_remaining", 0)
            if api_backoff > 0:
                backoff_str = f"{int(api_backoff)}s"
                left_lines.append(
                    self._fmt_kv(
                        "API Retry:",
                        backoff_str,
                        f"[yellow]{backoff_str}[/yellow]",
                        status_col_width,
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

        # Subagent model preference
        preferred_model = pacemaker_status.get("preferred_subagent_model", "auto")
        if preferred_model == "auto":
            left_lines.append(
                self._fmt_kv("Subagent:", "auto", "[cyan]auto[/cyan]", status_col_width)
            )
        else:
            left_lines.append(
                self._fmt_kv(
                    "Subagent:",
                    preferred_model,
                    f"[green]{preferred_model}[/green]",
                    status_col_width,
                )
            )

        # Hook inference model
        hook_model = pacemaker_status.get("hook_model", "auto")
        if hook_model == "auto":
            left_lines.append(
                self._fmt_kv(
                    "Hook Model:", "auto", "[cyan]auto[/cyan]", status_col_width
                )
            )
        else:
            color = "green"
            if "gpt" in hook_model.lower():
                codex_limit_id = pacemaker_status.get("codex_limit_id")
                if codex_limit_id == "premium":
                    color = "cyan"
                else:
                    codex_primary = pacemaker_status.get("codex_primary_pct")
                    codex_secondary = pacemaker_status.get("codex_secondary_pct")
                    if codex_primary is not None and codex_secondary is not None:
                        max_pct = max(codex_primary, codex_secondary)
                        if max_pct > CODEX_RED_THRESHOLD:
                            color = "red"
                        elif max_pct > CODEX_ORANGE_THRESHOLD:
                            color = COLOR_ORANGE
                        elif max_pct > CODEX_YELLOW_THRESHOLD:
                            color = "yellow"
            left_lines.append(
                self._fmt_kv(
                    "Hook Model:",
                    hook_model,
                    f"[{color}]{hook_model}[/{color}]",
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

        # Clean code rules count with optional breakdown: total (default + custom - deleted)
        rules_count = pacemaker_status.get("clean_code_rules_count", 0)
        breakdown = pacemaker_status.get("clean_code_rules_breakdown")
        if rules_count > 0:
            if breakdown:
                custom = breakdown.get("custom", 0)
                deleted = breakdown.get("deleted", 0)
                defaults = rules_count - custom + deleted
                plain_val = f"{rules_count} ({defaults} + {custom} - {deleted})"
                markup_val = (
                    f"[green]{rules_count}[/green]"
                    f" ([green]{defaults}[/green]"
                    f" + [cyan]{custom}[/cyan]"
                    f" - [red]{deleted}[/red])"
                )
                left_lines.append(
                    self._fmt_kv("Rules:", plain_val, markup_val, status_col_width)
                )
            else:
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

        # Centered "Press Ctrl+C to stop" across the two-column width
        total_width = (
            status_col_width + 4 + blockage_col_width
        )  # 22 + 4(padding) + 21 = 47
        ctrl_text = "Press Ctrl+C to stop"
        pad_left = (total_width - len(ctrl_text)) // 2
        centered_instruction = Text(" " * pad_left + ctrl_text, style="dim")

        return Group(table, centered_instruction)

    def render_event_feed(
        self,
        events,
        available_width,
        visible_lines=20,
        scroll_offset=0,
    ):
        """Render a scrollable governance event feed.

        Args:
            events: List of governance event dicts from get_governance_events()
            available_width: Width in characters for text wrapping
            visible_lines: Max lines to display (default 20)
            scroll_offset: Number of events to skip from top (default 0)

        Returns:
            Rich Text renderable with event feed
        """
        _ICON_MAP = {"IV": "\u2716", "TD": "\u26a0", "CC": "\u27e1"}
        separator = "\u2500" * available_width

        if not events:
            footer = "\u2500\u2500 0 events (last 1h) \u2191\u2193 scroll \u2500\u2500"
            return Text.from_markup(f"[dim]{footer}[/dim]")

        # Render all events into lines
        all_lines = []
        event_line_counts = []  # track lines per event for scroll calc

        for event in events:
            event_lines = []
            icon = _ICON_MAP.get(event.get("event_type", ""), "?")
            ts = event.get("timestamp", 0)
            try:
                dt = datetime.fromtimestamp(ts)
                time_str = dt.strftime("%H:%M:%S")
            except (OSError, ValueError):
                time_str = "??:??:??"

            etype = event.get("event_type", "??")
            proj = event.get("project_name", "unknown")

            # Extract reviewer tag from feedback if present
            feedback = event.get("feedback_text", "")
            reviewer_markup = ""
            match = _REVIEWER_TAG_RE.search(feedback)
            if match:
                reviewer_id = match.group(1)
                tag_info = REVIEWER_TAGS.get(reviewer_id)
                if tag_info:
                    tag_label, tag_color = tag_info
                    reviewer_markup = f" [{tag_color}]{tag_label}[/{tag_color}]"
                    # Strip the tag from feedback only when recognized
                    feedback = (
                        feedback[: match.start()] + feedback[match.end() :]
                    ).lstrip()

            header = f"{icon} {time_str} {etype}{reviewer_markup} {proj}"
            event_lines.append(header)
            wrap_width = max(available_width - 2, 20)
            styled_lines = _format_feedback_lines(feedback, wrap_width)
            event_lines.extend(styled_lines)

            event_lines.append(separator)
            event_line_counts.append(len(event_lines))
            all_lines.extend(event_lines)

        # Apply scroll offset (in events, not lines)
        line_start = sum(event_line_counts[:scroll_offset])
        visible_slice = all_lines[line_start : line_start + visible_lines]

        # Build output with scroll indicators
        output_lines = []

        if scroll_offset > 0:
            output_lines.append(
                f"[dim]\u25b2 {scroll_offset} more events (scroll \u2191)[/dim]"
            )

        for line in visible_slice:
            output_lines.append(line)

        # Check if there are more events below
        remaining_lines = len(all_lines) - line_start - visible_lines
        if remaining_lines > 0:
            # Count remaining events
            lines_accum = 0
            remaining_events = 0
            for i in range(scroll_offset, len(event_line_counts)):
                lines_accum += event_line_counts[i]
                if lines_accum > visible_lines:
                    remaining_events = len(event_line_counts) - i
                    break
            if remaining_events > 0:
                output_lines.append(
                    f"[dim]\u25bc {remaining_events} more events (scroll \u2193)[/dim]"
                )

        # Footer
        total = len(events)
        footer = (
            f"\u2500\u2500 {total} events (last 1h) \u2191\u2193 scroll \u2500\u2500"
        )
        output_lines.append(f"[dim]{footer}[/dim]")

        return Text.from_markup("\n".join(output_lines))

    # Layout constants for two-column event feed
    LEFT_COL_WIDTH = 50
    MIN_TWO_COL_WIDTH = 85

    def render_with_event_feed(
        self,
        main_content,
        events,
        terminal_width,
        terminal_height=0,
        scroll_offset=0,
    ):
        """Render main content with optional event feed in two-column layout.

        When terminal_width >= 85, creates a grid with main content on the
        left and a governance event feed on the right. When < 85, returns
        just the main content.

        Args:
            main_content: Rich renderable for the left/main column
            events: List of governance event dicts
            terminal_width: Current terminal width in columns
            terminal_height: Current terminal height in lines (0 = use default)
            scroll_offset: Event scroll offset (default 0)

        Returns:
            Rich renderable (Group or Table grid)
        """
        if terminal_width < self.MIN_TWO_COL_WIDTH:
            return main_content

        # Dynamic height: fill from top to Ctrl+C footer line
        # Reserve 3 lines for scroll indicators + footer
        if terminal_height > 0:
            visible_lines = max(terminal_height - 3, 10)
        else:
            visible_lines = 40

        right_width = terminal_width - self.LEFT_COL_WIDTH - 3
        right_width = max(right_width, 20)

        event_feed = self.render_event_feed(
            events,
            available_width=right_width,
            visible_lines=visible_lines,
            scroll_offset=scroll_offset,
        )

        grid = Table.grid(padding=(0, 1))
        grid.add_column("main", width=self.LEFT_COL_WIDTH)
        grid.add_column("sep", width=1)
        grid.add_column("feed", ratio=1)
        grid.add_row(main_content, Text("\u2502", style="dim"), event_feed)

        return grid


# Activity event groups: each tuple is a visual group separated by spaces.
# Within a group, codes are separated by dots (·).
_ACTIVITY_GROUPS = [
    ("IV", "TD", "CC"),  # PreToolUse: intent, TDD, clean code
    ("ST", "CX"),  # Stop: stop hook, context exhaustion
    ("PA", "PL"),  # Pacing: pacing decision, API poll
    ("LF",),  # PostToolUse: Langfuse push
    ("SS", "SM"),  # Secrets: stored, masked
    ("SE", "SA", "UP"),  # Session/Subagent/UserPrompt
]

# Color mapping per status
_STATUS_STYLES = {
    "green": "bold green",
    "red": "bold red",
    "blue": "bold blue",
}
_IDLE_STYLE = "dim"


def render_activity_line(events: list) -> "Text":
    """Render the real-time activity visualization line.

    Displays 2-letter event codes grouped visually with dots within groups
    and spaces between groups. Active events are colored by status;
    inactive codes shown dim.

    Visual: ▸ IV·TD·CC ST·CX PA·PL LF SS·SM SE·SA·UP

    Args:
        events: List of dicts with 'event_code' and 'status' keys,
                as returned by get_recent_activity().

    Returns:
        Rich Text object with styled event codes.
    """
    from rich.text import Text

    # Build lookup: event_code -> status for active events
    active = {e["event_code"]: e["status"] for e in events}

    text = Text()
    # Blink green/dim each second to show monitor loop is alive
    arrow_style = "bold green" if int(time.time()) % 2 == 0 else _IDLE_STYLE
    text.append("▸ ", style=arrow_style)

    all_known_codes = _get_all_known_codes()
    first_group = True
    for group in _ACTIVITY_GROUPS:
        # Only render codes that are known in the group
        known_in_group = [code for code in group if code in all_known_codes]

        if not known_in_group:
            continue

        if not first_group:
            text.append(" ", style=_IDLE_STYLE)
        first_group = False

        for i, code in enumerate(known_in_group):
            if i > 0:
                text.append("·", style=_IDLE_STYLE)

            if code in active:
                status = active[code]
                style = _STATUS_STYLES.get(status, _IDLE_STYLE)
                text.append(code, style=style)
            else:
                text.append(code, style=_IDLE_STYLE)

    return text


def _get_all_known_codes() -> set:
    """Return the set of all known 2-letter event codes."""
    codes: set[str] = set()
    for group in _ACTIVITY_GROUPS:
        codes.update(group)
    return codes


def render_collapsed_plan_tier_line(plan_badges: list, rate_tier: str) -> "Text":
    """Render collapsed Plan and Tier on one line.

    Format: '📦 Plan: MAX  ⚡ 20x'
    When only plan or only tier is present, renders what's available.

    Args:
        plan_badges: List of plan badge strings (e.g. ['MAX'], ['PRO'])
        rate_tier: Rate tier string (e.g. '20x', '5x') or empty string

    Returns:
        Rich Text object with plan and tier on one line.
    """
    from rich.text import Text

    text = Text()

    has_plan = bool(plan_badges)
    has_tier = bool(rate_tier)

    if has_plan:
        text.append("📦 Plan: ")
        for i, badge in enumerate(plan_badges):
            if i > 0:
                text.append(" ")
            # Map badge name to style
            if badge == "MAX":
                text.append(badge, style="bold yellow")
            elif badge == "PRO":
                text.append(badge, style="bold magenta")
            elif badge == "ENTERPRISE":
                text.append(badge, style="bold blue")
            else:
                text.append(badge, style="bold")

    if has_plan and has_tier:
        text.append("  ")

    if has_tier:
        text.append("⚡ ")
        text.append(rate_tier, style="dim")

    return text
