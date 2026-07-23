---
description: |
  [TOPIC] Ecosystem `[dev]` Extras Completeness
  [DETAILS] The fastmcp lesson (2026-05-02) — `[dev]` MUST install every dependency this package's own test suite imports unconditionally, or the tests must gate with `pytest.importorskip`; the boundary is whose feature is being tested (own `src/` → include and test unconditionally; sibling `scitex-*` → leave out and importorskip; 3rd-party integration → pragmatic match); the symmetric pyproject pattern where an optional feature extra `[X]` and its tests force the same dep into `[dev]`; detection via `audit-project`'s `PS-210`. Companion to `02_dependency-and-version-pinning.md`. Use when a fresh `pip install -e .[dev]` hits `ModuleNotFoundError` at test collection.
tags: [scitex-general-ecosystem-dev-extras-completeness]
---

## `[dev]` extras completeness — fastmcp lesson, 2026-05-02

**Rule.** `[dev]` MUST install every dependency that this package's own
test suite imports unconditionally. The only legitimate way to leave
something out of `[dev]` is to also gate the tests with
`pytest.importorskip(...)`. Pick one.

The boundary is **whose feature is being tested**:

| Tested feature lives in… | `[dev]` does | Tests do |
|---|---|---|
| **This package's own `src/`** (e.g. `scitex-notebook`'s MCP server uses `fastmcp`) | Pull the optional 3rd-party dep in so a fresh `pip install -e .[dev]` runs the full suite. **Do NOT** `importorskip`. | Run unconditionally — the feature is yours; commit to testing it. |
| **A sibling `scitex-*` package** (cross-cascade integration test) | Leave the sibling out. Listing it pulls in heavy transitive deps, can shadow editable installs ([03_interface/03_mcp/09 lesson 4](../03_interface/03_mcp/09_lessons-and-pitfalls.md)), and re-introduces lockstep coupling. | `pytest.importorskip("scitex_<sibling>")` — exists when the sibling is around, skips cleanly when not. |
| **A 3rd-party dep this package merely *integrates with*** (e.g. matplotlib plot test) | Pragmatic — include if every CI matrix entry has it; skip if some dimensions deliberately exclude it. | Match the `[dev]` choice. |

**Symmetric pyproject pattern.** When a package has an optional feature
extra `[X]` (e.g. `[mcp]`) AND the test suite covers that feature, the
`[dev]` extra must include the same dep:

```toml
[project.optional-dependencies]
mcp = ["fastmcp>=2.0"]                # production users opt in
dev = [
    "pytest>=7.0", "pytest-cov>=4.0", "ruff",
    # Optional features whose tests live in the suite — installed in
    # [dev] so a fresh `pip install -e .[dev]` runs the full suite.
    "fastmcp>=2.0",
]
```

**Why this matters.** A bare `pip install -e .[dev]` is the canonical
contributor-onboarding command and what every CI workflow runs
([02_package/07_github-actions.md](../02_package/07_github-actions.md)).
If `[dev]` is incomplete, contributors hit `ModuleNotFoundError` at
test-collection time and CI breaks on the first push that touches the
feature. The 2026-05-02 scitex-notebook MCP refactor hit this exact
failure mode on its first push to `develop`.

**Detection.** `audit-project`'s `PS-210` check flags any pyproject extra
whose declared deps are referenced unconditionally from `tests/` but
missing from `[dev]`.
