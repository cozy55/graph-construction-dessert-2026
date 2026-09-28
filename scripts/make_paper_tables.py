#!/usr/bin/env python3
"""Regenerate the revised paper's numerical tables from recorded or new runs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def make_tables(records_path: Path, stats_dir: Path, output: Path) -> None:
    runs = pd.DataFrame(json.loads(records_path.read_text()))
    output.mkdir(parents=True, exist_ok=True)
    resources, accounting = [], []
    for (dataset, seconds), group in runs.groupby(["dataset", "window_seconds"], sort=True):
        seconds = int(seconds)
        stats = pd.read_csv(stats_dir / f"{dataset}_{seconds}s.csv")
        first = group.iloc[0]
        resources.append({
            "dataset": dataset, "window_seconds": seconds, "repeats": len(group),
            "snapshots": len(stats), "mean_nodes": stats["nodes"].mean(),
            "mean_edges": stats["unique_edges" if dataset == "lanl" else "unique_flow_edges"].mean(),
            "median_seconds": group.construction_time_sec.median(),
            "min_seconds": group.construction_time_sec.min(), "max_seconds": group.construction_time_sec.max(),
            "median_sampled_rss_mib": group.peak_memory_mb.median(),
            "min_sampled_rss_mib": group.peak_memory_mb.min(), "max_sampled_rss_mib": group.peak_memory_mb.max(),
        })
        accounting.append({
            "dataset": dataset, "window_seconds": seconds, "input_rows": int(first.total_rows),
            "construction_rejected_rows": int(first.total_rows - first.mapped_rows),
            "mapped_rows": int(first.mapped_rows),
            "unique_window_keys": int(stats["unique_edges" if dataset == "lanl" else "unique_flow_edges"].sum()),
            "mapping_rate": float(first.event_mapping_rate),
        })
    resource_frame = pd.DataFrame(resources)
    for dataset, name in [("lanl", "table_i_lanl.csv"), ("cicids2017", "table_iv_cicids2017.csv")]:
        resource_frame.loc[resource_frame.dataset == dataset].to_csv(output / name, index=False)
    pd.DataFrame(accounting).to_csv(output / "table_v_mapping.csv", index=False)
    lanl_path = stats_dir / "lanl_3600s.csv"
    if lanl_path.exists():
        lanl = pd.read_csv(lanl_path)
        selected = lanl.loc[lanl.window_id != 672].sort_values(
            ["edge_churn", "new_edges", "unique_edges"], ascending=False, kind="mergesort").head(5)
        selected.loc[:, ["window_id", "events", "nodes", "unique_edges", "edge_churn"]].to_csv(
            output / "table_iii_churn.csv", index=False)
    print(f"Saved numerical paper tables to {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=Path, default=ROOT / "reference/benchmark_runs.json")
    parser.add_argument("--stats-dir", type=Path, default=ROOT / "reference/window_stats")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results/paper_tables")
    args = parser.parse_args()
    make_tables(args.records, args.stats_dir, args.output_dir)


if __name__ == "__main__":
    main()
