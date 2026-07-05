---
description: |
  [TOPIC] Ecosystem drift-report
  [DETAILS] `scitex-dev ecosystem drift-report` — the unified per-package × per-layer VERSION matrix across all 8 drift layers (PyPI, GitHub, both hosts, container base-image, agent overlay, CI, editable). SSoT = pyproject@develop; a disagreeing cell is drift; exit 1 on drift so it doubles as a scheduled gate. Companion to the version-drift-management skill (general/05_development/13). Use to answer "is this package the same version everywhere it lives?".
tags: [scitex-dev-drift-report]
---

# `ecosystem drift-report` — unified version-drift matrix

One command answering the operator's #1 question — *"is this package the
same version everywhere it lives?"* Prints a matrix, package rows × layer
columns → version, spanning all eight drift layers from
[13_version-drift-management.md](../general/05_development/13_version-drift-management.md)
§1, so drift across hosts / containers / agents is identifiable at a
glance instead of discovered when something breaks.

```bash
scitex-dev ecosystem drift-report                 # full matrix + drift detail
scitex-dev ecosystem drift-report -p scitex-io    # one package
scitex-dev ecosystem drift-report -h spartan      # one host's column
scitex-dev ecosystem drift-report --json          # structured matrix
scitex-dev ecosystem drift-report -q              # one-line summary
```

The eight layer columns, per package:

| # | Column | Holds | Source (reused, not reinvented) |
|---|--------|-------|---------------------------------|
| 1 | `pypi` | published latest version | `_release.versions.get_pypi_version` |
| 2 | `github` | latest release tag (what `main` shipped) | `get_git_latest_tag` |
| 3–4 | `host:<name>` | that host's `develop` checkout sha | `_ecosystem._packages.packages_audit` |
| 5 | `img` | container base-image version | `sac versions --json` (layer `base-image`) |
| 6 | `overlay` | agent overlay effective version (overlay-else-base) | `sac versions --json` (layer `agent-overlay`) |
| 7 | `ci` | out of scope for v1 — honestly `not-collected` | — |
| 8 | `editable` | current interpreter's installed version + localhost sha | `importlib.metadata` + `packages_audit` |

**SSoT + drift marking.** "What SHOULD the version be?" is
`pyproject.toml` on the local `develop` checkout (the `SSoT` column);
"what IS published?" is PyPI. Every other layer is a *cache* of the SSoT
— a cell that disagrees is DRIFT, marked with a trailing `*` (e.g.
`0.9.0*`). The report then lists, per drifting package, exactly which
layers disagree and how (`behind SSoT` / `ahead of SSoT` / `mixed`).

**Only KNOWN-different is drift.** An *unknown* cell renders `-` and
never counts as drift: a host that is unreachable (sleeping laptop), a
package not installed there, the not-collected CI layer, and the case
where `sac versions --json` is absent all degrade gracefully. This is
deliberate — a false-red gate is a detector people learn to ignore
(§4 broken-feedback-loop lesson), so a down host or a missing `sac`
never trips the exit code.

**sac integration (layers 5–6).** Shelled as `sac versions --json`
(list-form argv, never a shell). If `sac` is not on `PATH`, the verb is
unknown, or the output isn't parseable, those two columns show `-` with
a footnote `unavailable (sac versions --json not present)` and the report
still completes.

**Exit code.** `0` when no drift is detected, `1` when any KNOWN drift
exists — so it doubles as a scheduled gate. It is federated as the
`drift-report` **timer** JobSpec (kind `timer`, OnBootSec catch-up +
every 6h) via the `scitex_dev.jobs` entry-point; the timer appends the
matrix to `~/.scitex/dev/logs/timer-drift-report.log` (with `|| true` so
finding drift is a successful observation, not a failed unit). Install
it with `scitex-dev ecosystem up` alongside the other federated jobs.
