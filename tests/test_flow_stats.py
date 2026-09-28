from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from dhgraph.flow_stats import (
    aggregate_flow_chunk,
    compute_flow_window_statistics,
    detect_flow_columns,
    iter_flow_chunks,
)


def test_detect_cicids_style_columns() -> None:
    path = ROOT / "tests" / "fixtures" / "tiny_cicids_flow.csv"
    column_map = detect_flow_columns(path)
    assert column_map.timestamp == " Timestamp"
    assert column_map.src_host == " Source IP"
    assert column_map.dst_host == " Destination IP"
    assert column_map.dst_port == " Destination Port"
    assert column_map.protocol == " Protocol"
    assert column_map.label == " Label"


def test_flow_aggregation_with_datetime_timestamps() -> None:
    path = ROOT / "tests" / "fixtures" / "tiny_cicids_flow.csv"
    chunk = next(iter_flow_chunks(path, chunksize=100))
    aggregation = aggregate_flow_chunk(chunk, window_seconds=60)

    counters: dict[int, Counter[tuple[str, str, str]]] = {}
    for row in aggregation.edge_counts.itertuples(index=False):
        counters.setdefault(int(row.window_id), Counter())[
            (str(row.src_host), str(row.dst_host), str(row.service))
        ] += int(row.count)

    stats = compute_flow_window_statistics(
        counters,
        window_seconds=60,
        rows_by_window=aggregation.rows_by_window,
        mapped_rows_by_window=aggregation.mapped_rows_by_window,
        attack_rows_by_window=aggregation.attack_rows_by_window,
    )

    assert len(stats) == 2
    assert aggregation.total_rows == 10
    assert aggregation.mapped_rows == 10
    assert aggregation.attack_rows == 4

    first = stats.iloc[0]
    assert first["events"] == 5
    assert first["labeled_attack_events"] == 2
    assert first["unique_flow_edges"] == 4
    assert first["repeated_events"] == 1
    assert first["event_mapping_rate"] == 1.0

    second = stats.iloc[1]
    assert second["events"] == 5
    assert second["labeled_attack_events"] == 2
    assert second["unique_services"] == 3
