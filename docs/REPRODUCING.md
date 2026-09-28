# Reproducing the revised paper

Install the pinned requirements from the root README and prepare the two inputs
as described in `data/README.md`. The complete reproduction command is:

```sh
python scripts/reproduce_paper.py --repeats 3 --output-dir results/paper
```

The runner groups three repetitions of each configuration together, in this order:
LANL 3600, 21600, 86400 seconds, then CICIDS2017 300 and 3600 seconds. It keeps
the original constructors unchanged, compares each output to the reference,
checks event-count conservation, saves commands/logs and generates numerical
paper tables. An existing nonempty output directory is rejected.

To run one source only, pass `--datasets lanl` or `--datasets cicids2017`.
Use `--skip-reference-check` only for different/synthetic data; the run record
then explicitly records that paper reference checking was disabled.

## Individual construction commands

For standalone commands, set the construction thread policy first:

```sh
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1 NUMEXPR_NUM_THREADS=1

python scripts/lanl_auth_window_stats.py \
  --input data/lanl/processed/lanl_auth_chunk_00.csv \
  --output-dir results/lanl_1h --window-seconds 3600 \
  --chunksize 2000000 --aggregation-mode in-memory
python scripts/lanl_auth_window_stats.py \
  --input data/lanl/processed/lanl_auth_chunk_00.csv \
  --output-dir results/lanl_6h --window-seconds 21600 \
  --chunksize 2000000 --aggregation-mode in-memory
python scripts/lanl_auth_window_stats.py \
  --input data/lanl/processed/lanl_auth_chunk_00.csv \
  --output-dir results/lanl_24h --window-seconds 86400 \
  --chunksize 2000000 --aggregation-mode in-memory
python scripts/flow_window_stats.py \
  --input data/cicids/processed/cicids2017_flows.csv \
  --output-dir results/cicids_5m --window-seconds 300 \
  --chunksize 1000000 --dataset-name cicids2017 --timestamp-dayfirst
python scripts/flow_window_stats.py \
  --input data/cicids/processed/cicids2017_flows.csv \
  --output-dir results/cicids_1h --window-seconds 3600 \
  --chunksize 1000000 --dataset-name cicids2017 --timestamp-dayfirst
```

Repeat with distinct output directories for resource measurements. The wrapper
already handles all repetitions and the reference comparisons.

## Structural ranking and case study

```sh
python scripts/lanl_auth_window_anomaly_baseline.py \
  --window-stats results/lanl_1h/lanl_auth_window_stats_3600s.csv \
  --output results/lanl_1h/anomaly_scores.csv \
  --n-estimators 200 --contamination 0.05 --random-state 42
```

The expected reference has 673 windows, 34 flags, and window 672 as the top
structural outlier. The five case-study windows in Table III are 391, 7, 199, 511
and 343 after explicitly excluding the trailing partial window 672. Use
`make_paper_tables.py` for this revised-paper selection. The preserved general
`lanl_auth_case_study.py` ranks all input rows and does not automatically exclude
the partial window.

## Outputs and verification

- `*_window_stats_*s.csv`: graph-window counts, frequency, density and churn.
- `*_summary_*s.csv`: global row acceptance, snapshot means, time and sampled RSS.
- `*_top_*_*s.csv`: selected per-window entities, generated locally but not bundled.
- `results/paper/benchmark_runs.json` and `.csv`: all new measurements.
- `results/paper/window_stats/`: first-repetition outputs used for table generation.
- `results/paper/lanl_anomaly_scores.csv`: LANL ranking with all windows retained.
- `results/paper/tables/`: Tables I, III, IV and V as CSVs.

The constructors expose APIs that retain counts; a full graph is not serialized
by default. The optional `lanl_auth_export_sample_graphs.py` exports selected
small CSV/GraphML samples. Run any script with `--help` for its arguments.

To regenerate tables from a new run instead of the bundled reference:

```sh
python scripts/make_paper_tables.py \
  --records results/paper/benchmark_runs.json \
  --stats-dir results/paper/window_stats \
  --output-dir results/paper/tables
```

Historical `merge_lanl_results.py` is retained under `provenance/original_tools/`
for snapshot verification only. Its pre-review qualitative comparison and
single-run table descriptions are superseded by the revised paper and this table
generator. It is not the release's reproduction entry point.
