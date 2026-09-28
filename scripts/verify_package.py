#!/usr/bin/env python3
"""Verify the preserved paper source and the repository's content manifest."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "MANIFEST.sha256.json"
IGNORED = {".git", ".pytest_cache", "__pycache__", "build", "dist", "results", ".venv"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def release_files() -> list[Path]:
    return sorted(
        p for p in ROOT.rglob("*")
        if p.is_file() and p != MANIFEST
        and not any(x in IGNORED or x.startswith(".venv") or x.endswith(".egg-info")
                    for x in p.relative_to(ROOT).parts)
        and p.suffix not in {".pyc", ".pyo"}
        and p.name != ".DS_Store"
        and (p.relative_to(ROOT).parts[0] != "data" or p.name == "README.md")
    )


def verify_source() -> str:
    record = json.loads((ROOT / "provenance/source_manifest.json").read_text())
    for entry in record["files"]:
        path = ROOT / entry["package_path"]
        if sha256(path) != entry["sha256"]:
            raise ValueError(f"Paper source differs: {entry['package_path']}")
    lines = "".join(e["path"] + "\0" + e["sha256"] + "\n"
                    for e in sorted(record["files"], key=lambda e: e["path"]))
    digest = hashlib.sha256(lines.encode()).hexdigest()
    if digest != record["source_snapshot_sha256"]:
        raise ValueError("Original source manifest digest differs")
    return digest


def verify_reference() -> None:
    runs = json.loads((ROOT / "reference/benchmark_runs.json").read_text())
    expected = {("lanl", 3600), ("lanl", 21600), ("lanl", 86400),
                ("cicids2017", 300), ("cicids2017", 3600)}
    counts = Counter((r["dataset"], r["window_seconds"]) for r in runs)
    if set(counts) != expected or any(v != 3 for v in counts.values()):
        raise ValueError("Expected three recorded repetitions of each paper configuration")
    for dataset, seconds in expected:
        selected = [r for r in runs if (r["dataset"], r["window_seconds"]) == (dataset, seconds)]
        if {r["repeat"] for r in selected} != {1, 2, 3}:
            raise ValueError("Duplicate or missing repetition")
        if not all(r["original_window_statistics_match"] for r in selected):
            raise ValueError("An original run failed its recorded comparison")
        with (ROOT / "reference/window_stats" / f"{dataset}_{seconds}s.csv").open(newline="") as f:
            stats = list(csv.DictReader(f))
        events = sum(int(r["events"]) for r in stats)
        keys = "unique_edges" if dataset == "lanl" else "unique_flow_edges"
        if len(stats) != selected[0]["snapshots"] or events != selected[0]["mapped_rows"]:
            raise ValueError(f"Reference accounting differs for {dataset} {seconds}s")
        if sum(int(r[keys]) for r in stats) > events:
            raise ValueError("Unique retained keys exceed mapped events")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh-manifest", action="store_true",
                        help="Rewrite package checksums after intentional metadata/doc edits; still verify the paper source first.")
    args = parser.parse_args()
    digest = verify_source()
    verify_reference()
    files = release_files()
    if args.refresh_manifest:
        MANIFEST.write_text(json.dumps({
            "algorithm": "sha256",
            "files": {p.relative_to(ROOT).as_posix(): sha256(p) for p in files},
        }, indent=2) + "\n")
    if not MANIFEST.exists():
        raise ValueError("Missing package manifest; run with --refresh-manifest during release preparation")
    expected = json.loads(MANIFEST.read_text())["files"]
    actual = {p.relative_to(ROOT).as_posix(): sha256(p) for p in files}
    if actual != expected:
        changed = sorted(k for k in actual.keys() | expected.keys() if actual.get(k) != expected.get(k))
        raise ValueError("Package content changed: " + ", ".join(changed))
    print(f"Verified {len(files)} package files, all 16 original source files, and 15 paper runs.")
    print(f"Paper source snapshot: {digest}")


if __name__ == "__main__":
    main()
