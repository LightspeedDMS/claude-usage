#!/usr/bin/env python3
"""
Claude Usage Monitor - Factory Entry Point
Detects mode and instantiates appropriate monitor
"""

import sys
import json
import platform
from pathlib import Path
from rich.console import Console

console = Console()


# Re-export ClaudeUsageMonitor for backward compatibility with tests
# Actual implementation is in __init__.py
def __getattr__(name):
    """Lazy import to avoid circular dependency"""
    if name == "ClaudeUsageMonitor":
        from . import ClaudeUsageMonitor as _ClaudeUsageMonitor

        return _ClaudeUsageMonitor
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


def detect_mode(credentials_path):
    """Detect which mode to run in: 'console' or 'code'

    Priority order:
    1. Explicit mode field in credentials file (user override)
    2. Claude Code OAuth credentials (subscription/code mode)
    3. Anthropic Console Admin API key (console mode)
    4. macOS Keychain (if on macOS and file doesn't exist)
    """
    import os

    # Check credentials file
    try:
        with open(credentials_path) as f:
            data = json.load(f)

        # Check for explicit mode field override (highest priority)
        if "mode" in data and data["mode"] in ["console", "code"]:
            return data["mode"], None

        # Check for Claude Code OAuth credentials (second priority)
        if "claudeCode" in data or "claudeAiOauth" in data:
            return "code", None

        # Check for Anthropic Console Admin API key in file (third priority)
        if "anthropicConsole" in data and "adminApiKey" in data["anthropicConsole"]:
            return "console", None
    except FileNotFoundError:
        # File doesn't exist - check macOS Keychain
        if platform.system() == "Darwin":
            # Try to detect credentials in Keychain
            from .code_mode.auth import OAuthManager

            temp_oauth = OAuthManager(credentials_path)
            data, error = temp_oauth.extract_from_macos_keychain()
            if data and not error:
                return "code", None
    except Exception:
        pass

    # Check environment variable (lowest priority)
    if os.environ.get("ANTHROPIC_ADMIN_API_KEY"):
        return "console", None

    # No credentials found
    return None, "No credentials found"


def parse_args():
    """Parse command line arguments"""
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default=None)
    return parser.parse_args()


def main():
    """Main entry point - factory pattern"""
    args = parse_args()
    credentials_path = Path.home() / ".claude" / ".credentials.json"

    # Detect mode
    detected_mode, error = detect_mode(credentials_path)

    # CLI override takes precedence
    mode = args.mode if args.mode else detected_mode

    if not mode and error:
        console.print(f"[red]Error: {error}[/red]\n")
        return 1

    # Instantiate appropriate monitor based on mode
    if mode == "console":
        from .console_mode.monitor import ConsoleMonitor

        monitor = ConsoleMonitor(credentials_path)
    else:
        from .code_mode.monitor import CodeMonitor

        monitor = CodeMonitor(credentials_path)

    # Run the monitor
    return monitor.run()


if __name__ == "__main__":
    sys.exit(main())
