"""Regression and result formatting for token cost analysis."""

from typing import Dict, Tuple

import numpy as np

from .core import (
    _COL_INPUT,
    _COL_OUTPUT,
    _COL_CACHE_READ,
    _COL_CACHE_CREATE,
    _FAMILY_OFFSET,
    NEAR_ZERO,
)


def run_regression(X: np.ndarray, y: np.ndarray) -> Tuple[np.ndarray, float]:
    """
    Fit non-negative least squares: y = X @ coefficients.

    Projected approach: fit unconstrained, zero negatives, refit active set.
    """
    if X.shape[0] == 0:
        raise ValueError("Cannot run regression on empty data (zero intervals).")

    coeffs, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
    coeffs = np.maximum(coeffs, 0.0)

    active = coeffs > 0
    if active.any():
        c_active, _, _, _ = np.linalg.lstsq(X[:, active], y, rcond=None)
        coeffs[active] = np.maximum(c_active, 0.0)
        coeffs[~active] = 0.0

    y_pred = X @ coeffs
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - y.mean()) ** 2)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

    return coeffs, float(r2)


def _r2_label(r2: float) -> str:
    if r2 >= 0.9:
        return "excellent fit"
    if r2 >= 0.7:
        return "good fit"
    if r2 >= 0.5:
        return "moderate fit"
    return "poor fit"


def _ratio_str(a: float, b: float, label: str) -> str:
    if b > NEAR_ZERO:
        return f"  {label}: {a / b:.2f}x"
    return f"  {label}: N/A (denominator near zero)"


def _cost_table(coeffs: np.ndarray, label: str, r2: float) -> str:
    lines = [
        f"--- {label} Costs (% utilization per 1M tokens) ---",
        f"{'':20s} {'Input':>10s} {'Output':>10s} {'Cache Read':>12s} {'Cache Create':>14s}",
    ]
    for family, offset in _FAMILY_OFFSET.items():
        vals = [
            coeffs[offset + c]
            for c in (_COL_INPUT, _COL_OUTPUT, _COL_CACHE_READ, _COL_CACHE_CREATE)
        ]
        lines.append(
            f"  {family.capitalize():<18s} {vals[0]:>10.4f} {vals[1]:>10.4f} {vals[2]:>12.4f} {vals[3]:>14.4f}"
        )
    lines.append(f"\n  R\u00b2 = {r2:.2f} ({_r2_label(r2)})")
    return "\n".join(lines)


def format_raw_results(
    coeffs_5h: np.ndarray,
    coeffs_7d: np.ndarray,
    r2_5h: float,
    r2_7d: float,
    meta: Dict,
) -> str:
    """Format 12-feature (raw mode) results."""
    ds, de = meta.get("date_range", ("?", "?"))
    tier = meta.get("tier", "unknown")
    total = meta.get("total_tokens", 0)

    lines = [
        f"=== Claude Token Cost Analysis (Raw 12-Feature) — Tier: {tier} ===",
        f"Data: {ds} to {de}",
        f"Intervals: {meta.get('n_intervals_5h', 0):,} (5h) / {meta.get('n_intervals_7d', 0):,} (7d)",
        f"Total tokens: {total / 1_000_000:.1f}M",
        "",
        _cost_table(coeffs_5h, "Five-Hour Window", r2_5h),
        "",
        _cost_table(coeffs_7d, "Seven-Day Window", r2_7d),
        "",
        "--- Relative Cost Ratios (5h) ---",
    ]

    o_out = coeffs_5h[_FAMILY_OFFSET["opus"] + _COL_OUTPUT]
    s_out = coeffs_5h[_FAMILY_OFFSET["sonnet"] + _COL_OUTPUT]
    o_inp = coeffs_5h[_FAMILY_OFFSET["opus"] + _COL_INPUT]
    s_inp = coeffs_5h[_FAMILY_OFFSET["sonnet"] + _COL_INPUT]
    o_cr = coeffs_5h[_FAMILY_OFFSET["opus"] + _COL_CACHE_READ]

    lines.append(_ratio_str(o_out, s_out, "Opus output / Sonnet output"))
    lines.append(_ratio_str(o_inp, s_inp, "Opus input / Sonnet input"))
    lines.append(_ratio_str(o_out, o_inp, "Output / Input (Opus)"))
    lines.append(_ratio_str(s_out, s_inp, "Output / Input (Sonnet)"))
    lines.append(_ratio_str(o_cr, o_inp, "Cache read / Input (Opus)"))

    return "\n".join(lines)


