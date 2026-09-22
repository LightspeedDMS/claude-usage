"""Regression tests for UsageRenderer.render_bottom_section() — Section E.

Tests the real rendering code with no mocks.  All inputs are plain Python
dicts built by the helper factories in viz_regression_helpers.py.
Output is inspected by rendering to a captured string via Console.

Two-column layout:
  Left  — Pacing Status indicators
  Right — Blockages / Langfuse metrics / Secrets metrics
"""

from __future__ import annotations

from datetime import datetime

from rich.console import Group

from claude_usage.code_mode.display import UsageRenderer

from tests.viz_regression_helpers import (
    _make_pacemaker_status,
    _render_to_str,
)


# ===========================================================================
# Return type
# ===========================================================================


class TestRenderBottomSectionReturnType:
    def setup_method(self):
        self.r = UsageRenderer()

    def test_returns_group(self):
        result = self.r.render_bottom_section(
            _make_pacemaker_status(), blockage_stats={}
        )
        assert isinstance(result, Group)


# ===========================================================================
# Left column — Pacing Status
# ===========================================================================


class TestRenderBottomSectionLeftColumn:
    def setup_method(self):
        self.r = UsageRenderer()

    def _render(self, pm, blockage_stats=None, **kwargs):
        stats = blockage_stats if blockage_stats is not None else {}
        return _render_to_str(self.r.render_bottom_section(pm, stats, **kwargs))

    # ---- Header ----

    def test_pacing_status_header_present(self):
        assert "Settings" in self._render(_make_pacemaker_status())

    # ---- Tempo ----

    def test_tempo_on(self):
        rendered = self._render(_make_pacemaker_status(tempo_enabled=True))
        assert "Tempo" in rendered
        assert "on" in rendered

    def test_tempo_off(self):
        rendered = self._render(_make_pacemaker_status(tempo_enabled=False))
        assert "Tempo" in rendered
        assert "off" in rendered

    # ---- Subagent ----

    def test_subagent_on(self):
        assert "Subagent" in self._render(
            _make_pacemaker_status(subagent_reminder_enabled=True)
        )

    def test_subagent_idle(self):
        assert "idle" in self._render(
            _make_pacemaker_status(subagent_reminder_enabled=False)
        )

    # ---- Intent Validation ----

    def test_intent_val_on(self):
        rendered = self._render(_make_pacemaker_status(intent_validation_enabled=True))
        assert "Intent Val" in rendered

    def test_intent_val_off(self):
        rendered = self._render(_make_pacemaker_status(intent_validation_enabled=False))
        assert "Intent Val" in rendered
        assert "off" in rendered

    # ---- Langfuse ----

    def test_langfuse_shown_when_enabled(self):
        assert "Langfuse" in self._render(_make_pacemaker_status(langfuse_enabled=True))

    def test_langfuse_connected_indicator(self):
        rendered = self._render(
            _make_pacemaker_status(langfuse_enabled=True, langfuse_connected=True)
        )
        assert "✓" in rendered

    def test_langfuse_disconnected_custom_message(self):
        pm = dict(
            _make_pacemaker_status(langfuse_enabled=True, langfuse_connected=False)
        )
        pm["langfuse_connection"] = {"connected": False, "message": "Unreachable"}
        assert "✗" in self._render(pm)

    # ---- TDD ----

    def test_tdd_shown(self):
        assert "TDD" in self._render(_make_pacemaker_status(tdd_enabled=True))

    # ---- Subagent model preference ----

    def test_preferred_model_auto(self):
        rendered = self._render(
            _make_pacemaker_status(preferred_subagent_model="auto")
        )
        assert "Subagent:" in rendered
        assert "auto" in rendered

    def test_preferred_model_custom(self):
        rendered = self._render(
            _make_pacemaker_status(preferred_subagent_model="sonnet")
        )
        assert "Subagent:" in rendered
        assert "sonnet" in rendered

    # ---- Hook model ----

    def test_hook_model_auto(self):
        rendered = self._render(
            _make_pacemaker_status(hook_model="auto")
        )
        assert "Hook Model:" in rendered

    def test_hook_model_custom(self):
        rendered = self._render(
            _make_pacemaker_status(hook_model="gpt-5")
        )
        assert "Hook Model:" in rendered
        assert "gpt-5" in rendered

    # ---- Log level ----

    def test_log_level_warning(self):
        assert "WARNING" in self._render(_make_pacemaker_status(log_level=2))

    def test_log_level_info(self):
        assert "INFO" in self._render(_make_pacemaker_status(log_level=3))

    def test_log_level_debug(self):
        assert "DEBUG" in self._render(_make_pacemaker_status(log_level=4))

    # ---- Rules count ----

    def test_rules_count_shown(self):
        assert "17" in self._render(_make_pacemaker_status(clean_code_rules_count=17))

    # ---- Versions ----

    def test_pacemaker_version_shown(self):
        assert "2.3.4" in self._render(
            _make_pacemaker_status(pacemaker_version="2.3.4")
        )

    def test_usage_console_version_shown(self):
        assert "1.9.9" in self._render(
            _make_pacemaker_status(usage_console_version="1.9.9")
        )

    # ---- Error count ----

    def test_zero_errors(self):
        rendered = self._render(_make_pacemaker_status(error_count_24h=0))
        assert "Errors 24h" in rendered
        assert "0" in rendered

    def test_low_errors(self):
        assert "5" in self._render(_make_pacemaker_status(error_count_24h=5))

    def test_high_errors(self):
        assert "15" in self._render(_make_pacemaker_status(error_count_24h=15))

    def test_log_large_sentinel(self):
        assert "log large" in self._render(_make_pacemaker_status(error_count_24h=-1))

    # ---- Last update ----

    def test_last_update_shown(self):
        update_time = datetime(2025, 3, 9, 14, 30, 0)
        assert "14:30:00" in self._render(
            _make_pacemaker_status(), last_update=update_time
        )

    # ---- API backoff / fallback ----

    def test_api_backoff_shown_in_fallback_mode(self):
        pm = _make_pacemaker_status(fallback_mode=True, api_backoff_remaining=120)
        rendered = self._render(pm)
        assert "120s" in rendered
        assert "fallback" in rendered

    # ---- Ctrl+C instruction ----

    def test_ctrl_c_instruction_shown(self):
        assert "Ctrl+C" in self._render(_make_pacemaker_status())


