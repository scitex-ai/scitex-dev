---
description: |
  [TOPIC] Ecosystem Dependency And Version Pinning
  [DETAILS] Dependency hygiene and version-pinning rules across the SciTeX 3-layer cascade — what each package may depend on (upstream only, never downstream), how to declare minima (`>=X.Y` for scitex-* pkgs, exact pin only for security patches), the single-extra rule (`pip install "scitex[all]"` — `all` is the ONLY permitted extra, see `26_the-only-extra-is-all.md`; `dev`/`docs` are PEP 735 `[dependency-groups]`), coordinated release waves so downstream consumers can bump their minima immediately, detection of circular/skipping deps, and the "when you bump, bump consumers' minima" rule. Use when editing any `pyproject.toml`, planning a release wave, or auditing cross-package version drift.
tags: [scitex-general-ecosystem-dependency-and-version-pinning]
---

# Dependency Hygiene & Version Pinning

Companion to [01_ecosystem/01_upstream-and-downstream.md](01_upstream-and-downstream.md). The 3-layer cascade imposes strict rules on what each layer may depend on and how versions are pinned.

## Why minima matter — the multi-package development problem

SciTeX is 33+ packages developed **in parallel**, not in lockstep. A feature
added to `scitex-io` on Monday can be used by `scitex-writer` on Tuesday. If
`scitex-writer`'s `pyproject.toml` does NOT declare `scitex-io>=<new>`, this
happens:

```bash
$ pip install scitex-writer      # pip picks any scitex-io >= old minimum
$ python -c "from scitex_writer import foo; foo()"   # AttributeError — new API missing
```

pip cannot know that your new `scitex-writer` silently requires a new
`scitex-io` unless you spell it out. The rule:

> **Every time you import another `scitex-*` package at runtime, pin its
> minimum version (`>=X.Y.Z`) in `pyproject.toml`.**

Without this: every cross-package feature turns into a user-facing
`AttributeError`. With it: `pip install` is the single source of truth for
"which scitex combination is known to work together."

Mechanics (syntax, when to bump, ecosystem-specific layering rules)
follow below.

## Dependency Hygiene

Downstream is **standalone**, not **zero-dep**. Third-party runtime deps (numpy, matplotlib, click, …) are allowed; sibling/middle/upstream SciTeX packages are not, except via the `all` extra.

| Dep kind | Downstream | Middle | Upstream |
|----------|------------|--------|----------|
| Third-party (numpy, matplotlib, click, …) | ✅ Allowed, **keep minimal** | ✅ Allowed | ✅ Allowed |
| `scitex-dev` (shared infra) | ✅ Allowed (dev tooling / entry points) | ✅ Allowed | ✅ Allowed |
| Sibling downstream (e.g. figrecipe → scitex-writer) | ❌ Not at runtime — only inside `all` | ⚠️ Via plugin registry only | ✅ Allowed |
| Middle (`scitex-io`, `scitex-stats`, …) | ❌ Not at runtime — inside `all` only | ✅ Allowed between middle pkgs | ✅ Allowed |
| Upstream (`scitex` only — Axis 1) | ❌ **Never** | ❌ **Never** | ✅ Self |

**Axis 2 packages out of scope.** `scitex-cloud` (user-facing platform) and `scitex-orochi` / `scitex-agent-container` / `scitex-container` (dev tooling & orchestration) sit outside the library cascade — see [`01_ecosystem/01_upstream-and-downstream.md`](01_upstream-and-downstream.md) Axis 2A/2B. Library packages do **not** depend on them at runtime (the dependency arrow goes the other way: scitex-cloud *hosts* apps that use the library; scitex-orochi *manages* the cascade). When such a dependency does exist (e.g. an app shipped on scitex-cloud), it lives in the **app's** `pyproject.toml`, not the library's.

### Minimality checklist (downstream)

- [ ] Every runtime dep is actually imported in `src/`.
- [ ] No convenience deps that belong in the `dev` or `docs` **groups**.
- [ ] Heavy or rarely-used deps moved into the single `all` extra — **never** into a named per-feature extra ([26_the-only-extra-is-all.md](26_the-only-extra-is-all.md)).
- [ ] Any SciTeX-ecosystem dep is either `scitex-dev` (infra) or listed in `all`.
- [ ] `pip install <pkg>` in a clean venv produces a working package with no other `scitex-*` installed.

