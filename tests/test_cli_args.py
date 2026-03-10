"""Tests for CLI argument parsing"""

import io
import unittest
from unittest.mock import patch
from claude_usage import __version__
from claude_usage.monitor import parse_args


class TestCLIArgs(unittest.TestCase):
    """Test cases for CLI argument parsing"""

    def test_parse_args_defaults_to_none_when_no_mode_specified(self):
        """Test that --mode defaults to None when not specified"""
        with patch("sys.argv", ["monitor.py"]):
            args = parse_args()
            self.assertIsNone(args.mode)

    def test_parse_args_accepts_console_mode(self):
        """Test that --mode console is accepted"""
        with patch("sys.argv", ["monitor.py", "--mode", "console"]):
            args = parse_args()
            self.assertEqual(args.mode, "console")

    def test_version_flag_prints_version_and_exits(self):
        """Test that --version prints version string and exits with code 0"""
        with patch("sys.argv", ["monitor.py", "--version"]):
            with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                with self.assertRaises(SystemExit) as ctx:
                    parse_args()
                self.assertEqual(ctx.exception.code, 0)
                self.assertIn(__version__, mock_stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
