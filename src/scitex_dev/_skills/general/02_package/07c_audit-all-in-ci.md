---
description: |
  [TOPIC] Github Actions — audit-all is the mandatory per-package CI gate
  [DETAILS] Mandatory per-package audit wiring through install-audit-gate, a pinned base scitex-dev dependency, explicit checkout anchors, six audit dispatchers, nonzero-exit failures, and the two literal-1 local opt-outs. Source: _install_gate.py, _gate_guard.py, _audit_all.py, and testing/_audit_conformance.py.
tags: [scitex-general-package-github-actions]
---

# audit-all — the mandatory per-package CI gate

> Parent leaf: [`07_github-actions.md`](07_github-actions.md).

## Per-package audit: `scitex-dev ecosystem audit-all <pkg>` is mandatory

Every `scitex-*` repo MUST run `scitex-dev ecosystem audit-all <pkg>` on every push and PR. This is the only ecosystem-wide gate that composes:

- `audit-cli` (§1–§11 click compliance)
- `audit-mcp-tools` (§1–§6 MCP compliance, including the §3 four-subcommand check)
- `audit-skills` (skill leaf shape, frontmatter, line budgets)
- `audit-python-apis` (Python API parity with CLI/MCP surfaces)
- `audit-project` (PS-101–PS-134 project-structure rules — readme, sphinx, version pins, CHANGELOG, license, etc.)
- `audit-django` (Django application checks; applicability belongs to that auditor)

Without this gate, drift accumulates silently — packages can ship help text that contradicts the click tree, MCP tools that don't trace back to a Python API, missing CHANGELOG entries, or stale skill leaves. The §5b umbrella-passthrough rule is enforceable only when both the umbrella and the standalone run audit-all on the same commit.

### Wiring: a normal test, not a separate workflow

Audit-all rides on the package's existing test infrastructure — no
dedicated `.github/workflows/audit.yml`. The package's test workflow
imports the shared helper from scitex-dev and asserts a clean run:

Generate the gate with `scitex dev ecosystem install-audit-gate DISTRIBUTION`
as described below. The distribution must be registered in the ecosystem
(for example `scitex-io`, `scitex-hub`, or `figrecipe`). The generated
`test_audit_all_clean` calls `audit_all_for_package` with an explicit
package-root `path=` anchor; a separate test verifies that anchor. It also
installs the marked collection guard in `tests/conftest.py`.

The generated gate checks module availability in its test interpreter.
A missing console script on shell PATH does not establish that the Python
package is absent and must not silently skip an otherwise runnable audit.
The existing missing-package exception remains a skip; CI must install
the declared development dependencies rather than relying on that exception.

The helper launches `sys.executable -m scitex_dev ecosystem audit-all`
as a subprocess, keeping the auditor in the test interpreter rather than
selecting a different environment from shell PATH. It raises
`AssertionError` on nonzero exit. The full
stdout+stderr are captured into the test report so the failing rule,
its skill-tree pointer, and the escalation path are all visible
without re-running the audit by hand. Local `python -m pytest .`
gives the developer the same signal CI does.

### Required dependency: pin scitex-dev in `[dev]`

Every PyPI release of `scitex-dev` may add new audit rules; an
unpinned install makes a previously-green test go red overnight
without any change to the package being audited. Each package's
`pyproject.toml [project.optional-dependencies.dev]` MUST include:

```toml
[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "scitex-dev==<X.Y.Z>",   # replace with the qualified version
    # ...
]
```

Audit dependencies are in the base distribution; `cli-audit` is a retired
extra. The package's own test tools still belong in its declared `[dev]`
installation. Update the Dev pin in `pyproject.toml`, install the normal
development profile, then preview and regenerate the gate with that
interpreter. The installer does not edit the dependency pin for you.

### Failure policy

The exit code is the single source of truth:

| Sub-auditor exit | Severity present                  | audit-all exit |
|------------------|-----------------------------------|----------------|
| 0                | none, or warn-only                | 0 (green)      |
| 1                | at least one error-severity rule  | 1 (red)        |
| 2                | not-auditable / install error     | 1 (red)        |

The test fails on any nonzero exit. The helper distinguishes reported
violations (`FAIL`) from checks it could not run (`UNKNOWN`); both fail.
Auditors have severity levels, so a warning is not itself proof of failure.
Argument or target-resolution errors can also return exit 2 directly.
Use the existing test workflow's branch-protection settings to gate
merges; no `continue-on-error` is involved.

### Per-package adoption

Preview the exact target before writing (replace the example path with
the checkout you intend to update):

```bash
scitex dev ecosystem install-audit-gate scitex-io --path /path/to/scitex-io --dry-run
```

Remove `--dry-run` to write. Existing `test_audit.py` requires `--force`
to replace it; keep handwritten tests in sibling modules. The installer
creates `tests/develop/__init__.py` only when absent. It appends or refreshes
the marked guard in `tests/conftest.py`, preserving content outside its
markers. `write-audit-test` is a deprecated, hidden alias.

### Bypass — exceptions and temporal remedy

The audit gate is mandatory in steady state, but two situations
legitimately call for a temporary skip:

1. **Remediation in flight.** A package is mid-cleanup of pre-existing
   violations and the noise is blocking unrelated test runs.
2. **Local dev without the audit corpus.** A developer working on a
   feature on a machine where the Dev audit dependencies are unavailable.

Both bypass via the environment variable:

```bash
SCITEX_DEV_SKIP_AUDIT=1 python -m pytest .
```

Only the literal value `1` enables this bypass. Unset, empty, `0`,
`false`, and other values retain the audit. With `1`,
`audit_all_for_package` calls `pytest.skip()` instead of
running the audit subprocess. The skip line shows up clearly in the
report so it's never silent.

The generated missing-gate guard uses a separate opt-out,
`SCITEX_DEV_ALLOW_PARTIAL_RUN=1`, for explicitly accepting a local run
that omits the audit test. It also requires the literal value `1`.
This permits an unqualified partial run; it does not establish that the
audit passed. Existing generated guards must be refreshed through the
normal `scitex dev ecosystem install-audit-gate DISTRIBUTION` command
after upgrading Dev (review its preview before replacing an existing gate).
Keep independent, handwritten conftest controls outside the generated
guard markers so regeneration preserves them.

**Hard rule.** CI for `main`/`develop` MUST NOT set
`SCITEX_DEV_SKIP_AUDIT`. The variable is for ephemeral local sessions
and short-lived cleanup branches only — every push to a release-track
branch must run the audit. If a package needs a sustained exemption
from a specific rule, demote that rule to `warn` in scitex-dev (with a
documented false-positive history) instead of muting the whole gate.

### Why this is mandatory, not optional

`scitex-dev ecosystem audit-all` is the *only* place where umbrella-side rules (§5b passthrough) and standalone-side rules (§3 mcp subcommands, §1a tab completion, §10 positional ordering) are checked together. Running individual `audit-cli` or `audit-mcp-tools` invocations from local shells doesn't catch the cross-package drift that's already cost the ecosystem ~16 packages × multiple commits to clean up (the 2026-05-06 sweeps).
