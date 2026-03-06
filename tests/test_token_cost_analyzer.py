"""
Tests for token_cost_analyzer module.

TDD approach: these tests are written before the implementation.
They define the expected behavior of each public function.

Split into multiple increments:
- Increment 1 (this file): classify_model, parse_transcript_file, parse_transcript_timestamp
- Increment 2 (appended): build_intervals, filter_negative_deltas
- Increment 3 (appended): run_regression, empty transcripts handling
"""

import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone

import pytest

# The module under test — will fail import until implementation exists
from claude_usage.tools.token_cost_analyzer.core import (
    classify_model,
    parse_transcript_file,
    parse_transcript_timestamp,
)


# ---------------------------------------------------------------------------
# 1. classify_model
# ---------------------------------------------------------------------------


class TestClassifyModel:
    def test_opus_variants(self):
        assert classify_model("claude-opus-4-6") == "opus"
        assert classify_model("claude-opus-4-5") == "opus"
        assert classify_model("claude-opus-3-opus-20240229") == "opus"
        assert classify_model("CLAUDE-OPUS-4-6") == "opus"  # case-insensitive

    def test_sonnet_variants(self):
        assert classify_model("claude-sonnet-4-5-20250929") == "sonnet"
        assert classify_model("claude-sonnet-4-6") == "sonnet"
        assert classify_model("claude-sonnet-3-5") == "sonnet"

    def test_haiku_variants(self):
        assert classify_model("claude-haiku-4-5") == "haiku"
        assert classify_model("claude-haiku-3") == "haiku"

    def test_unknown_returns_none(self):
        assert classify_model("gpt-4") is None
        assert classify_model("") is None
        assert classify_model("claude-unknown-model") is None

    def test_custom_model_id_returns_none(self):
        # Custom/internal IDs that don't contain opus/sonnet/haiku
        assert classify_model("cmlpfbsh8002lpa07y6n3z76s") is None


# ---------------------------------------------------------------------------
# 2. parse_transcript_timestamp
# ---------------------------------------------------------------------------


class TestParseTranscriptTimestamp:
    def test_iso8601_to_epoch(self):
        ts = "2026-03-05T15:04:51.468Z"
        result = parse_transcript_timestamp(ts)
        expected = datetime(2026, 3, 5, 15, 4, 51, tzinfo=timezone.utc).timestamp()
        assert result == pytest.approx(expected, abs=1)

    def test_no_milliseconds(self):
        ts = "2026-01-01T00:00:00Z"
        result = parse_transcript_timestamp(ts)
        expected = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp()
        assert result == pytest.approx(expected, abs=1)


# ---------------------------------------------------------------------------
# 3. parse_transcript_file — deduplication of consecutive identical usage
# ---------------------------------------------------------------------------


