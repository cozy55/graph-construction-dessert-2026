#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from dhgraph.windowing import window_label  # noqa: E402


SCALABILITY_COLUMNS = [
    "window_label",
    "window_seconds",
    "snapshots",
    "total_rows",
    "mapped_rows",
    "event_mapping_rate",
    "construction_time_sec",
    "peak_memory_mb",
    "final_memory_mb",
    "mean_nodes",
    "mean_edges",
    "max_nodes",
    "max_edges",
    "mean_events",
    "max_events",
    "mean_density",
    "mean_edge_churn",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge LANL experiment outputs into paper tables.")
    parser.add_argument("--summary-files", nargs="+", required=True, help="Summary CSV files.")
    parser.add_argument("--output-dir", required=True, help="Directory for paper-ready outputs.")
    parser.add_argument(
        "--anomaly-files",
        nargs="*",
        default=[],
        help="Optional anomaly score CSV files to summarize.",
    )
    parser.add_argument(
        "--flow-summary-files",
        nargs="*",
        default=[],
        help="Optional CICIDS/flow summary CSV files for a cross-dataset scalability table.",
    )
    return parser.parse_args()


def load_summary_rows(paths: Iterable[str]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for raw_path in paths:
        path = Path(raw_path)
        frame = pd.read_csv(path)
        if frame.empty:
            continue
        row = frame.iloc[0].to_dict()
        if "window_seconds" not in row:
            raise ValueError(f"Summary file lacks window_seconds column: {path}")
        row["summary_file"] = str(path)
        row["window_label"] = window_label(int(row["window_seconds"]))
        rows.append(row)
    if not rows:
        raise ValueError("No non-empty summary rows were loaded.")
    return pd.DataFrame(rows).sort_values("window_seconds").reset_index(drop=True)


def load_flow_summary_rows(paths: Iterable[str]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for raw_path in paths:
        path = Path(raw_path)
        frame = pd.read_csv(path)
        if frame.empty:
            continue
        row = frame.iloc[0].to_dict()
        if "window_seconds" not in row:
            raise ValueError(f"Flow summary file lacks window_seconds column: {path}")
        row["summary_file"] = str(path)
        row["dataset"] = str(row.get("dataset_name", "flow"))
        row["graph_instantiation"] = "host-host and host-service flow graph"
        row["window_label"] = window_label(int(row["window_seconds"]))
        rows.append(row)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["dataset", "window_seconds"]).reset_index(drop=True)


def build_scalability_table(summary: pd.DataFrame) -> pd.DataFrame:
    table = summary.copy()
    for column in SCALABILITY_COLUMNS:
        if column not in table.columns:
            table[column] = pd.NA
    return table.loc[:, SCALABILITY_COLUMNS]


def build_cross_dataset_scalability_table(
    lanl_summary: pd.DataFrame,
    flow_summary: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    for _, row in lanl_summary.iterrows():
        rows.append(
            {
                "dataset": "LANL auth associations",
                "graph_instantiation": "user-host authentication graph",
                "window_label": row["window_label"],
                "window_seconds": int(row["window_seconds"]),
                "snapshots": int(row["snapshots"]),
                "total_rows": int(row["total_rows"]),
                "mapped_rows": int(row["mapped_rows"]),
                "event_mapping_rate": float(row["event_mapping_rate"]),
                "mean_nodes": float(row["mean_nodes"]),
                "mean_edges": float(row["mean_edges"]),
                "max_nodes": int(row["max_nodes"]),
                "max_edges": int(row["max_edges"]),
                "construction_time_sec": float(row["construction_time_sec"]),
                "peak_memory_mb": float(row["peak_memory_mb"]),
                "limitations": "Successful user-computer authentication associations only.",
            }
        )

    if not flow_summary.empty:
        for _, row in flow_summary.iterrows():
            rows.append(
                {
                    "dataset": row.get("dataset", "flow"),
                    "graph_instantiation": row.get(
                        "graph_instantiation", "host-host and host-service flow graph"
                    ),
                    "window_label": row["window_label"],
                    "window_seconds": int(row["window_seconds"]),
                    "snapshots": int(row["snapshots"]),
                    "total_rows": int(row["total_rows"]),
                    "mapped_rows": int(row["mapped_rows"]),
                    "event_mapping_rate": float(row["event_mapping_rate"]),
                    "mean_nodes": float(row["mean_nodes"]),
                    "mean_edges": float(row["mean_edges"]),
                    "max_nodes": int(row["max_nodes"]),
                    "max_edges": int(row["max_edges"]),
                    "construction_time_sec": float(row["construction_time_sec"]),
                    "peak_memory_mb": float(row["peak_memory_mb"]),
                    "limitations": (
                        "Flow labels may support supervised baselines, but this table "
                        "reports graph construction metrics only."
                    ),
                }
            )
    return pd.DataFrame(rows)


def build_representation_comparison_table() -> pd.DataFrame:
    rows = [
        {
            "representation": "Flat authentication table",
            "preserves_users": "yes",
            "preserves_hosts": "yes",
            "preserves_time": "yes",
            "explicit_edges": "no",
            "node_types": "no",
            "edge_types": "no",
            "edge_frequency_attributes": "no",
            "supports_temporal_churn": "manual aggregation required",
            "suitable_for_lateral_movement_style_analysis": "limited",
            "limitations": "Associations are row-level records, not explicit graph structure.",
        },
        {
            "representation": "Static homogeneous graph",
            "preserves_users": "yes, but untyped",
            "preserves_hosts": "yes, but untyped",
            "preserves_time": "no",
            "explicit_edges": "yes",
            "node_types": "no",
            "edge_types": "no",
            "edge_frequency_attributes": "optional, not temporal",
            "supports_temporal_churn": "no",
            "suitable_for_lateral_movement_style_analysis": "limited",
            "limitations": "Collapses users and hosts into one node type and loses window order.",
        },
        {
            "representation": "Static heterogeneous graph",
            "preserves_users": "yes",
            "preserves_hosts": "yes",
            "preserves_time": "no",
            "explicit_edges": "yes",
            "node_types": "yes",
            "edge_types": "yes",
            "edge_frequency_attributes": "optional, not temporal",
            "supports_temporal_churn": "no",
            "suitable_for_lateral_movement_style_analysis": "limited",
            "limitations": "Preserves typed user-host structure but collapses temporal dynamics.",
        },
        {
            "representation": "Dynamic homogeneous graph",
            "preserves_users": "yes, but untyped",
            "preserves_hosts": "yes, but untyped",
            "preserves_time": "yes",
            "explicit_edges": "yes",
            "node_types": "no",
            "edge_types": "limited",
            "edge_frequency_attributes": "no",
            "supports_temporal_churn": "yes",
            "suitable_for_lateral_movement_style_analysis": "partial",
            "limitations": "Temporal structure is retained, but user and host roles are not explicit.",
        },
        {
            "representation": "Dynamic heterogeneous graph",
            "preserves_users": "yes",
            "preserves_hosts": "yes",
            "preserves_time": "yes",
            "explicit_edges": "yes",
            "node_types": "yes",
            "edge_types": "yes",
            "edge_frequency_attributes": "no",
            "supports_temporal_churn": "yes",
            "suitable_for_lateral_movement_style_analysis": "yes",
            "limitations": "In this LANL experiment, only user-host authentication edges are available.",
        },
        {
            "representation": "Dynamic heterogeneous graph with edge frequency attributes",
            "preserves_users": "yes",
            "preserves_hosts": "yes",
            "preserves_time": "yes",
            "explicit_edges": "yes",
            "node_types": "yes",
            "edge_types": "yes",
            "edge_frequency_attributes": "yes",
            "supports_temporal_churn": "yes",
            "suitable_for_lateral_movement_style_analysis": "yes",
            "limitations": (
                "LANL supports only successful user-computer authentication associations; "
                "it does not provide failed logins, packet/flow features, DNS, ports, "
                "or native attack labels."
            ),
        },
    ]
    return pd.DataFrame(rows)


def build_anomaly_summary(paths: Iterable[str]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for raw_path in paths:
        path = Path(raw_path)
        frame = pd.read_csv(path)
        if frame.empty:
            continue
        missing = [column for column in ("anomaly_label", "anomaly_score", "anomaly_rank") if column not in frame]
        if missing:
            raise ValueError(f"Anomaly file {path} is missing column(s): {', '.join(missing)}")

        window_seconds = None
        if {"time_start_sec", "time_end_sec"}.issubset(frame.columns):
            durations = frame["time_end_sec"] - frame["time_start_sec"]
            if not durations.empty:
                window_seconds = int(durations.mode().iloc[0])

        top = frame.sort_values("anomaly_rank", ascending=True).iloc[0]
        anomaly_count = int((frame["anomaly_label"].astype(str) == "anomaly").sum())
        rows.append(
            {
                "anomaly_file": str(path),
                "window_label": window_label(window_seconds) if window_seconds else "unknown",
                "window_seconds": window_seconds,
                "total_windows": int(len(frame)),
                "anomaly_windows": anomaly_count,
                "anomaly_window_rate": anomaly_count / max(1, len(frame)),
                "top_window_id": int(top["window_id"]) if "window_id" in top else pd.NA,
                "top_anomaly_score": float(top["anomaly_score"]),
            }
        )
    return pd.DataFrame(rows)


def write_results_markdown(
    path: Path,
    scalability: pd.DataFrame,
    cross_dataset_scalability: pd.DataFrame,
    representation: pd.DataFrame,
    anomaly_summary: pd.DataFrame | None,
) -> None:
    lines = [
        "# LANL Paper Results Summary",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        "",
        "These tables summarize graph-window construction over successful LANL "
        "user-computer authentication associations. They do not report supervised "
        "attack-detection performance.",
        "",
        "## Scalability",
        "",
        _markdown_table(scalability),
        "",
        "## Cross-Dataset Scalability",
        "",
        _markdown_table(cross_dataset_scalability),
        "",
        "## Representation Comparison",
        "",
        _markdown_table(representation),
    ]
    if anomaly_summary is not None and not anomaly_summary.empty:
        lines.extend(["", "## Unsupervised Structural Anomaly Summary", "", _markdown_table(anomaly_summary)])
    lines.extend(
        [
            "",
            "## Paper CSVs",
            "",
            "- `paper_table_scalability.csv`: construction time, memory, snapshot counts, and graph sizes.",
            "- `paper_table_cross_dataset_scalability.csv`: LANL and optional flow-dataset construction metrics.",
            "- `paper_table_representation_comparison.csv`: representation-quality comparison.",
            "- `paper_table_anomaly_summary.csv`: optional summary of unsupervised structural anomaly scores.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_No rows._"
    columns = list(frame.columns)
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join(["---"] * len(columns)) + " |"
    rows = [header, separator]
    for _, row in frame.iterrows():
        values = [_format_markdown_value(row[column]) for column in columns]
        rows.append("| " + " | ".join(values) + " |")
    return "\n".join(rows)


def _format_markdown_value(value: object) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, float):
        return f"{value:.4g}"
    return str(value).replace("|", "/")


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    summary = load_summary_rows(args.summary_files)
    flow_summary = load_flow_summary_rows(args.flow_summary_files)
    scalability = build_scalability_table(summary)
    cross_dataset_scalability = build_cross_dataset_scalability_table(summary, flow_summary)
    representation = build_representation_comparison_table()
    anomaly_summary = build_anomaly_summary(args.anomaly_files) if args.anomaly_files else None

    scalability_path = output_dir / "paper_table_scalability.csv"
    cross_scalability_path = output_dir / "paper_table_cross_dataset_scalability.csv"
    representation_path = output_dir / "paper_table_representation_comparison.csv"
    markdown_path = output_dir / "paper_results_summary.md"

    scalability.to_csv(scalability_path, index=False)
    cross_dataset_scalability.to_csv(cross_scalability_path, index=False)
    representation.to_csv(representation_path, index=False)
    if anomaly_summary is not None:
        anomaly_summary.to_csv(output_dir / "paper_table_anomaly_summary.csv", index=False)
    write_results_markdown(
        markdown_path,
        scalability,
        cross_dataset_scalability,
        representation,
        anomaly_summary,
    )

    print(f"[done] wrote {scalability_path}")
    print(f"[done] wrote {cross_scalability_path}")
    print(f"[done] wrote {representation_path}")
    if anomaly_summary is not None:
        print(f"[done] wrote {output_dir / 'paper_table_anomaly_summary.csv'}")
    print(f"[done] wrote {markdown_path}")


if __name__ == "__main__":
    main()
