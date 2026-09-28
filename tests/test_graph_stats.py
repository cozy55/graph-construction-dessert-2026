from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from dhgraph.graph_stats import aggregate_auth_chunk, compute_window_statistics


def test_aggregate_tiny_auth_csv_and_compute_stats() -> None:
    csv_path = ROOT / "tests" / "fixtures" / "tiny_lanl_auth.csv"
    chunk = pd.read_csv(csv_path)
    aggregation = aggregate_auth_chunk(chunk, window_seconds=10)
    counters: dict[int, Counter[tuple[str, str]]] = {}
    for row in aggregation.edge_counts.itertuples(index=False):
        counters.setdefault(int(row.window_id), Counter())[
            (str(row.user), str(row.dst_host))
        ] += int(row.count)

    stats = compute_window_statistics(
        counters,
        window_seconds=10,
        rows_by_window=aggregation.rows_by_window,
        mapped_rows_by_window=aggregation.mapped_rows_by_window,
    )

    assert len(stats) == 2
    first = stats.loc[stats["window_id"] == 0].iloc[0]
    assert first["events"] == 5
    assert first["unique_users"] == 3
    assert first["unique_hosts"] == 2
    assert first["unique_edges"] == 3
    assert first["repeated_events"] == 2
    assert first["max_events_per_edge"] == 2
    assert first["graph_density"] == 3 / 6
    assert first["event_mapping_rate"] == 1.0

    second = stats.loc[stats["window_id"] == 1].iloc[0]
    assert second["events"] == 5
    assert second["unique_edges"] == 4
    assert second["new_edges"] == 4
    assert second["disappeared_edges"] == 3
    assert second["persistent_edges"] == 0
    assert second["edge_churn"] == 1.0
