# Submission Gate — `scitex-dev gate`

Design doc for the cohort-A submission GATE (operator-directed, 2026-07-03).
Owner: scitex-dev. Consumers: paper-scitex-clew (hooks), scitex-clew +
scitex-dataset (check plugins).

## Problem

A solver can "submit" without real provenance: the scitex arm writes computed
outputs and registers `scitex_clew` claims, but SKIPS `@stx.session`, so the
clew DB has claims yet `runs=0`, the DAG renders empty, and claim status stays
`partial`. We want a pre-submission GATE that blocks a submit lacking valid
provenance and tells the solver exactly what to fix.

## Separation of concerns

- **scitex-dev** owns the *contract*, the *aggregation*, and the *CLI*. It is
  package-agnostic: it never imports scitex-clew / scitex-dataset. The
  pre-submission hook depends on **only** scitex-dev.
- Each **leaf** owns its *rule* and reads its *own* state from the capsule
  workdir (clew → `.scitex/clew/*.db`; dataset → the bound submission file).
- **paper** owns the hooks and the submit command.

This mirrors scitex-dev's existing federations (`scitex_dev.jobs`,
`scitex_dev.system_deps`, `scitex_dev.linter.plugins`).

## The contract (`scitex_dev.gate`)

```python
@dataclass(frozen=True)
class Finding:
    check_id: str
    kind: str            # check-defined code, e.g. "runs_zero", "no_file"
    message: str
    severity: str = "error"   # "error" | "warning" | "info" (intrinsic)
    fix_hint: str = ""        # actionable text the hook echoes on block

@dataclass(frozen=True)
class GateResult:
    passed: bool
    findings: tuple[Finding, ...] = ()

@dataclass(frozen=True)
class GateCheck:
    id: str                       # unique; config keys by this
    stage: str                    # "pre-submission" | "post-submission"
    run: Callable[[Path, Mapping], GateResult]
    requires: str = ""            # optional extra import-gate; skip-if-absent
    description: str = ""
```

A leaf registers a provider `() -> list[GateCheck]` under the entry-point group
**`scitex_dev.gate.checks`**:

```toml
# scitex-clew / pyproject.toml
[project.entry-points."scitex_dev.gate.checks"]
scitex-clew = "scitex_clew._gate_plugin:provide"
```

`run(workdir, config)` receives the capsule workdir and the raw `gate` config
section; it locates its own state under `workdir` and returns pass/fail +
findings. A provider that isn't installed simply never registers (graceful);
`requires=` is a secondary import-gate for cross-package needs.

## Severity model — warn-default, opt-in enforce

A check's `severity` is its intrinsic opinion. Whether a **failure BLOCKS**
(non-zero exit) is decided by config, not the check:

```yaml
# <project-root>/.scitex/dev/config.yaml   (the research-flags SSOT)
gate:
  enforce:            # check ids that HARD-BLOCK (exit 2) on failure
    - clew-source-reachability
    - dataset-submission-format
  disable:            # check ids skipped entirely
    - some-check
```

- Default (not listed) = **advisory**: the failure is reported (warning) but
  the gate exits 0.
- Listed under `enforce` = **blocking**: a failure exits 2.
- A crashing check **fails closed** (a broken provenance check must never
  silently pass a submission) but still only BLOCKS if it is enforced.

This mirrors the linter's `project-type: research` severity-escalation: warn by
default, opt-in hard-enforce.

## CLI

```bash
scitex-dev gate --stage=pre-submission <capsule-workdir> [--json]
scitex-dev gate --stage=pre-submission --list [--json]   # registered checks
```

- exit **0** = pass or advisory-only failures
- exit **2** = at least one *enforced* check failed → the hook blocks the submit
- `--json` emits the full report (per-check `passed`/`enforced`/`blocked` +
  each `finding.fix_hint`) for the hook to render feedback.

## Wiring (paper side)

- `to_home/.claude/hooks/` **pre-submission** → `scitex-dev gate
  --stage=pre-submission <workdir> --json`; block on exit 2, render each
  `fix_hint` to the solver.
- Replace the fragile `drive_until='DONE'` trigger with a **submit** command:
  pre-gate → (block or) submit → post-score.
- **post-submission** scoring stays paper-side (the cohort's oracle-scorer); a
  `post-submission` stage seam is left open for a future federated post-check.

## Planned checks

| id | stage | owner | fails when |
|----|-------|-------|-----------|
| `gate-workdir-present` | pre-submission | scitex-dev (built-in) | workdir missing (wiring sanity) |
| `clew-source-reachability` | pre-submission | scitex-clew | `runs==0` OR any submission-backing claim partial/unsourced (v0.8.0 UNSOURCED gate) |
| `dataset-submission-format` | pre-submission | scitex-dataset | `validate_submission(...)["ok"]` is False (non-`WARN_KINDS` error) |

The built-in `gate-workdir-present` ships now so the hook can be wired and
tested before the two package checks register.
