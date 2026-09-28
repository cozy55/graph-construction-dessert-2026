from __future__ import annotations

import csv
import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import DefaultDict, Mapping

import pandas as pd

from .windowing import churn_counts, safe_divide, window_bounds


Edge = tuple[str, str]


@dataclass
class ChunkAggregation:
    edge_counts: pd.DataFrame
    rows_by_window: Counter[int]
    mapped_rows_by_window: Counter[int]
    total_rows: int
    mapped_rows: int
    invalid_timestamp_rows: int


def _empty_edge_count_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=["window_id", "user", "dst_host", "count"])


def _clean_entity_column(series: pd.Series) -> tuple[pd.Series, pd.Series]:
    values = series.astype("string").str.strip()
    valid = (values.notna() & values.ne("")).fillna(False)
    return values, valid


def aggregate_auth_chunk(chunk: pd.DataFrame, window_seconds: int) -> ChunkAggregation:
    """Aggregate one CSV chunk to per-window user-host edge counts."""

    if window_seconds <= 0:
        raise ValueError("window_seconds must be a positive integer.")

    required = {"timestamp", "user", "dst_host"}
    missing = sorted(required - set(chunk.columns))
    if missing:
        raise ValueError(f"Input chunk is missing required column(s): {', '.join(missing)}")

    total_rows = int(len(chunk))
    if total_rows == 0:
        return ChunkAggregation(
            edge_counts=_empty_edge_count_frame(),
            rows_by_window=Counter(),
            mapped_rows_by_window=Counter(),
            total_rows=0,
            mapped_rows=0,
            invalid_timestamp_rows=0,
        )

    timestamps = pd.to_numeric(chunk["timestamp"], errors="coerce")
    valid_timestamp = timestamps.notna()
    invalid_timestamp_rows = int((~valid_timestamp).sum())

    rows_by_window: Counter[int] = Counter()
    if valid_timestamp.any():
        valid_window_ids = (
            timestamps.loc[valid_timestamp].astype("int64") // int(window_seconds)
        )
        rows_by_window.update(
            {int(k): int(v) for k, v in valid_window_ids.value_counts(sort=False).items()}
        )

    users, valid_users = _clean_entity_column(chunk["user"])
    hosts, valid_hosts = _clean_entity_column(chunk["dst_host"])
    mapped_mask = (valid_timestamp & valid_users & valid_hosts).fillna(False)
    mapped_rows = int(mapped_mask.sum())

    if mapped_rows == 0:
        return ChunkAggregation(
            edge_counts=_empty_edge_count_frame(),
            rows_by_window=rows_by_window,
            mapped_rows_by_window=Counter(),
            total_rows=total_rows,
            mapped_rows=0,
            invalid_timestamp_rows=invalid_timestamp_rows,
        )

    mapped_window_ids = (
        timestamps.loc[mapped_mask].astype("int64") // int(window_seconds)
    ).astype("int64")
    mapped = pd.DataFrame(
        {
            "window_id": mapped_window_ids.to_numpy(),
            "user": users.loc[mapped_mask].astype(str).to_numpy(),
            "dst_host": hosts.loc[mapped_mask].astype(str).to_numpy(),
        }
    )

    grouped = (
        mapped.groupby(["window_id", "user", "dst_host"], sort=False, observed=True)
        .size()
        .reset_index(name="count")
    )
    grouped["count"] = grouped["count"].astype("int64")

    mapped_rows_by_window: Counter[int] = Counter()
    mapped_rows_by_window.update(
        {
            int(k): int(v)
            for k, v in grouped.groupby("window_id", sort=False)["count"].sum().items()
        }
    )

    return ChunkAggregation(
        edge_counts=grouped,
        rows_by_window=rows_by_window,
        mapped_rows_by_window=mapped_rows_by_window,
        total_rows=total_rows,
        mapped_rows=mapped_rows,
        invalid_timestamp_rows=invalid_timestamp_rows,
    )


