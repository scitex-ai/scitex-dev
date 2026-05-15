---
description: |
  [TOPIC] GitHub Actions workflow file naming + structure convention.
  [DETAILS] One workflow file = one check. Descriptive kebab-case filenames
  that name the target/runtime (e.g. `rtd-build-on-ubuntu-latest.yml`,
  `pytest-on-ubuntu-py3-11-3-12-3-13.yml`, `pypi-publish-on-release.yml`).
  Multi-concern workflows must be split. The workflow `name:` field and each
  `jobs.<id>.name` should match the file's purpose. Exempt: `cla.yml` (the
  CLA Assistant action hard-codes that filename). Audited by PS-164.
tags: [scitex-general-package-workflows-naming]
---

# GitHub Actions — Workflow Naming + Structure (SciTeX)

## Rule: one workflow file = one check

A single file under `.github/workflows/` runs one logically-coherent check.
Multi-concern workflows (multiple jobs with unrelated purposes) MUST be split
into separate files. This keeps the GitHub Actions UI scannable (each row is
one named check), branch-protection rules unambiguous (gate on
`pytest-on-ubuntu-py3-11-3-12-3-13 / test`, not the opaque `Test / test`),
and a red check tells you exactly which surface broke.

Matrix expansion is one file. A 3-Python-version test matrix is still one
check; we name the file `pytest-on-ubuntu-py3-11-3-12-3-13.yml`, not
three files.

## File naming

Kebab-case. Includes the *target* (what runs) and, where useful, the
*runtime* (where it runs):

| Good | Bad |
|------|-----|
| `rtd-build-on-ubuntu-latest.yml` | `docs.yml` |
| `pytest-on-ubuntu-py3-11-3-12-3-13.yml` | `test.yml` |
| `pypi-publish-on-release.yml` | `publish-pypi.yml`, `release.yml` |
| `live-haiku-api-integration-on-ubuntu-latest.yml` | `integration.yml` |
| `scitex-dev-audit-all-on-ubuntu-latest.yml` | `audit.yml` |
| `sync-main-to-release-tag-on-push.yml` | `sync.yml` |

Rationale: when CI shows ten green checks on a PR, reviewers must be able
to glance at the names and know what the surface area is. Generic names
(`ci.yml`, `lint.yml`, `build.yml`) waste that signal.

## `name:` field and job names

The workflow's top-level `name:` should match the file's purpose, written
out (e.g. `name: PyPI publish on release`). Each `jobs.<id>.name`
likewise gets a descriptive label so the GitHub Actions UI shows
`PyPI publish on release / Publish to PyPI` rather than `Test / test`.

## Exempt filenames

`cla.yml` — the CLA Assistant GitHub App pins this filename in its
documentation; renaming it breaks the integration. Keep it as-is.

## Splitting heuristic

If a workflow file's `jobs:` block has more than one entry, the job IDs
should share a common stem (e.g. `test-3-11` + `test-3-12` + `test-3-13`,
or `build` + `build-docs`). If they don't (e.g. `test` + `install-check`,
or `lint` + `docs`), split into two files. The "common stem" rule
captures matrix-style fanout vs. unrelated concerns.

### Carve-outs to the splitting heuristic

Two patterns are explicitly NOT split-violations even when job IDs look
unrelated at a glance:

1. **Matrix fan-out.** A single test matrix across Python versions /
   OSes / extras is one logical check; the GitHub UI already shows one
   row per matrix cell, so we don't need separate files. Captured by
   the common-stem rule above.
2. **Build → publish → release pipelines.** A release workflow that
   chains `build` → `test-built-wheel` → `publish-pypi` → `create-github-release`
   is one logical pipeline whose later jobs depend on earlier ones via
   `needs:`. The job IDs don't share a stem, but splitting them across
   files would break the artifact handoff. The auditor (PS-164) treats
   a workflow as a pipeline (and skips the multi-job check) when at
   least one job has a `needs:` edge pointing inside the same file.

### Filename ↔ `name:` token-overlap (linter)

PS-164's check (3) measures Jaccard similarity between the filename
stem and the workflow's `name:` slug. Zero-token-overlap drift (e.g.
filename `pytest-on-ubuntu-py3-11-3-12-3-13.yml` with `name: Quality
Gate`) is rejected because branch protection keys on display name and a
reviewer scanning the Actions tab can no longer correlate filename to
row. Keep at least one substantive token shared between filename and
`name:`.

## Audit

`PS-164` (severity `W` — warning) scans `.github/workflows/` for:

1. Files with a vague-name denylist match: `docs.yml`, `test.yml`,
   `lint.yml`, `ci.yml`, `build.yml`, `release.yml`, `publish.yml`,
   `audit.yml`, `quality.yml`, `sync.yml`, `integration.yml`.
2. Files with more than one job whose IDs do not share a common stem
   (heuristic for "multiple unrelated concerns").
3. Workflow `name:` field that obviously mismatches the filename
   (filename stem vs. `name:` slug Jaccard < 0.2).

`cla.yml` is excluded from all three checks.

Warning-only during adoption. Promote to error once the ecosystem is
clean.

## Migration

```bash
# Inventory current workflows
ls .github/workflows/

# Rename in a single commit per file; update branch-protection rules
# to point at the new check name BEFORE deleting the old file.
git mv .github/workflows/docs.yml \
       .github/workflows/rtd-build-on-ubuntu-latest.yml
```

Branch protection: GitHub identifies required status checks by their
*display name* (which is `name:` field, fallback filename stem), so
update both the file name AND the workflow's `name:` field, then update
branch protection to the new label.
