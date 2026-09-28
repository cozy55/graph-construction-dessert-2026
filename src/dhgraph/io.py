from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Iterator, Sequence

import pandas as pd
import psutil


LANL_AUTH_REQUIRED_COLUMNS: tuple[str, ...] = ("timestamp", "user", "dst_host")


class MemoryTracker:
    """Small helper for reporting resident memory while chunk processing."""

    def __init__(self) -> None:
        self._process = psutil.Process(os.getpid())
        self.peak_mb = 0.0

    def sample_mb(self) -> float:
        current_mb = self._process.memory_info().rss / (1024 * 1024)
        self.peak_mb = max(self.peak_mb, current_mb)
        return current_mb


def read_csv_columns(path: str | Path) -> list[str]:
    input_path = Path(path)
    if not input_path.exists():
        raise FileNotFoundError(f"Input CSV does not exist: {input_path}")
    return list(pd.read_csv(input_path, nrows=0).columns)


def validate_required_columns(path: str | Path, required: Sequence[str]) -> None:
    columns = set(read_csv_columns(path))
    missing = [column for column in required if column not in columns]
    if missing:
        required_text = ", ".join(required)
        missing_text = ", ".join(missing)
        raise ValueError(
            f"Input CSV is missing required column(s): {missing_text}. "
            f"Required columns are: {required_text}."
        )


def iter_lanl_auth_chunks(
    path: str | Path,
    chunksize: int,
    usecols: Iterable[str] = LANL_AUTH_REQUIRED_COLUMNS,
) -> Iterator[pd.DataFrame]:
    """Yield only the columns needed for user-host authentication graphs."""

    if chunksize <= 0:
        raise ValueError("--chunksize must be a positive integer.")

    input_path = Path(path)
    validate_required_columns(input_path, tuple(usecols))
    yield from pd.read_csv(
        input_path,
        usecols=list(usecols),
        chunksize=chunksize,
        dtype={"user": "string", "dst_host": "string"},
    )


def ensure_parent_dir(path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return output_path
