from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import DefaultDict, Iterable, Mapping

import pandas as pd

from .io import read_csv_columns, validate_required_columns
from .windowing import churn_counts, safe_divide, window_bounds


FlowEdge = tuple[str, str, str]
HostEdge = tuple[str, str]
ServiceEdge = tuple[str, str]


FLOW_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "timestamp": (
        "timestamp",
        "time",
        "ts",
        "flow start timestamp",
        "flow_start_timestamp",
        "starttime",
        "start_time",
        "date flow start",
    ),
    "src_host": (
        "src_host",
        "src_ip",
        "source ip",
        "source_ip",
        "src ip",
        "srcip",
    ),
    "dst_host": (
        "dst_host",
        "dst_ip",
        "destination ip",
        "destination_ip",
        "dst ip",
        "dstip",
    ),
    "src_port": (
        "src_port",
        "source port",
        "source_port",
        "src port",
        "sport",
    ),
    "dst_port": (
        "dst_port",
        "destination port",
        "destination_port",
        "dst port",
        "dport",
    ),
    "protocol": ("protocol", "proto"),
    "label": ("label", "class", "attack", "attack_label"),
}

BENIGN_LABELS = {"", "0", "benign", "normal", "background"}


@dataclass
class FlowColumnMap:
    timestamp: str
    src_host: str
    dst_host: str
    src_port: str | None = None
    dst_port: str | None = None
    protocol: str | None = None
    label: str | None = None

    def usecols(self) -> list[str]:
        values = [
            self.timestamp,
            self.src_host,
            self.dst_host,
            self.src_port,
            self.dst_port,
            self.protocol,
            self.label,
        ]
        return list(dict.fromkeys(value for value in values if value is not None))


@dataclass
class FlowChunkAggregation:
    edge_counts: pd.DataFrame
    rows_by_window: Counter[int]
    mapped_rows_by_window: Counter[int]
    attack_rows_by_window: Counter[int]
    total_rows: int
    mapped_rows: int
    attack_rows: int
    invalid_timestamp_rows: int


def detect_flow_columns(path: str | Path) -> FlowColumnMap:
    columns = read_csv_columns(path)
    normalized = {_normalize_column_name(column): column for column in columns}

    detected: dict[str, str | None] = {}
    for canonical, aliases in FLOW_COLUMN_ALIASES.items():
        detected[canonical] = None
        for alias in aliases:
            match = normalized.get(_normalize_column_name(alias))
            if match is not None:
                detected[canonical] = match
                break

    required = ["timestamp", "src_host", "dst_host"]
    missing = [column for column in required if detected[column] is None]
    if missing:
        available = ", ".join(columns)
        raise ValueError(
            "Could not detect required flow column(s): "
            + ", ".join(missing)
            + f". Available columns: {available}"
        )

    return FlowColumnMap(
        timestamp=str(detected["timestamp"]),
        src_host=str(detected["src_host"]),
        dst_host=str(detected["dst_host"]),
        src_port=detected["src_port"],
        dst_port=detected["dst_port"],
        protocol=detected["protocol"],
        label=detected["label"],
    )


def iter_flow_chunks(
    path: str | Path,
    chunksize: int,
    column_map: FlowColumnMap | None = None,
) -> Iterable[pd.DataFrame]:
    if chunksize <= 0:
        raise ValueError("--chunksize must be a positive integer.")

    mapping = column_map or detect_flow_columns(path)
    validate_required_columns(path, (mapping.timestamp, mapping.src_host, mapping.dst_host))
    rename_map = {
        mapping.timestamp: "timestamp",
        mapping.src_host: "src_host",
        mapping.dst_host: "dst_host",
    }
    optional = {
        mapping.src_port: "src_port",
        mapping.dst_port: "dst_port",
        mapping.protocol: "protocol",
        mapping.label: "label",
    }
    rename_map.update({k: v for k, v in optional.items() if k is not None})

    for chunk in pd.read_csv(path, usecols=mapping.usecols(), chunksize=chunksize):
        yield chunk.rename(columns=rename_map)


