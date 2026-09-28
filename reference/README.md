# Recorded evidence from the revised paper

These are historical measurements and aggregate statistics, not new results
generated when the package is unpacked. Raw datasets, endpoint lists, reviewer
emails and manuscript drafts are not included.

| File | Content |
| --- | --- |
| `environment.json` | Recorded direct library versions, machine, thread policy and original source manifest |
| `benchmark_runs.json` / `.csv` | All 15 measurements: three per configuration |
| `input_audit.json` | Raw/prepared identities, per-file CICIDS row accounting and input SHA-256 values |
| `window_stats/*.csv` | One complete reference window-statistics table for each of the five configurations |
| `isolation_forest_recheck.json` | Recorded model parameters and expected 673 windows / 34 flags |
| `isolation_forest_recheck.csv` | Reference LANL structural scores and ranks |

All 15 runs matched the original saved per-window statistics at tolerance
`1e-12`. Only one copy per configuration is bundled because the statistics match;
all resource measurements remain available in `benchmark_runs.*`.

Global mapped-row counts equal the sum of per-window `events`. Unique-key totals
are 6,173,663 / 1,837,978 / 822,032 for LANL 1 h / 6 h / 24 h, and 727,682 / 584,040
for flow 5 min / 1 h. The flow Host–Host projection totals are 386,423 / 256,657;
Host–Service totals are 465,884 / 410,586.

`peak_memory_mb` and `final_memory_mb` are historical field names whose values
are actually MiB. Reference runtime/RSS values describe the recorded workstation,
not a performance requirement for another machine. Dates in the record identify
measurement times, not software publication dates.

The manifest embedded in `environment.json` uses original relative filenames.
`provenance/source_manifest.json` maps them to the two relocated historical files
in this package, while preserving every original file's bytes.
