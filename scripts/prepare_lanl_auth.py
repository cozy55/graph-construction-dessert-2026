#!/usr/bin/env python3
"""Stream the LANL association archive into the paper's nine-column CSV shape."""
from __future__ import annotations

import argparse
import bz2
import csv
import hashlib
import json
from pathlib import Path
import tempfile

COLUMNS = ["timestamp", "user", "src_host", "dst_host", "auth_result",
           "auth_type", "logon_type", "auth_orientation", "label"]


def prepare(source: Path, output: Path) -> dict:
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    triples = hashlib.sha256()
    rows = 0
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="",
                                     dir=output.parent, delete=False) as dst:
        temporary = Path(dst.name)
        try:
            writer = csv.writer(dst, lineterminator="\n")
            writer.writerow(COLUMNS)
            with bz2.open(source, "rt", encoding="utf-8", newline="") as src:
                for line, record in enumerate(csv.reader(src), 1):
                    if (len(record) != 3 or not record[0].isdigit()
                            or not record[1].strip() or not record[2].strip()):
                        raise ValueError(f"Invalid raw authentication record at line {line}")
                    t, user, host = record
                    writer.writerow([t, user, "unknown", host, "Success", "user_computer_auth",
                                     "unknown", "user_to_computer", "normal"])
                    triples.update((",".join(record) + "\n").encode())
                    rows += 1
            if rows == 0:
                raise ValueError("The raw archive contains no records")
        except BaseException:
            dst.close()
            temporary.unlink(missing_ok=True)
            raise
    temporary.replace(output)
    return {"raw_file": source.name, "prepared_rows": rows, "dropped_rows": 0,
            "ordered_triples_sha256": triples.hexdigest(),
            "note": "Metadata placeholders are ignored by the constructor; normal is not an attack annotation."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-bz2", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("data/lanl/processed/lanl_auth_chunk_00.csv"))
    args = parser.parse_args()
    result = prepare(args.input_bz2, args.output)
    args.output.with_suffix(".audit.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
