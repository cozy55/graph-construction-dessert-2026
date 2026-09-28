# Source provenance

The paper's source snapshot identifier is
`5b4db5524a275a0077c4ace9f3e58ac807fa751c79071169d25cf2128f2bb247`.
`source_manifest.json` lists all 16 original files, their SHA-256 hashes, and
their locations in this package. All files remain byte-identical.

Two historical files are relocated:

- Original `requirements.txt` → `provenance/original_requirements.txt`.
  The new root requirements file pins the tested environment.
- Original `scripts/merge_lanl_results.py` → `provenance/original_tools/merge_lanl_results.py`.
  This historical pre-review helper is retained as evidence, not as an executable
  release entry point. Use `scripts/make_paper_tables.py` for the revised numerical
  tables and the paper itself for the qualitative representation comparison.

The digest is SHA-256 over UTF-8 lines of
`original-relative-path + NUL + per-file-SHA256 + newline`, sorted by original
relative path. `scripts/verify_package.py` checks that digest and all file hashes.
`MANIFEST.sha256.json` separately covers the complete new repository package.

`package_validation.json` records the actual local package checks. It is separate
from the historical 15-run benchmark evidence in `reference/`.
