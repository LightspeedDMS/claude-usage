"""Tests for panel carousel keybinding and version bump."""

import inspect
import queue

from claude_usage.code_mode.monitor import CodeMonitor


def _make_monitor():
    """Create a bare CodeMonitor without __init__ side effects."""
    m = CodeMonitor.__new__(CodeMonitor)
    m.panel_index = 0
    m.scroll_offset = 0
    m.user_scrolled = False
    return m


class TestPanelIndex:
    def test_initial_value_is_zero(self):
        """Verify __init__ initializes panel_index to 0.

        We cannot call real __init__ without credentials, so we inspect the
        source of __init__ to confirm the assignment is present.  This test
        will fail (RED) until the attribute is added to __init__.
        """
        source = inspect.getsource(CodeMonitor.__init__)
        assert "self.panel_index = 0" in source, (
            "CodeMonitor.__init__ must initialise self.panel_index = 0"
        )


class TestDrainKeyQueuePanel:
    def test_right_increments_panel(self):
        m = _make_monitor()
        q = queue.Queue()
        q.put("RIGHT")
        m._drain_key_queue(q, 10)
        assert m.panel_index == 1

    def test_left_decrements_panel(self):
        m = _make_monitor()
        m.panel_index = 1
        q = queue.Queue()
        q.put("LEFT")
        m._drain_key_queue(q, 10)
        assert m.panel_index == 0

    def test_right_at_max_stays(self):
        m = _make_monitor()
        m.panel_index = 1
        q = queue.Queue()
        q.put("RIGHT")
        m._drain_key_queue(q, 10)
        assert m.panel_index == 1

    def test_left_at_zero_stays(self):
        m = _make_monitor()
        q = queue.Queue()
        q.put("LEFT")
        m._drain_key_queue(q, 10)
        assert m.panel_index == 0


class TestVersionBump:
    def test_version_is_2_15_0(self):
        from claude_usage import __version__
        assert __version__ == "2.15.0"