class WindowEdgeAggregator:
    """Collect per-window edge counts, optionally spilling chunk aggregates to CSV."""

    def __init__(
        self,
        output_dir: str | Path,
        mode: str = "in-memory",
        max_memory_mb: float | None = None,
        keep_partials: bool = False,
    ) -> None:
        if mode not in {"in-memory", "auto", "disk"}:
            raise ValueError("aggregation mode must be one of: in-memory, auto, disk.")
        self.mode = mode
        self.max_memory_mb = max_memory_mb
        self.keep_partials = keep_partials
        self.counters: DefaultDict[int, Counter[Edge]] = defaultdict(Counter)
        self.partial_dir = Path(output_dir) / "_partial_edge_counts"
        self.partial_files: list[Path] = []
        self._part_counter = 0
        if self.mode == "disk":
            self.partial_dir.mkdir(parents=True, exist_ok=True)

    def update(self, grouped_edges: pd.DataFrame, current_memory_mb: float | None = None) -> None:
        if grouped_edges.empty:
            return

        if self.mode == "disk":
            self._write_grouped_dataframe(grouped_edges)
            return

        self._update_counters(self.counters, grouped_edges)
        if (
            self.mode == "auto"
            and self.max_memory_mb is not None
            and current_memory_mb is not None
            and current_memory_mb > self.max_memory_mb
        ):
            self.flush_to_part()

    def flush_to_part(self) -> None:
        if not self.counters:
            return
        self.partial_dir.mkdir(parents=True, exist_ok=True)
        path = self.partial_dir / f"part_{self._part_counter:06d}.csv"
        self._part_counter += 1
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["window_id", "user", "dst_host", "count"])
            for window_id in sorted(self.counters):
                counter = self.counters[window_id]
                for (user, host), count in sorted(counter.items()):
                    writer.writerow([window_id, user, host, int(count)])
        self.partial_files.append(path)
        self.counters.clear()

    def finalize(self, read_chunksize: int = 1_000_000) -> dict[int, Counter[Edge]]:
        if not self.partial_files:
            return dict(self.counters)

        self.flush_to_part()
        final_counters: DefaultDict[int, Counter[Edge]] = defaultdict(Counter)
        for path in sorted(self.partial_files):
            for frame in pd.read_csv(
                path,
                chunksize=read_chunksize,
                dtype={"user": "string", "dst_host": "string"},
            ):
                self._update_counters(final_counters, frame)

        if not self.keep_partials and self.partial_dir.exists():
            shutil.rmtree(self.partial_dir)
        return dict(final_counters)

    def _write_grouped_dataframe(self, grouped_edges: pd.DataFrame) -> None:
        self.partial_dir.mkdir(parents=True, exist_ok=True)
        path = self.partial_dir / f"part_{self._part_counter:06d}.csv"
        self._part_counter += 1
        grouped_edges.to_csv(path, index=False)
        self.partial_files.append(path)

    @staticmethod
    def _update_counters(
        counters: DefaultDict[int, Counter[Edge]],
        grouped_edges: pd.DataFrame,
    ) -> None:
        for row in grouped_edges.itertuples(index=False):
            counters[int(row.window_id)][(str(row.user), str(row.dst_host))] += int(row.count)


def compute_window_statistics(
    edge_counts_by_window: Mapping[int, Mapping[Edge, int]],
    window_seconds: int,
    rows_by_window: Mapping[int, int] | None = None,
    mapped_rows_by_window: Mapping[int, int] | None = None,
) -> pd.DataFrame:
    rows_by_window = rows_by_window or {}
    mapped_rows_by_window = mapped_rows_by_window or {}
    all_window_ids = sorted(
        set(edge_counts_by_window) | set(rows_by_window) | set(mapped_rows_by_window)
    )

    records: list[dict[str, float | int]] = []
    previous_edges: set[Edge] | None = None
    previous_users: set[str] | None = None
    previous_hosts: set[str] | None = None

    for window_id in all_window_ids:
        counter = Counter(edge_counts_by_window.get(window_id, {}))
        edges = set(counter)
        users = {user for user, _ in edges}
        hosts = {host for _, host in edges}
        events = int(sum(counter.values()))
        unique_edges = int(len(edges))
        unique_users = int(len(users))
        unique_hosts = int(len(hosts))
        nodes = unique_users + unique_hosts
        repeated_events = max(0, events - unique_edges)
        max_events_per_edge = int(max(counter.values(), default=0))
        time_start_sec, time_end_sec = window_bounds(window_id, window_seconds)

        new_edges, disappeared_edges, persistent_edges, edge_churn = churn_counts(
            edges, previous_edges
        )
        new_users, disappeared_users, _persistent_users, user_churn = churn_counts(
            users, previous_users
        )
        new_hosts, disappeared_hosts, _persistent_hosts, host_churn = churn_counts(
            hosts, previous_hosts
        )

        window_total_rows = int(rows_by_window.get(window_id, events))
        window_mapped_rows = int(mapped_rows_by_window.get(window_id, events))
        event_mapping_rate = safe_divide(window_mapped_rows, window_total_rows)

        records.append(
            {
                "window_id": int(window_id),
                "time_start_sec": int(time_start_sec),
                "time_end_sec": int(time_end_sec),
                "events": events,
                "unique_users": unique_users,
                "unique_hosts": unique_hosts,
                "nodes": nodes,
                "unique_edges": unique_edges,
                "repeated_events": repeated_events,
                "mean_events_per_edge": safe_divide(events, unique_edges),
                "max_events_per_edge": max_events_per_edge,
                "graph_density": safe_divide(unique_edges, unique_users * unique_hosts),
                "new_edges": int(new_edges),
                "disappeared_edges": int(disappeared_edges),
                "persistent_edges": int(persistent_edges),
                "edge_churn": edge_churn,
                "new_users": int(new_users),
                "new_hosts": int(new_hosts),
                "user_churn": user_churn,
                "host_churn": host_churn,
                "event_mapping_rate": event_mapping_rate,
            }
        )

        previous_edges = edges
        previous_users = users
        previous_hosts = hosts

    return pd.DataFrame.from_records(records)


