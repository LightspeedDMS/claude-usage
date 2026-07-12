"""Lock-in test for claude-pace-maker Story #85.

Story #85 adds gpt-5.6-sol, gpt-5.6-terra, gpt-5.6-luna, and gpt-5.4-mini as
selectable Codex hook-model reviewers in claude-pace-maker. Per the story's
approved design, plain (non "codex-<profile>") codex tokens — including these
four new models — keep collapsing to the reviewer label "codex-gpt5" in
resolve_and_call_with_reviewer() / _call_single_reviewer() on the pace-maker
side (see claude-pace-maker/src/pacemaker/inference/registry.py and
competitive.py). That means ZERO display-code changes are required here: the
existing "codex-gpt5" -> ("[Codex]", "yellow") entry in REVIEWER_TAGS already
covers every gpt-5.6-*/gpt-5.4-mini validation event.

This test locks in that "codex-gpt5" resolution so a future refactor of
REVIEWER_TAGS or get_reviewer_tag_info() cannot silently break rendering for
the new Story #85 models without a visible test failure here.
"""

from claude_usage.code_mode.display import REVIEWER_TAGS, get_reviewer_tag_info


class TestStory85Gpt56CodexReviewerTagLockIn:
    """codex-gpt5 must still resolve to [Codex]/yellow after Story #85."""

    def test_codex_gpt5_in_reviewer_tags(self):
        assert "codex-gpt5" in REVIEWER_TAGS

    def test_codex_gpt5_exact_entry_is_codex_yellow(self):
        assert REVIEWER_TAGS["codex-gpt5"] == ("[Codex]", "yellow")

    def test_get_reviewer_tag_info_codex_gpt5_returns_codex_yellow(self):
        """The reviewer label produced for gpt-5.6-sol/terra/luna/gpt-5.4-mini
        validations (verbatim "codex-gpt5", per registry.py's non-"codex-"-prefix
        branch) must render as [Codex]/yellow with no display-code change."""
        result = get_reviewer_tag_info("codex-gpt5")
        assert result == ("[Codex]", "yellow")
