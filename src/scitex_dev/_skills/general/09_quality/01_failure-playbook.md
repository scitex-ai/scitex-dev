---
description: |
  [TOPIC] Scitex Ecosystem Quality Failure Playbook — triage entry point
  [DETAILS] The severity-tagged symptom→fix routing table for failures seen across the SciTeX ecosystem, plus the triage order that says what to fix first. Each row routes to a recipe in one of two sibling leaves: `05_packaging-and-release-failures.md` (the repo is right, the published artifact is wrong — PyPI publisher, wheel drift, extras, undeclared transitive deps, license metadata) and `06_compat-and-refactor-drift.md` (nothing was edited, but what the code references changed — numpy 2 / pandas, optional deps, path migrations, CLI renames). Paired with 09_quality/02_checklist.md — §99 is the strategic runbook, §98 is the cookbook. Use when a CI run is red and you need to identify the symptom before reaching for a fix.
tags: [scitex-general-quality-failure-playbook]
---

# SciTeX Quality Failure Playbook — Triage

Symptoms observed during ecosystem-wide remediation passes, with severity
ratings and a pointer to the canonical fix. Enter here from §3 of the
checklist when a probe flags one of these patterns.

The recipes divide into two classes, and the class tells you where to look:

- **[05_packaging-and-release-failures.md](05_packaging-and-release-failures.md)**
  — *the repo is right and the artifact consumers get is wrong.* An editable
  install, a green Test job, and a pushed tag can all agree while the
  published package is broken; detection always requires stepping outside the
  checkout (fresh venv, downloaded wheel, PyPI index).
- **[06_compat-and-refactor-drift.md](06_compat-and-refactor-drift.md)** —
  *the code was never edited, but what it references changed.* A dependency's
  new major, our own layout migration, our own rename — the breakage lands in
  a file nobody touched, usually a test.

**Severity:**
- **CRITICAL** — blocks multiple downstream repos or the whole release wave
- **HIGH** — blocks a single repo's CI or release
- **MEDIUM** — test-level assertion / config threshold
- **LOW** — cosmetic / content drift

## 1. CI failure-mode table (from §3 of checklist)

Section numbers in the Fix column are stable across the split: §3–§4, §6–§8
and §10–§11 live in [05_packaging-and-release-failures.md](05_packaging-and-release-failures.md);
§5, §9 and §12 live in [06_compat-and-refactor-drift.md](06_compat-and-refactor-drift.md).

| Severity | Symptom | Root cause | Fix |
|---|---|---|---|
| **CRITICAL** | `ModuleNotFoundError: scitex_dev._skills_quality_pytest` across many repos | `scitex-dev` on PyPI lacks the module even though it exists on develop | Bump scitex-dev version, release → downstream picks it up (§4, packaging) |
| **CRITICAL** | Publish-to-PyPI `invalid-publisher: no corresponding publisher` | trusted publishing not configured on PyPI (or form silently discarded the save) | See §3 (packaging) — verify "Manage current publishers" lists the entry after submit |
| **HIGH** | Downstream `ModuleNotFoundError` for something that IS in git | new submodule added after last tag; PyPI wheel is stale | See §4 (packaging) — bump version + re-release |
| **HIGH** | `pytest: command not found` | `pip install -e .[dev]` but no `[dev]` extra defined | add explicit `pip install pytest pytest-cov` to workflow |
| **HIGH** | First CI push of a new feature fails at test-collection: `ModuleNotFoundError: No module named '<dep>'` (e.g. `fastmcp`) | Package has an optional `[X]` extra for the new feature, tests import the dep unconditionally, but `[dep]` is missing from `[dev]` so bare `pip install -e .[dev]` cannot collect those tests. | **Pick one and stay consistent**: (a) add the optional dep to `[dev]` so `[dev]` = union of "test infra + every test-imported optional"; (b) gate the tests with `pytest.importorskip("<dep>")`. The boundary rule is in [01_ecosystem/02_dependency-and-version-pinning.md `[dev]` extras completeness](../01_ecosystem/02_dependency-and-version-pinning.md) — features owned by *this* package go in `[dev]`; sibling-scitex **optional** integration imports use `importorskip`. A sibling that is a DECLARED runtime dependency (in `[project].dependencies`) is imported unconditionally — if it is missing the install is broken and the suite must go red, and `importorskip` would report that as green. |
| **HIGH** | `isinstance(obj, plotly.graph_objs.Figure)` → `NoneType has no attribute 'graph_objs'` | optional plotly fell back to `None`, check was unconditional | helper that short-circuits when dep is `None` — see §5 (drift) |
| **HIGH** | `Doc-Drift Nightly` fails with `cannot import scitex_<x>` | downstream pkg not pulled by `.[all]` | add explicit `pip install scitex-<x>` after the `.[all]` line, or fix `[x]` extra |
| **MEDIUM** | `assert func() is True` fails on numpy 2 runners | `np.any()`/`np.all()` return `np.True_`; `np.True_ is not True` | coerce at return: `return bool(np.any(...))` — see §5 (drift) |
| **MEDIUM** | `Unnamed: *` columns in pandas DataFrame | loader's dtype guard matches `"object"` only; pandas ≥ 2.2 uses `str` dtype | try/except over string-match — see §5 (drift) |
| **MEDIUM** | Test uses `patch("pkg._torch")` and fails | `_torch` sentinel isn't a module-level attr | add `try: import torch as _torch / except: _torch = None` at module top, or `pytest.importorskip("torch")` |
| **MEDIUM** | `patch("git.Repo")` fails with `No module named 'git'` | gitpython not a test dep | `pytest.importorskip("git")` at top of test class |
| **MEDIUM** | `patch("pkg._get_x.split") AttributeError` | module was simplified to a one-line alias; mock target no longer exists | replace stale mock-based tests with a minimal alias check (`assert get_x is new_x`) |
| **MEDIUM** | Test references fake package e.g. `'mypackage'` | test never had a fixture | `tmp_path` + `sys.path.insert` + real package creation, or skip |
| **LOW** | `Doc-Drift Nightly` cancelled | 10-minute `timeout-minutes` hit by pip resolver backtracking | bump to 25 min, or constrain sphinx version to avoid backtracking |
| **LOW** | `coverage < fail_under` even though tests all pass | aspirational threshold; real coverage is lower | lower `fail_under` to current floor; raise again when new tests land |
| **LOW** | Skill quality `§2.prefix: MANIFEST.md filename must match NN_kebab-name.md` | MANIFEST.md is a system file, not a leaf | upgrade scitex-dev to a version where the checker exempts `SYSTEM_FILES = {"MANIFEST.md"}` |
| **LOW** | Skill quality `§3.index-monolith: SKILL.md > 6144B` | bloated frontmatter description or substantive content leaked into the index | trim `description:` (auto-derived from `what`/`when`/`how` — keep those concise); promote any prose section to a leaf |
| **LOW** | Skill quality `§4.monolith: NN_foo.md > 10240B` | leaf grew unmanageably | split into two leaves with new prefixes, link both from `SKILL.md`, prefer topical split over length-based |

## 2. Triage order

Agent-mode: address CRITICAL before anything else — one CRITICAL can mask dozens of downstream failures. Then HIGH. Batch MEDIUM (they usually share a root cause). LOW is opportunistic.
