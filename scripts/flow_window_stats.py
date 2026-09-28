#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gc
import sys
import time
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from dhgraph.flow_stats import (  # noqa: E402
    FlowWindowEdgeAggregator,
    aggregate_flow_chunk,
    build_flow_summary_row,
    build_top_flow_services,
    build_top_flow_sources,
    compute_flow_window_statistics,
    detect_flow_columns,
    iter_flow_chunks,
)
from dhgraph.io import MemoryTracker  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Aggregate CICIDS-style flow CSV records into dynamic host-host and "
            "host-service graph-window statistics. Processing is chunked and does "
            "not load the full CSV into memory."
        )
    )
    parser.add_argument("--input", required=True, help="Flow CSV path.")
    parser.add_argument("--output-dir", required=True, help="Directory for outputs.")
    parser.add_argument("--dataset-name", default="cicids2017", help="Dataset name for summary.")
    parser.add_argument("--window-seconds", required=True, type=int)
    parser.add_argument("--chunksize", type=int, default=1_000_000)
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument(
        "--timestamp-unit",
        choices=("auto", "s", "ms", "us", "ns"),
        default="auto",
        help="Numeric timestamp unit. Datetime strings are parsed automatically when needed.",
    )
    parser.add_argument(
        "--timestamp-dayfirst",
        action="store_true",
        help="Parse datetime strings as day/month/year. Recommended for CICIDS2017.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    column_map = detect_flow_columns(input_path)
    print(f"[columns] {column_map}", flush=True)

    started = time.perf_counter()
    memory = MemoryTracker()
    memory.sample_mb()
    aggregator = FlowWindowEdgeAggregator()

    total_rows = 0
    mapped_rows = 0
    attack_rows = 0
    invalid_timestamp_rows = 0
    rows_by_window: Counter[int] = Counter()
    mapped_rows_by_window: Counter[int] = Counter()
    attack_rows_by_window: Counter[int] = Counter()

    for chunk_index, chunk in enumerate(
        iter_flow_chunks(input_path, args.chunksize, column_map=column_map), start=1
    ):
        aggregation = aggregate_flow_chunk(
            chunk,
            window_seconds=args.window_seconds,
            timestamp_unit=args.timestamp_unit,
            timestamp_dayfirst=args.timestamp_dayfirst,
        )
        total_rows += aggregation.total_rows
        mapped_rows += aggregation.mapped_rows
        attack_rows += aggregation.attack_rows
        invalid_timestamp_rows += aggregation.invalid_timestamp_rows
        rows_by_window.update(aggregation.rows_by_window)
        mapped_rows_by_window.update(aggregation.mapped_rows_by_window)
        attack_rows_by_window.update(aggregation.attack_rows_by_window)
        aggregator.update(aggregation.edge_counts)

        current_memory_mb = memory.sample_mb()
        print(
            f"[chunk {chunk_index}] rows={aggregation.total_rows:,} "
            f"mapped={aggregation.mapped_rows:,} "
            f"edge_groups={len(aggregation.edge_counts):,} "
            f"attack_rows={aggregation.attack_rows:,} "
            f"rss_mb={current_memory_mb:.1f} peak_mb={memory.peak_mb:.1f}",
            flush=True,
        )
        del chunk, aggregation
        gc.collect()

    edge_counts_by_window = aggregator.finalize()
    final_memory_mb = memory.sample_mb()
    stats = compute_flow_window_statistics(
        edge_counts_by_window=edge_counts_by_window,
        window_seconds=args.window_seconds,
        rows_by_window=rows_by_window,
        mapped_rows_by_window=mapped_rows_by_window,
        attack_rows_by_window=attack_rows_by_window,
    )
    summary = build_flow_summary_row(
        input_path=input_path,
        dataset_name=args.dataset_name,
        window_seconds=args.window_seconds,
        chunksize=args.chunksize,
        total_rows=total_rows,
        mapped_rows=mapped_rows,
        attack_rows=attack_rows,
        stats=stats,
        construction_time_sec=time.perf_counter() - started,
        peak_memory_mb=memory.peak_mb,
        final_memory_mb=final_memory_mb,
    )
    top_sources = build_top_flow_sources(edge_counts_by_window, args.window_seconds, args.top_n)
    top_services = build_top_flow_services(edge_counts_by_window, args.window_seconds, args.top_n)

    suffix = f"{args.window_seconds}s"
    stats_path = output_dir / f"{args.dataset_name}_flow_window_stats_{suffix}.csv"
    summary_path = output_dir / f"{args.dataset_name}_flow_summary_{suffix}.csv"
    top_sources_path = output_dir / f"{args.dataset_name}_flow_top_sources_{suffix}.csv"
    top_services_path = output_dir / f"{args.dataset_name}_flow_top_services_{suffix}.csv"

    stats.to_csv(stats_path, index=False)
    summary.to_csv(summary_path, index=False)
    top_sources.to_csv(top_sources_path, index=False)
    top_services.to_csv(top_services_path, index=False)

    print(
        "[done] wrote:\n"
        f"  {stats_path}\n"
        f"  {summary_path}\n"
        f"  {top_sources_path}\n"
        f"  {top_services_path}\n"
        f"[done] total_rows={total_rows:,} mapped_rows={mapped_rows:,} "
        f"attack_rows={attack_rows:,} invalid_timestamp_rows={invalid_timestamp_rows:,}",
        flush=True,
    )


if __name__ == "__main__":
    main()
