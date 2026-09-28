#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


CASE_STUDY_COLUMNS = [
    "window_id",
    "time_start_sec",
    "time_end_sec",
    "events",
    "unique_users",
    "unique_hosts",
    "nodes",
    "unique_edges",
    "new_edges",
    "disappeared_edges",
    "persistent_edges",
    "edge_churn",
    "new_users",
    "new_hosts",
    "user_churn",
    "host_churn",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Select LANL authentication windows with high structural churn for "
            "lateral-movement-style inspection. This does not confirm attacks."
        )
    )
    parser.add_argument("--window-stats", required=True, help="Window stats CSV.")
    parser.add_argument("--output", required=True, help="Output top-churn CSV.")
    parser.add_argument("--top-k", type=int, default=10, help="Number of windows to export.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.top_k <= 0:
        raise ValueError("--top-k must be a positive integer.")

    stats = pd.read_csv(args.window_stats)
    missing = [column for column in CASE_STUDY_COLUMNS if column not in stats.columns]
    if missing:
        raise ValueError(
            "Window stats CSV is missing required column(s): " + ", ".join(missing)
        )

    selected = (
        stats.sort_values(
            ["edge_churn", "new_edges", "unique_edges"],
            ascending=[False, False, False],
            kind="mergesort",
        )
        .head(args.top_k)
        .loc[:, CASE_STUDY_COLUMNS]
        .copy()
    )
    selected["interpretation_note"] = (
        "High authentication-edge churn; relevant for structural inspection, "
        "not a confirmed attack."
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    selected.to_csv(output_path, index=False)
    print(f"[done] wrote {output_path} ({len(selected)} rows)")


if __name__ == "__main__":
    main()
