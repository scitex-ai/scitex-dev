---
description: |
  [TOPIC] Ecosystem `dev` Group Completeness
  [DETAILS] The fastmcp lesson (2026-05-02), re-seated 2026-08-31 onto the PEP 735 `dev` dependency-GROUP after the only-permitted-extra-is-`all` ruling — `dev` MUST install every dependency this package's own test suite imports unconditionally, or the tests must gate with `pytest.importorskip`; the boundary is whose feature is being tested (own `src/` → include and test unconditionally; optional sibling `scitex-*` → leave out and importorskip; DECLARED sibling → import unconditionally and let a broken install go red; 3rd-party integration → pragmatic match); the symmetric pyproject pattern where an optional dep in `all` and its tests force the same dep into the `dev` group; detection via `audit-project`'s `PS-210`, which INVERTS under the new shape until it is migrated. Companion to `02_dependency-and-version-pinning.md` and `26_the-only-extra-is-all.md`. Use when a fresh `pip install -e . --group dev` hits `ModuleNotFoundError` at test collection.
tags: [scitex-general-ecosystem-dev-extras-completeness]
---

## `dev` group completeness — fastmcp lesson, 2026-05-02

**The `[dev]` extra became the `dev` group on 2026-08-31.** The operator
ruled that the only permitted extra is `all`
([26_the-only-extra-is-all.md](26_the-only-extra-is-all.md)), so `dev` and
`docs` moved to PEP 735 `[dependency-groups]`. **The lesson below did not
change.** It was never about the TOML table `dev` lived in; it is about the
gap between what a contributor's one-command install produces and what the
suite imports. Read `dev` throughout as the dependency group.

**Rule.** `dev` MUST install every dependency that this package's own test
suite imports unconditionally. The only legitimate way to leave something
out of `dev` is to also gate the tests with `pytest.importorskip(...)`.
Pick one.

The boundary is **whose feature is being tested**:

| Tested feature lives in… | `dev` does | Tests do |
|---|---|---|
| **This package's own `src/`** (e.g. `scitex-notebook`'s MCP server uses `fastmcp`) | Pull the optional 3rd-party dep in so a fresh `pip install -e . --group dev` runs the full suite. **Do NOT** `importorskip`. | Run unconditionally — the feature is yours; commit to testing it. |
| **A sibling `scitex-*` package that is an OPTIONAL peer** (cross-cascade integration test) | Leave the sibling out. Listing it pulls in heavy transitive deps, can shadow editable installs ([03_interface/03_mcp/09 lesson 4](../03_interface/03_mcp/09_lessons-and-pitfalls.md)), and re-introduces lockstep coupling. | `pytest.importorskip("scitex_<sibling>")` — exists when the sibling is around, skips cleanly when not. |
| **A sibling `scitex-*` package that is a DECLARED RUNTIME DEPENDENCY** (it is in `[project].dependencies`) | Nothing to add — `pip install -e .` already installs it. | Import it **unconditionally**. Do **NOT** `importorskip`: if a declared dependency is missing, the install is BROKEN and the suite must go RED. A skip converts a broken install into a green run. |
| **A 3rd-party dep this package merely *integrates with*** (e.g. matplotlib plot test) | Pragmatic — include if every CI matrix entry has it; skip if some dimensions deliberately exclude it. | Match the `dev` choice. |

**Two axes, not one.** The first axis is *whose feature is being tested*
(own `src/` vs sibling). The second, added 2026-08-16, is *declared vs
optional* — and it only bites inside the sibling row, which is why it went
unnoticed. "Sibling" was read as a synonym for "optional peer", but a
sibling can be a hard entry in `[project].dependencies`; `scitex-hpc`
declares `scitex-config` and `scitex-ssh` exactly that way. For those,
`importorskip` is wrong in the most expensive direction: the module is
absent only when the install is broken, and the skip reports that as green.

The test to apply is not "is it a sibling?" but **"if this import fails, is
the package still usable?"** No → import unconditionally and let the suite
go red. Yes → `importorskip`. *(Raised by scitex-hpc, card
`importorskip-gates-go-green-when-their-subject-is-absent-20260803`, which
correctly conceded the sibling-vs-own half of its own argument and kept the
half that survives.)*

**Symmetric pyproject pattern.** When a package ships an optional feature
whose dep lives in `all` (e.g. `fastmcp`, behind what used to be an `[mcp]`
extra) AND the test suite covers that feature, the `dev` group must include
the same dep:

```toml
[project.optional-dependencies]
all = [
    # --- MCP server ---------------------------------------------
    "fastmcp>=2.0",                   # production users opt in via [all]
]

[dependency-groups]
dev = [
    "pytest>=7.0", "pytest-cov>=4.0", "ruff",
    # Optional features whose tests live in the suite — repeated here
    # so a fresh `pip install -e . --group dev` runs the full suite.
    "fastmcp>=2.0",
]
```

The duplication is deliberate and it is not a smell. `all` is the *user's*
answer and `dev` is the *contributor's*; a dep that serves both audiences is
named twice. Do not try to collapse it by having `dev` depend on the `all`
extra — that reintroduces the heavy transitive install the optional-peer row
exists to avoid.

**Why this matters.** A single one-command install is the canonical
contributor-onboarding step and what every CI workflow runs
([02_package/07_github-actions.md](../02_package/07_github-actions.md)). If
`dev` is incomplete, contributors hit `ModuleNotFoundError` at
test-collection time and CI breaks on the first push that touches the
feature. The 2026-05-02 scitex-notebook MCP refactor hit this exact failure
mode on its first push to `develop`.

The command changed with the table:

```bash
pip install -e . --group dev      # needs pip >= 25.1
uv  pip install -e . --group dev  # any recent uv
```

An older pip in a CI image cannot install a dependency group at all. That is
a hard blocker for the migration, not a warning
([26 §5](26_the-only-extra-is-all.md)).

**Detection — and `PS-210` currently INVERTS.** `audit-project`'s `PS-210`
check was written against the extras shape: `_extras_index`
(`_cli/audit/_project/_check_dev_extras_complete.py`) builds its `dev` set
from `project.optional-dependencies["dev"]` and its "other extras" set from
every remaining extra, then flags any other-extra dep that `tests/` imports
unguarded and `dev` lacks.

After a package migrates, `optional-dependencies` holds only `all`: the
`dev` set is **empty** and the other-extras set is **every leaf**, so the
rule fires on essentially everything. It does not fall silent — it becomes a
false-positive storm, which is the opposite failure and looks nothing like
the one you would predict. Migrate the check to read
`[dependency-groups].dev` before migrating a package it audits.
