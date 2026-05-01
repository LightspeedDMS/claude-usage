"""UI rendering for Console mode usage monitor"""

from rich.text import Text
from rich.console import Group

from .constants import ADMIN_KEYS_URL, CREDENTIALS_PATH_HINT


class ConsoleRenderer:
    """Renders Console API usage data with MTD display"""

    def render_settings_panel(self, settings_info):
        """Render account/org settings info panel.

        Args:
            settings_info: dict with keys email, org_name, org_role,
                billing_type, account_created_at, primary_api_key_present,
                admin_api_key_source.  Any field may be None.

        Returns:
            Rich Group renderable.
        """
        lines = []

        email = settings_info.get("email") if settings_info is not None else None
        org_name = settings_info.get("org_name") if settings_info is not None else None
        org_role = settings_info.get("org_role") if settings_info is not None else None
        billing_type = (
            settings_info.get("billing_type") if settings_info is not None else None
        )
        primary_api_key_present = (
            settings_info.get("primary_api_key_present", False)
            if settings_info is not None
            else False
        )
        admin_api_key_source = (
            settings_info.get("admin_api_key_source")
            if settings_info is not None
            else None
        )

        email_str = email if email else "(email unavailable)"
        lines.append(Text(f"📧 {email_str}"))

        org_str = org_name if org_name else "(organization unavailable)"
        lines.append(Text(f"🏢 {org_str}"))

        if org_role:
            lines.append(Text(f"🎭 Role: {org_role}"))
        else:
            lines.append(Text("🎭 Role: (unavailable)", style="dim"))

        if billing_type == "usage_based":
            billing_style = "cyan"
        elif billing_type == "subscription":
            billing_style = "green"
        elif billing_type:
            billing_style = ""
        else:
            billing_style = "dim"
        billing_str = billing_type if billing_type else "(unavailable)"
        lines.append(Text(f"💳 Billing: {billing_str}", style=billing_style))

        if primary_api_key_present:
            suffix = (
                settings_info.get("primary_api_key_suffix")
                if settings_info is not None
                else None
            )
            if suffix:
                primary_str = f"set in ~/.claude.json (…{suffix})"
            else:
                primary_str = "set in ~/.claude.json"
        else:
            primary_str = "not set"
        lines.append(Text(f"🔑 Primary API key: {primary_str}"))

        if admin_api_key_source:
            lines.append(Text(f"🔐 Admin API key: {admin_api_key_source}"))
        else:
            lines.append(Text("🔐 Admin API key: not configured"))

        return Group(*lines)

    def render(
        self,
        org_data,
        mtd_data,
        workspaces,
        last_update,
        projection,
        error=None,
        settings_info=None,
    ):
        """Generate rich display for Console API usage"""
        content = []

        # Settings panel shown whenever settings_info is available (not None)
        if settings_info is not None:
            content.append(self.render_settings_panel(settings_info))
            content.append(Text(""))

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
            # Show friendly admin-key guidance when settings_info is present
            # (is not None) AND the source indicates no real admin key is
            # configured: either None (no key at all) or "claude_json_primary"
            # (primary API key used as fallback — not a real admin key).
            # If settings_info is absent, fall back to the generic error line.
            admin_key_source = (
                settings_info.get("admin_api_key_source")
                if settings_info is not None
                else "unknown"
            )
            no_real_admin_key = admin_key_source is None
            if settings_info is not None and no_real_admin_key:
                content.append(
                    Text(
                        '⚠️  MTD usage data requires an Admin API key (role "admin" can create one)',
                        style="bold yellow",
                    )
                )
                content.append(Text(f"  1. Generate at: {ADMIN_KEYS_URL}", style="dim"))
                content.append(Text("  2. Either set env var:", style="dim"))
                content.append(
                    Text(
                        "       export ANTHROPIC_ADMIN_API_KEY=sk-ant-admin-...",
                        style="dim",
                    )
                )
                content.append(
                    Text(f"     Or add to {CREDENTIALS_PATH_HINT}:", style="dim")
                )
                content.append(
                    Text(
                        '       {"anthropicConsole": {"adminApiKey": "sk-ant-admin-..."}}',
                        style="dim",
                    )
                )
            else:
                content.append(Text(f"⚠️  {error}", style="bold red"))
            content.append(Text(""))

        # Show loading message if no content yet
        if not content:
            content.append(Text("Loading...", style="dim"))

        # Combine content
        return Group(*content)

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
