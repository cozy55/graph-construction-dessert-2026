# Upload and publish this code package

This directory is the repository root. Upload its contents, including the hidden
`.github/`, `.gitignore` and `.gitattributes` entries. Do not upload the outer ZIP
as the only repository file. Source data, local results and virtual environments
are excluded from version control.

## Publication metadata

The package version is `1.0.0`; it has not been published by this preparation step.
The repository URL and code license remain unset, as requested by the author.
When those choices are available:

1. Add the chosen license text in `LICENSE`, and its SPDX identifier in
   `CITATION.cff`. The package currently declares no license.
2. Add the actual `repository-code` URL in `CITATION.cff`, and the same URL in
   the README. Add the real release date when a release is published.
3. Complete `docs/PAPER_AVAILABILITY.md` with the repository URL, final commit
   and release tag. Add an archival DOI only if an archive is actually created.

After intentional metadata/document changes, refresh the package checksums:

```sh
python scripts/verify_package.py --refresh-manifest
python scripts/verify_package.py
python -m pytest -q
```

This still verifies all preserved paper-source files against their original
snapshot. Metadata changes do not justify silently changing the numerical core.

## Upload with Git

Create an empty repository on your chosen Git host. Set `REPOSITORY_URL` to its
actual clone URL, then run these commands from this directory:

```sh
git init -b main
git add .
git status --short
git diff --cached --stat
git commit -m "Add DESSERT 2026 graph construction reproducibility package"
git remote add origin "$REPOSITORY_URL"
git push -u origin main
```

`git status` should list code, documentation, synthetic fixtures and aggregate
reference records. It should not list real datasets, virtual environments or
generated run directories. This package contains no preconfigured remote, account
credentials or Git history.

After the uploaded checks pass, tag the revision that the paper will cite:

```sh
git tag -a v1.0.0 -m "DESSERT 2026 reproducibility release"
git push origin v1.0.0
git rev-parse HEAD
```

Record that final commit hash in the paper. The existing paper-source SHA-256
identifies the original measured implementation; it is not a Git commit hash.
The two identifiers can coexist because the release adds packaging and tests
around the preserved implementation.

If further code changes are needed, give them a new version and document whether
they affect results. Keep the version cited by the paper retrievable.

The included [GitHub Actions workflow](../.github/workflows/tests.yml) follows
[GitHub's Python testing documentation](https://docs.github.com/en/actions/tutorials/build-and-test-code/python).
It requests read-only repository permissions and does not publish or deploy.
Citation metadata follows the
[Citation File Format 1.2.0 guide](https://github.com/citation-file-format/citation-file-format/blob/main/schema-guide.md).
