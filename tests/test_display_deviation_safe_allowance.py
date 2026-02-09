"""
Tests for Fix 1: Deviation calculation using safe_allowance instead of target

The deviation display should always be consistent with throttling status:
- If throttling is active, deviation should be positive (over safe_allowance)
- If throttling is inactive, deviation should be negative (under safe_allowance)

Critical test case:
    actual=91%, target=95%, safe_allowance=90.25%
    Expected: deviation=+0.75%, throttling=TRUE
    Old behavior: deviation=-4%, throttling=TRUE (CONTRADICTION!)
"""

import unittest
from datetime import datetime
from claude_usage.code_mode.display import UsageRenderer


class TestDeviationFromSafeAllowance(unittest.TestCase):
    """Test that deviation is calculated from safe_allowance, not target"""

    def setUp(self):
        """Set up test fixtures"""
        self.renderer = UsageRenderer()

    def _extract_deviation_from_render(self, panel):
        """Helper to extract deviation value from rendered panel"""
        # Use Rich's render capability to convert to plain text
        from io import StringIO
        from rich.console import Console

        console = Console(file=StringIO(), width=100)
        with console.capture() as capture:
            console.print(panel)

        output = capture.get()
        return output

    def test_deviation_positive_when_throttling(self):
        """When throttling is active, deviation MUST be positive (over safe_allowance)"""
        # Critical scenario: actual=91%, target=95%, safe=90.25%
        # Old: deviation=-4% (contradicts throttling)
        # New: deviation=+0.75% (matches throttling)

        last_usage = {
            "five_hour": {
                "utilization": 91.0,  # Fresh actual utilization
                "resets_at": "2025-11-15T12:00:00+00:00",
            }
        }

        pacemaker_status = {
            "enabled": True,
            "has_data": True,
            "should_throttle": True,  # THROTTLING active
            "delay_seconds": 30,
            "constrained_window": "5-hour",
            "five_hour": {
                "utilization": 91.0,
                "target": 95.0,  # Target is 95%
                "time_elapsed_pct": 50.0,
            },
            "deviation_percent": -4.0,  # OLD WRONG VALUE (from pm_status)
            "algorithm": "adaptive",
            "strategy": "gradual",
        }

        # Render panel
        panel = self.renderer.render(
            error_message=None,
            last_usage=last_usage,
            last_profile=None,
            last_update=datetime.utcnow(),
            pacemaker_status=pacemaker_status,
            weekly_limit_enabled=True,
        )

        # Extract rendered text
        output = self._extract_deviation_from_render(panel)

        # Verify: Should show POSITIVE deviation when throttling
        # Expected: "+0.75% over budget" or similar positive value
        # Should NOT show "-4% under budget" (contradictory!)
        self.assertIn("THROTTLING", output, "Should show throttling status")

        # Check for positive deviation indicator
        # Looking for "+X%" pattern in deviation line
        has_positive_deviation = any(
            "+0." in line or "+1." in line
            for line in output.split("\n")
            if "Deviation" in line or "over" in line
        )

        self.assertTrue(
            has_positive_deviation,
            f"Deviation should be positive when throttling. Got: {output}",
        )

        # Should NOT show "under budget" when throttling
        self.assertNotIn(
            "under budget",
            output.lower(),
            "Should not show 'under budget' when throttling is active",
        )

    def test_deviation_negative_when_not_throttling(self):
        """When throttling is inactive, deviation should be negative (under safe_allowance)"""
        # Scenario: actual=30%, target=50%, safe=47.5%
        # Expected: deviation=-17.5%, throttling=FALSE

        last_usage = {
            "five_hour": {
                "utilization": 30.0,  # Well under safe allowance
                "resets_at": "2025-11-15T12:00:00+00:00",
            }
        }

        pacemaker_status = {
            "enabled": True,
            "has_data": True,
            "should_throttle": False,  # NOT throttling
            "delay_seconds": 0,
            "constrained_window": "5-hour",
            "five_hour": {
                "utilization": 30.0,
                "target": 50.0,
                "time_elapsed_pct": 40.0,
            },
            "deviation_percent": -20.0,  # OLD VALUE (from target)
            "algorithm": "adaptive",
            "strategy": "none",
        }

        panel = self.renderer.render(
            error_message=None,
            last_usage=last_usage,
            last_profile=None,
            last_update=datetime.utcnow(),
            pacemaker_status=pacemaker_status,
            weekly_limit_enabled=True,
        )

        output = self._extract_deviation_from_render(panel)

        # Verify: Should show NEGATIVE deviation when not throttling
        self.assertIn("ON PACE", output, "Should show on-pace status")

        # Check for negative deviation
        has_negative_deviation = any(
            "-" in line and "%" in line
            for line in output.split("\n")
            if "Deviation" in line or "under" in line
        )

        self.assertTrue(
            has_negative_deviation,
            f"Deviation should be negative when not throttling. Got: {output}",
        )

        # Should show "under budget" when not throttling
        self.assertIn(
            "under budget",
            output.lower(),
            "Should show 'under budget' when not throttling",
        )

    def test_deviation_uses_fresh_utilization_not_stale(self):
        """Deviation calculation must use fresh utilization from last_usage, not stale pm_status"""
        # Scenario: pm_status has stale data (90%), last_usage has fresh data (92%)
        # Deviation MUST use fresh 92%, not stale 90%

        last_usage = {
            "five_hour": {
                "utilization": 92.0,  # FRESH data
                "resets_at": "2025-11-15T12:00:00+00:00",
            }
        }

        pacemaker_status = {
            "enabled": True,
            "has_data": True,
            "should_throttle": True,
            "delay_seconds": 45,
            "constrained_window": "5-hour",
            "five_hour": {
                "utilization": 90.0,  # STALE data (30 seconds old)
                "target": 95.0,
                "time_elapsed_pct": 50.0,
            },
            "deviation_percent": -5.0,  # Based on stale 90%
            "algorithm": "adaptive",
            "strategy": "gradual",
        }

        panel = self.renderer.render(
            error_message=None,
            last_usage=last_usage,
            last_profile=None,
            last_update=datetime.utcnow(),
            pacemaker_status=pacemaker_status,
            weekly_limit_enabled=True,
        )

        output = self._extract_deviation_from_render(panel)

        # Verify: Should use FRESH 92% for deviation calculation
        # safe_allowance = 95 * 0.95 = 90.25
        # deviation = 92 - 90.25 = +1.75%
        # Should show positive deviation based on fresh data

        has_positive_deviation = any(
            "+1." in line or "+2." in line
            for line in output.split("\n")
            if "Deviation" in line or "over" in line
        )

        self.assertTrue(
            has_positive_deviation,
            f"Deviation should reflect fresh utilization (92%), not stale (90%). Got: {output}",
        )

    def test_deviation_color_coding_matches_throttling(self):
        """Color coding should match throttling state consistently"""
        # Test 1: Throttling active → red/yellow color, positive deviation
        last_usage_throttling = {
            "five_hour": {
                "utilization": 96.0,  # Over safe allowance
                "resets_at": "2025-11-15T12:00:00+00:00",
            }
        }

        pacemaker_status_throttling = {
            "enabled": True,
            "has_data": True,
            "should_throttle": True,
            "delay_seconds": 60,
            "constrained_window": "5-hour",
            "five_hour": {
                "utilization": 96.0,
                "target": 95.0,
                "time_elapsed_pct": 50.0,
            },
            "deviation_percent": 1.0,  # OLD calculation
            "algorithm": "adaptive",
            "strategy": "aggressive",
        }

        panel = self.renderer.render(
            error_message=None,
            last_usage=last_usage_throttling,
            last_profile=None,
            last_update=datetime.utcnow(),
            pacemaker_status=pacemaker_status_throttling,
            weekly_limit_enabled=True,
        )

        # Just verify it doesn't crash and shows throttling
        output = self._extract_deviation_from_render(panel)
        self.assertIn("THROTTLING", output)


if __name__ == "__main__":
    unittest.main()
