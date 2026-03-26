"""
Global test fixtures for claude-usage-reporting.

Sets PACEMAKER_TEST_MODE to prevent imported pacemaker modules from
writing errors/warnings to the production log file during test runs.
"""

import os

# Suppress pacemaker logging during tests — prevents test noise
# from polluting ~/.claude-pace-maker/pace-maker-*.log
os.environ["PACEMAKER_TEST_MODE"] = "1"
