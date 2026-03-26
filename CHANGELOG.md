# Changelog

## [2.4.0] - 2026-03-26

### Added
- **`importlib.reload()` for pacemaker modules**: Rules count and version now update in real-time after `./install.sh` without requiring a monitor restart
- **`tests/conftest.py`**: Sets `PACEMAKER_TEST_MODE=1` globally to prevent test runs from polluting the production pace-maker log file
- **Module reload tests**: `test_pacemaker_module_reload.py` verifies rules count and version pick up changes dynamically

### Fixed
- **Stale rules count**: `DEFAULT_CLEAN_CODE_RULES_COUNT` updated from 17 to 25 to match pace-maker v2.5.0
- **Stale import in test**: `test_new_status_indicators.py` now imports `DEFAULT_CLEAN_CODE_RULES_COUNT` from the module instead of hardcoding 17
- **Test log pollution**: Test suite no longer writes errors/warnings to `~/.claude-pace-maker/pace-maker-*.log` (was inflating "Errors in 24hrs" counter)
