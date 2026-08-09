---
description: |
  [TOPIC] Github Actions
  [DETAILS] Canonical GitHub Actions workflows that every SciTeX repo ships — test matrix across supported Python versions, PyPI publish via trusted-publisher OIDC (no API tokens), CLA-bot, reusable workflow patterns, artefact caching, the `pip install -e ".[dev]"` rule, dep-hygiene gotchas (test imports must use the standalone module name not the umbrella shim), and release-gate checks that guard the main branch. Use when creating a new scitex-* repo, auditing CI drift across the ecosystem, or debugging a red workflow.
tags: [scitex-general-package-github-actions]
---

# GitHub Actions (SciTeX)

> Split-out leaves of THIS section: [audit-all CI gate](07c_audit-all-in-ci.md) · [scitex-python transitional CI](07d_scitex-python-transitional-ci.md)

## THE canonical CI mechanism — one thin org-reusable caller

Operator decision (2026-07-21): every scitex-* repo ships exactly ONE CI
workflow, `.github/workflows/ci.yml` — a thin caller that delegates all job
bodies to the org-level reusable workflows in `scitex-ai/.github@main`
(`pytest-matrix.yml`, `import-smoke.yml`, `quality-audit.yml`,
`rtd-sphinx-build.yml`). A shared workflow cannot drift per-repo.

Deploy it with the single mechanism:

```bash
scitex-dev ecosystem ci-template apply <repo-dir> --yes
# or (alias that also sets the CI_RUNS_ON Actions Variable):
scitex-dev ci runner register <repo-dir> --yes
```

Rules:

- Runner selection: Actions Variable `CI_RUNS_ON`, default
  `["self-hosted","Linux","X64","scitex-ci"]`. Prefer hardware we own where
  CI turnaround matters; `ubuntu-latest` is ALLOWED (free for public repos,
  just slower) and is reported by PS-169 at **W — advisory, never blocking**.
  Operator directive 2026-08-05 superseded the 2026-07-14 self-hosted-only
  mandate; do NOT cite PS-169 as an ERROR, which this line did until now and
  which led two peer agents to misdiagnose a blocked migration.
- The runner rule that DOES block is **PS-224 (E)**: a **self-hosted** label
  set no registered machine serves. Such a job is not slow, it is
  undeliverable — GitHub queues an unmatchable job forever instead of
  rejecting it. Label sets made entirely of GitHub-provided images are out of
  scope (GitHub serves them).
- Do NOT hand-write per-repo CI job bodies (the retired consolidated
  `pr-ci.yml`/`release-ci.yml` pair and the in-SIF `ci.yml.template` are
  gone); `apply` deletes superseded files, including `newb-docs*`.
- Preserved alongside `ci.yml`: `cla.yml`, `auto-merge-to-develop.*`,
  `pypi-publish-*`, `rtd-sphinx-*`.
- Branch protection must reference the caller contexts
  (`"<caller-job-id> / <reusable job name>"`, e.g.
  `pytest-matrix / pytest-matrix-on-ubuntu-py3.12`); `apply` gates on this.

## Test job — install with the `[dev]` extra

CI runners start clean: no `pytest`, no `pytest-cov`, no `pytest-asyncio`, no project deps. The single canonical install line in every test workflow is:

```yaml
- name: Install
  run: pip install -e ".[dev]"
```

The `[dev]` extra in `pyproject.toml` MUST cover everything the test suite imports:

```toml
[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-cov",
    "pytest-asyncio>=0.21",   # only if any test uses @pytest.mark.asyncio
    # … any other dev-time-only dep (mypy, ruff for the CI lint job, etc.)
]
```

Common breakage modes:

| Symptom in CI logs | Root cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'pytest'` | bare `pip install -e .` | switch to `pip install -e ".[dev]"` |
| `PytestUnknownMarkWarning: Unknown pytest.mark.asyncio` then test counted as fail | `pytest-asyncio` missing from `[dev]` | add it |
| `ModuleNotFoundError: No module named 'click'` while running CLI | runtime dep declared only under `[dev]` | move to `dependencies = [...]` |

## Test imports — use the standalone module name, not the umbrella shim

**Rule.** Inside a standalone `scitex-X` package's `tests/`, always import via `scitex_X` directly:

```python
# YES — works in any environment that has scitex-X installed
from scitex_template import clone_template_from_cache
from scitex_template._mcp.handlers import list_templates_handler

