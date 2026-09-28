#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from zipfile import ZipFile

import pandas as pd


REQUIRED_COLUMNS = (
    "Source IP",
    "Source Port",
    "Destination IP",
    "Destination Port",
    "Protocol",
    "Timestamp",
    "Label",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare CICIDS2017 GeneratedLabelledFlows.zip for graph-window "
            "construction by extracting only endpoint, service, timestamp, and "
            "label columns into a compact canonical CSV."
        )
    )
    parser.add_argument("--input-zip", required=True, help="GeneratedLabelledFlows.zip path.")
    parser.add_argument(
        "--output",
        default="data/cicids/processed/cicids2017_flows.csv",
        help="Canonical output CSV.",
    )
    parser.add_argument("--chunksize", type=int, default=200_000)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.chunksize <= 0:
        raise ValueError("--chunksize must be a positive integer.")

    input_zip = Path(args.input_zip)
    output = Path(args.output)
    if not input_zip.exists():
        raise FileNotFoundError(f"Input zip does not exist: {input_zip}")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    wrote_header = False
    total_rows = 0
    file_count = 0

    with ZipFile(input_zip) as zf:
        csv_names = sorted(name for name in zf.namelist() if name.lower().endswith(".csv"))
        if not csv_names:
            raise ValueError(f"No CSV files found inside {input_zip}")

        for name in csv_names:
            file_count += 1
            with zf.open(name) as handle:
                reader = pd.read_csv(
                    handle,
                    chunksize=args.chunksize,
                    skipinitialspace=True,
                    encoding="latin1",
                    engine="python",
                    on_bad_lines="skip",
                    usecols=lambda column: str(column).strip() in REQUIRED_COLUMNS,
                )
                file_rows = 0
                for chunk_index, chunk in enumerate(reader, start=1):
                    chunk.columns = [str(column).strip() for column in chunk.columns]
                    missing = [column for column in REQUIRED_COLUMNS if column not in chunk.columns]
                    if missing:
                        raise ValueError(
                            f"{name} is missing required column(s): {', '.join(missing)}"
                        )

                    out = pd.DataFrame(
                        {
                            "timestamp": chunk["Timestamp"],
                            "src_host": chunk["Source IP"],
                            "src_port": chunk["Source Port"],
                            "dst_host": chunk["Destination IP"],
                            "dst_port": chunk["Destination Port"],
                            "protocol": chunk["Protocol"],
                            "label": chunk["Label"],
                            "source_file": Path(name).name,
                        }
                    )
                    before_drop = int(len(out))
                    out = out.dropna(
                        subset=[
                            "timestamp",
                            "src_host",
                            "src_port",
                            "dst_host",
                            "dst_port",
                            "protocol",
                            "label",
                        ]
                    )
                    out = out[
                        out[
                            [
                                "timestamp",
                                "src_host",
                                "src_port",
                                "dst_host",
                                "dst_port",
                                "protocol",
                                "label",
                            ]
                        ]
                        .astype(str)
                        .apply(lambda col: col.str.strip().ne(""))
                        .all(axis=1)
                    ]
                    out.to_csv(output, mode="a", header=not wrote_header, index=False)
                    wrote_header = True
                    rows = int(len(out))
                    dropped = before_drop - rows
                    file_rows += rows
                    total_rows += rows
                    print(
                        f"[{Path(name).name} chunk {chunk_index}] rows={rows:,} "
                        f"dropped={dropped:,} file_rows={file_rows:,} "
                        f"total_rows={total_rows:,}",
                        flush=True,
                    )

            print(f"[file done] {Path(name).name}: {file_rows:,} rows", flush=True)

    print(
        f"[done] files={file_count} rows={total_rows:,} output={output}",
        flush=True,
    )


if __name__ == "__main__":
    main()
