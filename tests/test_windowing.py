from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from dhgraph.windowing import assign_window_ids, churn_counts, window_bounds, window_label


def test_assign_window_ids_from_string_timestamps() -> None:
    timestamps = pd.Series(["0", "1", "3599", "3600", "7200"])
    window_ids = assign_window_ids(timestamps, 3600)
    assert window_ids.tolist() == [0, 0, 0, 1, 2]


def test_window_bounds_and_labels() -> None:
    assert window_bounds(2, 3600) == (7200, 10800)
    assert window_label(3600) == "1h"
    assert window_label(21600) == "6h"
    assert window_label(86400) == "24h"


def test_churn_counts_first_and_second_window() -> None:
    first = {("U1", "C1"), ("U2", "C2")}
    assert churn_counts(first, None) == (2, 0, 0, 0.0)

    second = {("U2", "C2"), ("U3", "C3")}
    new_items, disappeared_items, persistent_items, churn = churn_counts(second, first)
    assert new_items == 1
    assert disappeared_items == 1
    assert persistent_items == 1
    assert churn == 2 / 3
