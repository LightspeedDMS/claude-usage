"""Shared helpers for visualization regression tests.

Provides fixture-builder functions used by:
  - test_viz_regression_activity_line.py
  - test_viz_regression_plan_tier.py
  - test_viz_regression_renderer.py
  - test_viz_regression_bottom_section.py
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import StringIO


def _render_to_str(renderable, width: int = 120) -> str:
    """Render any Rich renderable to a plain string via Console capture."""
    from rich.console import Console

    console = Console(file=StringIO(), width=width, force_terminal=True)
    with console.capture() as capture:
        console.print(renderable)
    return capture.get()


def _future_iso(hours: float = 3.0) -> str:
    """Return an ISO-format UTC datetime string ``hours`` from now."""
    dt = datetime.now(timezone.utc) + timedelta(hours=hours)
    return dt.isoformat()


def _past_iso(hours: float = 1.0) -> str:
    """Return an ISO-format UTC datetime string ``hours`` in the past."""
    dt = datetime.now(timezone.utc) - timedelta(hours=hours)
    return dt.isoformat()


def _make_usage(
    five_util: float = 40.0,
    five_resets: str | None = None,
    seven_util: float = 30.0,
    seven_resets: str | None = None,
) -> dict:
    return {
        "five_hour": {
            "utilization": five_util,
            "resets_at": five_resets if five_resets is not None else _future_iso(2),
        },
        "seven_day": {
            "utilization": seven_util,
            "resets_at": seven_resets if seven_resets is not None else _future_iso(48),
        },
    }


def _make_profile(
    display_name: str = "Alice",
    email: str = "alice@example.com",
    org_name: str = "Acme Corp",
    org_type: str = "",
    has_pro: bool = False,
    has_max: bool = True,
    rate_tier: str = "20x",
) -> dict:
    return {
        "account": {
            "display_name": display_name,
            "email": email,
            "has_claude_pro": has_pro,
            "has_claude_max": has_max,
        },
        "organization": {
            "name": org_name,
            "organization_type": org_type,
            "rate_limit_tier": rate_tier,
        },
    }


def _make_pacemaker_status(
    enabled: bool = True,
    has_data: bool = True,
    should_throttle: bool = False,
    delay_seconds: int = 0,
    five_hour_target: float = 60.0,
    seven_day_target: float = 50.0,
    constrained_window: str = "5-hour",
    five_hour_limit_enabled: bool = True,
    tempo_enabled: bool = True,
    subagent_reminder_enabled: bool = True,
    intent_validation_enabled: bool = True,
    tdd_enabled: bool = True,
    langfuse_enabled: bool = False,
    langfuse_connected: bool = False,
    preferred_subagent_model: str = "auto",
    hook_model: str = "auto",
    clean_code_rules_count: int = 17,
    log_level: int = 2,
    pacemaker_version: str = "1.0.0",
    usage_console_version: str = "1.2.0",
    error_count_24h: int = 0,
    api_backoff_remaining: float = 0,
    fallback_mode: bool = False,
) -> dict:
    return {
        "enabled": enabled,
        "has_data": has_data,
        "should_throttle": should_throttle,
        "delay_seconds": delay_seconds,
        "five_hour": {"utilization": 40.0, "target": five_hour_target},
        "seven_day": {"utilization": 30.0, "target": seven_day_target},
        "constrained_window": constrained_window,
        "five_hour_limit_enabled": five_hour_limit_enabled,
        "tempo_enabled": tempo_enabled,
        "subagent_reminder_enabled": subagent_reminder_enabled,
        "intent_validation_enabled": intent_validation_enabled,
        "tdd_enabled": tdd_enabled,
        "langfuse_enabled": langfuse_enabled,
        "langfuse_connection": {"connected": langfuse_connected},
        "preferred_subagent_model": preferred_subagent_model,
        "hook_model": hook_model,
        "clean_code_rules_count": clean_code_rules_count,
        "log_level": log_level,
        "pacemaker_version": pacemaker_version,
        "usage_console_version": usage_console_version,
        "error_count_24h": error_count_24h,
        "api_backoff_remaining": api_backoff_remaining,
        "fallback_mode": fallback_mode,
    }
