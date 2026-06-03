# Changelog

All notable changes to `scitex-dev` are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.17.1] — 2026-06-03

### Fixed
- **`audit-project` PS-108 / PS-108b slug labels (#101).** The violation tag
  that audit-all prints for these flat-package-layout rules used to read
  `[PS-108 §1 readme-missing-license-badge]` / `[PS-108b §1
  readme-missing-pypi-py-version-badge]` — slugs from long-retired README
  rules that confused every reader of the audit output. PS-108 / PS-108b
  actually detect prefix-cluster mess and too-many-flat-py-files; the slugs
  now read `src-prefix-cluster-mess` and `src-flat-py-files-over-threshold`.
  Two AAA + one-assert regression tests guard the invariant that neither
  slug contains the word `readme`. No behaviour change beyond the printed
  label.

## [0.17.0] — 2026-06-01

### Added
- **`audit-project` MVP lint rules for SciTeX/Clew conventions (`PS-PATH-001` / `PS-PATH-002` / `PS-CLEW-001` / `PS-AGENT-001`) (#98).** Four new rules under `src/scitex_dev/_cli/audit/_project/`:
  - **`PS-PATH-001` (E)** — `config/PATH.yaml` with the forbidden outer `PATH:` wrapper. The filename gives the namespace; wrapping moves real values to `CONFIG.PATH.PATH.<KEY>` and breaks 100% of access sites with `AttributeError`.
  - **`PS-PATH-002` (E)** — `config/PATH.yaml` leaf values without the `f"..."` prefix. `eval(CONFIG.PATH.<KEY>)` on bare `"./data/foo"` raises `SyntaxError` because the body parses as a Python expression `./data/foo`, not a string literal.
  - **`PS-CLEW-001` (W)** — `*.py` calls `scitex_clew.add_claim` but the same module never calls `clew.verify_claim` / `clew.list_claims` for self-verification. Encourages the "solver runs Clew at its own runtime and notices failures itself" pattern from the paper-scitex-clew operator directive 2026-06-01.
  - **`PS-AGENT-001` (E)** — `scripts/agent/*.py` registers clew claims but never persists a real `claims.json` file. The DAG terminus must be a file, not a script node.
  - 34 new tests (25 + 9 split-siblings to comply with PA-307 §3 TQ002 / TQ007).
- linter: host the scitex-umbrella `STX-I001`–`I007` (import hygiene) and `STX-S001`–`S008` (`@stx.session` structure) rules in-house as first-class engine built-ins (`_rules/_import_hygiene.py`, `_rules/_session_structure.py`, registered in `_rules.ALL_RULES`). Every id, severity, category, message, suggestion, and `requires` gate is preserved verbatim, so runtime behavior is identical — the scitex-gated rules still fire only when scitex is installed. These no longer depend on the umbrella's `scitex_dev.linter.plugins` entry-point plugin; `scitex-dev linter` surfaces them straight from its own registry. The plugin-loader mechanism is untouched (other leaf packages still use it). Umbrella-thinning Phase A — lets the umbrella delete its `scitex/_linter_plugin.py` once it pins this release.

### Fixed
- **Skill page `scientific/02_research-project_03_project-structure-config-and-data.md` (#97):** the YAML example violated the two firm rules immediately above it (outer `PATH:` wrapper + bare-string leaves). Rewritten to follow both rules unambiguously; the rules themselves are unchanged — they were already correct.

### Changed
- Untracked the orphan `docs/to_claude/examples/example-python-project-scitex/config/PATH.yaml` example (gitignored by `.gitignore:14` but accidentally tracked from before the gitignore line was added). The same file is correctly untracked in scitex-clew and scitex-io. Aligns scitex-dev with the rest of the ecosystem.

## [0.16.1] — 2026-05-31

### Added
- **`audit-python-apis` honours `.scitex/dev/config.yaml` `audit.skip`
  (PA-rule scoping).** PA-* rules can now be deferred per-project, mirroring
  the long-standing `audit-project` mechanism (`cfg.applies(rule) and rule not
  in cfg.skip`). A deferred rule is dropped from the violation set entirely, so
  it no longer drives the error-level exit code that `audit-all` gates on. This
  lets a project scope down the otherwise exception-free PA-306 (no-mocks) and
  PA-307 (test-quality) error rules — e.g. a Django app that legitimately uses
  test doubles for external services — without faking or deleting the rules.
  The `audit-python-apis` CLI command now resolves the repo root (via `--repo`
  or the registry's `local_path`, same as `audit-project`) and threads it into
  `audit_api(..., repo_root=...)`; `repo_root=None` preserves the legacy
  unscoped behaviour exactly. (The `_config` package already documented this as
  "since 0.16.1".)
- **`django` project-type relaxes PA-306 (no-mocks) to a warning.** Django apps
  legitimately use test doubles for external services (HTTP, browser, telegram,
  ssh), so the no-mocks rule is wrong-by-default for them. A `django`
  project-type downgrades PA-306 from error to warning (PA-307 still applies at
  full severity). Explicit and documented, not a silent exception. The
  `audit.skip` path remains the general, principled mechanism; the django
  default is a convenience on top of it.

## [0.15.0] — 2026-05-30

### Added
- **`audit-django` auditor — the "apps and config" Django app standard
  (ADR 0002).** New `scitex-dev ecosystem audit-django <pkg>` rule
  (also run by `audit-all`) checks a Django repo against the canonical
  layout codified in scitex-hub's `docs/adr/0002-scitex-django-app-standard.md`:
  Django project in `config/` (DJ-1xx), apps under `apps/` (DJ-2xx),
  project `templates/`+`static/` (DJ-3xx), the `src/scitex_<name>/`
  pip-package sibling (DJ-4xx), and the web stack in the `[all]` extra
  (DJ-5xx). Non-Django packages (no `manage.py`) are skipped; `scitex-hub`
  is the reference implementation and passes by definition.

### Fixed
- **`init-config --project-type` now exposes all project types.** The
  command previously offered only `Choice(["pip", "research"])` while the
  loader SSOT is `{pip, research, special, django, deferred}`, so
  `django`/`special`/`deferred` could only be set by hand-editing
  `.scitex/dev/config.yaml`. The choices are now sourced from
  `PROJECT_TYPES` (no drift) and the help documents the hybrid
  pip+django case.

## [0.14.0] — 2026-05-28

### Added
- **Dashboard GH-Release column (and MISSING signal)** — the `RELEASE`
  column on `scitex-dev ecosystem dashboard list` (default verbosity)
  now reads `MISSING` in red when a package has a local git tag but
  the GitHub Release for that tag is absent. This is the canonical
  signal for the 2026-05-27 footgun where the publish workflow's awk
  release-notes extractor failed under `bash -e`, leaving PyPI
  populated but no Release attached. The new
  `gh_release_lookup_done` flag on `PackageState` distinguishes
  "not yet queried" (dim `N/C`) from "queried, no release" (red
  `MISSING`). Markdown export gained the column too.
- **`dashboard export --format org` / `--format pdf`** — emits a
  ywatanabe-convention Org-mode report ("the usual PDF" source) and
  optionally converts to PDF via `pandoc` or `emacs --batch`. When
  neither tool is on PATH the `.org` sidecar is still written and the
  CLI prints a clear "convert on host" message (exit 0; the .org file
  is the usable artefact). `to_pdf` always writes the `.org` next to
  the requested `.pdf` output. The report includes a "GH-Release
  gaps" section listing packages with a tag but no Release.
- **`tests/results/` accepted as a known `tests/` subdir (PS-302).** Test
  runs produce a variety of artifacts beyond coverage (captured payloads,
  fixture output, relocated `.coverage` data files); `tests/results/` is
  now a first-class gitignored artifacts category alongside
  `tests/coverage/` / `tests/logs/`. Added to `_KNOWN_TEST_SUBDIRS`, the
  PS-302 rule text, and both project-structure skill leaves (general +
  scientific). Backward-compatible — nothing that passed before now fails.

### Fixed
- **GitHub Release notes extraction never fails the publish workflow** —
  the `Extract release notes from CHANGELOG.md` step in
  `.github/workflows/pypi-publish-and-github-release-on-tag.yml`
  explicitly disables `-e`, guards `CHANGELOG.md` absence, swallows
  awk errors, and guarantees a non-empty `release-notes.md` before
  exiting 0. Previously a missing `## [X.Y.Z]` section could fail
  the `release` job even after PyPI had successfully published —
  the 2026-05-27 wave bit crossref-local 0.7.4 and openalex-local
  0.7.6 (both on PyPI, no GH Release). Note: this is scitex-dev's
  own workflow only; downstream repos must re-sync the file (see
  PR for the propagation note).

## [0.13.0] — 2026-05-27

### Added
- **§6 per-package MCP-tool allowlist (`mcp_tools_allowlist`)** — packages that
  intentionally expose a *curated* MCP surface (a few high-level verbs, not a
  1:1 mirror of their Python API) can declare the exact tool names in
  `[tool.scitex_dev] mcp_tools_allowlist` (pyproject) or
  `audit.mcp-tools-allowlist` (`.scitex/dev/config.yaml`). §6 then verifies the
  registered MCP surface matches the declared set — flagging undeclared tools
  and declared-but-unregistered names — instead of the all-or-nothing
  `mcp_parity_exempt` skip or the full-API-mirror heuristic. `skills_list` /
  `skills_get` are always permitted. Helpers live in
  `scitex_dev._cli.audit._summary._mcp_parity` (`mcp_tools_allowlist` /
  `_allowlist_violations`); first adopter is scitex-ml's stateless analysis
  CLI/MCP surface.
- **§6a per-package env-var allowlist (`[tool.scitex_dev] env_allowlist`)** —
  packages that legitimately ship operator-facing env vars predating the
  SciTeX ecosystem (acronym brands like `SAC_*`, integrations with external
  operator tooling) can now declare the prefix in their own
  `pyproject.toml` instead of being forced into a global
  `SCITEX_<PKG>_*` rename that would break every running deployment.
  Entries apply "equal-to-stripped or prefix-match" — same shape as the
  universal allowlist — so `env_allowlist = ["SAC_"]` covers any
  `SAC_*` var while `env_allowlist = ["GH_TOKEN"]` covers only the
  exact name. Mirror of the existing `mcp_parity_exempt` opt-out:
  same `[tool.scitex_dev]` namespace, same checked-out-tree
  resolution (registry `local_path` when present, else walk up from
  the import location), same sparingly-used contract. Helper lives
  in the new `scitex_dev._cli.audit._summary._env_allowlist` module
  (`read_pkg_env_allowlist` / `is_var_in_pkg_allowlist`); `_audit
  ._is_allowed_env` and `_audit._scan_env_vars` consult it on every
  audit-cli run. Documented in
  `_skills/general/03_interface_02_cli/12_config-and-env.md` §6a.

## [0.12.2] — 2026-05-24

### Fixed
- **§6 MCP-parity exemption unreadable in CI** — `is_mcp_parity_exempt`
  resolved the audited package's repo root only via the ecosystem registry's
  fixed `local_path` (`get_local_path`). On CI runners that path does not
  exist (the package is editable-installed from `$GITHUB_WORKSPACE`), so a
  declared exemption (`.scitex/dev/config.yaml audit.mcp-parity-exempt: true`
  or pyproject `[tool.scitex_dev] mcp_parity_exempt`) was never read and §6
  fired for exempt packages (e.g. figrecipe's 74 matplotlib-mirror MCP tools)
  regardless of the checked-out config. `_audited_repo_root` now falls back to
  resolving the repo root from the installed tree via `importlib.util
  .find_spec` (mirroring audit-project's `_resolve_repo_root`), so the
  exemption is read from the tree actually being audited.

## [0.12.1] — 2026-05-24

### Fixed
- **audit-project orphan-hinter fd regression (#63)** — 0.12.0 switched the
  PS-204 orphan-test hinter's file discovery from stdlib `rglob` to the Rust
  `fd`/`fdfind` tool with NO fallback, so `audit-project` hard-crashed with
  `FdNotFoundError` on any runner without `fd` (e.g. GitHub `ubuntu-latest`),
  turning the quality CI red ecosystem-wide. `fd_find_files` now keeps `fd`
  as the preferred fast path but, when it is absent, emits a **loud warning**
  (`RuntimeWarning`, "fd/fdfind not found on PATH — falling back to slower
  stdlib scan; install fd for speed") and falls back to a stdlib `rglob`
  walk so the audit runs to completion. No silent fallback, no hard crash by
  default.

### Added
- **`audit.require-fd` strict knob** — a repo may opt into fail-loud-on-missing
  -fd via `.scitex/dev/config.yaml` `audit.require-fd: true` (or pyproject
  `[tool.scitex_dev] audit.require_fd = true`). When enabled and `fd` is
  absent, the orphan-hinter raises `FdNotFoundError` instead of falling back —
  for CI that wants to guarantee the fast path ran. The resolver mirrors
  `is_mcp_parity_exempt`'s pyproject + config.yaml resolution.

## [0.12.0] — 2026-05-24

### Added
- **`mcp_parity_exempt` per-package opt-out** — packages may declare
  `[tool.scitex_dev] mcp_parity_exempt` in `pyproject.toml` to opt out of
  the §6 MCP-parity audit rule, replacing transitional `skip_rules=("§6",)`
  hacks in downstream test suites (#62).
- **Research project-type (RP-2xx)** — research projects skip publish-only
  rules while keeping the universal mirror/structure rules (#58).
- **PS-173** — ADR format audit (filename convention + lean-template sections).
- **PS-149** — hard-dependency overreach (heavy lib declared as a hard dep but
  used feature-only) (#53).
- **PS-168** — per-package secret-exception config via `pyproject.toml` (#52).
- **PS-148** — downstream optional-deps guarded in `src/` (severity W during
  ecosystem adoption) (#51).
- **quota-keepalive** managed cron job (#50).

### Changed
- **Ecosystem registry: `scitex-cloud` → `scitex-hub`** — renamed the cloud
  package identity in the ecosystem registry (#61).
- **audit-all** — parallelized per-audit dispatch with `fd`-backed file
  discovery for faster ecosystem audits (#49).
- **MCP tool listing** — routed through `get_tools_sync` for FastMCP 2.x/3.x
  compatibility (#47).
- **Sphinx** — fixed 11 warnings and enforced `-W` (warnings-as-errors) on the
  develop docs gate (#48).

### Fixed
- CI `_sphinx_html` commit-back step made non-fatal.
- Codecov PR comments disabled to stop email noise.

## [0.11.17] — 2026-05-16

### Added
- **Branding registry + PS-2xx audit** — single source of truth for
  package branding, with PS-2xx rules auditing README / pyproject /
  docs against the registry. Ships the new `scitex_dev._branding`
  module (`get`, `get_env`, `register_method_aliases`) that figrecipe,
  socialia, and other ecosystem packages consume.
- **Ecosystem CLI** — `--help` now organizes subcommands by category;
  added `bulk` fan-out for running a command across all packages;
  `list --category <name>` filters packages by category.

### Changed
- Audit refinements:
  - **PS-167** — refined detection logic to reduce false positives.
  - **PS-201** — shim tolerance: allow thin re-export shims to satisfy
    the rule without tripping the audit.
  - **PS-202 / PS-204** — test path convention now mirrors source path.
- Test infrastructure: split `test.yml` into a pytest matrix and an
  import-smoke job; renamed workflow files for clarity.

## [0.11.16] — 2026-05-15

### Added (audit rules)
- **PS-164** — workflow-naming convention (one-file-per-check; descriptive
  filenames; short top-level `name:` labels).
- **PS-211** / **PS-212** — `tests/smoke/` and `tests/e2e/` directory rules.

### Changed
- **PS-122** — RTD detection is now content-based (looks for a `sphinx-build`
  step) rather than filename-based, so the rule survives workflow renames.
- Workflow files renamed to the PS-164 convention:
  - `docs.yml` -> `rtd-sphinx-build-on-ubuntu-latest.yml`
  - `newb.yml` -> `newb-docs-quality-on-ubuntu-latest.yml`
  - `publish-pypi.yml` -> `pypi-publish-and-github-release-on-tag.yml`
  - `quality-audit.yml` -> `scitex-dev-quality-audit-on-ubuntu-latest.yml`
  - `sync-main.yml` -> `sync-main-to-release-tag-on-push.yml`
  - `test.yml` -> split into `pytest-matrix-on-ubuntu-py3-11-3-12-3-13.yml`
    and `import-smoke-on-ubuntu-py3-12.yml`.
- README badges normalized to `shields.io` short labels
  (`docs`, `tests`, `install-check`, `quality`, `cov`).

### Fixed
- `audit/_project` — resolve `_spdx_from_pyproject` undefined reference.
- `audit/license` — `tomli` fallback for Python 3.10 (`tomllib` is 3.11+).
- `audit` — `skip_rules` now matches `ERRO:`-prefixed lines and reads stderr.

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