Good example (`figrecipe`): `matplotlib`, `numpy`, `ruamel.yaml`, `scipy`, `click`, `rich` — six tight runtime deps, everything else (Pillow, seaborn, scitex integration) in `all`.

For `dev` group completeness (the fastmcp lesson — which optional
deps `dev` must install vs `pytest.importorskip`, the symmetric
pyproject pattern, `PS-210`), see
[19_dev-extras-completeness.md](19_dev-extras-completeness.md).

## Optional Dependency Pattern

Downstream packages declare upstream features as **optional**, in the one
permitted extra, so they remain standalone.

**The only permitted extra is `all`** — operator ruling 2026-08-31,
[26_the-only-extra-is-all.md](26_the-only-extra-is-all.md). Per-feature
extras (`[scitex]`, `[io]`, `[imaging]`, `[mcp]`, …) are wrong by design: a
user cannot be expected to remember which extra maps to which feature. Tell
people `pip install "<pkg>[all]"` and stop. Organise `all` with **comments**,
not with additional extras; `dev` and `docs` are PEP 735
`[dependency-groups]`, not extras.

### `pyproject.toml`
```toml
[project.optional-dependencies]
all = [
    # --- SciTeX integration --------------------------------------
    # Extras propagate through a dependency spec, so `[all]` here pulls
    # each leaf with its own `[all]` (measured — 26 §4.2).
    "scitex[all]>=2.24.0",
]

[dependency-groups]              # NOT published to consumers (26 §4.3)
dev = ["pytest>=7.0", "ruff"]
docs = ["sphinx>=7.0"]
```

### `_AVAILABLE` flags in code
```python
try:
    import scitex as stx
    _SCITEX_AVAILABLE = True
except ImportError:
    _SCITEX_AVAILABLE = False
```

### Clear instructions when deps are missing
```python
def some_feature_requiring_scitex():
    if not _SCITEX_AVAILABLE:
        raise ImportError(
            "This feature requires scitex. "
            'Install it with: pip install "figrecipe[all]"'
        )
```

For the full **Version Pinning Rules** (lower/upper bounds, bumping
consumer minima on release, breaking-change coordinated waves, the
SciTeX-ecosystem-specific downstream/middle/upstream layering, and the
quick rule of thumb), see
[18_version-pinning-rules.md](18_version-pinning-rules.md).

## Quick Checklist (dependencies & versions)

- [ ] **Downstream**: third-party runtime deps are minimal, justified, and actually imported.
- [ ] **Downstream**: `pip install <pkg>` in a clean venv yields a working package with no other `scitex-*` installed.
- [ ] **Downstream**: tests pass with only the `dev` group installed.
- [ ] **Downstream**: every cross-package SciTeX dep lives in the `all` extra, never in bare `dependencies` and never in a per-feature extra.
- [ ] **All layers**: `[project.optional-dependencies]` declares `all` and nothing else; `dev` / `docs` are `[dependency-groups]` ([26](26_the-only-extra-is-all.md)).
- [ ] **Middle**: middle→middle deps explicit at runtime; middle→downstream lives in the `dev` group (test/integration only).
- [ ] **All layers**: every dep has a lower bound (`>=X.Y`); no speculative upper bounds.
- [ ] **All layers**: no `==` exact pins outside security patches (and even then, with a tracking issue and an `<X` cap on the next minor).
- [ ] **All layers**: any `<X` upper bound has a linked tracking issue and a follow-up to remove it.
- [ ] **Producers**: when releasing a feature consumers need, bump their minimum **only** in consumers that actually use it.
- [ ] **Producers**: breaking changes major-bump the producer and update every consumer's lower bound *and* code in one coordinated wave.
- [ ] **Axis 2**: no library package depends on `scitex-cloud` / `scitex-orochi` / `scitex-agent-container` / `scitex-container` at runtime.
