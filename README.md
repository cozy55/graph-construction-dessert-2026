# DESSERT 2026 — Dynamic Heterogeneous Graph Construction

Research code accompanying **“Dynamic Heterogeneous Graph Construction from
Authentication and Network Events for Anomaly Analysis”**, by Oleksandr
Martsenkov and Oleg Savenko, DESSERT 2026.

This package constructs typed temporal counts from LANL user–computer
authentication associations and CICIDS2017 network flows. It computes window
statistics, repeated-edge frequencies and churn, and provides an Isolation Forest
baseline for structural inspection. An outlier score is not a confirmed attack.

Package version: **1.0.0**. The numerical implementation is the exact source used
for the revised paper's measurements. Installation metadata, portable preparation
and reproduction commands, tests, and citation metadata have been added around it.
The preserved paper-source snapshot is
`5b4db5524a275a0077c4ace9f3e58ac807fa751c79071169d25cf2128f2bb247`.

## Quick start

The recorded environment uses **Python 3.11.6** on macOS arm64. Use Python 3.11
and the supplied pins for reproduction. The commands below assume a macOS/Linux
shell and are run from the repository root.

```sh
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pip install --no-deps -e .
python scripts/verify_package.py
python -m pytest -q
python scripts/run_demo.py
```

The demo uses synthetic fixtures only. It verifies 10 events in two windows for
each source: seven retained authentication keys and nine joint flow tuples.
Outputs are written to `results/demo/`. Choose a fresh `--output-dir` to rerun it.
The demo's two-window anomaly output only checks that the pipeline executes.

## Reproduce the paper

1. Obtain the source datasets using [data/README.md](data/README.md).
2. Prepare the canonical CSV files using the documented commands.
3. Run all five configurations, with three repetitions each:

```sh
python scripts/reproduce_paper.py
```

The default inputs are `data/lanl/processed/lanl_auth_chunk_00.csv` and
`data/cicids/processed/cicids2017_flows.csv`. Other locations can be supplied with
`--lanl-input` and `--cicids-input`. Runs are sequential and compare every output
window-statistics column to the bundled reference with tolerance `1e-12`.
Output goes to `results/paper/`; existing run directories are not overwritten.

The full LANL input has **67,054,840 rows** and its prepared CSV is about 5.3 GB;
CICIDS2017 has **2,830,743 prepared flows**. Allow space for archives, prepared
files and outputs. Construction retains aggregated keys in memory, so memory use
still grows with input diversity. The measured workstation had 24 GB RAM.

To regenerate numerical paper tables without downloading data:

```sh
python scripts/make_paper_tables.py
```

This writes CSV versions of Tables I, III, IV and V to `results/paper_tables/`.
It summarizes the recorded measurements; it does not rerun the datasets.
Table II is a qualitative representation comparison, explained in the paper.

## Recorded results

| Dataset | Window | Snapshots | Mapped rows | Unique window keys | Median seconds | Median sampled RSS, MiB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| LANL | 1 h | 673 | 67,054,840 | 6,173,663 | 67.08 | 1,048.2 |
| LANL | 6 h | 113 | 67,054,840 | 1,837,978 | 57.83 | 725.3 |
| LANL | 24 h | 29 | 67,054,840 | 822,032 | 58.79 | 612.8 |
| CICIDS2017 | 5 min | 496 | 2,830,743 | 727,682 | 10.35 | 816.1 |
| CICIDS2017 | 1 h | 50 | 2,830,743 | 584,040 | 10.17 | 681.3 |

Each resource value is the median of three sequential local runs. Runtime and
memory are machine-dependent. RSS is sampled, not monitored continuously.
For flows, unique keys are joint `(source host, destination host, service)` tuples;
they are not the sum of Host–Host and Host–Service projection edges.

## Repository contents

| Location | Purpose |
| --- | --- |
| `src/dhgraph/` | Original aggregation, statistics, anomaly and small-graph export library |
| `scripts/` | Dataset preparation, construction, demo, reproduction and table commands |
| `tests/` | Unit and integration tests, with synthetic CSV fixtures |
| `reference/` | Recorded environment, 15 measurements, input audit and aggregate window outputs |
| `provenance/` | Original-source hashes and two relocated historical files |
| `docs/METHODS.md` | Mapping, validation, timestamps, model settings and measurement scope |
| `docs/REPRODUCING.md` | Individual commands and expected outputs |
| `docs/PUBLISHING.md` | Upload, versioning and release instructions |
| `docs/PAPER_AVAILABILITY.md` | Code-availability paragraph to complete after publication |
| `CITATION.cff` | Machine-readable software citation metadata |

The GitHub Actions workflow runs package checks, tests and the synthetic demo on
Linux and macOS. Remote workflow runs begin after the repository is uploaded;
local validation is recorded in `provenance/package_validation.json`.

## Citation and license status

Use `CITATION.cff` when citing this software, and cite the accompanying paper once
its final bibliographic details are available. The repository URL, archival DOI,
release date and license have deliberately not been invented. A license has not
yet been selected, and this package makes no open-source-license claim.
See [the publication guide](docs/PUBLISHING.md) for the fields to complete.

Source datasets are not bundled. Obtain them from their official providers;
their terms are separate from any future code license.
