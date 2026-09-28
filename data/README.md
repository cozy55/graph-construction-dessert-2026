# Source data and preparation

Only this README is tracked in `data/`. Real archives and prepared files are
excluded by `.gitignore`. Files under `tests/fixtures/` are synthetic examples.

## LANL authentication associations

Provider: [User–Computer Authentication Associations in Time](https://csr.lanl.gov/data/auth/),
A. D. Kent, 2014, DOI [10.11578/1160076](https://doi.org/10.11578/1160076).
Obtain **`lanl-auth-dataset-1-00.bz2`**. This is the three-field association corpus,
not the separate LANL Unified Host and Network dataset.

Each compressed record is `time,user,computer`. The new streaming preparation
command preserves order and duplicates and creates the nine-column CSV shape used
in the measured runs. Only `timestamp,user,dst_host` are read by construction.
Six other fields are ignored metadata/placeholders. In particular, the placeholder
`normal` value is not a ground-truth attack annotation.

```sh
python scripts/prepare_lanl_auth.py \
  --input-bz2 data/raw/lanl-auth-dataset-1-00.bz2 \
  --output data/lanl/processed/lanl_auth_chunk_00.csv
```

Raw rows with the wrong field count, a non-integer timestamp, or a blank endpoint
stop preparation with a line number; they are not silently discarded. The supplied
corpus has no such records. An existing output file is not overwritten.
An adjacent `.audit.json` records the row count and ordered-triple checksum.

Expected rows: **67,054,840**. Timestamp range: **1–2,419,200 relative seconds**.
There is no calendar epoch or timezone interpretation for this dataset.
Expected ordered-triple digest (UTF-8 `time,user,computer` plus LF per record):
`3cc509a538ae4cbc8cf4e1409044c4336df429db8398faae3ae1d44f3a1f0f7b`.

## CICIDS2017 labelled flows

Provider: [University of New Brunswick CICIDS2017](https://www.unb.ca/cic/datasets/ids-2017.html).
Obtain **`GeneratedLabelledFlows.zip`**. The measured archive has eight CSV members
under its `TrafficLabelling ` directory (including the trailing space):

- `Friday-WorkingHours-Afternoon-DDos.pcap_ISCX.csv`
- `Friday-WorkingHours-Afternoon-PortScan.pcap_ISCX.csv`
- `Friday-WorkingHours-Morning.pcap_ISCX.csv`
- `Monday-WorkingHours.pcap_ISCX.csv`
- `Thursday-WorkingHours-Afternoon-Infilteration.pcap_ISCX.csv`
- `Thursday-WorkingHours-Morning-WebAttacks.pcap_ISCX.csv`
- `Tuesday-WorkingHours.pcap_ISCX.csv`
- `Wednesday-workingHours.pcap_ISCX.csv`

```sh
python scripts/prepare_cicids_labelled_flows.py \
  --input-zip data/raw/GeneratedLabelledFlows.zip \
  --output data/cicids/processed/cicids2017_flows.csv \
  --chunksize 200000
```

This preserved script visits archive members in sorted order and reads Latin-1 CSV
with `skipinitialspace=True`, `engine="python"` and `on_bad_lines="skip"`.
It selects timestamp, source/destination IP and port, protocol and label; rows
with missing or whitespace-only selected fields are removed. There is no
deduplication. This original command replaces its output path, so choose the
intended output file explicitly.

The archive audit found **3,119,345 CSV records**, including **288,602 empty
records** in the WebAttacks file. Removing those empty records retains all
**2,830,743 nonempty flows**. No malformed-width record was found in this archive.
The prepared file was reproduced byte for byte in the recorded environment.
Per-file accounting and file hashes are in `reference/input_audit.json`.

## Check file identity

```sh
python scripts/verify_inputs.py \
  --lanl-raw data/raw/lanl-auth-dataset-1-00.bz2 \
  --cicids-raw data/raw/GeneratedLabelledFlows.zip
python scripts/verify_inputs.py \
  --lanl-prepared data/lanl/processed/lanl_auth_chunk_00.csv \
  --cicids-prepared data/cicids/processed/cicids2017_flows.csv
```

Any subset of the four paths can be supplied. Hashing reads complete files but
uses bounded memory. A hash mismatch means the bytes differ from the measured
inputs; do not silently substitute another release and call it the same experiment.
