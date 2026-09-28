from __future__ import annotations

from collections.abc import Set
from typing import Any

import pandas as pd


def safe_divide(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return float(numerator) / float(denominator)


def assign_window_ids(timestamps: pd.Series, window_seconds: int) -> pd.Series:
    if window_seconds <= 0:
        raise ValueError("window_seconds must be a positive integer.")
    numeric = pd.to_numeric(timestamps, errors="coerce")
    return (numeric // window_seconds).astype("Int64")


def window_bounds(window_id: int, window_seconds: int) -> tuple[int, int]:
    start = int(window_id) * int(window_seconds)
    return start, start + int(window_seconds)


def churn_counts(
    current: Set[Any],
    previous: Set[Any] | None,
) -> tuple[int, int, int, float]:
    """Return new, disappeared, persistent, and normalized churn."""

    if previous is None:
        return len(current), 0, 0, 0.0

    new_items = current - previous
    disappeared_items = previous - current
    persistent_items = current & previous
    union_size = len(current | previous)
    churn = safe_divide(len(new_items) + len(disappeared_items), union_size)
    return len(new_items), len(disappeared_items), len(persistent_items), churn


def window_label(window_seconds: int) -> str:
    if window_seconds % 86400 == 0:
        days = window_seconds // 86400
        return f"{days}d" if days != 1 else "24h"
    if window_seconds % 3600 == 0:
        hours = window_seconds // 3600
        return f"{hours}h"
    if window_seconds % 60 == 0:
        minutes = window_seconds // 60
        return f"{minutes}m"
    return f"{window_seconds}s"
