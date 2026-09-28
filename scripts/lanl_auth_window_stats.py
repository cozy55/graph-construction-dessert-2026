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

from dhgraph.graph_stats import (  # noqa: E402
    WindowEdgeAggregator,
    aggregate_auth_chunk,
    build_summary_row,
    build_top_hosts,
    build_top_users,
    compute_window_statistics,
)
from dhgraph.io import MemoryTracker, iter_lanl_auth_chunks, validate_required_columns  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Aggregate LANL user-computer authentication associations into dynamic "
            "user-host graph windows. The script uses only user and dst_host; src_host "
            "is not treated as a meaningful node for this LANL dataset."
        )
    )
    parser.add_argument("--input", required=True, help="Processed LANL authentication CSV.")
    parser.add_argument("--output-dir", required=True, help="Directory for CSV outputs.")
    parser.add_argument("--window-seconds", required=True, type=int, help="Window size in seconds.")
    parser.add_argument("--chunksize", type=int, default=2_000_000, help="Pandas CSV chunksize.")
    parser.add_argument("--top-n", type=int, default=20, help="Top users/hosts per window.")
    parser.add_argument(
        "--aggregation-mode",
        choices=("in-memory", "auto", "disk"),
        default="in-memory",
        help=(
            "in-memory keeps per-window edge counts in dictionaries; auto spills those "
            "dictionaries to intermediate CSV when --max-memory-mb is exceeded; disk "
            "writes each chunk aggregate to intermediate CSV immediately."
        ),
    )
    parser.add_argument(
        "--max-memory-mb",
        type=float,
        default=None,
        help="Memory threshold for --aggregation-mode auto.",
    )
    parser.add_argument(
        "--keep-partials",
        action="store_true",
        help="Keep intermediate _partial_edge_counts CSV files after consolidation.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    validate_required_columns(input_path, ("timestamp", "user", "dst_host"))

    started = time.perf_counter()
    memory = MemoryTracker()
    memory.sample_mb()
    edge_aggregator = WindowEdgeAggregator(
        output_dir=output_dir,
        mode=args.aggregation_mode,
        max_memory_mb=args.max_memory_mb,
        keep_partials=args.keep_partials,
    )

    total_rows = 0
    mapped_rows = 0
    invalid_timestamp_rows = 0
    rows_by_window: Counter[int] = Counter()
    mapped_rows_by_window: Counter[int] = Counter()

    for chunk_index, chunk in enumerate(
        iter_lanl_auth_chunks(input_path, args.chunksize), start=1
    ):
        aggregation = aggregate_auth_chunk(chunk, args.window_seconds)
        total_rows += aggregation.total_rows
        mapped_rows += aggregation.mapped_rows
        invalid_timestamp_rows += aggregation.invalid_timestamp_rows
        rows_by_window.update(aggregation.rows_by_window)
        mapped_rows_by_window.update(aggregation.mapped_rows_by_window)

        edge_aggregator.update(aggregation.edge_counts)
        current_memory_mb = memory.sample_mb()
        if (
            args.aggregation_mode == "auto"
            and args.max_memory_mb is not None
            and current_memory_mb > args.max_memory_mb
        ):
            edge_aggregator.flush_to_part()
            current_memory_mb = memory.sample_mb()

        print(
            f"[chunk {chunk_index}] rows={aggregation.total_rows:,} "
            f"mapped={aggregation.mapped_rows:,} "
            f"edge_groups={len(aggregation.edge_counts):,} "
            f"rss_mb={current_memory_mb:.1f} peak_mb={memory.peak_mb:.1f}",
            flush=True,
        )
        del chunk, aggregation
        gc.collect()

    print("[finalize] consolidating window edge counts", flush=True)
    edge_counts_by_window = edge_aggregator.finalize()
    final_memory_mb = memory.sample_mb()

    stats = compute_window_statistics(
        edge_counts_by_window=edge_counts_by_window,
        window_seconds=args.window_seconds,
        rows_by_window=rows_by_window,
        mapped_rows_by_window=mapped_rows_by_window,
    )
    summary = build_summary_row(
        input_path=input_path,
        window_seconds=args.window_seconds,
        chunksize=args.chunksize,
        total_rows=total_rows,
        mapped_rows=mapped_rows,
        stats=stats,
        construction_time_sec=time.perf_counter() - started,
        peak_memory_mb=memory.peak_mb,
        final_memory_mb=final_memory_mb,
    )
    top_users = build_top_users(edge_counts_by_window, args.window_seconds, args.top_n)
    top_hosts = build_top_hosts(edge_counts_by_window, args.window_seconds, args.top_n)

    suffix = f"{args.window_seconds}s"
    stats_path = output_dir / f"lanl_auth_window_stats_{suffix}.csv"
    summary_path = output_dir / f"lanl_auth_summary_{suffix}.csv"
    top_users_path = output_dir / f"lanl_auth_top_users_{suffix}.csv"
    top_hosts_path = output_dir / f"lanl_auth_top_hosts_{suffix}.csv"

    stats.to_csv(stats_path, index=False)
    summary.to_csv(summary_path, index=False)
    top_users.to_csv(top_users_path, index=False)
    top_hosts.to_csv(top_hosts_path, index=False)

    print(
        "[done] wrote:\n"
        f"  {stats_path}\n"
        f"  {summary_path}\n"
        f"  {top_users_path}\n"
        f"  {top_hosts_path}\n"
        f"[done] total_rows={total_rows:,} mapped_rows={mapped_rows:,} "
        f"invalid_timestamp_rows={invalid_timestamp_rows:,}",
        flush=True,
    )


if __name__ == "__main__":
    main()