def aggregate_flow_chunk(
    chunk: pd.DataFrame,
    window_seconds: int,
    timestamp_unit: str = "auto",
    timestamp_dayfirst: bool = False,
) -> FlowChunkAggregation:
    required = {"timestamp", "src_host", "dst_host"}
    missing = sorted(required - set(chunk.columns))
    if missing:
        raise ValueError(f"Input chunk is missing required column(s): {', '.join(missing)}")

    total_rows = int(len(chunk))
    if total_rows == 0:
        return FlowChunkAggregation(
            edge_counts=_empty_flow_edge_frame(),
            rows_by_window=Counter(),
            mapped_rows_by_window=Counter(),
            attack_rows_by_window=Counter(),
            total_rows=0,
            mapped_rows=0,
            attack_rows=0,
            invalid_timestamp_rows=0,
        )

    timestamps = parse_timestamps_to_seconds(
        chunk["timestamp"],
        timestamp_unit=timestamp_unit,
        dayfirst=timestamp_dayfirst,
    )
    valid_timestamp = timestamps.notna()
    invalid_timestamp_rows = int((~valid_timestamp).sum())

    rows_by_window: Counter[int] = Counter()
    if valid_timestamp.any():
        valid_window_ids = (timestamps.loc[valid_timestamp].astype("int64") // window_seconds)
        rows_by_window.update(
            {int(k): int(v) for k, v in valid_window_ids.value_counts(sort=False).items()}
        )

    src_hosts, valid_src = _clean_entity_column(chunk["src_host"])
    dst_hosts, valid_dst = _clean_entity_column(chunk["dst_host"])
    mapped_mask = (valid_timestamp & valid_src & valid_dst).fillna(False)
    mapped_rows = int(mapped_mask.sum())

    if mapped_rows == 0:
        return FlowChunkAggregation(
            edge_counts=_empty_flow_edge_frame(),
            rows_by_window=rows_by_window,
            mapped_rows_by_window=Counter(),
            attack_rows_by_window=Counter(),
            total_rows=total_rows,
            mapped_rows=0,
            attack_rows=0,
            invalid_timestamp_rows=invalid_timestamp_rows,
        )

    services = _build_service_labels(chunk, mapped_mask)
    mapped_window_ids = (
        timestamps.loc[mapped_mask].astype("int64") // int(window_seconds)
    ).astype("int64")
    mapped = pd.DataFrame(
        {
            "window_id": mapped_window_ids.to_numpy(),
            "src_host": src_hosts.loc[mapped_mask].astype(str).to_numpy(),
            "dst_host": dst_hosts.loc[mapped_mask].astype(str).to_numpy(),
            "service": services.to_numpy(),
        }
    )
    grouped = (
        mapped.groupby(["window_id", "src_host", "dst_host", "service"], sort=False, observed=True)
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

    attack_rows_by_window: Counter[int] = Counter()
    attack_rows = 0
    if "label" in chunk.columns:
        labels = chunk["label"].astype("string").str.strip().str.lower().fillna("")
        attack_mask = mapped_mask & ~labels.isin(BENIGN_LABELS)
        attack_rows = int(attack_mask.sum())
        if attack_rows:
            attack_window_ids = (
                timestamps.loc[attack_mask].astype("int64") // int(window_seconds)
            )
            attack_rows_by_window.update(
                {
                    int(k): int(v)
                    for k, v in attack_window_ids.value_counts(sort=False).items()
                }
            )

    return FlowChunkAggregation(
        edge_counts=grouped,
        rows_by_window=rows_by_window,
        mapped_rows_by_window=mapped_rows_by_window,
        attack_rows_by_window=attack_rows_by_window,
        total_rows=total_rows,
        mapped_rows=mapped_rows,
        attack_rows=attack_rows,
        invalid_timestamp_rows=invalid_timestamp_rows,
    )


class FlowWindowEdgeAggregator:
    def __init__(self) -> None:
        self.counters: DefaultDict[int, Counter[FlowEdge]] = defaultdict(Counter)

    def update(self, grouped_edges: pd.DataFrame) -> None:
        if grouped_edges.empty:
            return
        for row in grouped_edges.itertuples(index=False):
            key = (str(row.src_host), str(row.dst_host), str(row.service))
            self.counters[int(row.window_id)][key] += int(row.count)

    def finalize(self) -> dict[int, Counter[FlowEdge]]:
        return dict(self.counters)


def compute_flow_window_statistics(
    edge_counts_by_window: Mapping[int, Mapping[FlowEdge, int]],
    window_seconds: int,
    rows_by_window: Mapping[int, int] | None = None,
    mapped_rows_by_window: Mapping[int, int] | None = None,
    attack_rows_by_window: Mapping[int, int] | None = None,
) -> pd.DataFrame:
    rows_by_window = rows_by_window or {}
    mapped_rows_by_window = mapped_rows_by_window or {}
    attack_rows_by_window = attack_rows_by_window or {}
    all_window_ids = sorted(
        set(edge_counts_by_window)
        | set(rows_by_window)
        | set(mapped_rows_by_window)
        | set(attack_rows_by_window)
    )

    records: list[dict[str, float | int]] = []
    previous_flow_edges: set[FlowEdge] | None = None
    previous_hosts: set[str] | None = None
    previous_services: set[str] | None = None

    for window_id in all_window_ids:
        counter = Counter(edge_counts_by_window.get(window_id, {}))
        flow_edges = set(counter)
        host_edges: set[HostEdge] = {(src, dst) for src, dst, _service in flow_edges}
        service_edges: set[ServiceEdge] = {(src, service) for src, _dst, service in flow_edges}
        hosts = {src for src, _dst, _service in flow_edges} | {
            dst for _src, dst, _service in flow_edges
        }
        services = {service for _src, _dst, service in flow_edges}

        events = int(sum(counter.values()))
        unique_flow_edges = int(len(flow_edges))
        repeated_events = max(0, events - unique_flow_edges)
        unique_hosts = int(len(hosts))
        unique_services = int(len(services))
        nodes = unique_hosts + unique_services
        start, end = window_bounds(window_id, window_seconds)

        new_edges, disappeared_edges, persistent_edges, edge_churn = churn_counts(
            flow_edges, previous_flow_edges
        )
        new_hosts, _disappeared_hosts, _persistent_hosts, host_churn = churn_counts(
            hosts, previous_hosts
        )
        new_services, _disappeared_services, _persistent_services, service_churn = churn_counts(
            services, previous_services
        )

        window_total_rows = int(rows_by_window.get(window_id, events))
        window_mapped_rows = int(mapped_rows_by_window.get(window_id, events))
        attack_rows = int(attack_rows_by_window.get(window_id, 0))

        records.append(
            {
                "window_id": int(window_id),
                "time_start_sec": int(start),
                "time_end_sec": int(end),
                "events": events,
                "unique_hosts": unique_hosts,
                "unique_services": unique_services,
                "nodes": nodes,
                "unique_host_edges": int(len(host_edges)),
                "unique_service_edges": int(len(service_edges)),
                "unique_flow_edges": unique_flow_edges,
                "repeated_events": repeated_events,
                "mean_events_per_flow_edge": safe_divide(events, unique_flow_edges),
                "max_events_per_flow_edge": int(max(counter.values(), default=0)),
                "host_graph_density": safe_divide(
                    len(host_edges), unique_hosts * max(1, unique_hosts - 1)
                ),
                "host_service_density": safe_divide(
                    len(service_edges), unique_hosts * unique_services
                ),
                "new_flow_edges": int(new_edges),
                "disappeared_flow_edges": int(disappeared_edges),
                "persistent_flow_edges": int(persistent_edges),
                "flow_edge_churn": edge_churn,
                "new_hosts": int(new_hosts),
                "new_services": int(new_services),
                "host_churn": host_churn,
                "service_churn": service_churn,
                "event_mapping_rate": safe_divide(window_mapped_rows, window_total_rows),
                "labeled_attack_events": attack_rows,
                "labeled_attack_event_rate": safe_divide(attack_rows, window_mapped_rows),
            }
        )

        previous_flow_edges = flow_edges
        previous_hosts = hosts
        previous_services = services

    return pd.DataFrame.from_records(records)


def build_flow_summary_row(
    input_path: str | Path,
    dataset_name: str,
    window_seconds: int,
    chunksize: int,
    total_rows: int,
    mapped_rows: int,
    attack_rows: int,
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
        "dataset_name": dataset_name,
        "window_seconds": int(window_seconds),
        "chunksize": int(chunksize),
        "total_rows": int(total_rows),
        "mapped_rows": int(mapped_rows),
        "event_mapping_rate": safe_divide(mapped_rows, total_rows),
        "labeled_attack_events": int(attack_rows),
        "labeled_attack_event_rate": safe_divide(attack_rows, mapped_rows),
        "snapshots": int(len(stats)),
        "mean_nodes": mean_or_zero("nodes"),
        "mean_edges": mean_or_zero("unique_flow_edges"),
        "max_nodes": max_or_zero("nodes"),
        "max_edges": max_or_zero("unique_flow_edges"),
        "mean_events": mean_or_zero("events"),
        "max_events": max_or_zero("events"),
        "mean_host_density": mean_or_zero("host_graph_density"),
        "mean_flow_edge_churn": mean_or_zero("flow_edge_churn"),
        "construction_time_sec": float(construction_time_sec),
        "peak_memory_mb": float(peak_memory_mb),
        "final_memory_mb": float(final_memory_mb),
        "run_timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    return pd.DataFrame([row])


def build_top_flow_sources(
    edge_counts_by_window: Mapping[int, Mapping[FlowEdge, int]],
    window_seconds: int,
    top_n: int,
) -> pd.DataFrame:
    rows = []
    for window_id in sorted(edge_counts_by_window):
        counts: Counter[str] = Counter()
        destinations: DefaultDict[str, set[str]] = defaultdict(set)
        for (src, dst, _service), count in edge_counts_by_window[window_id].items():
            counts[src] += int(count)
            destinations[src].add(dst)
        start, end = window_bounds(window_id, window_seconds)
        for rank, (src, events) in enumerate(
            sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:top_n], start=1
        ):
            rows.append(
                {
                    "window_id": int(window_id),
                    "time_start_sec": int(start),
                    "time_end_sec": int(end),
                    "rank": rank,
                    "src_host": src,
                    "events": int(events),
                    "unique_destinations": int(len(destinations[src])),
                }
            )
    return pd.DataFrame(
        rows,
        columns=[
            "window_id",
            "time_start_sec",
            "time_end_sec",
            "rank",
            "src_host",
            "events",
            "unique_destinations",
        ],
    )


def build_top_flow_services(
    edge_counts_by_window: Mapping[int, Mapping[FlowEdge, int]],
    window_seconds: int,
    top_n: int,
) -> pd.DataFrame:
    rows = []
    for window_id in sorted(edge_counts_by_window):
        counts: Counter[str] = Counter()
        sources: DefaultDict[str, set[str]] = defaultdict(set)
        for (src, _dst, service), count in edge_counts_by_window[window_id].items():
            counts[service] += int(count)
            sources[service].add(src)
        start, end = window_bounds(window_id, window_seconds)
        for rank, (service, events) in enumerate(
            sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:top_n], start=1
        ):
            rows.append(
                {
                    "window_id": int(window_id),
                    "time_start_sec": int(start),
                    "time_end_sec": int(end),
                    "rank": rank,
                    "service": service,
                    "events": int(events),
                    "unique_sources": int(len(sources[service])),
                }
            )
    return pd.DataFrame(
        rows,
        columns=[
            "window_id",
            "time_start_sec",
            "time_end_sec",
            "rank",
            "service",
            "events",
            "unique_sources",
        ],
    )


def parse_timestamps_to_seconds(
    series: pd.Series,
    timestamp_unit: str = "auto",
    dayfirst: bool = False,
) -> pd.Series:
    if timestamp_unit not in {"auto", "s", "ms", "us", "ns"}:
        raise ValueError("timestamp_unit must be one of: auto, s, ms, us, ns.")

    numeric = pd.to_numeric(series, errors="coerce")
    numeric_ratio = float(numeric.notna().mean()) if len(numeric) else 0.0
    if timestamp_unit != "auto" or numeric_ratio >= 0.9:
        unit = timestamp_unit if timestamp_unit != "auto" else _infer_numeric_unit(numeric)
        divisor = {"s": 1, "ms": 1_000, "us": 1_000_000, "ns": 1_000_000_000}[unit]
        return numeric / divisor

    datetimes = _parse_datetimes(series, dayfirst=dayfirst)
    seconds = pd.Series(pd.NA, index=series.index, dtype="Float64")
    valid = datetimes.notna()
    if valid.any():
        divisor = _datetime_integer_divisor(datetimes.dtype)
        seconds.loc[valid] = datetimes.loc[valid].astype("int64") / divisor
    return seconds


def _parse_datetimes(series: pd.Series, dayfirst: bool) -> pd.Series:
    try:
        return pd.to_datetime(
            series,
            errors="coerce",
            utc=True,
            format="mixed",
            dayfirst=dayfirst,
        )
    except TypeError:
        return pd.to_datetime(series, errors="coerce", utc=True, dayfirst=dayfirst)


def _infer_numeric_unit(series: pd.Series) -> str:
    valid = series.dropna().abs()
    if valid.empty:
        return "s"
    median = float(valid.median())
    if median > 1e17:
        return "ns"
    if median > 1e14:
        return "us"
    if median > 1e11:
        return "ms"
    return "s"


def _datetime_integer_divisor(dtype: object) -> int:
    dtype_text = str(dtype)
    if "[ns" in dtype_text:
        return 1_000_000_000
    if "[us" in dtype_text:
        return 1_000_000
    if "[ms" in dtype_text:
        return 1_000
    return 1


def _normalize_column_name(column: str) -> str:
    return " ".join(str(column).strip().lower().replace("_", " ").split())


def _clean_entity_column(series: pd.Series) -> tuple[pd.Series, pd.Series]:
    values = series.astype("string").str.strip()
    valid = (values.notna() & values.ne("")).fillna(False)
    return values, valid


def _build_service_labels(chunk: pd.DataFrame, mapped_mask: pd.Series) -> pd.Series:
    if "protocol" in chunk.columns:
        protocol = chunk["protocol"].astype("string").str.strip().fillna("unknown_proto")
    else:
        protocol = pd.Series("unknown_proto", index=chunk.index, dtype="string")

    if "dst_port" in chunk.columns:
        ports = chunk["dst_port"].astype("string").str.strip().fillna("unknown_port")
        ports = ports.str.replace(r"\.0$", "", regex=True)
    else:
        ports = pd.Series("unknown_port", index=chunk.index, dtype="string")

    services = protocol + "/" + ports
    return services.loc[mapped_mask].astype(str)


def _empty_flow_edge_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=["window_id", "src_host", "dst_host", "service", "count"])