def build_top_users(
    edge_counts_by_window: Mapping[int, Mapping[Edge, int]],
    window_seconds: int,
    top_n: int,
) -> pd.DataFrame:
    columns = [
        "window_id",
        "time_start_sec",
        "time_end_sec",
        "rank",
        "user",
        "events",
        "unique_hosts",
    ]
    if top_n <= 0:
        return pd.DataFrame(columns=columns)

    rows: list[dict[str, int | str]] = []
    for window_id in sorted(edge_counts_by_window):
        user_events: Counter[str] = Counter()
        user_hosts: DefaultDict[str, set[str]] = defaultdict(set)
        for (user, host), count in edge_counts_by_window[window_id].items():
            user_events[user] += int(count)
            user_hosts[user].add(host)
        start, end = window_bounds(window_id, window_seconds)
        ranked = sorted(user_events.items(), key=lambda item: (-item[1], item[0]))[:top_n]
        for rank, (user, events) in enumerate(ranked, start=1):
            rows.append(
                {
                    "window_id": int(window_id),
                    "time_start_sec": int(start),
                    "time_end_sec": int(end),
                    "rank": rank,
                    "user": user,
                    "events": int(events),
                    "unique_hosts": int(len(user_hosts[user])),
                }
            )
    return pd.DataFrame(rows, columns=columns)


def build_top_hosts(
    edge_counts_by_window: Mapping[int, Mapping[Edge, int]],
    window_seconds: int,
    top_n: int,
) -> pd.DataFrame:
    columns = [
        "window_id",
        "time_start_sec",
        "time_end_sec",
        "rank",
        "host",
        "events",
        "unique_users",
    ]
    if top_n <= 0:
        return pd.DataFrame(columns=columns)

    rows: list[dict[str, int | str]] = []
    for window_id in sorted(edge_counts_by_window):
        host_events: Counter[str] = Counter()
        host_users: DefaultDict[str, set[str]] = defaultdict(set)
        for (user, host), count in edge_counts_by_window[window_id].items():
            host_events[host] += int(count)
            host_users[host].add(user)
        start, end = window_bounds(window_id, window_seconds)
        ranked = sorted(host_events.items(), key=lambda item: (-item[1], item[0]))[:top_n]
        for rank, (host, events) in enumerate(ranked, start=1):
            rows.append(
                {
                    "window_id": int(window_id),
                    "time_start_sec": int(start),
                    "time_end_sec": int(end),
                    "rank": rank,
                    "host": host,
                    "events": int(events),
                    "unique_users": int(len(host_users[host])),
                }
            )
    return pd.DataFrame(rows, columns=columns)


def build_summary_row(
    input_path: str | Path,
    window_seconds: int,
    chunksize: int,
    total_rows: int,
    mapped_rows: int,
    stats: pd.DataFrame,
    construction_time_sec: float,
    peak_memory_mb: float,
    final_memory_mb: float,
) -> pd.DataFrame:
    def mean_or_zero(column: str) -> float:
        if stats.empty or column not in stats:
            return 0.0
        return float(stats[column].mean())

    def max_or_zero(column: str) -> int:
        if stats.empty or column not in stats:
            return 0
        return int(stats[column].max())

    row = {
        "input_path": str(input_path),
        "window_seconds": int(window_seconds),
        "chunksize": int(chunksize),
        "total_rows": int(total_rows),
        "mapped_rows": int(mapped_rows),
        "event_mapping_rate": safe_divide(mapped_rows, total_rows),
        "snapshots": int(len(stats)),
        "mean_nodes": mean_or_zero("nodes"),
        "mean_edges": mean_or_zero("unique_edges"),
        "max_nodes": max_or_zero("nodes"),
        "max_edges": max_or_zero("unique_edges"),
        "mean_events": mean_or_zero("events"),
        "max_events": max_or_zero("events"),
        "mean_density": mean_or_zero("graph_density"),
        "mean_edge_churn": mean_or_zero("edge_churn"),
        "construction_time_sec": float(construction_time_sec),
        "peak_memory_mb": float(peak_memory_mb),
        "final_memory_mb": float(final_memory_mb),
        "run_timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    return pd.DataFrame([row])
