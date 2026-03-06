"""Interval-building functions for token cost analysis."""

from collections import defaultdict
from typing import Dict, List, Tuple

import numpy as np

from .core import (
    N_FEATURES,
    _COL_INPUT,
    _COL_OUTPUT,
    _COL_CACHE_READ,
    _COL_CACHE_CREATE,
    _FAMILY_OFFSET,
)


def _to_arrays(rows: List[np.ndarray], ys: List[float], n_cols: int):
    """Convert row/y lists to numpy arrays."""
    if not rows:
        return np.zeros((0, n_cols)), np.zeros(0)
    return np.array(rows), np.array(ys)


def _accumulate_features(
    events: List[Dict],
    t_start: int,
    t_end: int,
    sorted_events: List[Dict],
    start_idx: int,
) -> Tuple[np.ndarray, int]:
    """Sum token features for events in [t_start, t_end). Returns (feature_vec, next_idx)."""
    feature_vec = np.zeros(N_FEATURES)
    idx = start_idx
    n = len(sorted_events)

    while idx < n and sorted_events[idx]["timestamp"] < t_end:
        ev = sorted_events[idx]
        if ev["timestamp"] >= t_start:
            offset = _FAMILY_OFFSET.get(ev["model_family"])
            if offset is not None:
                feature_vec[offset + _COL_INPUT] += ev["input_tokens"] / 1_000_000
                feature_vec[offset + _COL_OUTPUT] += ev["output_tokens"] / 1_000_000
                feature_vec[offset + _COL_CACHE_READ] += (
                    ev["cache_read_tokens"] / 1_000_000
                )
                feature_vec[offset + _COL_CACHE_CREATE] += (
                    ev["cache_creation_tokens"] / 1_000_000
                )
        idx += 1

    return feature_vec, idx


def build_intervals(
    snapshots: List[Tuple[int, float, float]],
    token_events: List[Dict],
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Build 12-feature regression matrices from consecutive snapshot pairs."""
    if len(snapshots) < 2:
        empty = np.zeros((0, N_FEATURES))
        return empty, np.zeros(0), empty, np.zeros(0)

    sorted_events = sorted(token_events, key=lambda e: e["timestamp"])
    rows_5h, y_5h, rows_7d, y_7d = [], [], [], []
    event_idx = 0

    for i in range(len(snapshots) - 1):
        t1, u5_t1, u7_t1 = snapshots[i]
        t2, u5_t2, u7_t2 = snapshots[i + 1]
        d5, d7 = u5_t2 - u5_t1, u7_t2 - u7_t1

        if d5 <= 0 and d7 <= 0:
            while (
                event_idx < len(sorted_events)
                and sorted_events[event_idx]["timestamp"] < t2
            ):
                event_idx += 1
            continue

        fv, event_idx = _accumulate_features(
            sorted_events, t1, t2, sorted_events, event_idx
        )
        if fv.sum() == 0:
            continue

        if d5 > 0:
            rows_5h.append(fv)
            y_5h.append(d5)
        if d7 > 0:
            rows_7d.append(fv)
            y_7d.append(d7)

    X5, y5 = _to_arrays(rows_5h, y_5h, N_FEATURES)
    X7, y7 = _to_arrays(rows_7d, y_7d, N_FEATURES)
    return X5, y5, X7, y7


def _bucket_snapshots(snapshots, bucket_seconds):
    """Group snapshots into time buckets."""
    bucketed: Dict[int, List] = defaultdict(list)
    for ts, u5, u7 in snapshots:
        bucketed[ts // bucket_seconds].append((ts, u5, u7))
    return bucketed


def build_weighted_intervals(
    snapshots: List[Tuple[int, float, float]],
    costed_events: List[Dict],
    aggregate_hours: int = 1,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Build 4-feature intervals using API-equivalent cost.

    Columns: [total_api_cost, opus_cost, sonnet_cost, haiku_cost]
    """
    if len(snapshots) < 2:
        empty = np.zeros((0, 4))
        return empty, np.zeros(0), empty, np.zeros(0)

    bucket_seconds = aggregate_hours * 3600
    bucketed = _bucket_snapshots(snapshots, bucket_seconds)
    sorted_events = sorted(costed_events, key=lambda e: e["timestamp"])

    rows_5h, y_5h, rows_7d, y_7d = [], [], [], []
    model_idx = {"opus": 1, "sonnet": 2, "haiku": 3}
    event_idx = 0
    n_events = len(sorted_events)

    for bk in sorted(bucketed.keys()):
        snaps = bucketed[bk]
        if len(snaps) < 2:
            continue

        first, last = snaps[0], snaps[-1]
        t_start, t_end = first[0], last[0]
        if t_end <= t_start:
            continue

        d5, d7 = last[1] - first[1], last[2] - first[2]
        if d5 <= 0 and d7 <= 0:
            while (
                event_idx < n_events and sorted_events[event_idx]["timestamp"] < t_end
            ):
                event_idx += 1
            continue

        costs = np.zeros(4)
        local_idx = event_idx
        while local_idx < n_events and sorted_events[local_idx]["timestamp"] < t_end:
            ev = sorted_events[local_idx]
            if ev["timestamp"] >= t_start:
                costs[0] += ev["api_cost"]
                mi = model_idx.get(ev["model_family"])
                if mi is not None:
                    costs[mi] += ev["api_cost"]
            local_idx += 1
        event_idx = local_idx

        if costs[0] == 0:
            continue
        if d5 > 0:
            rows_5h.append(costs.copy())
            y_5h.append(d5)
        if d7 > 0:
            rows_7d.append(costs.copy())
            y_7d.append(d7)

    return _to_arrays(rows_5h, y_5h, 4) + _to_arrays(rows_7d, y_7d, 4)
