#!/usr/bin/env python3
"""Repeat the five revised-paper configurations and compare graph statistics."""
from __future__ import annotations

import argparse
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

import pandas as pd

from make_paper_tables import make_tables
from verify_package import verify_source

ROOT = Path(__file__).resolve().parents[1]
CONFIGURATIONS = [("lanl", 3600), ("lanl", 21600), ("lanl", 86400),
                  ("cicids2017", 300), ("cicids2017", 3600)]
THREADS = {k: "1" for k in ["OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                           "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"]}


def positive(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lanl-input", type=Path, default=ROOT / "data/lanl/processed/lanl_auth_chunk_00.csv")
    parser.add_argument("--cicids-input", type=Path, default=ROOT / "data/cicids/processed/cicids2017_flows.csv")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results/paper")
    parser.add_argument("--datasets", nargs="+", choices=["lanl", "cicids2017"], default=["lanl", "cicids2017"])
    parser.add_argument("--repeats", type=positive, default=3)
    parser.add_argument("--lanl-chunksize", type=positive, default=2_000_000)
    parser.add_argument("--flow-chunksize", type=positive, default=1_000_000)
    parser.add_argument("--skip-reference-check", action="store_true",
                        help="Use only for a different/synthetic input; outputs will not be labelled a paper replication.")
    args = parser.parse_args()
    inputs = {"lanl": args.lanl_input.resolve(), "cicids2017": args.cicids_input.resolve()}
    for dataset in args.datasets:
        if not inputs[dataset].is_file():
            parser.error(f"Missing {dataset} prepared input: {inputs[dataset]}")
    output = args.output_dir.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("Choose an empty output directory; existing runs are never overwritten")
    digest = verify_source()
    output.mkdir(parents=True, exist_ok=True)
    windows = output / "window_stats"
    windows.mkdir()
    env = os.environ.copy()
    env.update(THREADS)
    (output / "environment.json").write_text(json.dumps({
        "python": platform.python_version(), "platform": platform.platform(),
        "cpu_reported_by_platform": platform.processor(), "logical_cpu_count": os.cpu_count(),
        "packages": {x: metadata.version(x) for x in ["pandas", "numpy", "scikit-learn", "psutil", "networkx"]},
        "thread_limits": THREADS, "source_snapshot_sha256": digest,
        "repeats": args.repeats, "reference_check_enabled": not args.skip_reference_check,
        "hardware_note": "Record physical CPU model, RAM and storage separately before comparing resource results.",
    }, indent=2) + "\n")
    records = []
    for dataset, seconds in CONFIGURATIONS:
        if dataset not in args.datasets:
            continue
        prefix = "lanl_auth" if dataset == "lanl" else "cicids2017_flow"
        script = "lanl_auth_window_stats.py" if dataset == "lanl" else "flow_window_stats.py"
        for repeat in range(1, args.repeats + 1):
            dest = output / "runs" / f"{dataset}_{seconds}s_r{repeat}"
            dest.mkdir(parents=True)
            options = ["--input", str(inputs[dataset]), "--output-dir", str(dest),
                       "--window-seconds", str(seconds), "--chunksize",
                       str(args.lanl_chunksize if dataset == "lanl" else args.flow_chunksize)]
            options += (["--aggregation-mode", "in-memory"] if dataset == "lanl"
                        else ["--dataset-name", "cicids2017", "--timestamp-dayfirst"])
            command = [sys.executable, str(ROOT / "scripts" / script), *options]
            (dest / "command.json").write_text(json.dumps(command, indent=2) + "\n")
            print(f"Running {dataset} {seconds}s, repetition {repeat}/{args.repeats}", flush=True)
            with (dest / "run.log").open("w") as log:
                subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
            current_path = dest / f"{prefix}_window_stats_{seconds}s.csv"
            current = pd.read_csv(current_path)
            if not args.skip_reference_check:
                expected = pd.read_csv(ROOT / "reference/window_stats" / f"{dataset}_{seconds}s.csv")
                pd.testing.assert_frame_equal(current, expected, check_dtype=False, rtol=1e-12, atol=1e-12)
            if repeat == 1:
                shutil.copy2(current_path, windows / f"{dataset}_{seconds}s.csv")
            else:
                pd.testing.assert_frame_equal(current, pd.read_csv(windows / f"{dataset}_{seconds}s.csv"),
                                              check_dtype=False, rtol=1e-12, atol=1e-12)
            row = pd.read_csv(dest / f"{prefix}_summary_{seconds}s.csv").iloc[0].to_dict()
            if int(current.events.sum()) != int(row["mapped_rows"]):
                raise AssertionError("Event-count conservation failed")
            row.update(dataset=dataset, repeat=repeat,
                       reference_statistics_match=None if args.skip_reference_check else True)
            records.append(row)
            (output / "benchmark_runs.json").write_text(json.dumps(records, indent=2) + "\n")
            pd.DataFrame(records).to_csv(output / "benchmark_runs.csv", index=False)
            print(f"  {row['construction_time_sec']:.2f} s; sampled RSS {row['peak_memory_mb']:.1f} MiB", flush=True)
    if "lanl" in args.datasets:
        subprocess.run([sys.executable, str(ROOT / "scripts/lanl_auth_window_anomaly_baseline.py"),
                        "--window-stats", str(windows / "lanl_3600s.csv"),
                        "--output", str(output / "lanl_anomaly_scores.csv"),
                        "--n-estimators", "200", "--contamination", "0.05", "--random-state", "42"],
                       cwd=ROOT, env=env, check=True)
    make_tables(output / "benchmark_runs.json", windows, output / "tables")
    if args.skip_reference_check:
        print("Completed custom-input runs. Paper reference comparisons were disabled.")
    else:
        print(f"All {len(records)} runs matched the paper's saved window statistics.")


if __name__ == "__main__":
    main()
