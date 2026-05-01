"""Shared pace-maker data fetching logic.

Centralises the augmentation of pacemaker_status and retrieval of blockage
stats, metrics, and event feeds — logic that was previously duplicated between
code_mode/monitor.py and console_mode/monitor.py.
"""

from __future__ import annotations

import importlib.util
import logging
from collections import namedtuple
from typing import Optional

_log = logging.getLogger(__name__)

_ACTIVITY_WINDOW_SECONDS = 10
_GOVERNANCE_WINDOW_SECONDS = 3600
_ERROR_COUNT_WINDOW_HOURS = 24

PaceMakerBundle = namedtuple(
    "PaceMakerBundle",
    [
        "pacemaker_status",
        "blockage_stats",
        "langfuse_metrics",
        "secrets_metrics",
        "activity_events",
        "governance_events",
    ],
)


def _safe_read(fn, label: str):
    """Call fn; log debug and return None on any exception.

    Reserved for stats, metrics, and event fetches where silent degradation
    is acceptable.  Not used for core status or augmentation calls.
    """
    try:
        return fn()
    except Exception as exc:
        _log.debug("pacemaker %s failed: %s", label, exc)
        return None


def _get_usage_console_version() -> str:
    """Return claude_usage.__version__; thin wrapper so tests can patch it.

    Raises:
        ImportError: when the package version is not importable.
    """
    from claude_usage import __version__

    return __version__


def _import_usage_model(reader):
    """Load UsageModel via importlib without mutating sys.path.

    Uses spec_from_file_location when reader provides a source path; falls
    back to a normal import otherwise.  Logs debug and returns None on any
    failure so callers degrade gracefully.
    """
    try:
        pm_src = reader._get_pacemaker_src_path()
        if pm_src is not None:
            spec = importlib.util.spec_from_file_location(
                "pacemaker.usage_model", pm_src / "pacemaker" / "usage_model.py"
            )
            if spec is not None and spec.loader is not None:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                return mod.UsageModel
        from pacemaker.usage_model import UsageModel

        return UsageModel
    except Exception as exc:
        _log.debug("pacemaker UsageModel not importable: %s", exc)
        return None


def _augment_status(reader, status: dict, include_weekly_limit: bool) -> None:
    """Inject augmentation keys into *status* in-place.

    When include_weekly_limit=False, removes weekly_limit_enabled from the
    dict (console mode does not render weekly-limit bars).
    Fallbacks: usage_console_version->"unknown" on ImportError;
    api_backoff_remaining->0 on unavailable/AttributeError/OSError.
    """
    if not include_weekly_limit:
        status.pop("weekly_limit_enabled", None)
    status["langfuse_enabled"] = reader.get_langfuse_status()
    status["langfuse_connection"] = reader.test_langfuse_connection()
    status["pacemaker_version"] = reader.get_pacemaker_version()
    try:
        status["usage_console_version"] = _get_usage_console_version()
    except ImportError as exc:
        _log.debug("claude_usage.__version__ import failed: %s", exc)
        status["usage_console_version"] = "unknown"
    status["error_count_24h"] = reader.get_recent_error_count(_ERROR_COUNT_WINDOW_HOURS)
    UsageModel = _import_usage_model(reader)
    try:
        if UsageModel is None:
            status["api_backoff_remaining"] = 0
        else:
            model = UsageModel()
            status["api_backoff_remaining"] = (
                model.get_backoff_remaining() if model.is_in_backoff() else 0
            )
    except (AttributeError, OSError) as exc:
        _log.debug("pacemaker backoff check failed: %s", exc)
        status["api_backoff_remaining"] = 0


def fetch_pacemaker_bundle(
    reader, include_weekly_limit: bool
) -> Optional[PaceMakerBundle]:
    """Fetch and augment all pace-maker data into a single bundle.

    Returns None when pace-maker is not installed.
    Returns a PaceMakerBundle with pacemaker_status=None when get_status()
    returns None.  include_weekly_limit controls weekly_limit_enabled retention.
    """
    if not reader.is_installed():
        return None
    pacemaker_status = reader.get_status()
    if pacemaker_status is not None:
        _augment_status(reader, pacemaker_status, include_weekly_limit)
    return PaceMakerBundle(
        pacemaker_status=pacemaker_status,
        blockage_stats=_safe_read(
            reader.get_blockage_stats_with_labels, "get_blockage_stats_with_labels"
        ),
        langfuse_metrics=_safe_read(
            reader.get_langfuse_metrics, "get_langfuse_metrics"
        ),
        secrets_metrics=_safe_read(reader.get_secrets_metrics, "get_secrets_metrics"),
        activity_events=_safe_read(
            lambda: reader.get_recent_activity(window_seconds=_ACTIVITY_WINDOW_SECONDS),
            "get_recent_activity",
        ),
        governance_events=_safe_read(
            lambda: reader.get_governance_events(
                window_seconds=_GOVERNANCE_WINDOW_SECONDS
            ),
            "get_governance_events",
        ),
    )
