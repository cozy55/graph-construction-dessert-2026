# Construction and measurement specification

## Mapping and aggregation

LANL uses `(window, user, destination host)` keys. Users and hosts are distinct
entity roles even if their raw strings coincide. Each accepted row increments one
directed `authenticates_to` count. Repeated rows increase frequency.

Flows use `(window, source host, destination host, service)` keys. Service is the
literal `protocol/destination-port` string; a trailing `.0` is removed from port
text. This is a category shared across destination hosts. The Host–Host projection
uses `(source, destination)`, and the Host–Service projection uses `(source, service)`.
Projected frequencies can be obtained by summing joint counts. The CSV statistics
report the distinct keys for each projection and for the joint table separately.
Source port and label are not part of the joint key. Flow hosts share one type;
services have a separate type. No host-specific service identity is inferred.

## Parsing, validation and time

Both construction inputs are uncompressed, comma-delimited CSVs with headers.
The pandas C reader uses default NA recognition and raises on malformed CSV rows.
The paper's chunk sizes are 2,000,000 LANL rows and 1,000,000 flow rows.
Only required or selected optional columns are read. Endpoints are stripped.
Missing/blank required endpoints and timestamps that fail conversion are rejected.

LANL timestamps are numeric relative seconds. Flow clock strings use
`to_datetime(format="mixed", dayfirst=True, utc=True, errors="coerce")` for the
paper runs. Zone-free clocks are assigned UTC for numeric indexing; this is a
normalization convention, not a claim about the capture timezone. The code does
not reconstruct missing AM/PM information. Other numeric inputs support explicit
`s`, `ms`, `us` and `ns` units; the optional auto-detection path is not needed for
the paper's datetime strings.

The constructors convert valid timestamps to integer seconds and use integer
division by window width with origin zero. The evaluated timestamps are
nonnegative whole seconds. Only observed windows are emitted; empty time gaps are
not filled. A window containing only rejected endpoints may still appear because
its valid timestamps contribute to the window denominator.

The global mapping rate is accepted rows divided by all prepared input rows.
Per-window rates use rows with timestamps assignable to that window, so invalid
timestamps are excluded from per-window denominators but remain in the global
denominator. Every prepared row passed validation in both measured datasets.

Churn compares the current and previous emitted key sets:

```text
churn = (|current \ previous| + |previous \ current|) / |current union previous|
```

It is zero for the first snapshot and for an empty union. For flows, it compares
joint flow tuples across successive observed windows, including across gaps.
Aggregation preserves multiplicity and window membership, not within-window event
order or individual timestamps. All retained keys remain in memory at final
consolidation, including when LANL partial aggregates are spilled to disk.

## Isolation Forest

The paper's LANL baseline fits StandardScaler and Isolation Forest to the same
673 one-hour windows that it scores. It has no held-out detector test set.

- `n_estimators=200`, `contamination=0.05`, `random_state=42`, `n_jobs=-1`.
- Recorded defaults: `max_samples="auto"` (256), `max_features=1.0`,
  `bootstrap=False`, `warm_start=False`, `verbose=0`.
- Missing and nonfinite feature values become zero.
- The score is negative `score_samples`; larger scores are more unusual.
- All 673 windows remain in fitting/scoring. Trailing partial window 672 contains
  only 25 events and is excluded only from the paper's five-window churn case study.
- The 34 flags (5.05%) follow from the chosen contamination threshold. They do not
  estimate an attack rate or establish a malicious label.

The 17 features, in order, are:

```text
events, unique_users, unique_hosts, nodes, unique_edges, repeated_events,
mean_events_per_edge, max_events_per_edge, graph_density, new_edges,
disappeared_edges, persistent_edges, edge_churn, new_users, new_hosts,
user_churn, host_churn
```

CICIDS labels are used for descriptive per-window counts only. They are not inputs
to structural scoring. The optional flow anomaly helper is included, but its
scores are not the LANL baseline reported in the paper.

## Resource measurements

Three sequential runs per configuration were recorded on macOS 26.7 arm64,
Apple M4 Pro (12 cores: 8 performance and 4 efficiency), 24 GB RAM and an internal
Apple SSD AP0512Z NVMe drive. Python was 3.11.6. The five direct library versions
are preserved in `reference/environment.json` and pinned in `requirements.txt`.
Transitive package pins were recorded when preparing this repository and are not
presented as an independently archived transitive lock from the original run.

Each constructor is one process. `OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS`,
`MKL_NUM_THREADS`, `VECLIB_MAXIMUM_THREADS` and `NUMEXPR_NUM_THREADS` are set to 1
by the reproduction runner before starting each child process. Isolation Forest
retains its original `n_jobs=-1` and is outside construction timing.

The internal timer starts after initial column checks and includes prepared-CSV
reading, grouping, merging and window statistics. It excludes imports, raw
preparation, top-entity outputs, final CSV writing, graph exports and anomaly
scoring. RSS is sampled at initialization, after each chunk and after consolidation.
The maximum observed sample is reported in **MiB (2^20 bytes)**, although historical
CSV field names still say `peak_memory_mb`. Transient peaks can be missed.

The OS file cache was not flushed and workstation background activity was not
controlled. These are local feasibility measurements. The table command reports
medians and observed minimum/maximum values; it does not infer confidence intervals
or hardware-independent performance. Graph-window statistics matched all 15 runs;
runtime and RSS are not equality targets in reproduction.
