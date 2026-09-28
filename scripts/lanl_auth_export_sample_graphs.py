#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from dhgraph.export import export_selected_window_samples  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Export capped user-host authentication sample graphs for selected LANL "
            "windows. Full 67M-row graphs are never built in memory."
        )
    )
    parser.add_argument("--input", required=True, help="Processed LANL authentication CSV.")
    parser.add_argument("--windows", required=True, help="CSV containing selected window_id values.")
    parser.add_argument("--output-dir", required=True, help="Directory for edge/node/GraphML files.")
    parser.add_argument("--window-seconds", required=True, type=int)
    parser.add_argument("--chunksize", type=int, default=2_000_000)
    parser.add_argument("--max-edges", type=int, default=5_000)
    parser.add_argument(
        "--no-graphml",
        action="store_true",
        help="Write only edge/node CSV files and skip GraphML export.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    outputs = export_selected_window_samples(
        input_path=args.input,
        windows_path=args.windows,
        output_dir=args.output_dir,
        window_seconds=args.window_seconds,
        chunksize=args.chunksize,
        max_edges=args.max_edges,
        write_graphml=not args.no_graphml,
    )
    for window_id, edges_path, nodes_path, graphml_path in outputs:
        graphml_text = f", graphml={graphml_path}" if graphml_path is not None else ""
        print(
            f"[window {window_id}] edges={edges_path}, nodes={nodes_path}{graphml_text}"
        )
    print(f"[done] exported {len(outputs)} selected window sample graph(s)")


if __name__ == "__main__":
    main()
