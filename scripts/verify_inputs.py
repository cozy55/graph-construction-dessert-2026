#!/usr/bin/env python3
"""Check supplied dataset files against the paper's recorded SHA-256 values."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for kind in ["lanl-raw", "lanl-prepared", "cicids-raw", "cicids-prepared"]:
        parser.add_argument("--" + kind, type=Path)
    args = parser.parse_args()
    audit = json.loads((ROOT / "reference/input_audit.json").read_text())
    checked = 0
    for arg, dataset, field in [
        ("lanl_raw", "lanl", "raw_file_sha256"),
        ("lanl_prepared", "lanl", "prepared_file_sha256"),
        ("cicids_raw", "cicids2017", "raw_file_sha256"),
        ("cicids_prepared", "cicids2017", "prepared_file_sha256"),
    ]:
        path = getattr(args, arg)
        if path is None:
            continue
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest() != audit[dataset][field]:
            raise ValueError(f"Checksum differs for {path.name}: {digest.hexdigest()}")
        checked += 1
        print(f"Matched {path.name}: {digest.hexdigest()}")
    if not checked:
        parser.error("Supply at least one dataset file to check")


if __name__ == "__main__":
    main()