# NO — only works when the scitex umbrella + its sys.modules alias shim
# are both installed. Fresh CI venv installs scitex-X alone, so this raises
# ModuleNotFoundError at collection time:
from scitex.template import clone_template_from_cache
from scitex.template._mcp.handlers import list_templates_handler
```

The same rule applies to internal imports inside `src/scitex_X/`. The umbrella shim path is only for users discovering the API via `scitex.X.…`; it is never a runtime path the package itself should rely on.

**Quick sed to fix a broken test suite after extraction:**

```bash
grep -rl "from scitex\.<name>\." tests/ \
  | xargs sed -i 's/from scitex\.<name>\b/from scitex_<name>/g'
```

## Downstream-dep hygiene in CI

A standalone `scitex-X` package SHOULD install cleanly without the `scitex` umbrella present (general/01_ecosystem/02 §"Dependency Hygiene"). This is enforced in CI by running the test job in a fresh venv that installs ONLY `pip install -e ".[dev]"` — no `scitex`. If any test imports `scitex.…` (the umbrella) it will fail; that's the intended signal.

When a few legacy code paths still need umbrella access (e.g. the cloner's remote-clone fallback that uses `scitex.git`), declare a separate optional extra:

```toml
[project.optional-dependencies]
legacy = ["scitex"]
```

…and gate the imports with `try/except ImportError`. The default `[dev]` install must NOT pull `[legacy]`; otherwise the dep-hygiene check is meaningless.

## SciTeX-Specific CLA Allowlist

```yaml
# cla.yml — <username> (committer) is always in the allowlist for SciTeX packages
allowlist: bot*,<username>
```

## scitex-python transitional pattern and module-specific workflows

> Moved to its own leaf: [07d_scitex-python-transitional-ci.md](07d_scitex-python-transitional-ci.md) — the path-filtered reusable-workflow shape for modules that still live in the scitex-python monorepo, plus the per-module workflow/path-filter table.

## PyPI publish — OIDC trusted publisher only

```yaml
# publish-pypi.yml
on:
  push:
    tags: ['v*']
jobs:
  publish:
    runs-on: ubuntu-latest
    environment:
      name: pypi
      url: https://pypi.org/p/<pkg-name>     # MUST match exact PyPI project name
    permissions:
      id-token: write                        # required for OIDC
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install build
      - run: python -m build
      - uses: pypa/gh-action-pypi-publish@release/v1
```

Trigger: push a `v0.1.0`-style tag. The first publish requires a one-time browser configuration at https://pypi.org/manage/account/publishing/ — bind the GitHub repo + workflow name + environment name. After that, every tag triggers an automatic release. **Never** store `PYPI_API_TOKEN` in repo secrets.

Naming patterns:
- Tag-based publish: used by most scitex-* packages (push `v*` tag).
- Release-based publish: used by scitex-python (GitHub Release published).

## Weekly quality audit

Every package inheriting from `scitex-minimal-template` carries `.github/workflows/scitex-quality.yml`. Runs `scitex-dev quality {audit-cli, audit-frontmatter, audit-docs, audit-lines, audit-scope}` on a Monday cron + on push/PR. Warn-only (`continue-on-error: true`) until the package is clean; flip individual steps to fail-the-build once green.

## Per-package audit: `scitex-dev ecosystem audit-all <pkg>` is mandatory

> Moved to its own leaf: [07c_audit-all-in-ci.md](07c_audit-all-in-ci.md) — the composed audit gate (`audit-cli` / `audit-mcp-tools` / `audit-skills` / `audit-python-apis` / `audit-project`), its `tests/develop/test_audit.py` wiring, the pinned `scitex-dev[cli-audit]` dep, the exit-code failure policy, `write-audit-test` adoption, and the `SCITEX_DEV_SKIP_AUDIT` bypass.

## Release-gate checklist

Before tagging `v*`:

1. CI green on `main` (the test workflow + scitex-quality both passing).
2. `CHANGELOG.md` updated with the new version section.
3. Version bumped in `pyproject.toml` AND any `__version__.py`.
4. Local fresh-venv probe: `pip install -e ".[dev]"` then `pytest` — must mirror what CI sees.
5. `pip install` from a sibling dir without scitex installed (dep-hygiene self-check).
6. Tag pushed (`git push origin v0.1.0`) — triggers `publish-pypi.yml`.
