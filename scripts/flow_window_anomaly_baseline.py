#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from dhgraph.anomaly import score_flow_window_anomalies  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run unsupervised structural anomaly scoring over flow graph-window "
            "statistics. Labels, if present in the source dataset, are not used to "
            "train this baseline."
        )
    )
    parser.add_argument("--window-stats", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--n-estimators", type=int, default=200)
    parser.add_argument("--contamination", type=float, default=0.05)
    parser.add_argument("--random-state", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    stats = pd.read_csv(args.window_stats)
    scored = score_flow_window_anomalies(
        stats,
        n_estimators=args.n_estimators,
        contamination=args.contamination,
        random_state=args.random_state,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    scored.to_csv(output_path, index=False)
    top20_path = output_path.with_name("flow_window_anomaly_top20.csv")
    scored.sort_values("anomaly_rank", ascending=True).head(20).to_csv(top20_path, index=False)
    print(f"[done] wrote {output_path}")
    print(f"[done] wrote {top20_path}")
    print("[note] This is unsupervised structural scoring, not supervised detection.")


if __name__ == "__main__":
    main()
