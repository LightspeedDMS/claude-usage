"""
Integration tests for Fix 1 and Fix 2 working together

Verifies that:
- Fix 1: Deviation is calculated from safe_allowance (not target)
- Fix 2: 5-hour window has 30-minute preload (10% allowance at start)
- Both fixes interact correctly: fresh utilization + preload-aware deviation
"""

import unittest
from datetime import datetime, timedelta
from claude_usage.code_mode.display import UsageRenderer
from claude_usage.code_mode.pacemaker_integration import PaceMakerReader
from io import StringIO
from rich.console import Console


class TestBothFixesIntegration(unittest.TestCase):
    """Test that Fix 1 and Fix 2 work together correctly"""

    def setUp(self):
        """Set up test fixtures"""
        self.renderer = UsageRenderer()

    def _extract_text_from_panel(self, panel):
        """Helper to extract plain text from rendered panel"""
        console = Console(file=StringIO(), width=100)
        with console.capture() as capture:
            console.print(panel)
        return capture.get()

    def test_deviation_reflects_preload_at_window_start(self):
        """At window start with preload, deviation should reflect 10% allowance"""
        # Scenario: Window just reset, user has used 5%
        # Expected behavior:
        #   - 5-hour target: 10% (from preload)
        #   - safe_allowance: 10% × 0.95 = 9.5%
        #   - actual: 5%
        #   - deviation: 5% - 9.5% = -4.5% (under safe budget)
        #   - throttling: FALSE

        now = datetime.utcnow()
        last_usage = {
            "five_hour": {
                "utilization": 5.0,  # FRESH data: 5% used
                "resets_at": (now + timedelta(hours=5)).isoformat() + "+00:00",
            }
        }

        # Simulate pacemaker status with preload
        pacemaker_status = {
            "enabled": True,
            "has_data": True,
            "should_throttle": False,  # NOT throttling (under safe budget)
            "delay_seconds": 0,
            "constrained_window": "5-hour",
            "five_hour": {
                "utilization": 5.0,
                "target": 10.0,  # 10% from preload
                "time_elapsed_pct": 0.0,
            },
            "deviation_percent": -5.0,  # OLD WRONG: from target (5% - 10% = -5%)
            "algorithm": "adaptive",
            "strategy": "none",
        }

        panel = self.renderer.render(
            error_message=None,
            last_usage=last_usage,
            last_profile=None,
            last_overage=None,
            last_update=now,
            projection=None,
            pacemaker_status=pacemaker_status,
            weekly_limit_enabled=True,
        )

        output = self._extract_text_from_panel(panel)

        # Verify: Should show NEGATIVE deviation (under safe budget)
        self.assertIn("ON PACE", output, "Should show ON PACE status")

        # Deviation should be around -4.5% (5% - 9.5% safe allowance)
        # Look for negative deviation
        has_negative_deviation = any(
            "-4." in line or "-5." in line
            for line in output.split("\n")
            if "Deviation" in line
        )

        self.assertTrue(
            has_negative_deviation,
            f"Deviation should be negative (around -4.5%). Got output: {output}"
        )

        self.assertIn("under budget", output.lower())

    def test_deviation_positive_when_over_preload_allowance(self):
        """When using > 9.5% immediately, deviation should be positive and throttling active"""
        # Scenario: Window just reset, user burned through 11% immediately
        # Expected behavior:
        #   - 5-hour target: 10% (from preload)
        #   - safe_allowance: 9.5%
        #   - actual: 11%
        #   - deviation: 11% - 9.5% = +1.5% (over safe budget)
        #   - throttling: TRUE

        now = datetime.utcnow()
        last_usage = {
            "five_hour": {
                "utilization": 11.0,  # FRESH data: 11% used
                "resets_at": (now + timedelta(hours=5)).isoformat() + "+00:00",
            }
        }

        pacemaker_status = {
            "enabled": True,
            "has_data": True,
            "should_throttle": True,  # THROTTLING (over safe budget)
            "delay_seconds": 20,
            "constrained_window": "5-hour",
            "five_hour": {
                "utilization": 10.0,  # STALE data (slightly old)
                "target": 10.0,  # 10% from preload
                "time_elapsed_pct": 0.0,
            },
            "deviation_percent": 0.0,  # OLD WRONG: based on stale data
            "algorithm": "adaptive",
            "strategy": "minimal",
        }

        panel = self.renderer.render(
            error_message=None,
            last_usage=last_usage,
            last_profile=None,
            last_overage=None,
            last_update=now,
            projection=None,
            pacemaker_status=pacemaker_status,
            weekly_limit_enabled=True,
        )

        output = self._extract_text_from_panel(panel)

        # Verify: Should show POSITIVE deviation (over safe budget)
        self.assertIn("THROTTLING", output, "Should show THROTTLING status")

        # Deviation should be around +1.5% (11% - 9.5% safe allowance)
        has_positive_deviation = any(
            "+1." in line or "+2." in line
            for line in output.split("\n")
            if "Deviation" in line or "over" in line
        )

        self.assertTrue(
            has_positive_deviation,
            f"Deviation should be positive (around +1.5%). Got output: {output}"
        )

        self.assertIn("over budget", output.lower())

    def test_fresh_utilization_with_preload_after_30_minutes(self):
        """After preload period, deviation uses fresh utilization and normal accrual"""
        # Scenario: 35 minutes into window (after preload), user at 12%
        # Expected behavior:
        #   - 5-hour target: >10% (normal accrual after preload)
        #   - safe_allowance: target × 0.95
        #   - actual: 12% (fresh)
        #   - deviation: depends on target, but uses fresh data

        now = datetime.utcnow()
        window_start = now - timedelta(minutes=35)
        resets_at = window_start + timedelta(hours=5)

        last_usage = {
            "five_hour": {
                "utilization": 12.0,  # FRESH data
                "resets_at": resets_at.isoformat() + "+00:00",
            }
        }

        pacemaker_status = {
            "enabled": True,
            "has_data": True,
            "should_throttle": False,  # Depends on actual target
            "delay_seconds": 0,
            "constrained_window": "5-hour",
            "five_hour": {
                "utilization": 11.0,  # STALE data
                "target": 13.0,  # Example target after preload
                "time_elapsed_pct": 11.67,  # 35/300 minutes
            },
            "deviation_percent": -2.0,  # OLD: based on stale util
            "algorithm": "adaptive",
            "strategy": "none",
        }

        panel = self.renderer.render(
            error_message=None,
            last_usage=last_usage,
            last_profile=None,
            last_overage=None,
            last_update=now,
            projection=None,
            pacemaker_status=pacemaker_status,
            weekly_limit_enabled=True,
        )

        output = self._extract_text_from_panel(panel)

        # Verify: Deviation should reflect FRESH 12%, not stale 11%
        # safe_allowance = 13% × 0.95 = 12.35%
        # deviation = 12% - 12.35% = -0.35% (negative, under budget)

        has_negative_deviation = any(
            "-0." in line or "-1." in line
            for line in output.split("\n")
            if "Deviation" in line
        )

        self.assertTrue(
            has_negative_deviation,
            f"Deviation should reflect fresh utilization (12%). Got output: {output}"
        )


if __name__ == "__main__":
    unittest.main()
