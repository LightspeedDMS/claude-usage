#!/usr/bin/env python3
"""
Unit tests for CodeMonitor._drain_key_queue() scroll behavior.

Tests that user_scrolled resets to False when scroll_offset returns to 0,
fixing the bug where auto-scroll was permanently disabled after any scroll.
"""

import queue

import pytest

from claude_usage.code_mode.monitor import CodeMonitor


@pytest.fixture
def monitor():
    """Create a CodeMonitor without __init__ for isolated unit testing."""
    m = CodeMonitor.__new__(CodeMonitor)
    m.scroll_offset = 0
    m.user_scrolled = False
    return m


class TestDrainKeyQueueScrollReset:
    """Tests for user_scrolled reset when scroll_offset returns to 0."""

    def test_scroll_up_to_zero_resets_user_scrolled(self, monitor):
        """When UP brings scroll_offset from 1 to 0, user_scrolled resets to False."""
        monitor.scroll_offset = 1
        monitor.user_scrolled = True

        key_queue = queue.Queue()
        key_queue.put("UP")

        monitor._drain_key_queue(key_queue, max_events=5)

        assert monitor.scroll_offset == 0
        assert monitor.user_scrolled is False

    def test_scroll_up_partial_keeps_user_scrolled(self, monitor):
        """When UP decrements but scroll_offset > 0, user_scrolled stays True."""
        monitor.scroll_offset = 3
        monitor.user_scrolled = True

        key_queue = queue.Queue()
        key_queue.put("UP")

        monitor._drain_key_queue(key_queue, max_events=5)

        assert monitor.scroll_offset == 2
        assert monitor.user_scrolled is True

    def test_scroll_down_sets_user_scrolled(self, monitor):
        """DOWN key sets user_scrolled to True."""
        monitor.scroll_offset = 0
        monitor.user_scrolled = False

        key_queue = queue.Queue()
        key_queue.put("DOWN")

        monitor._drain_key_queue(key_queue, max_events=5)

        assert monitor.scroll_offset == 1
        assert monitor.user_scrolled is True

    def test_quit_returns_true(self, monitor):
        """QUIT key causes _drain_key_queue to return True."""
        key_queue = queue.Queue()
        key_queue.put("QUIT")

        result = monitor._drain_key_queue(key_queue, max_events=5)

        assert result is True

    def test_no_keys_returns_false(self, monitor):
        """Empty queue returns False (no quit)."""
        key_queue = queue.Queue()

        result = monitor._drain_key_queue(key_queue, max_events=5)

        assert result is False

    def test_multiple_ups_to_zero_resets_user_scrolled(self, monitor):
        """Multiple UP keys that bring offset to 0 reset user_scrolled."""
        monitor.scroll_offset = 2
        monitor.user_scrolled = True

        key_queue = queue.Queue()
        key_queue.put("UP")
        key_queue.put("UP")

        monitor._drain_key_queue(key_queue, max_events=5)

        assert monitor.scroll_offset == 0
        assert monitor.user_scrolled is False

    def test_up_at_zero_does_not_go_negative(self, monitor):
        """UP at scroll_offset=0 does not decrement below 0."""
        monitor.scroll_offset = 0
        monitor.user_scrolled = False

        key_queue = queue.Queue()
        key_queue.put("UP")

        monitor._drain_key_queue(key_queue, max_events=5)

        assert monitor.scroll_offset == 0
        assert monitor.user_scrolled is False
