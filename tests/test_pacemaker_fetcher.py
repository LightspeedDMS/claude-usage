"""Tests for claude_usage.shared.pacemaker_fetcher.fetch_pacemaker_bundle.

TDD spec: fetch_pacemaker_bundle() centralises all pace-maker augmentation
logic shared between code_mode/monitor.py and console_mode/monitor.py.

Behaviors under test:
 1. Returns None when reader.is_installed() is False.
 2. Returns bundle with all named fields populated; pacemaker_status preserves
    source fields from get_status().
 3. pacemaker_status is augmented with langfuse_enabled, langfuse_connection,
    pacemaker_version, usage_console_version, error_count_24h, api_backoff_remaining.
 4. include_weekly_limit=True  → weekly_limit_enabled present in pacemaker_status.
    include_weekly_limit=False → weekly_limit_enabled NOT injected by fetcher.
 5. usage_console_version falls back to "unknown" when version import raises.
 6. api_backoff_remaining: 0 when UsageModel unavailable; from model when available;
    0 on AttributeError from model constructor.
 7. Bundle returned with pacemaker_status=None when get_status() returns None.
 8. activity_events/governance_events is None when their reader methods raise.

All invocations of fetch_pacemaker_bundle go through the module-level
_fetch_bundle() helper to eliminate repeated arrange/act blocks.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

_MODULE = "claude_usage.shared.pacemaker_fetcher"

# Sentinel: distinguish "use default" from "explicitly pass None"
_UNSET = object()


# ---------------------------------------------------------------------------
# Test infrastructure helpers
# ---------------------------------------------------------------------------

def _make_reader(
    *,
    installed: bool = True,
    status: object = _UNSET,
    langfuse_enabled: bool = False,
    langfuse_connection: dict | None = None,
    pacemaker_version: str = "1.0.0",
    error_count: int = 0,
    blockage_stats: dict | None = None,
    langfuse_metrics: dict | None = None,
    secrets_metrics: dict | None = None,
    activity_events: list | None = None,
    governance_events: list | None = None,
) -> MagicMock:
    """Build a mock PaceMakerReader.

    Pass status=None to make get_status() return None explicitly.
    Omit status to use the default {"enabled": True} dict.
    """
    reader = MagicMock()
    reader.is_installed.return_value = installed
    reader.get_status.return_value = (
        {"enabled": True} if status is _UNSET else status
    )
    reader.get_langfuse_status.return_value = langfuse_enabled
    reader.test_langfuse_connection.return_value = (
        langfuse_connection if langfuse_connection is not None else {"connected": False}
    )
    reader.get_pacemaker_version.return_value = pacemaker_version
    reader.get_recent_error_count.return_value = error_count
    reader.get_blockage_stats_with_labels.return_value = (
        blockage_stats if blockage_stats is not None else {}
    )
    reader.get_langfuse_metrics.return_value = (
        langfuse_metrics if langfuse_metrics is not None else {}
    )
    reader.get_secrets_metrics.return_value = (
        secrets_metrics if secrets_metrics is not None else {}
    )
    reader.get_recent_activity.return_value = (
        activity_events if activity_events is not None else []
    )
    reader.get_governance_events.return_value = (
        governance_events if governance_events is not None else []
    )
    reader._get_pacemaker_src_path.return_value = None
    return reader


def _fetch_bundle(reader, include_weekly_limit: bool, *, model_cls=None):
    """Call fetch_pacemaker_bundle with _import_usage_model patched.

    All tests route through this helper so the import and patch setup
    are never duplicated in test bodies.

    Args:
        reader: mock PaceMakerReader.
        include_weekly_limit: forwarded to fetch_pacemaker_bundle.
        model_cls: if None, UsageModel is unavailable; otherwise the class
            to return from _import_usage_model.

    Returns:
        The PaceMakerBundle (or None).
    """
    from claude_usage.shared.pacemaker_fetcher import fetch_pacemaker_bundle

    with patch(f"{_MODULE}._import_usage_model", return_value=model_cls):
        return fetch_pacemaker_bundle(reader, include_weekly_limit=include_weekly_limit)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFetchPacemakerBundleNotInstalled(unittest.TestCase):
    """Behavior 1: returns None when pace-maker is not installed."""

    def test_returns_none_regardless_of_include_weekly_limit(self):
        """is_installed()=False → None for both include_weekly_limit values."""
        reader = _make_reader(installed=False)
        for flag in (True, False):
            with self.subTest(include_weekly_limit=flag):
                result = _fetch_bundle(reader, include_weekly_limit=flag)
                self.assertIsNone(result)
        reader.get_status.assert_not_called()


class TestFetchPacemakerBundleAllFields(unittest.TestCase):
    """Behaviors 2 & 7: bundle fields and status=None handling."""

    def test_all_bundle_fields_populated_and_status_preserves_source(self):
        """Bundle has all named fields; pacemaker_status preserves get_status() keys."""
        reader = _make_reader(
            status={"enabled": True, "sentinel_key": "sentinel_val"},
            blockage_stats={"Intent": 3},
            langfuse_metrics={"total_traces": 5},
            secrets_metrics={"total": 1},
            activity_events=[{"ts": 10}],
            governance_events=[{"ts": 20, "decision": "allow"}],
        )
        bundle = _fetch_bundle(reader, include_weekly_limit=False)

        self.assertIsNotNone(bundle)
        self.assertEqual(bundle.pacemaker_status["enabled"], True)
        self.assertEqual(bundle.pacemaker_status["sentinel_key"], "sentinel_val")
        self.assertEqual(bundle.blockage_stats, {"Intent": 3})
        self.assertEqual(bundle.langfuse_metrics, {"total_traces": 5})
        self.assertEqual(bundle.secrets_metrics, {"total": 1})
        self.assertEqual(bundle.activity_events, [{"ts": 10}])
        self.assertEqual(bundle.governance_events, [{"ts": 20, "decision": "allow"}])

    def test_bundle_returned_with_none_pacemaker_status(self):
        """get_status()=None → bundle is returned but pacemaker_status is None."""
        reader = _make_reader(status=None)
        bundle = _fetch_bundle(reader, include_weekly_limit=False)

        self.assertIsNotNone(bundle)
        self.assertIsNone(bundle.pacemaker_status)


class TestFetchPacemakerBundleStatusAugmentation(unittest.TestCase):
    """Behavior 3: pacemaker_status is augmented with all required keys and values."""

    def test_augmentation_keys_all_present(self):
        """All augmentation keys are present in pacemaker_status (subTest per key)."""
        required_keys = [
            "langfuse_enabled",
            "langfuse_connection",
            "pacemaker_version",
            "usage_console_version",
            "error_count_24h",
            "api_backoff_remaining",
        ]
        reader = _make_reader(
            langfuse_enabled=True,
            langfuse_connection={"connected": True},
            pacemaker_version="3.1.4",
            error_count=7,
        )
        bundle = _fetch_bundle(reader, include_weekly_limit=False)

        for key in required_keys:
            with self.subTest(key=key):
                self.assertIn(key, bundle.pacemaker_status)

    def test_augmentation_values_match_reader_returns(self):
        """Augmented values match what the reader methods returned."""
        reader = _make_reader(
            langfuse_enabled=True,
            langfuse_connection={"connected": True, "url": "http://lf"},
            pacemaker_version="3.1.4",
            error_count=7,
        )
        bundle = _fetch_bundle(reader, include_weekly_limit=False)

        self.assertTrue(bundle.pacemaker_status["langfuse_enabled"])
        self.assertEqual(
            bundle.pacemaker_status["langfuse_connection"],
            {"connected": True, "url": "http://lf"},
        )
        self.assertEqual(bundle.pacemaker_status["pacemaker_version"], "3.1.4")
        self.assertEqual(bundle.pacemaker_status["error_count_24h"], 7)


class TestFetchPacemakerBundleWeeklyLimit(unittest.TestCase):
    """Behavior 4: include_weekly_limit controls weekly_limit_enabled injection."""

    def test_weekly_limit_injection_per_flag(self):
        """subTest table: weekly_limit_enabled presence and value per flag."""
        cases = [
            (True,  {"enabled": True, "weekly_limit_enabled": True},  True,  True),
            (True,  {"enabled": True, "weekly_limit_enabled": False}, True,  False),
            (False, {"enabled": True},                                False, None),
        ]
        for include_flag, status, expect_key, expect_value in cases:
            with self.subTest(include_flag=include_flag):
                reader = _make_reader(status=status)
                bundle = _fetch_bundle(reader, include_weekly_limit=include_flag)

                if expect_key:
                    self.assertIn("weekly_limit_enabled", bundle.pacemaker_status)
                    self.assertEqual(
                        bundle.pacemaker_status["weekly_limit_enabled"], expect_value
                    )
                else:
                    self.assertNotIn("weekly_limit_enabled", bundle.pacemaker_status)


class TestFetchPacemakerBundleVersionAndBackoff(unittest.TestCase):
    """Behaviors 5 & 6: version fallback and api_backoff_remaining variants."""

    def test_usage_console_version_unknown_on_import_error(self):
        """_get_usage_console_version raising ImportError → version is 'unknown'."""
        reader = _make_reader()
        with patch(
            f"{_MODULE}._get_usage_console_version",
            side_effect=ImportError("no module"),
        ):
            bundle = _fetch_bundle(reader, include_weekly_limit=False)

        self.assertEqual(bundle.pacemaker_status["usage_console_version"], "unknown")

    def test_api_backoff_remaining_variants(self):
        """subTest table: api_backoff_remaining for all UsageModel states."""
        mock_in_backoff = MagicMock()
        mock_in_backoff.is_in_backoff.return_value = True
        mock_in_backoff.get_backoff_remaining.return_value = 42.0

        mock_not_in_backoff = MagicMock()
        mock_not_in_backoff.is_in_backoff.return_value = False

        cases = [
            ("model_unavailable",  None,                                              0),
            ("in_backoff",         MagicMock(return_value=mock_in_backoff),           42.0),
            ("not_in_backoff",     MagicMock(return_value=mock_not_in_backoff),       0),
            ("attribute_error",    MagicMock(side_effect=AttributeError("bad attr")), 0),
        ]
        for case_name, model_cls, expected in cases:
            with self.subTest(case=case_name):
                reader = _make_reader()
                bundle = _fetch_bundle(
                    reader,
                    include_weekly_limit=False,
                    model_cls=model_cls,
                )
                self.assertEqual(
                    bundle.pacemaker_status["api_backoff_remaining"], expected
                )


class TestFetchPacemakerBundleEventExceptions(unittest.TestCase):
    """Behavior 8: event-fetch exceptions yield None fields, not propagated."""

    def test_event_fields_none_on_reader_exception(self):
        """subTest table: activity_events and governance_events become None on raise."""
        cases = [
            ("activity_events",   "get_recent_activity"),
            ("governance_events", "get_governance_events"),
        ]
        for field_name, method_name in cases:
            with self.subTest(field=field_name):
                reader = _make_reader()
                getattr(reader, method_name).side_effect = RuntimeError("db locked")
                bundle = _fetch_bundle(reader, include_weekly_limit=False)
                self.assertIsNone(getattr(bundle, field_name))


if __name__ == "__main__":
    unittest.main()
