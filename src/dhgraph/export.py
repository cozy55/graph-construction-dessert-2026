from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Mapping

import pandas as pd

from .graph_stats import Edge, aggregate_auth_chunk
from .io import iter_lanl_auth_chunks


def load_selected_window_ids(windows_path: str | Path) -> list[int]:
    windows = pd.read_csv(windows_path)
    if "window_id" not in windows.columns:
        raise ValueError("Selected-windows CSV must contain a window_id column.")
    return [int(value) for value in windows["window_id"].dropna().tolist()]


def aggregate_selected_windows(
    input_path: str | Path,
    selected_window_ids: list[int],
    window_seconds: int,
    chunksize: int,
) -> dict[int, Counter[Edge]]:
    selected = set(selected_window_ids)
    counters: dict[int, Counter[Edge]] = {window_id: Counter() for window_id in selected_window_ids}
    if not selected:
        return counters

    for chunk_index, chunk in enumerate(iter_lanl_auth_chunks(input_path, chunksize), start=1):
        aggregation = aggregate_auth_chunk(chunk, window_seconds)
        grouped = aggregation.edge_counts
        if grouped.empty:
            print(f"[chunk {chunk_index}] no mapped rows in selected-window export")
            continue
        grouped = grouped[grouped["window_id"].isin(selected)]
        for row in grouped.itertuples(index=False):
            counters[int(row.window_id)][(str(row.user), str(row.dst_host))] += int(row.count)
        print(
            f"[chunk {chunk_index}] scanned_rows={aggregation.total_rows} "
            f"selected_edge_groups={len(grouped)}"
        )
    return counters


def export_window_sample(
    window_id: int,
    edge_counter: Mapping[Edge, int],
    output_dir: str | Path,
    max_edges: int,
    write_graphml: bool = True,
) -> tuple[Path, Path, Path | None]:
    if max_edges <= 0:
        raise ValueError("--max-edges must be a positive integer.")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ranked_edges = sorted(
        edge_counter.items(),
        key=lambda item: (-int(item[1]), item[0][0], item[0][1]),
    )[:max_edges]

    edge_rows = [
        {
            "source": user,
            "target": host,
            "edge_type": "authenticates_to",
            "count": int(count),
        }
        for (user, host), count in ranked_edges
    ]
    edges_path = out_dir / f"window_{int(window_id)}_edges.csv"
    pd.DataFrame(edge_rows, columns=["source", "target", "edge_type", "count"]).to_csv(
        edges_path, index=False
    )

    node_rows = []
    seen_nodes: set[tuple[str, str]] = set()
    for (user, host), _count in ranked_edges:
        user_node = (user, "user")
        host_node = (host, "host")
        if user_node not in seen_nodes:
            seen_nodes.add(user_node)
            node_rows.append({"node_id": user, "node_type": "user"})
        if host_node not in seen_nodes:
            seen_nodes.add(host_node)
            node_rows.append({"node_id": host, "node_type": "host"})

    nodes_path = out_dir / f"window_{int(window_id)}_nodes.csv"
    pd.DataFrame(node_rows, columns=["node_id", "node_type"]).to_csv(nodes_path, index=False)

    graphml_path: Path | None = None
    if write_graphml:
        graphml_path = out_dir / f"window_{int(window_id)}.graphml"
        _write_graphml(ranked_edges, graphml_path)

    return edges_path, nodes_path, graphml_path


def export_selected_window_samples(
    input_path: str | Path,
    windows_path: str | Path,
    output_dir: str | Path,
    window_seconds: int,
    chunksize: int,
    max_edges: int,
    write_graphml: bool = True,
) -> list[tuple[int, Path, Path, Path | None]]:
    selected_window_ids = load_selected_window_ids(windows_path)
    counters = aggregate_selected_windows(
        input_path=input_path,
        selected_window_ids=selected_window_ids,
        window_seconds=window_seconds,
        chunksize=chunksize,
    )
    outputs = []
    for window_id in selected_window_ids:
        edges_path, nodes_path, graphml_path = export_window_sample(
            window_id=window_id,
            edge_counter=counters.get(window_id, Counter()),
            output_dir=output_dir,
            max_edges=max_edges,
            write_graphml=write_graphml,
        )
        outputs.append((window_id, edges_path, nodes_path, graphml_path))
    return outputs


def _write_graphml(ranked_edges: list[tuple[Edge, int]], graphml_path: Path) -> None:
    try:
        import networkx as nx
    except ImportError as exc:
        raise ImportError(
            "networkx is required for GraphML export. Install requirements.txt or "
            "run with --no-graphml."
        ) from exc

    graph = nx.DiGraph()
    for (user, host), count in ranked_edges:
        user_key = f"user:{user}"
        host_key = f"host:{host}"
        graph.add_node(user_key, node_id=user, node_type="user")
        graph.add_node(host_key, node_id=host, node_type="host")
        graph.add_edge(
            user_key,
            host_key,
            edge_type="authenticates_to",
            count=int(count),
        )
    nx.write_graphml(graph, graphml_path)
