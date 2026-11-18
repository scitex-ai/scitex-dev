---
description: |
  [TOPIC] Github Actions
  [DETAILS] Canonical GitHub Actions workflows that every SciTeX repo ships — test matrix across supported Python versions, PyPI publish via trusted-publisher OIDC (no API tokens), CLA-bot, reusable workflow patterns, artefact caching, the `pip install -e . --group dev` rule (PEP 735 groups replaced the `[dev]` extra on 2026-08-31 — needs uv or pip >= 25.1), dep-hygiene gotchas (test imports must use the standalone module name not the umbrella shim), and release-gate checks that guard the main branch. Use when creating a new scitex-* repo, auditing CI drift across the ecosystem, or debugging a red workflow.
tags: [scitex-general-package-github-actions]
---

# GitHub Actions (SciTeX)

> Split-out leaves of THIS section: [audit-all CI gate](07c_audit-all-in-ci.md) · [scitex-python transitional CI](07d_scitex-python-transitional-ci.md)

## THE canonical CI mechanism — one thin org-reusable caller

Operator decision (2026-07-21): every scitex-* repo ships exactly ONE CI
workflow, `.github/workflows/ci.yml` — a thin caller that delegates all job
bodies to the org-level reusable workflows in `scitex-ai/.github` at the
reviewed immutable revision pinned in the bundled `ci.yml.tmpl`
(`pytest-matrix.yml`, `import-smoke.yml`, `quality-audit.yml`,
`rtd-sphinx-build.yml`). A shared workflow cannot drift per-repo.

Deploy it with the single mechanism:

```bash
scitex-dev ecosystem ci-template apply <repo-dir> --yes
# or (alias that also sets the CI_RUNS_ON Actions Variable):
scitex-dev ci runner register <repo-dir> --yes
```

Rules:

- Runner preference: Actions Variable `CI_RUNS_ON`; the bundled caller defaults
  to `["ubuntu-latest"]` when absent. The reusable workflow owns actual runner
  admission. A preference or label set confers no authorization; company runners
  require the membership checks documented by the owning admission workflow.
  GitHub-hosted runners remain allowed (PS-169 is advisory during adoption).
- The runner rule that DOES block is **PS-224 (E)**: a **self-hosted** label
  set no registered machine serves. Such a job is not slow, it is
  undeliverable — GitHub queues an unmatchable job forever instead of
  rejecting it. Label sets made entirely of GitHub-provided images are out of
  scope (GitHub serves them).
- Do NOT hand-write per-repo CI job bodies (the retired consolidated
  `pr-ci.yml`/`release-ci.yml` pair and the in-SIF `ci.yml.template` are
  gone); `apply` deletes superseded files, including `newb-docs*`.
- Separate CLA, publishing and release-sync workflows remain required. `apply`
  preserves protected CLA, auto-merge and publisher prefixes. RTD protection is
  lifted only when the emitted caller actually declares its superseding RTD job;
  see `ci_template/_workflows.py` and `test__workflows.py`.
- PS-164/PS-165 recognize the complete bundled caller configuration, rather than
  exempting its filename alone. See [workflow presence](07b_workflow-presence.md)
  for delegated coverage and the limits of this static recognition.
- Branch protection must reference the caller contexts
  (`"<caller-job-id> / <reusable job name>"`, e.g.
  `pytest-matrix / pytest-matrix-on-ubuntu-py3.12`); `apply` gates on this.

## Test job — install with the `dev` dependency-group

CI runners start clean: no `pytest`, no `pytest-cov`, no `pytest-asyncio`, no project deps. The single canonical install line in every test workflow is:

```yaml
- name: Install
  run: pip install -e . --group dev      # needs pip >= 25.1
```

The `dev` group in `pyproject.toml` MUST cover everything the test suite imports:

```toml
[dependency-groups]              # PEP 735 — NOT published to consumers
dev = [
    "pytest>=7.0",
    "pytest-cov",
    "pytest-asyncio>=0.21",   # only if any test uses @pytest.mark.asyncio
    # … any other dev-time-only dep (mypy, ruff for the CI lint job, etc.)
]
```