def _weighted_window_block(label: str, coeffs: np.ndarray, r2: float, n: int) -> str:
    """Format one window's weighted results."""
    lines = [f"--- {label} ---"]
    if n == 0:
        lines.append("  (insufficient data)")
        return "\n".join(lines)

    lines.append(f"  R\u00b2 = {r2:.3f} ({_r2_label(r2)})")

    names = ["Total", "Opus", "Sonnet", "Haiku"]
    for i, name in enumerate(names):
        c = coeffs[i] if i < len(coeffs) else 0
        if c > NEAR_ZERO:
            lines.append(f"  {name:8s} $1 API-equiv = {c:.4f}% utilization")
        else:
            lines.append(f"  {name:8s} N/A")

    if coeffs[0] > NEAR_ZERO:
        cost_per_pct = 1.0 / coeffs[0]
        lines.append(f"  => 1% util costs ~${cost_per_pct:.2f} API-equiv")
        lines.append(f"  => 100% util = ~${cost_per_pct * 100:.0f} API-equiv")

    return "\n".join(lines)


def _cross_validation_block(coeffs_5h: np.ndarray, coeffs_7d: np.ndarray) -> str:
    """Cross-validate per-model ratios against API pricing."""
    lines = ["--- Cross-Validation: Subscription vs API pricing ---"]

    for label, coeffs in [("5h", coeffs_5h), ("7d", coeffs_7d)]:
        opus_c = coeffs[1] if len(coeffs) > 1 else 0
        sonnet_c = coeffs[2] if len(coeffs) > 2 else 0
        haiku_c = coeffs[3] if len(coeffs) > 3 else 0

        lines.append(f"  [{label}] Per-model coeff ratios:")
        if sonnet_c > NEAR_ZERO and opus_c > NEAR_ZERO:
            lines.append(f"    Opus/Sonnet:  {opus_c / sonnet_c:.2f}x  (API=5.0x)")
        else:
            lines.append("    Opus/Sonnet:  insufficient data")
        if haiku_c > NEAR_ZERO and sonnet_c > NEAR_ZERO:
            lines.append(f"    Sonnet/Haiku: {sonnet_c / haiku_c:.2f}x  (API=3.75x)")
        else:
            lines.append("    Sonnet/Haiku: insufficient data")

    return "\n".join(lines)


def format_weighted_results(
    coeffs_5h: np.ndarray,
    coeffs_7d: np.ndarray,
    r2_5h: float,
    r2_7d: float,
    meta: Dict,
) -> str:
    """Format weighted-cost regression results."""
    ds, de = meta.get("date_range", ("?", "?"))
    tier = meta.get("tier", "unknown")
    agg = meta.get("aggregate_hours", 1)
    total_cost = meta.get("total_api_cost", 0)

    lines = [
        f"=== Claude Token Cost Analysis (Weighted) — Tier: {tier} ===",
        f"Data: {ds} to {de} | Aggregation: {agg}h",
        f"Intervals: {meta.get('n_intervals_5h', 0):,} (5h) / {meta.get('n_intervals_7d', 0):,} (7d)",
        f"Total tokens: {meta.get('total_tokens', 0) / 1_000_000:.1f}M | API-equiv: ${total_cost:.2f}",
        "",
        _weighted_window_block(
            "Five-Hour Window", coeffs_5h, r2_5h, meta.get("n_intervals_5h", 0)
        ),
        "",
        _weighted_window_block(
            "Seven-Day Window", coeffs_7d, r2_7d, meta.get("n_intervals_7d", 0)
        ),
        "",
        _cross_validation_block(coeffs_5h, coeffs_7d),
    ]

    return "\n".join(lines)
