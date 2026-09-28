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

from dhgraph.anomaly import score_window_anomalies  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run unsupervised structural anomaly scoring over LANL graph-window "
            "statistics. This is not supervised attack detection."
        )
    )
    parser.add_argument("--window-stats", required=True, help="Window stats CSV.")
    parser.add_argument("--output", required=True, help="Output anomaly scores CSV.")
    parser.add_argument("--n-estimators", type=int, default=200)
    parser.add_argument("--contamination", type=float, default=0.05)
    parser.add_argument("--random-state", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.n_estimators <= 0:
        raise ValueError("--n-estimators must be a positive integer.")

    stats = pd.read_csv(args.window_stats)
    scored = score_window_anomalies(
        stats,
        n_estimators=args.n_estimators,
        contamination=args.contamination,
        random_state=args.random_state,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    scored.to_csv(output_path, index=False)

    top20_path = output_path.with_name("window_anomaly_top20.csv")
    scored.sort_values("anomaly_rank", ascending=True).head(20).to_csv(top20_path, index=False)
    print(
        f"[done] wrote {output_path}\n"
        f"[done] wrote {top20_path}\n"
        "[note] Scores are unsupervised structural anomaly scores, not supervised "
        "attack labels."
    )


if __name__ == "__main__":
    main()
