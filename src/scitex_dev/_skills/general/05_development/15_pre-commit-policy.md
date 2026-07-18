---
description: |
  [TOPIC] What may and may not run in a pre-commit hook, and why a
  `language: system` hook that invokes a Python tool is banned.
  [DETAILS] Pre-commit runs FAST, BOUNDED, DETERMINISTIC checks only —
  never the test suite. Tests belong in CI, which already runs them on
  three Python versions. A commit-time test gate, if genuinely wanted,
  MUST use `language: python` + `additional_dependencies:` (isolated
  venv, explicit dep) — never `language: system` + an ambient tool.
  Enforced mechanically by audit rule PS-HOOK-001.
tags: [scitex-general-development-pre-commit-policy]
---

# Pre-commit policy

## The rule

**Pre-commit runs fast, bounded, deterministic checks. It does not run the test
suite.**

Allowed: `ruff`, `ruff-format`, `check-yaml`, `check-added-large-files`,
`trailing-whitespace`, `end-of-file-fixer`, `check-merge-conflict`,
`detect-private-key`. All of these are pinned remote hooks (`repo:
https://github.com/...` + `rev:`), which pre-commit installs into an isolated,
cached environment. They take seconds and behave identically on every machine.

Not allowed: the test suite. Tests belong in CI, which already runs the full
suite on three Python versions (3.11/3.12/3.13) on every push, in ~7-8 minutes,
in a clean environment.

## Why: the incident that produced this page (2026-07)

figrecipe shipped this hook:

```yaml
- id: pytest-testmon
  entry: python -m pytest --testmon
  language: system            # ← the defect
```

`pytest-testmon` was **not a declared dependency of figrecipe.** `language:
system` means pre-commit executes the entry against **whatever is on the ambient
`$PATH`** — so the hook resolved to a different interpreter on every machine:

| where | what actually happened | exit |
|---|---|---|
| clean host | `error: unrecognized arguments: --testmon` | 4 |
| agent container | `ModuleNotFoundError: matplotlib` | 4 |
| the one machine whose owner had hand-installed testmon | it really ran | 0/1 |

**For almost everyone the hook never ran a single test. It only blocked the
commit.** Zero `.testmondata` files existed anywhere in the fleet. The gate was
not slow — it was inert, and it failed *closed*. It had been that way for weeks.

Two more, measured the same day:

- **`davinci-resolve-mcp`** — `entry: python -m pytest tests/`, `language:
  system`, `stages: [pre-commit]`. `pytest` appears in its `pyproject.toml` ONLY
  under `[tool.pytest.ini_options]` — a *config* section, not a dependency. It
  worked purely because pytest happened to be ambient, and it took **over 14
  minutes on every commit**.
- **`pip-project-template`** — a hook named "quick smoke tests" that inherits
  `--cov-fail-under=100` from `addopts`. The smoke subset covers ~42 % of the
  package *by construction*, so `41.59 < 100` and the hook **cannot ever pass**.
  A permanently-red gate — and, because it lived in the *template*, it was copied
  into every repo seeded from it.

## The defect, precisely

**A bare command name under `language: system` is a `$PATH` lookup.** A `$PATH`
lookup for a Python tool resolves to whichever virtualenv happens to be active at
commit time. Measured, same repo, same `.pre-commit-config.yaml`, two machines:

```
host       → /home/ywatanabe/.env-3.11/bin/pytest    (py3.11, operator's venv)
container  → /opt/venv-sac/bin/pytest                (py3.12, no repo deps)
```

Two different interpreters, two different package sets, zero configuration
difference. **Nondeterministic by construction.**

Declaring the tool in `[project.optional-dependencies].dev` does **not** fix
this. Pre-commit never activates your dev venv. The declaration is a promise
about an environment nobody guaranteed is the one running the hook. (Five of the
six repos found in the fleet sweep *did* declare `pytest>=8` in a dev extra. All
five were still nondeterministic.)

**A gate that is nondeterministic across machines is worse than no gate**: it
blocks honest commits while catching nothing. That is not a hypothetical — it is
exactly what happened, fleet-wide, for weeks.

## If you genuinely want a commit-time test gate

It MUST be `language: python` + `additional_dependencies:`. Pre-commit then
builds an **isolated, cached virtualenv** and installs exactly those deps into
it. The dependency becomes explicit and the resolution becomes hermetic:

```yaml
- id: skills-python-tests
  name: skills python tests
  entry: pytest -q skills
  language: python                        # ← isolated venv, built by pre-commit
  additional_dependencies: ["pytest>=8,<9"]   # ← EXPLICIT, versioned
  pass_filenames: false
  files: "^skills/.*\\.py$"               # ← bounded: only when these change
```

(This is openclaw's hook — the in-fleet exemplar.) It must also be **bounded**:
scope it with `files:` so it runs on a slice, not the whole suite. If it takes
minutes, it does not belong in the commit path.

## What stays legitimate under `language: system`

`language: system` is fine for tools that are **not** resolved out of a Python
virtualenv:

```yaml
- entry: pnpm audit --prod --audit-level=high     # node toolchain
- entry: swiftlint --config .swiftlint.yml        # swift toolchain
- entry: ./scripts/pre-commit/run-node-tool.sh …  # explicit repo-local path
- entry: bash -c '! grep -rn "pdb.set_trace" src/'  # POSIX, always present
```

An **explicit path** is a deliberate, repo-controlled choice. A **bare name** is
the `$PATH` lottery. That is the whole distinction.

## Enforcement

Audit rule **PS-HOOK-001** (`scitex-dev ecosystem audit-project`) fires when a
`language: system` hook invokes a bare `python`/`python3` or a known third-party
Python console script (`pytest`, `mypy`, `ruff`, `black`, …). Non-Python
toolchains and explicit paths are never flagged.

```bash
scitex-dev ecosystem audit-project --path . --rule PS-HOOK-001
```

Opt-out (rare — prefer fixing the hook): put `# PS-HOOK-001: allow` anywhere in
`.pre-commit-config.yaml`.

## A warm-cache wrapper is a PRE-PUSH tool, not a pre-commit one

The core rule above is unchanged: **there is no test suite at pre-commit; tests
belong in CI.** The fix for "the commit-time test gate is slow" is not a faster
gate — it is **no gate** at commit time.

A warm-cache testmon wrapper (`scitex-dev-testmon` / `run_testmon.sh`) does have
one sanctioned home, but it is a *different gate*: the **pre-push** hook
(`scitex-dev hooks enable-pre-push`), which runs a narrow, diff-scoped,
time-bound subset before `git push` so the operator does not push → CI-red →
patch → push merry-go-round. There the wrapper earns its keep — it seed-copies a
persistent per-(repo, pyXY) `.testmondata` so a fresh release worktree runs only
impacted tests instead of cold-running the full suite. (The earlier
bare-`$PATH`/`python3` defect that made it inert has been fixed: it now pins an
absolute interpreter, and pre-push.sh Step 4 is its live caller.) That does
**not** license a commit-time test gate: keep the wrapper at pre-push, keep
pre-commit for fast/bounded/deterministic checks, and keep the heavy suite in
CI.
