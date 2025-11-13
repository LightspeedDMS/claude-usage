#!/usr/bin/env python3
"""Manual test to visually verify progress bar display at different utilization levels

This script demonstrates that the progress bar correctly shows:
- 2% utilization: small green bar with remaining space neutral/dim
- 50% utilization: half green bar with half remaining neutral
- 85% utilization: mostly bright yellow bar with small remaining neutral space
- 100% utilization: full red bar

Run this script and visually inspect the output to verify the fix.
"""

import time
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from claude_usage.display import UsageRenderer


def main():
    """Display progress bars at different utilization levels"""
    console = Console()
    renderer = UsageRenderer()

    test_cases = [
        (2, "Very low utilization (2%) - Should show small GREEN bar"),
        (25, "Low utilization (25%) - Should show quarter GREEN bar"),
        (50, "Medium utilization (50%) - Should show half GREEN bar"),
        (60, "Medium-high utilization (60%) - Should show more than half YELLOW bar"),
        (85, "High utilization (85%) - Should show mostly BRIGHT YELLOW bar"),
        (95, "Very high utilization (95%) - Should show almost full BRIGHT YELLOW bar"),
        (100, "Full utilization (100%) - Should show completely filled RED bar"),
        (120, "Over utilization (120%) - Should show completely filled RED bar"),
    ]

    console.print("\n[bold cyan]Progress Bar Visual Verification Test[/bold cyan]\n")
    console.print(
        "This test verifies that the progress bar displays correctly at different utilization levels."
    )
    console.print(
        "The bar should only be colored for the utilized portion, with remaining space neutral/dim.\n"
    )

    for utilization, description in test_cases:
        console.print(Panel(Text(description, style="bold"), border_style="blue"))

        # Create test data
        five_hour_data = {
            "utilization": utilization,
            "resets_at": "2025-11-12T23:00:00+00:00",
        }

        content = []
        renderer._render_five_hour_limit(content, five_hour_data)

        # Display the progress bar
        for item in content:
            console.print(item)

        console.print()  # Empty line for spacing
        time.sleep(0.5)  # Brief pause for visual inspection

    console.print("\n[bold green]✓ Manual verification complete![/bold green]")
    console.print("\nExpected behavior:")
    console.print(
        "  - Low utilization (0-50%): Small/partial GREEN bar with neutral remaining space"
    )
    console.print(
        "  - Medium utilization (51-80%): Partial YELLOW bar with neutral remaining space"
    )
    console.print(
        "  - High utilization (81-99%): Mostly BRIGHT YELLOW bar with small neutral remaining space"
    )
    console.print("  - Full/over (100%+): Completely filled RED bar")
    console.print(
        "\n[bold yellow]If the bars above match this description, the fix is working correctly.[/bold yellow]\n"
    )


if __name__ == "__main__":
    main()