# ===========================================================================
# Right column — Blockage statistics
# ===========================================================================


class TestBlockageRowTruncationHelper:
    """Unit coverage for _truncate_blockage_label() (code review, commit 53fb2c2):
    a label long enough to overflow the 21-char blockage column must be
    truncated with an ellipsis so the row's label+colon+space+value never
    exceeds the column width — this is what prevents misalignment/wrapping.
    """

    def setup_method(self):
        self.r = UsageRenderer()

    def test_short_label_returned_unchanged_with_colon(self):
        result = self.r._truncate_blockage_label("Clean Code", "39", width=21)
        assert result == "Clean Code:"

    def test_boundary_label_with_3digit_value_gets_ellipsis(self):
        result = self.r._truncate_blockage_label("Reviewer Unavail.", "123", width=21)
        assert result.endswith("…")
        assert len(result) + 1 + len("123") <= 21

    def test_very_long_unknown_label_gets_ellipsis(self):
        long_label = "Some Really Long Unknown Category Name"
        result = self.r._truncate_blockage_label(long_label, "7", width=21)
        assert result.endswith("…")
        assert len(result) + 1 + len("7") <= 21


class TestRenderBottomSectionBlockages:
    def setup_method(self):
        self.r = UsageRenderer()

    def _render(self, pm, blockage_stats, width=120, **kwargs):
        return _render_to_str(
            self.r.render_bottom_section(pm, blockage_stats, **kwargs), width=width
        )

    def test_blockages_header_present(self):
        assert "Blockages" in self._render(_make_pacemaker_status(), {"Total": 0})

    def test_categories_shown(self):
        stats = {"Intent Validation": 5, "Intent TDD": 2, "Total": 7}
        rendered = self._render(_make_pacemaker_status(), stats)
        assert "Intent Validation" in rendered
        assert "Intent TDD" in rendered

    def test_total_count_shown(self):
        rendered = self._render(
            _make_pacemaker_status(), {"Intent Validation": 3, "Total": 3}
        )
        assert "Total" in rendered
        assert "3" in rendered

    def test_none_blockage_stats_shows_unavailable(self):
        rendered = self._render(_make_pacemaker_status(), blockage_stats=None)
        assert "unavailable" in rendered

    def test_empty_dict_shows_unavailable(self):
        # An empty dict is falsy, so the code takes the else branch: "(unavailable)"
        rendered = self._render(_make_pacemaker_status(), blockage_stats={})
        assert "unavailable" in rendered

    def test_reviewer_unavail_row_value_aligned_two_column(self):
        """Code review (commit 53fb2c2): "Reviewer Unavailable:" was
        exactly 21 chars = blockage_col_width, collapsing _fmt_kv's
        padding to a 1-space fallback and misaligning the value column
        relative to other rows. Both composed rows must total exactly 21
        chars (label+padding+value), matching _fmt_kv's normal alignment.
        """
        stats = {"Clean Code": 39, "Reviewer Unavail.": 0, "Total": 39}
        rendered = self._render(_make_pacemaker_status(), stats)
        assert "Clean Code:        39" in rendered
        assert "Reviewer Unavail.:  0" in rendered

    def test_reviewer_unavail_3digit_row_ellipsis_and_aligned_two_column(self):
        """A 3-digit count leaves no room for the full 18-char
        "Reviewer Unavail.:" label within the 21-char column — it must
        truncate with an ellipsis rather than overflow."""
        stats = {"Reviewer Unavail.": 123, "Total": 123}
        rendered = self._render(_make_pacemaker_status(), stats)
        assert self._segment_on_one_line("Reviewer Unavail… 123", rendered)

    def test_reviewer_unavail_row_no_wrap_single_column_width(self):
        """At the review-flagged narrow threshold (~51 cols), the
        3-digit reviewer-unavailable row must still render on one
        unbroken line, not wrap across two."""
        stats = {"Reviewer Unavail.": 123, "Total": 123}
        rendered = self._render(_make_pacemaker_status(), stats, width=51)
        assert self._segment_on_one_line("Reviewer Unavail… 123", rendered)

    def test_long_unknown_category_row_no_wrap_single_column_width(self):
        """Same long-unknown-category truncation, but at the narrow
        ~51-col width explicitly called out in code review — must stay
        on one line, not wrap."""
        long_label = "Some Really Long Unknown Category Name"
        stats = {long_label: 7, "Total": 7}
        rendered = self._render(_make_pacemaker_status(), stats, width=51)
        assert self._segment_on_one_line("Some Really Long U… 7", rendered)
        assert long_label not in rendered

    @staticmethod
    def _segment_on_one_line(segment, rendered):
        """True iff `segment` (which itself contains no newline) appears
        fully within a single line of `rendered` — proving the row is not
        wrapped across two output lines, not just present somewhere in
        the whole multi-line blob."""
        return any(segment in line for line in rendered.splitlines())

    def test_long_unknown_category_row_ellipsis_and_no_wrap_two_column(self):
        """A category humanized from an unrecognized DB value (see
        _humanize_blockage_category) can be arbitrarily long; it must be
        truncated with an ellipsis rather than wrapping the row."""
        long_label = "Some Really Long Unknown Category Name"
        stats = {long_label: 7, "Total": 7}
        rendered = self._render(_make_pacemaker_status(), stats)
        assert "Some Really Long U… 7" in rendered
        # Sanity: the untruncated label must NOT appear anywhere (proves
        # truncation happened, not an accidental line-length coincidence).
        assert long_label not in rendered


