"""End-to-end tests for main() function"""

import unittest
import os
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestMainE2E(unittest.TestCase):
    """End-to-end test cases for main() function"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.credentials_path = Path(self.temp_dir) / ".credentials.json"

    def tearDown(self):
        """Clean up test fixtures"""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_main_calls_parse_args_on_startup(self):
        """Test that main() calls parse_args() and that the CLI --mode value
        (not auto-detection) determines which monitor is instantiated.

        NOTE: main() was refactored from a ClaudeUsageMonitor().resolve_mode()
        façade to a factory pattern (detect_mode() + direct CodeMonitor/
        ConsoleMonitor instantiation, see claude_usage/monitor.py). This test
        previously asserted against the old façade's resolve_mode(), which
        main() no longer calls at all — the mock was never invoked, so the
        test failed unconditionally. Rewritten to assert against main()'s
        actual current collaborators.
        """
        # Mock everything except parse_args to test it gets called
        with patch("sys.argv", ["monitor.py", "--mode", "console"]):
            with patch.dict(os.environ, {}, clear=True):
                # detect_mode would auto-detect "code" here (deliberately
                # contradicting the CLI arg) to prove --mode wins.
                with patch(
                    "claude_usage.monitor.detect_mode", return_value=("code", None)
                ) as mock_detect_mode:
                    with patch(
                        "claude_usage.console_mode.monitor.ConsoleMonitor"
                    ) as MockConsoleMonitor:
                        mock_monitor = MockConsoleMonitor.return_value
                        mock_monitor.run.return_value = 0

                        # Import and run main
                        from claude_usage.monitor import main

                        result = main()

                        # parse_args() ran (detect_mode was consulted as part
                        # of main()'s flow) and CLI --mode console overrode
                        # the auto-detected "code" mode.
                        mock_detect_mode.assert_called_once()
                        MockConsoleMonitor.assert_called_once()
                        mock_monitor.run.assert_called_once()
                        self.assertEqual(result, 0)

    def test_main_console_mode_no_firefox_manager_access(self):
        """Test that main() doesn't access firefox_manager in console mode

        Bug (hang): this test used to leave mode selection to the real
        detect_mode(), which reads Path.home() / ".claude" / ".credentials.json"
        — the ACTUAL developer machine's file, outside test control. On any
        machine with real Claude Code OAuth credentials installed (i.e. every
        normal dev box, confirmed via py-spy: the hang always bottomed out at
        CodeMonitor.run() / code_mode/monitor.py:494), detect_mode() resolves
        to "code" mode, not "console". main() then instantiates a REAL,
        unmocked CodeMonitor and calls its real run() loop, whose Live import
        (claude_usage.code_mode.monitor.Live) was never the one this test
        patched (claude_usage.console_mode.monitor.Live) — so the
        KeyboardInterrupt injection had no effect and the real `while True:
        time.sleep(1)` loop ran forever.

        Fix: the Live-context KeyboardInterrupt injection below is the
        test's PRE-EXISTING, unchanged mechanism (same pattern used in
        test_main_calls_parse_args_on_startup above and throughout this
        suite, e.g. test_main_integration.py) for bounding main()'s
        intentionally-infinite polling loop — the loop has no other exit
        signal to inject short of this. The only NEW patch added here is
        detect_mode(), which stands in for reading ambient OS/filesystem
        state (~/.claude/.credentials.json) that is explicitly outside this
        test's control and is not part of the console-mode business logic
        under test; forcing it makes mode resolution deterministic across
        machines instead of accidentally depending on whichever real
        credentials happen to be installed on the box running the suite.
        """
        # Create admin credentials for console mode (dummy, non-key-shaped
        # placeholder values — not real credentials)
        credentials_data = {
            "anthropicConsole": {"adminApiKey": "test-fake-admin-key-not-real"}
        }
        with open(self.credentials_path, "w") as f:
            json.dump(credentials_data, f)

        with patch("sys.argv", ["monitor.py"]):
            with patch.dict(
                os.environ,
                {"ANTHROPIC_ADMIN_API_KEY": "test-fake-env-admin-key-not-real"},
                clear=True,
            ):
                with patch(
                    "claude_usage.monitor.detect_mode",
                    return_value=("console", None),
                ):
                    with patch("claude_usage.console_mode.monitor.Live") as MockLive:
                        with patch("claude_usage.monitor.console"):
                            # Make Live context manager raise KeyboardInterrupt to exit loop
                            MockLive.return_value.__enter__.return_value = (
                                MagicMock()
                            )
                            MockLive.return_value.__enter__.side_effect = (
                                KeyboardInterrupt()
                            )

                            # Import and run main with real ConsoleMonitor
                            from claude_usage.monitor import main

                            try:
                                main()
                            except KeyboardInterrupt:
                                pass
                            # Test passes if no AttributeError about firefox_manager


if __name__ == "__main__":
    unittest.main()
