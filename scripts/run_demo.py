#!/usr/bin/env python3
"""Run both constructors on synthetic fixtures and check known counts."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results/demo")
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("Choose an empty output directory for the demo")
    env = os.environ.copy()
    for key in ["OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"]:
        env[key] = "1"
    commands = [
        ["lanl_auth_window_stats.py", "--input", str(ROOT / "tests/fixtures/tiny_lanl_auth.csv"),
         "--output-dir", str(output / "lanl"), "--window-seconds", "10", "--chunksize", "3"],
        ["flow_window_stats.py", "--input", str(ROOT / "tests/fixtures/tiny_cicids_flow.csv"),
         "--output-dir", str(output / "flow"), "--window-seconds", "60", "--chunksize", "3"],
        ["lanl_auth_window_anomaly_baseline.py", "--window-stats",
         str(output / "lanl/lanl_auth_window_stats_10s.csv"), "--output", str(output / "lanl/anomaly_scores.csv")],
    ]
    for script, *options in commands:
        subprocess.run([sys.executable, str(ROOT / "scripts" / script), *options], env=env, check=True)
    lanl = pd.read_csv(output / "lanl/lanl_auth_window_stats_10s.csv")
    flow = pd.read_csv(output / "flow/cicids2017_flow_window_stats_60s.csv")
    if lanl.events.tolist() != [5, 5] or lanl.unique_edges.tolist() != [3, 4]:
        raise AssertionError("Synthetic LANL counts differ from the hand-checked example")
    if flow.events.tolist() != [5, 5] or flow.unique_flow_edges.tolist() != [4, 5]:
        raise AssertionError("Synthetic flow counts differ from the hand-checked example")
    print("Demo passed: each input maps 10 events into 2 windows; LANL retains 7 keys and flows 9 joint tuples.")
    print("The two-window anomaly output is a pipeline check, not a meaningful detector evaluation.")


if __name__ == "__main__":
    main()