*(Amended 2026-08-31. This was `pip install -e ".[dev]"` against a `[dev]`
**extra**. The operator ruled that the only permitted extra is `all`
([01_ecosystem/26_the-only-extra-is-all.md](../01_ecosystem/26_the-only-extra-is-all.md)),
so `dev` and `docs` became PEP 735 dependency groups. The completeness rule
below is unchanged — only the table it reads and the flag that installs it.)*

**`--group` has a floor, and it is a hard blocker.** It needs `uv`, or
**pip >= 25.1**. A runner image pinning an older pip fails the install step
outright; it does not silently fall back to anything. Check the pip version
in the image before switching a workflow, not after it goes red. The same
applies to the docs job: `pip install -e . --group docs`.

Common breakage modes:

| Symptom in CI logs | Root cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'pytest'` | bare `pip install -e .` | switch to `pip install -e . --group dev` |
| `PytestUnknownMarkWarning: Unknown pytest.mark.asyncio` then test counted as fail | `pytest-asyncio` missing from the `dev` group | add it |
| `ModuleNotFoundError: No module named 'click'` while running CLI | runtime dep declared only in the `dev` group | move to `dependencies = [...]` |
| `no such option: --group` | pip < 25.1 in the runner image | pin a newer pip, or use `uv pip install` |

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

A standalone `scitex-X` package SHOULD install cleanly without the `scitex` umbrella present (general/01_ecosystem/02 §"Dependency Hygiene"). This is enforced in CI by running the test job in a fresh venv that installs ONLY `pip install -e . --group dev` — no `scitex`. If any test imports `scitex.…` (the umbrella) it will fail; that's the intended signal.

When a few legacy code paths still need umbrella access (e.g. the cloner's remote-clone fallback that uses `scitex.git`), put the umbrella in `all` and gate the imports with `try/except ImportError`:

```toml
[project.optional-dependencies]
all = [
    # --- legacy umbrella fallbacks (cloner remote-clone) ---------
    "scitex[all]",
]
```

*(Amended 2026-08-31 — this used to prescribe a separate `legacy = ["scitex"]` extra. Per-feature extras are retired ([01_ecosystem/26](../01_ecosystem/26_the-only-extra-is-all.md)); the isolation the rule needs comes from the `dev` group not depending on `all`, not from `legacy` being its own name.)*

The default `dev`-group install must NOT pull `all`; otherwise the dep-hygiene check is meaningless. That is now the whole of the rule, and it is easier to hold: a dependency group and an extra are separate tables, so `dev` cannot pick up `all` by accident.

## SciTeX-Specific CLA Allowlist

```yaml
# cla.yml — <username> (committer) is always in the allowlist for SciTeX packages
allowlist: bot*,<username>
```

## scitex-python transitional pattern and module-specific workflows

> Moved to its own leaf: [07d_scitex-python-transitional-ci.md](07d_scitex-python-transitional-ci.md) — the path-filtered reusable-workflow shape for modules that still live in the scitex-python monorepo, plus the per-module workflow/path-filter table.

## PyPI publish — OIDC trusted publisher only

```yaml
# pypi-publish-and-github-release-on-tag.yml
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

The bundled caller delegates quality checks to its `quality-audit` reusable
workflow job. Follow that pinned callee and the mandatory audit gate below;
do not create a second legacy `scitex-quality.yml` or add warning-only waivers.

## Per-package audit: `scitex-dev ecosystem audit-all <pkg>` is mandatory

> Moved to its own leaf: [07c_audit-all-in-ci.md](07c_audit-all-in-ci.md) — the composed audit gate (`audit-cli` / `audit-mcp-tools` / `audit-skills` / `audit-python-apis` / `audit-project`), its `tests/develop/test_audit.py` wiring, the pinned `scitex-dev[cli-audit]` dep, the exit-code failure policy, `write-audit-test` adoption, and the `SCITEX_DEV_SKIP_AUDIT` bypass.

## Release-gate checklist

Before tagging `v*`:

1. CI green on `main` (the test and quality checks both passing).
2. `CHANGELOG.md` updated with the new version section.
3. Version bumped in `pyproject.toml` AND any `__version__.py`.
4. Local fresh-venv probe: `pip install -e . --group dev` then `pytest` — must mirror what CI sees.
5. `pip install` from a sibling dir without scitex installed (dep-hygiene self-check).
6. Tag pushed (`git push origin v0.1.0`) — triggers `pypi-publish-and-github-release-on-tag.yml`.