class TestParseTranscriptFile:
    def _make_entry(self, ts, model, input_t, output_t, cache_read=0, cache_create=0):
        return json.dumps(
            {
                "type": "assistant",
                "timestamp": ts,
                "message": {
                    "model": model,
                    "usage": {
                        "input_tokens": input_t,
                        "output_tokens": output_t,
                        "cache_read_input_tokens": cache_read,
                        "cache_creation_input_tokens": cache_create,
                    },
                },
            }
        )

    def test_single_entry_returned(self):
        entry = self._make_entry("2026-03-05T10:00:00.000Z", "claude-opus-4-6", 100, 50)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(entry + "\n")
            path = f.name
        try:
            result = parse_transcript_file(path)
            assert len(result) == 1
            assert result[0]["model_family"] == "opus"
            assert result[0]["input_tokens"] == 100
            assert result[0]["output_tokens"] == 50
        finally:
            os.unlink(path)

    def test_duplicate_consecutive_entries_collapsed(self):
        """Claude writes 2-4 identical usage entries per API turn; collapse to 1."""
        entry = self._make_entry(
            "2026-03-05T10:00:00.000Z", "claude-sonnet-4-6", 200, 80
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            for _ in range(3):
                f.write(entry + "\n")
            path = f.name
        try:
            result = parse_transcript_file(path)
            assert len(result) == 1
        finally:
            os.unlink(path)

    def test_different_usage_entries_both_kept(self):
        """Two entries with different usage values are distinct API turns."""
        entry1 = self._make_entry(
            "2026-03-05T10:00:00.000Z", "claude-opus-4-6", 100, 50
        )
        entry2 = self._make_entry(
            "2026-03-05T10:01:00.000Z", "claude-opus-4-6", 150, 70
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(entry1 + "\n")
            f.write(entry2 + "\n")
            path = f.name
        try:
            result = parse_transcript_file(path)
            assert len(result) == 2
        finally:
            os.unlink(path)

    def test_unknown_model_skipped(self):
        entry = self._make_entry("2026-03-05T10:00:00.000Z", "gpt-4", 100, 50)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(entry + "\n")
            path = f.name
        try:
            result = parse_transcript_file(path)
            assert len(result) == 0
        finally:
            os.unlink(path)

    def test_lines_without_usage_skipped(self):
        lines = [
            json.dumps(
                {
                    "type": "user",
                    "timestamp": "2026-03-05T10:00:00.000Z",
                    "message": {"content": "Hello"},
                }
            ),
            self._make_entry("2026-03-05T10:01:00.000Z", "claude-sonnet-4-6", 10, 5),
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            for line in lines:
                f.write(line + "\n")
            path = f.name
        try:
            result = parse_transcript_file(path)
            assert len(result) == 1
        finally:
            os.unlink(path)

    def test_malformed_json_lines_skipped(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write("not valid json\n")
            f.write(
                self._make_entry("2026-03-05T10:00:00.000Z", "claude-opus-4-6", 10, 5)
                + "\n"
            )
            path = f.name
        try:
            result = parse_transcript_file(path)
            assert len(result) == 1
        finally:
            os.unlink(path)

    def test_timestamp_converted_to_epoch(self):
        entry = self._make_entry("2026-03-05T00:00:00.000Z", "claude-opus-4-6", 1, 1)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(entry + "\n")
            path = f.name
        try:
            result = parse_transcript_file(path)
            expected = datetime(2026, 3, 5, 0, 0, 0, tzinfo=timezone.utc).timestamp()
            assert result[0]["timestamp"] == pytest.approx(expected, abs=1)
        finally:
            os.unlink(path)

    def test_cache_tokens_parsed(self):
        entry = self._make_entry(
            "2026-03-05T10:00:00.000Z",
            "claude-opus-4-6",
            input_t=10,
            output_t=5,
            cache_read=1000,
            cache_create=5000,
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(entry + "\n")
            path = f.name
        try:
            result = parse_transcript_file(path)
            assert result[0]["cache_read_tokens"] == 1000
            assert result[0]["cache_creation_tokens"] == 5000
        finally:
            os.unlink(path)

    def test_empty_file_returns_empty_list(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name
        try:
            result = parse_transcript_file(path)
            assert result == []
        finally:
            os.unlink(path)

    def test_file_with_only_non_usage_lines(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps({"type": "user", "message": "hello"}) + "\n")
            f.write(json.dumps({"type": "system", "info": "start"}) + "\n")
            path = f.name
        try:
            result = parse_transcript_file(path)
            assert result == []
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Increment 2a: build_intervals
# ---------------------------------------------------------------------------

from claude_usage.tools.token_cost_analyzer.intervals import (
    build_intervals,
)  # noqa: E402


def _make_event(ts, family, inp, out, cr=0, cc=0):
    return {
        "timestamp": ts,
        "model_family": family,
        "input_tokens": inp,
        "output_tokens": out,
        "cache_read_tokens": cr,
        "cache_creation_tokens": cc,
    }


class TestBuildIntervals:
    def test_tokens_assigned_to_correct_interval(self):
        snapshots = [(1000, 10.0, 5.0), (2000, 11.0, 5.5)]
        events = [_make_event(1500, "opus", 1_000_000, 0)]
        X_5h, y_5h, X_7d, y_7d = build_intervals(snapshots, events)
        assert X_5h.shape[0] == 1
        assert y_5h[0] == pytest.approx(1.0)  # delta five_hour = 11.0 - 10.0
        assert X_5h[0, 0] == pytest.approx(1.0)  # opus_input col 0: 1M tokens

    def test_negative_delta_intervals_excluded(self):
        snapshots = [(1000, 20.0, 10.0), (2000, 15.0, 8.0)]
        events = [_make_event(1500, "sonnet", 500_000, 0)]
        X_5h, y_5h, X_7d, y_7d = build_intervals(snapshots, events)
        assert X_5h.shape[0] == 0

    def test_zero_token_intervals_excluded(self):
        snapshots = [(1000, 10.0, 5.0), (2000, 11.0, 5.5)]
        X_5h, y_5h, X_7d, y_7d = build_intervals(snapshots, [])
        assert X_5h.shape[0] == 0

    def test_tokens_outside_interval_not_counted(self):
        snapshots = [(1000, 10.0, 5.0), (2000, 11.0, 5.5)]
        events = [_make_event(999, "opus", 1_000_000, 0)]
        X_5h, y_5h, X_7d, y_7d = build_intervals(snapshots, events)
        assert X_5h.shape[0] == 0

    def test_multiple_model_families_in_same_interval(self):
        snapshots = [(1000, 10.0, 5.0), (2000, 13.0, 6.5)]
        events = [
            _make_event(1100, "opus", 1_000_000, 0),
            _make_event(1200, "sonnet", 0, 1_000_000),
        ]
        X_5h, y_5h, X_7d, y_7d = build_intervals(snapshots, events)
        assert X_5h.shape[0] == 1
        assert X_5h[0, 0] == pytest.approx(1.0)  # opus_input col 0
        assert X_5h[0, 5] == pytest.approx(1.0)  # sonnet_output col 5

    def test_feature_matrix_has_12_columns(self):
        snapshots = [(1000, 10.0, 5.0), (2000, 11.0, 5.5)]
        events = [_make_event(1500, "haiku", 500_000, 200_000)]
        X_5h, y_5h, X_7d, y_7d = build_intervals(snapshots, events)
        assert X_5h.shape[1] == 12

    def test_tokens_scaled_to_millions(self):
        snapshots = [(1000, 10.0, 5.0), (2000, 11.0, 5.5)]
        events = [_make_event(1500, "opus", 500_000, 0)]
        X_5h, y_5h, X_7d, y_7d = build_intervals(snapshots, events)
        assert X_5h[0, 0] == pytest.approx(0.5)

    def test_single_snapshot_returns_empty(self):
        snapshots = [(1000, 10.0, 5.0)]
        events = [_make_event(500, "opus", 1_000_000, 0)]
        X_5h, y_5h, X_7d, y_7d = build_intervals(snapshots, events)
        assert X_5h.shape[0] == 0


# ---------------------------------------------------------------------------
# Increment 2b: TestFilterNegativeDeltas
# ---------------------------------------------------------------------------


class TestFilterNegativeDeltas:
    """Focused tests on negative-delta filtering across multiple intervals."""

    def test_mixed_positive_negative_intervals(self):
        snapshots = [
            (1000, 10.0, 5.0),
            (2000, 12.0, 6.0),  # +2.0 five_hour — KEEP
            (3000, 11.0, 5.5),  # -1.0 five_hour — DROP
            (4000, 13.0, 6.5),  # +2.0 five_hour — KEEP
        ]
        events = [
            _make_event(1500, "opus", 1_000_000, 0),
            _make_event(2500, "opus", 1_000_000, 0),
            _make_event(3500, "opus", 1_000_000, 0),
        ]
        X_5h, y_5h, X_7d, y_7d = build_intervals(snapshots, events)
        assert X_5h.shape[0] == 2
        assert all(y >= 0 for y in y_5h)

    def test_zero_delta_excluded(self):
        snapshots = [(1000, 10.0, 5.0), (2000, 10.0, 5.0)]
        events = [_make_event(1500, "opus", 1_000_000, 0)]
        X_5h, y_5h, X_7d, y_7d = build_intervals(snapshots, events)
        assert X_5h.shape[0] == 0


# ---------------------------------------------------------------------------
# Increment 2c: TestR2Label and TestFormatResults
# ---------------------------------------------------------------------------

from claude_usage.tools.token_cost_analyzer.regression import (  # noqa: E402
    format_raw_results as format_results,
    _r2_label,
)


class TestR2Label:
    def test_excellent_at_0_9(self):
        assert "excellent" in _r2_label(0.9)
        assert "excellent" in _r2_label(1.0)

    def test_good_at_0_7(self):
        assert "good" in _r2_label(0.7)
        assert "good" in _r2_label(0.89)

    def test_moderate_at_0_5(self):
        assert "moderate" in _r2_label(0.5)
        assert "moderate" in _r2_label(0.69)

    def test_poor_below_0_5(self):
        assert "poor" in _r2_label(0.0)
        assert "poor" in _r2_label(0.49)


class TestFormatResults:
    def _make_coeffs(self, opus_inp=0.042, opus_out=0.213, sonnet_out=0.043):
        coeffs = np.zeros(12)
        coeffs[0] = opus_inp  # opus_input
        coeffs[1] = opus_out  # opus_output
        coeffs[5] = sonnet_out  # sonnet_output
        return coeffs

    def _make_meta(self):
        return {
            "date_range": ("2026-01-01", "2026-03-06"),
            "n_intervals_5h": 500,
            "n_intervals_7d": 400,
            "total_tokens": 45_000_000,
        }

    def test_output_is_string(self):
        coeffs = self._make_coeffs()
        result = format_results(coeffs, coeffs, 0.87, 0.82, self._make_meta())
        assert isinstance(result, str)

    def test_contains_model_families(self):
        coeffs = self._make_coeffs()
        result = format_results(coeffs, coeffs, 0.87, 0.82, self._make_meta())
        assert "Opus" in result
        assert "Sonnet" in result
        assert "Haiku" in result

    def test_contains_r_squared(self):
        coeffs = self._make_coeffs()
        result = format_results(coeffs, coeffs, 0.87, 0.82, self._make_meta())
        assert "R" in result and "0.87" in result

    def test_zero_denominator_ratio_shows_na(self):
        coeffs = np.zeros(12)
        result = format_results(coeffs, coeffs, 0.5, 0.4, self._make_meta())
        assert "N/A" in result

    def test_ratio_computed_when_denominator_nonzero(self):
        coeffs = self._make_coeffs(opus_inp=0.042, opus_out=0.213, sonnet_out=0.043)
        result = format_results(coeffs, coeffs, 0.87, 0.82, self._make_meta())
        assert "x" in result  # ratio shown with x suffix


# ---------------------------------------------------------------------------
# Increment 2d: TestLoadSnapshots
# ---------------------------------------------------------------------------

from claude_usage.tools.token_cost_analyzer.core import load_snapshots  # noqa: E402


class TestLoadSnapshots:
    def _make_db(self, rows):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        conn = sqlite3.connect(path)
        conn.execute(
            """
            CREATE TABLE usage_snapshots (
                id INTEGER PRIMARY KEY,
                timestamp INTEGER NOT NULL,
                five_hour_util REAL NOT NULL,
                five_hour_resets_at TEXT,
                seven_day_util REAL NOT NULL,
                seven_day_resets_at TEXT,
                session_id TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )
        """
        )
        conn.executemany("INSERT INTO usage_snapshots VALUES (?,?,?,?,?,?,?,?)", rows)
        conn.commit()
        conn.close()
        return path

    def test_returns_sorted_by_timestamp(self):
        rows = [
            (1, 1000, 10.0, None, 20.0, None, "s1", 1000),
            (2, 500, 5.0, None, 10.0, None, "s1", 500),
            (3, 1500, 15.0, None, 30.0, None, "s1", 1500),
        ]
        path = self._make_db(rows)
        try:
            snaps = load_snapshots(path)
            timestamps = [s[0] for s in snaps]
            assert timestamps == sorted(timestamps)
        finally:
            os.unlink(path)

    def test_returns_timestamp_five_hour_seven_day_tuples(self):
        rows = [(1, 1000, 42.5, None, 17.3, None, "s1", 1000)]
        path = self._make_db(rows)
        try:
            snaps = load_snapshots(path)
            assert len(snaps) == 1
            ts, five_h, seven_d = snaps[0]
            assert ts == 1000
            assert five_h == pytest.approx(42.5)
            assert seven_d == pytest.approx(17.3)
        finally:
            os.unlink(path)

    def test_empty_db_returns_empty_list(self):
        path = self._make_db([])
        try:
            snaps = load_snapshots(path)
            assert snaps == []
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Increment 2e: TestCollectAllTokenEvents
# ---------------------------------------------------------------------------

from claude_usage.tools.token_cost_analyzer.core import (
    collect_all_token_events,
)  # noqa: E402


class TestCollectAllTokenEvents:
    def _write_jsonl(self, directory, filename, entries):
        path = os.path.join(directory, filename)
        with open(path, "w") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")
        return path

    def _usage_entry(self, ts, model, inp, out):
        return {
            "type": "assistant",
            "timestamp": ts,
            "message": {
                "model": model,
                "usage": {
                    "input_tokens": inp,
                    "output_tokens": out,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 0,
                },
            },
        }

    def test_collects_events_from_jsonl_files(self):
        with tempfile.TemporaryDirectory() as d:
            self._write_jsonl(
                d,
                "session1.jsonl",
                [
                    self._usage_entry(
                        "2026-03-05T10:00:00.000Z", "claude-opus-4-6", 100, 50
                    ),
                ],
            )
            events = collect_all_token_events(d)
            assert len(events) == 1
            assert events[0]["model_family"] == "opus"

    def test_collects_from_subdirectories(self):
        with tempfile.TemporaryDirectory() as d:
            subdir = os.path.join(d, "subproject")
            os.makedirs(subdir)
            self._write_jsonl(
                subdir,
                "session2.jsonl",
                [
                    self._usage_entry(
                        "2026-03-05T11:00:00.000Z", "claude-sonnet-4-6", 200, 80
                    ),
                ],
            )
            events = collect_all_token_events(d)
            assert len(events) == 1
            assert events[0]["model_family"] == "sonnet"

    def test_empty_directory_returns_empty(self):
        with tempfile.TemporaryDirectory() as d:
            events = collect_all_token_events(d)
            assert events == []

    def test_since_epoch_filters_old_files(self):
        with tempfile.TemporaryDirectory() as d:
            path = self._write_jsonl(
                d,
                "old.jsonl",
                [
                    self._usage_entry(
                        "2026-01-01T00:00:00.000Z", "claude-opus-4-6", 10, 5
                    ),
                ],
            )
            # Set mtime to the past
            past = datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp()
            os.utime(path, (past, past))

            since = datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp()
            events = collect_all_token_events(d, since_epoch=since)
            assert events == []


# ---------------------------------------------------------------------------
# Increment 3: TestRunRegression
# ---------------------------------------------------------------------------

import numpy as np  # noqa: E402
from claude_usage.tools.token_cost_analyzer.regression import (
    run_regression,
)  # noqa: E402


class TestRunRegression:
    def test_recovers_known_coefficients(self):
        """Synthetic data with one active feature; verify coefficient recovery."""
        rng = np.random.default_rng(42)
        n = 200
        tokens = rng.uniform(0.1, 5.0, n)
        X = np.zeros((n, 12))
        X[:, 0] = tokens
        y = 0.05 * tokens + rng.normal(0, 0.001, n)

        coeffs, r2 = run_regression(X, y)

        assert len(coeffs) == 12
        assert coeffs[0] == pytest.approx(0.05, abs=0.005)
        assert all(abs(c) < 0.01 for c in coeffs[1:])
        assert r2 > 0.95

    def test_coefficients_non_negative(self):
        """Costs cannot be negative — regression must return non-negative values."""
        rng = np.random.default_rng(7)
        n = 100
        X = rng.uniform(0, 1, (n, 12))
        y = 0.03 * X[:, 2] + rng.normal(0, 0.0005, n)
        y = np.clip(y, 0, None)

        coeffs, r2 = run_regression(X, y)
        assert all(c >= -1e-9 for c in coeffs), f"Negative coefficient found: {coeffs}"

    def test_returns_r_squared_in_valid_range(self):
        rng = np.random.default_rng(0)
        n = 50
        X = rng.uniform(0, 1, (n, 12))
        y = 0.1 * X[:, 0] + 0.2 * X[:, 5] + rng.normal(0, 0.001, n)
        y = np.clip(y, 0, None)
        coeffs, r2 = run_regression(X, y)
        assert 0.0 <= r2 <= 1.0

    def test_empty_data_raises(self):
        X = np.zeros((0, 12))
        y = np.zeros(0)
        with pytest.raises(ValueError):
            run_regression(X, y)

    def test_zero_variance_y_returns_zero_r2(self):
        """When all y values are identical, ss_tot=0 → R² defaults to 0.0."""
        X = np.ones((10, 12))
        y = np.full(10, 5.0)
        coeffs, r2 = run_regression(X, y)
        assert r2 == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Increment 4a: TestEdgeCaseCoverage — parse edge cases
# ---------------------------------------------------------------------------


class TestEdgeCaseCoverage:
    """Covers remaining uncovered parse/file-access branches."""

    def test_parse_timestamp_invalid_format_raises(self):
        from claude_usage.tools.token_cost_analyzer.core import (
            parse_transcript_timestamp,
        )

        with pytest.raises(ValueError):
            parse_transcript_timestamp("not-a-date")

    def test_parse_transcript_file_missing_timestamp_skipped(self):
        """Entry without timestamp field is skipped (line 108)."""
        entry = json.dumps(
            {
                "type": "assistant",
                "message": {
                    "model": "claude-opus-4-6",
                    "usage": {
                        "input_tokens": 1,
                        "output_tokens": 1,
                        "cache_read_input_tokens": 0,
                        "cache_creation_input_tokens": 0,
                    },
                },
            }
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(entry + "\n")
            path = f.name
        try:
            result = parse_transcript_file(path)
            assert result == []
        finally:
            os.unlink(path)

    def test_parse_transcript_file_nonexistent_returns_empty(self):
        """OSError on file open returns empty list (lines 133-134)."""
        result = parse_transcript_file("/nonexistent/path/file.jsonl")
        assert result == []

    def test_parse_transcript_file_empty_lines_skipped(self):
        """Blank lines in JSONL are silently skipped (line 87)."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write("\n\n\n")
            f.write(
                json.dumps(
                    {
                        "type": "assistant",
                        "timestamp": "2026-03-05T10:00:00.000Z",
                        "message": {
                            "model": "claude-opus-4-6",
                            "usage": {
                                "input_tokens": 1,
                                "output_tokens": 1,
                                "cache_read_input_tokens": 0,
                                "cache_creation_input_tokens": 0,
                            },
                        },
                    }
                )
                + "\n"
            )
            path = f.name
        try:
            result = parse_transcript_file(path)
            assert len(result) == 1
        finally:
            os.unlink(path)

    def test_parse_transcript_file_bad_timestamp_skipped(self):
        """Entry with unparseable timestamp is skipped (lines 122-123)."""
        entry = json.dumps(
            {
                "type": "assistant",
                "timestamp": "not-a-timestamp",
                "message": {
                    "model": "claude-opus-4-6",
                    "usage": {
                        "input_tokens": 1,
                        "output_tokens": 1,
                        "cache_read_input_tokens": 0,
                        "cache_creation_input_tokens": 0,
                    },
                },
            }
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(entry + "\n")
            path = f.name
        try:
            result = parse_transcript_file(path)
            assert result == []
        finally:
            os.unlink(path)

    def test_collect_verbose_prints_total(self, capsys):
        """verbose=True prints total files scanned message (line 392)."""
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "s.jsonl"), "w") as f:
                f.write(
                    json.dumps(
                        {
                            "type": "assistant",
                            "timestamp": "2026-03-05T10:00:00.000Z",
                            "message": {
                                "model": "claude-sonnet-4-6",
                                "usage": {
                                    "input_tokens": 5,
                                    "output_tokens": 3,
                                    "cache_read_input_tokens": 0,
                                    "cache_creation_input_tokens": 0,
                                },
                            },
                        }
                    )
                    + "\n"
                )
            collect_all_token_events(d, verbose=True)
            captured = capsys.readouterr()
            assert "Total files scanned" in captured.err
