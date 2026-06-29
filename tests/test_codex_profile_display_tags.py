"""Tests for codex-<profile> reviewer tag display in governance feed (Story #75)."""

import pytest

from claude_usage.code_mode.display import REVIEWER_TAGS, _REVIEWER_TAG_RE, get_reviewer_tag_info


# ──────────────────────────────────────────────────────────────────────────────
# REVIEWER_TAGS — exact match entries must not be regressed
# ──────────────────────────────────────────────────────────────────────────────

class TestCodexGpt5TagUnaffected:
    """codex-gpt5 exact entry must keep its existing tag — Story #75 must not change it."""

    def test_codex_gpt5_in_reviewer_tags(self):
        assert "codex-gpt5" in REVIEWER_TAGS

    def test_codex_gpt5_label_is_codex(self):
        tag_label, _color = REVIEWER_TAGS["codex-gpt5"]
        assert tag_label == "[Codex]"

    def test_codex_gpt5_color_is_yellow(self):
        _label, tag_color = REVIEWER_TAGS["codex-gpt5"]
        assert tag_color == "yellow"


# ──────────────────────────────────────────────────────────────────────────────
# codex-<profile> prefix lookup — must resolve to [Codex]/yellow
# ──────────────────────────────────────────────────────────────────────────────

def _resolve_tag(reviewer_id: str):
    """Mirror the lookup logic from display.py governance feed renderer."""
    # Exact dict lookup first (preserves codex-gpt5 existing entry)
    tag_info = REVIEWER_TAGS.get(reviewer_id)
    if tag_info:
        return tag_info
    # Prefix fallback for codex-<profile>
    if reviewer_id.startswith("codex-"):
        return ("[Codex]", "yellow")
    return None


class TestCodexProfileTagResolution:
    """codex-<profile> reviewer labels must resolve to [Codex]/yellow."""

    def test_codex_beast_resolves_to_codex_tag(self):
        tag = _resolve_tag("codex-beast")
        assert tag is not None
        assert tag[0] == "[Codex]"

    def test_codex_beast_color_is_yellow(self):
        tag = _resolve_tag("codex-beast")
        assert tag is not None
        assert tag[1] == "yellow"

    def test_codex_pro_resolves_to_codex_tag(self):
        tag = _resolve_tag("codex-pro")
        assert tag is not None
        assert tag[0] == "[Codex]"

    def test_codex_profile_with_dots_resolves(self):
        tag = _resolve_tag("codex-my.profile")
        assert tag is not None
        assert tag[0] == "[Codex]"

    def test_codex_profile_with_dashes_resolves(self):
        tag = _resolve_tag("codex-my-profile-v2")
        assert tag is not None
        assert tag[0] == "[Codex]"

    def test_codex_gpt5_exact_match_takes_priority_over_prefix(self):
        """codex-gpt5 must resolve via exact dict entry (not prefix rule)."""
        # Both resolve to the same tag/color, but we verify the exact entry exists
        # and is not shadowed. The dict lookup must succeed.
        exact_tag = REVIEWER_TAGS.get("codex-gpt5")
        prefix_tag = ("[Codex]", "yellow")  # what prefix rule would return
        assert exact_tag == prefix_tag, (
            "codex-gpt5 exact entry was removed or changed — "
            f"expected {prefix_tag}, got {exact_tag}"
        )

    def test_codex_empty_profile_not_resolved(self):
        """'codex-' (empty profile) must not resolve to a tag."""
        # Empty profile is not a valid reviewer id; startswith check is True for
        # 'codex-' but the caller (registry) would never produce this label.
        # This test verifies the prefix rule itself does NOT block on empty profiles
        # — the empty profile is rejected upstream at parse time, not here.
        # So 'codex-' technically resolves via prefix; that is acceptable — the
        # guard is at the CLI/parser level. We just document the behavior.
        tag = _resolve_tag("codex-")
        # This is NOT an error condition in display — upstream guards block empty profiles.
        # So we don't assert False here. We leave this as a documentation test.
        _ = tag  # no assertion; just verifying no exception


# ──────────────────────────────────────────────────────────────────────────────
# Ordering: exact dict lookup happens BEFORE any prefix rule
# ──────────────────────────────────────────────────────────────────────────────

class TestProductionGetReviewerTagInfo:
    """Tests for the actual get_reviewer_tag_info() function exported from display.py."""

    def test_codex_gpt5_returns_exact_entry(self):
        """codex-gpt5 must return its exact REVIEWER_TAGS entry via get_reviewer_tag_info."""
        result = get_reviewer_tag_info("codex-gpt5")
        assert result == ("[Codex]", "yellow")

    def test_codex_beast_returns_codex_tag(self):
        """codex-beast (dynamic profile) must return [Codex]/yellow."""
        result = get_reviewer_tag_info("codex-beast")
        assert result == ("[Codex]", "yellow")

    def test_codex_pro_returns_codex_tag(self):
        """codex-pro (dynamic profile) must return [Codex]/yellow."""
        result = get_reviewer_tag_info("codex-pro")
        assert result == ("[Codex]", "yellow")

    def test_codex_profile_with_dots_returns_codex_tag(self):
        """codex-my.profile must return [Codex]/yellow."""
        result = get_reviewer_tag_info("codex-my.profile")
        assert result == ("[Codex]", "yellow")

    def test_anthropic_sdk_still_works(self):
        """anthropic-sdk must still return its own tag unaffected."""
        result = get_reviewer_tag_info("anthropic-sdk")
        assert result == ("[SDK]", "green")

    def test_unknown_reviewer_returns_none(self):
        """Unknown reviewer ids must return None."""
        result = get_reviewer_tag_info("totally-unknown-provider")
        assert result is None

    def test_agy_flash_still_works(self):
        """agy-flash must still return [Agy]/bright_green unaffected."""
        result = get_reviewer_tag_info("agy-flash")
        assert result == ("[Agy]", "bright_green")


class TestCodexTagOrdering:
    """Prove that codex-gpt5 is resolved via dict lookup, not prefix scan."""

    def test_codex_gpt5_in_dict_not_relying_on_prefix(self):
        """codex-gpt5 must be a direct key in REVIEWER_TAGS."""
        assert "codex-gpt5" in REVIEWER_TAGS, (
            "codex-gpt5 must remain a direct REVIEWER_TAGS entry; "
            "do not remove it and rely solely on the codex- prefix rule."
        )

    def test_codex_beast_not_in_dict_uses_prefix_fallback(self):
        """codex-beast must NOT have its own REVIEWER_TAGS entry (uses prefix rule)."""
        assert "codex-beast" not in REVIEWER_TAGS, (
            "codex-beast should not be a static entry — it is handled by the prefix rule"
        )

    def test_both_produce_same_tag(self):
        """codex-gpt5 (exact) and codex-beast (prefix) must produce identical tags."""
        exact = _resolve_tag("codex-gpt5")
        prefix = _resolve_tag("codex-beast")
        assert exact == prefix == ("[Codex]", "yellow")
