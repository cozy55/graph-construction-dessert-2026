from __future__ import annotations

import bz2
from collections import Counter
import csv
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile

import pandas as pd
import pytest

from dhgraph.graph_stats import WindowEdgeAggregator, aggregate_auth_chunk, compute_window_statistics
from dhgraph.flow_stats import FlowWindowEdgeAggregator, aggregate_flow_chunk, compute_flow_window_statistics

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("mode", ["in-memory", "disk", "auto"])
@pytest.mark.parametrize("chunksize", [1, 3, 100])
def test_chunk_boundaries_spilling_and_rejection_accounting(tmp_path, mode, chunksize):
    frame = pd.DataFrame({
        "timestamp": ["0", "1", "bad", "10", "11", "30", "31", "32"],
        "user": ["u", "u", "u", "u", " ", "u", "x", "u"],
        "dst_host": ["h", "h", "h", "h", "h", "h", "h", None],
    })
    aggregator = WindowEdgeAggregator(tmp_path, mode=mode, max_memory_mb=0)
    rows, mapped = Counter(), Counter()
    total = accepted = invalid = 0
    for start in range(0, len(frame), chunksize):
        part = aggregate_auth_chunk(frame.iloc[start:start + chunksize], 10)
        aggregator.update(part.edge_counts, current_memory_mb=1)
        rows.update(part.rows_by_window)
        mapped.update(part.mapped_rows_by_window)
        total += part.total_rows
        accepted += part.mapped_rows
        invalid += part.invalid_timestamp_rows
    stats = compute_window_statistics(aggregator.finalize(), 10, rows, mapped)
    assert (total, accepted, invalid) == (8, 5, 1)
    assert stats.window_id.tolist() == [0, 1, 3]
    assert stats.events.tolist() == [2, 1, 2]
    assert stats.unique_edges.tolist() == [1, 1, 2]
    assert stats.edge_churn.tolist() == [0.0, 0.0, 0.5]
    assert stats.event_mapping_rate.tolist() == pytest.approx([1.0, 0.5, 2 / 3])
    assert not (tmp_path / "_partial_edge_counts").exists()


def test_flow_joint_keys_and_shared_service_projection():
    frame = pd.DataFrame({
        "timestamp": ["0", "1", "2", "bad", "3"],
        "src_host": ["A", "A", "A", "A", " "],
        "dst_host": ["B", "C", "B", "B", "B"],
        "protocol": [6] * 5, "dst_port": ["80.0"] * 5,
        "label": ["BENIGN", "Bot", "BENIGN", "Bot", "Bot"],
    })
    part = aggregate_flow_chunk(frame, 10, timestamp_unit="s")
    aggregator = FlowWindowEdgeAggregator()
    aggregator.update(part.edge_counts)
    stats = compute_flow_window_statistics(aggregator.finalize(), 10, part.rows_by_window,
                                          part.mapped_rows_by_window, part.attack_rows_by_window)
    row = stats.iloc[0]
    assert (part.total_rows, part.mapped_rows, part.invalid_timestamp_rows) == (5, 3, 1)
    assert set(part.edge_counts.service) == {"6/80"}
    assert (row.events, row.unique_flow_edges, row.unique_host_edges, row.unique_service_edges) == (3, 2, 2, 1)
    assert row.nodes == 4
    assert row.event_mapping_rate == 3 / 4  # Invalid timestamps cannot be assigned to a window.
    assert row.labeled_attack_events == 1


def load_preparer():
    spec = importlib.util.spec_from_file_location("prepare_lanl", ROOT / "scripts/prepare_lanl_auth.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.prepare


def test_lanl_preparation_preserves_duplicates_and_ignores_metadata(tmp_path):
    raw = tmp_path / "raw.bz2"
    raw.write_bytes(bz2.compress(b"1,u,h\n1,u,h\n10,v,j\n"))
    output = tmp_path / "prepared.csv"
    result = load_preparer()(raw, output)
    with output.open(newline="") as f:
        records = list(csv.DictReader(f))
    assert len(records) == result["prepared_rows"] == 3
    assert records[0] == records[1]
    assert [(r["timestamp"], r["user"], r["dst_host"]) for r in records] == [
        ("1", "u", "h"), ("1", "u", "h"), ("10", "v", "j")]
    with pytest.raises(FileExistsError):
        load_preparer()(raw, output)


@pytest.mark.parametrize("raw_bytes", [b"1,u\n", b"bad,u,h\n", b"1, ,h\n", b""])
def test_lanl_preparation_rejects_invalid_input_atomically(tmp_path, raw_bytes):
    raw = tmp_path / "raw.bz2"
    raw.write_bytes(bz2.compress(raw_bytes))
    output = tmp_path / "prepared.csv"
    with pytest.raises(ValueError):
        load_preparer()(raw, output)
    assert not output.exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["raw.bz2"]


def test_cicids_archive_preparation_removes_empty_rows_only(tmp_path):
    archive = tmp_path / "flows.zip"
    header = "Source IP, Source Port, Destination IP, Destination Port, Protocol, Timestamp, Label\n"
    event = "10.0.0.1,1234,10.0.0.2,80,6,03/07/2017 08:00:00,BENIGN\n"
    with ZipFile(archive, "w") as z:
        z.writestr("TrafficLabelling /example.csv", header + event + ",,,,,,\n" + event)
    output = tmp_path / "prepared.csv"
    subprocess.run([sys.executable, str(ROOT / "scripts/prepare_cicids_labelled_flows.py"),
                    "--input-zip", str(archive), "--output", str(output), "--chunksize", "1"], check=True)
    frame = pd.read_csv(output)
    assert len(frame) == 2
    assert frame.iloc[0].equals(frame.iloc[1])
    assert frame.source_file.tolist() == ["example.csv", "example.csv"]


def test_repository_demo_runs_outside_checkout(tmp_path):
    output = tmp_path / "demo"
    subprocess.run([sys.executable, str(ROOT / "scripts/run_demo.py"),
                    "--output-dir", str(output)], cwd=tmp_path, check=True)
    assert (output / "lanl/anomaly_scores.csv").is_file()


def test_all_five_configurations_on_synthetic_inputs(tmp_path):
    output = tmp_path / "runs"
    subprocess.run([sys.executable, str(ROOT / "scripts/reproduce_paper.py"),
                    "--lanl-input", str(ROOT / "tests/fixtures/tiny_lanl_auth.csv"),
                    "--cicids-input", str(ROOT / "tests/fixtures/tiny_cicids_flow.csv"),
                    "--output-dir", str(output), "--repeats", "1", "--lanl-chunksize", "3",
                    "--flow-chunksize", "3", "--skip-reference-check"], cwd=tmp_path, check=True)
    records = json.loads((output / "benchmark_runs.json").read_text())
    assert len(records) == 5
    assert all(r["mapped_rows"] == 10 and r["reference_statistics_match"] is None for r in records)
    assert (output / "tables/table_v_mapping.csv").is_file()


def test_reference_check_rejects_different_input(tmp_path):
    result = subprocess.run([sys.executable, str(ROOT / "scripts/reproduce_paper.py"),
                             "--datasets", "lanl", "--repeats", "1",
                             "--lanl-input", str(ROOT / "tests/fixtures/tiny_lanl_auth.csv"),
                             "--output-dir", str(tmp_path / "runs")], capture_output=True, text=True)
    assert result.returncode != 0
    assert "DataFrame" in result.stderr