# ===========================================================================
# Right column — Langfuse metrics
# ===========================================================================


class TestRenderBottomSectionLangfuse:
    def setup_method(self):
        self.r = UsageRenderer()

    def _render(self, pm, langfuse_metrics):
        return _render_to_str(
            self.r.render_bottom_section(
                pm, {"Total": 0}, langfuse_metrics=langfuse_metrics
            )
        )

    def test_langfuse_header_always_present(self):
        assert "Langfuse" in self._render(_make_pacemaker_status(), None)

    def test_metrics_values_shown(self):
        metrics = {"sessions": 10, "traces": 25, "spans": 100, "total": 135}
        rendered = self._render(_make_pacemaker_status(), metrics)
        assert "Sessions" in rendered
        assert "10" in rendered
        assert "25" in rendered
        assert "135" in rendered

    def test_none_metrics_shows_unavailable(self):
        assert "unavailable" in self._render(_make_pacemaker_status(), None)


# ===========================================================================
# Right column — Secrets metrics
# ===========================================================================


class TestRenderBottomSectionSecrets:
    def setup_method(self):
        self.r = UsageRenderer()

    def _render(self, pm, secrets_metrics):
        return _render_to_str(
            self.r.render_bottom_section(
                pm, {"Total": 0}, secrets_metrics=secrets_metrics
            )
        )

    def test_secrets_header_always_present(self):
        assert "Secrets" in self._render(_make_pacemaker_status(), None)

    def test_masked_and_stored_counts_shown(self):
        secrets = {"secrets_masked": 7, "secrets_stored": 3}
        rendered = self._render(_make_pacemaker_status(), secrets)
        assert "Masked" in rendered
        assert "7" in rendered
        assert "Stored" in rendered
        assert "3" in rendered

    def test_none_secrets_shows_unavailable(self):
        assert "unavailable" in self._render(_make_pacemaker_status(), None)
