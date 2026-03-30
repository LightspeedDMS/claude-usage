# Changelog

## [2.5.0] - 2026-03-30

### Added
- **Live governance event feed** (#52): Two-column layout with scrollable event feed showing intent validation rejections (✖), TDD failures (⚠), and clean code violations (⟡) from all Claude sessions
- **`get_governance_events()`**: Reads governance events from pace-maker SQLite DB with 1h time window, graceful degradation on errors
- **`render_event_feed()`**: Rich-rendered event feed with markdown formatting (bold, code, bullets), scroll indicators, and dynamic visible lines based on terminal height
- **`render_with_event_feed()`**: Two-column grid layout — fixed left column (existing metrics) + fluid right column (event feed) separated by │
- **Responsive layout**: Event feed appears at >= 85 columns, hides below; right column expands fluidly with terminal width
- **Keyboard scrolling**: Non-blocking daemon thread captures ↑/↓ arrow keys for scrolling through event history with cbreak terminal mode
- **Scroll state machine**: Auto-scroll to newest on new events unless user has manually scrolled; preserves position when user is reading
- **20 new tests**: `test_governance_events.py` (7), `test_event_feed_renderer.py` (7), `test_two_column_event_layout.py` (6)

### Fixed
- **Terminal display garbled during Live refresh**: Changed `tty.setraw()` to `tty.setcbreak()` for keyboard input — raw mode was disabling output processing needed by Rich

## [2.4.0] - 2026-03-26

### Added
- **`importlib.reload()` for pacemaker modules**: Rules count and version now update in real-time after `./install.sh` without requiring a monitor restart
- **`tests/conftest.py`**: Sets `PACEMAKER_TEST_MODE=1` globally to prevent test runs from polluting the production pace-maker log file
- **Module reload tests**: `test_pacemaker_module_reload.py` verifies rules count and version pick up changes dynamically

### Fixed
- **Stale rules count**: `DEFAULT_CLEAN_CODE_RULES_COUNT` updated from 17 to 25 to match pace-maker v2.5.0
- **Stale import in test**: `test_new_status_indicators.py` now imports `DEFAULT_CLEAN_CODE_RULES_COUNT` from the module instead of hardcoding 17
- **Test log pollution**: Test suite no longer writes errors/warnings to `~/.claude-pace-maker/pace-maker-*.log` (was inflating "Errors in 24hrs" counter)
