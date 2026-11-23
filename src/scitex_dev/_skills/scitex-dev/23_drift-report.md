---
description: |
  [TOPIC] Ecosystem drift-report
  [DETAILS] Version and checkout-reference matrix, missing-baseline findings, independent install checks, and observe-timer limits. Unknown cells and an exit of zero do not establish full fleet coverage.
tags: [scitex-dev-drift-report]
---

# Ecosystem drift report

Use the umbrella route when installed; standalone bootstrap examples follow:

```bash
scitex-dev ecosystem drift-report -p scitex-io --json
scitex-dev ecosystem drift-report -h spartan
scitex-dev ecosystem drift-report -q
```

The collector performs live PyPI, Git/host and `sac` probes. Inspect installed
help and intended scope before running it. `--package` and `--host` are repeatable
matrix filters; `--host all` selects the default enabled hosts. Independent
install checks below still run when the matrix is filtered.

## References and layers

`SSoT` is the committed `pyproject.toml` version read from local `develop`,
falling back to `origin/develop` when the first ref is absent. The reader does
not substitute a dirty working tree, another checked-out branch or local HEAD.
A missing checkout/ref/file/version yields no reference. This reader does not
resolve a dynamic version from a build backend.

The `github` value comes from `git describe --tags --abbrev=0 --match v*` at
`origin/main`, falling back to `main`. It is a reachable tag in the local clone,
not a live GitHub Releases query or proof of the latest published artifact.
A newer tag elsewhere in that clone can produce a reachability note. Ref
readers do not themselves fetch; results depend on the clone's available refs.

The historical eight-layer model has one column per selected host, so the
actual column count varies:

| JSON layer key | Human header | Value and comparison |
|---|---|---|
| `pypi` | `pypi` | PyPI version against reference version |
| `github` | `github` | Reachable version tag against reference version |
| `host:<name>` | host name | Abbreviated checkout SHA; full SHA compared with `packages_audit`'s origin reference |
| `base-image` | `img` | Versions reported by `sac`, compared with reference version |
| `agent-overlay` | `overlay` | Per-agent overlay version, else its image's base version |
| `ci` | `ci` | Always unknown: `not-collected (v1)` |
| `editable` | `editable` | Current interpreter's installed version against reference version |

The editable cell is a version cell; checkout SHAs belong to host columns.
Container cells collapse equal raw version strings to one value. Multiple
strings yield `mixed` with the image/agent breakdown and mark that cell as drift.
Version comparison otherwise uses the existing PEP 440 helpers. A `*` marks a
cell's drift; `-` means unknown, and `???` means the row has no version reference.

## Unknown data and exit status

An unknown individual cell does not itself count as drift. An unreachable host,
missing package or unavailable `sac` can therefore leave coverage incomplete
without making a judgeable row inconsistent. Inspect notes and collected scope.

A missing reference version is different: the row is **NOT JUDGEABLE**, neither
consistent nor counted in `drifting`, and makes `DriftMatrix.has_drift` true.
The CLI's normal completed-report exit is 1 if any of these are present:

- a judgeable row with a drifting cell;
- a row with no reference version;
- a critical-package staleness warning;
- an untrustworthy-install finding.

Otherwise it exits 0. This is the model's current verdict, not proof that every
host/layer/package was checked; unexpected collection errors remain separate.
The full human report names NOT JUDGEABLE rows. Quiet output appends nonzero
`NOT JUDGEABLE` and `untrustworthy install(s)` counts alongside the existing
drifting and critical-staleness counts. These are distinct finding categories,
not additional package rows. Consistent-only text and unavailable-container
notes retain their existing format. JSON carries row references/consistency/
cells and the two independent warning lists; its summary still omits a
dedicated unjudgeable count. Full human output includes integrity details and
the interpreter path before staleness and the matrix. Quiet output gives counts,
not affected-package details or hints; use full output or JSON for those. Neither
quiet counts nor the JSON summary establish complete collection coverage.

## Independent interpreter checks

The critical staleness watch uses `_model.CRITICAL_PACKAGES`. It compares the
verified installed version with a local checkout's version when available,
otherwise PyPI. This separate reader uses the checkout file, not the matrix's
committed-ref reader. It reports strictly behind versions; absent, current,
ahead or unavailable readings are omitted without establishing their health.

The install-integrity scan defaults to every registered ecosystem package in
the current interpreter. It reports untrustworthy claimed metadata, including
orphaned or drifted installs; absent packages and bare paths claiming no version
are omitted. It is distinct from staleness and invalidates a version-only
interpretation for affected packages. Neither check verifies other hosts.

## Container collection and timer

`sac versions --json` uses list-form argv. Absent executable, nonzero exit,
probe failure, unparseable output or zero rows makes both container layers
unavailable with a reason. Even exit 0 with `[]` proves no container coverage.
The full report prints a BLIND LAYERS warning when container data is unavailable.
A nonempty response still does not prove that every intended image/agent exists
in those rows or that a live process uses the reported content.

The `scitex_dev.jobs` provider declares `scitex-dev-drift-report` as a timer
with `OnBootSec=5min` and `OnUnitActiveSec=6h`. Its command uses the shared
`scitex-dev ecosystem cron exec` log sink (default
`~/.scitex/dev/runtime/logs/timer-drift-report.log`) and runs the report with
`|| true`. That wrapper masks any report nonzero exit, including a collection
failure; unit success alone proves neither a complete observation nor no drift.
A declared JobSpec does not prove installation, activation or a successful run.

## Owning evidence and limits

Source: `_ecosystem/_drift_report/{_collect,_refs,_model,_build,_sac}.py`,
`_package_watch.py`, `_untrustworthy_installs.py`, CLI
`_cli/ecosystem/_cmds/_drift_report.py`, and `_ecosystem_jobs/_provider.py`.
Existing controls: `tests/scitex_dev/_ecosystem/_drift_report/` (including real
Git repositories in `test__refs.py` and full-report composition controls in
`test__build_integrity_banner.py` and quiet finding counts in
`test__build_quiet_findings.py`), CLI registration/help in
`tests/scitex_dev/_cli/ecosystem/_cmds/test__drift_report.py`, and job declarations
in `tests/scitex_dev/_ecosystem_jobs/test__provider.py`. Some collection and
install controls use declared injected probes. Pure assembly/renderer tests,
help and owned Git fixtures do not establish live PyPI/SSH/container collection,
timer execution, wheel content, process currency or release/deployment readiness.
