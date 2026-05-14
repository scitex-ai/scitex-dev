# Changelog

All notable changes to `scitex-dev` are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.11.5] — 2026-05-07

### Fixed
- **PS-502 / PS-503 ignore `.ipynb`-only stems.** When an example's
  stem is owned by a `.ipynb` file (no matching `<n>.py`), the
  rendered cell outputs ARE the demo — the `_out/` sibling is
  optional and any legacy directory left over from a `.py → .ipynb`
  migration does not trigger PS-502/PS-503. Rules still fire when a
  `.py` example is present.

## [0.11.4] — 2026-05-07

### Added (audit rules — README structure)
- **PS-141** (audit-project) — README.md must have a mandatory `## Demo`
  section whose body contains at least one visual element (markdown
  image, non-shield HTML `<img>`, or fenced ```mermaid block).
- **PS-142** (audit-project) — README.md must have a mandatory
  `## Architecture` section. Accepted body forms: ```mermaid fence,
  ASCII text diagram (fenced ≥10 lines), file-tree characters
  (`├──`/`└──`/`│`), or `<img>` tag.
- **PS-143** (audit-project) — README.md sections must appear in the
  canonical order: `Problem and Solution → Installation →
  Architecture → <N> Interfaces → Demo → Quick Start → Part of
  SciTeX`. Optional sections may be skipped; relative order of those
  present must hold.
- **PS-144** (audit-project) — `## Problem and Solution` table cells
  must (a) contain ≥1 `**bold**` span, (b) keep bold coverage ≤30%
  of cell text, and (c) stay ≤200 characters per cell. Bolding entire
  sentences defeats emphasis; flat prose defeats the table.

### Added (audit rules — examples chapter)
- **PS-503** (audit-project) — `examples/<n>_*_out/` must contain a
  `FINISHED_SUCCESS/<session_id>/` subdirectory with at least one
  tracked artefact. Proves the example was run end-to-end via
  `@stx.session`, not hand-fabricated.
- **PS-504** (audit-project) — `.ipynb` example must commit cell
  outputs. GitHub renders cell outputs inline; a stripped notebook is
  invisible to viewers. Detected by walking the notebook JSON for any
  `code` cell with a non-empty `outputs` list.
- **PS-505** (audit-project) — `tests/examples/test_<n>.py` for an
  `.ipynb` example must invoke `jupyter nbconvert --execute` or
  `pytest --nbval[-lax]`. Subprocess `python <name>.ipynb` does not
  execute notebook cells.
- **PS-506** (audit-project) — `.ipynb` that imports `matplotlib` must
  include the `%matplotlib inline` cell magic. Without it the figure
  outputs aren't embedded in cell outputs and rendered notebooks on
  GitHub show no plots.
- **PS-507** (audit-project) — `.ipynb` that imports `matplotlib` must
  call `plt.show()` at least once. Even with `%matplotlib inline`,
  deferring display can leave figures un-rendered.
- **PS-508** (audit-project) — `.ipynb` example must not contain
  warning output (DeprecationWarning, UserWarning, FutureWarning, etc.)
  in committed cell outputs. Demos must run cleanly. Detected by
  scanning cell `outputs` for stderr-stream warnings or
  `output_type=error` with a `Warning`-named class.

All six new rules default to severity `error` (CI-failing). The
notebook-aware checks live in `_check_examples.py` and parse the
notebook JSON locally — no execution, fast.

## [0.11.3] — 2026-05-07

### Added
- `audit_all_for_package(..., skip_rules=("PS-108b", "PS-121"))` —
  packages can locally bypass aspirational structural rules from their
  `tests/develop/test_audit.py` while a refactor is pending. The
  ecosystem default keeps these rules at `error`; opt-in only.

### Fixed
- **Top-level compatibility shims now ship in the wheel:**
  `scitex_dev.decorators`, `scitex_dev._skills_quality`, and
  `scitex_dev._skills_quality_pytest`. Consumer packages
  (`scitex-dataset`, etc.) import these top-level paths; the actual
  implementations moved to `scitex_dev._ecosystem._skills.*` but the
  shims preserve the public import surface. v0.11.2 was missing them,
  so every consumer's CI failed with
  `ModuleNotFoundError: scitex_dev.decorators` /
  `scitex_dev._skills_quality_pytest`.

## [0.11.2] — 2026-05-07

### Fixed
- **`scitex_dev/testing/` subpackage now ships in the wheel.** It was
  added after the v0.11.1 tag, so the published v0.11.1 wheel was
  missing it — every package's `tests/develop/test_audit.py` failed in
  CI with `ModuleNotFoundError: No module named 'scitex_dev.testing'`.
  v0.11.2 unblocks the test-suite-integrated audit gate across the
  ecosystem.

### Added (audit rules)
- **PA-304** (audit-python-apis) — standalone source must not import the
  umbrella (`from scitex.X` / `import scitex` / `import scitex.X`).
  Module-level only; function-scoped lazy imports + `__main__` guards
  exempt; `examples/`, `docs/`, `_demo_*.py` files exempt;
  umbrella-private (`scitex._foo`) exempt.
- **PA-305** (audit-python-apis) — modules importing `playwright.async_api`
  must call `scitex_browser.debugging.capture_debug_artifacts_async`
  somewhere in the same module.
- **PS-139** (audit-project) — standalone `pyproject.toml` must not list
  `scitex` (umbrella) as a runtime or extras dependency.
- **PS-140** (audit-project) — packages with cross-package imports must
  ship `tests/integration/test_cross_package_imports.py`. Stale
  `CROSS_PACKAGE_IMPORTS` lists also flag.
- **§1a** — `install-shell-completion` and `print-shell-completion`
  subcommands are now mandatory for every CLI (was advisory).
- **§2 no-interactive-prompts** — CLI source must not call
  `click.confirm`, `click.prompt`, `getpass.getpass`, or bare
  `input()`. Mutating actions gate on `--yes`/`-y` instead.

### Added (helpers + skills)
- `scitex_browser.debugging.capture_debug_artifacts_async` — async
  helper that saves screenshot + HTML in one call. Used by
  `click_with_fallbacks_async` / `fill_with_fallbacks_async` to
  auto-capture before/after every interaction by default (opt-out via
  `capture_debug=False`).
- `_skills/general/02_package_09_browser-automation-debugging.md` —
  rule + pattern + anti-patterns for stepwise PNG+HTML capture.
- `scitex-dev ecosystem write-ci-workflow <pkg>` — materialises the canonical
  `.github/workflows/audit.yml` inside a package's local checkout. The
  generated workflow runs `audit-all` on every push and PR, with no
  `continue-on-error`; failure is driven by the audit-all exit code.
- `scitex_dev._ecosystem._core.should_skip_audit(pkg, auditor)` — single
  source of truth for "does this auditor apply to this package?". Each
  auditor consults it on entry and emits `skip pkg: <reason>` when the
  package's category doesn't apply.

### Changed
- **Audit rule severities promoted `warn` → `error`.** Per the 2026-05-06
  directive, every actionable rule with a documented spec now defaults to
  `error` severity (CI must fail). 38 project rules + 11 CLI/MCP § sections
  promoted in one sweep. Rules can be demoted back to `warn` only after a
  documented false positive lands on develop.
- **Audit exit codes now reflect actual severity.** `run_audit`,
  `run_audit_mcp`, and the `*_all` variants now return `1` whenever any
  violation reaches `error` severity (warnings alone exit `0`,
  not-auditable exits `2`). Previously every audit returned `0` regardless
  of violations, hiding ecosystem-wide drift from CI.
- `_emit_human` now labels lines `error pkg: N error(s)` vs
  `warn pkg: N warning(s)` based on the highest severity present, instead
  of always saying "warn".
- `_skills/general/02_package_07_github-actions.md` corrected the CI
  failure-policy section: `continue-on-error: true` is forbidden (it
  hides the signal); merge-gating uses branch-protection required-checks
  instead.

## [0.11.1] - 2026-05-06

### Added
- `attach_shell_completion(group, *, prog_name)` helper for any click
  group to register `install-shell-completion` and
  `print-shell-completion` subcommands consistently.

### Fixed
- `<cli>` placeholder substitution in shell-completion help text.
