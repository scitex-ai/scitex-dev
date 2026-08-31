---
description: |
  [TOPIC] The Only Permitted Extra Is `all`
  [DETAILS] Operator ruling 2026-08-31 — `[project.optional-dependencies]` may declare exactly ONE extra, `all`. Per-feature extras (`[io]`, `[db]`, `[plt]`, …) are wrong by design: a user cannot be expected to remember which extra maps to which feature, so the guidance collapses to one line — tell people `pip install "scitex[all]"` and stop. `[project] dependencies` stays minimal; `all` lists leaves as `scitex-<x>[all]` (extras propagate through a dependency spec — measured); `dev` and `docs` move to PEP 735 `[dependency-groups]`, which do NOT reach consumers' published metadata (measured). Underscore-prefixed "private" extras are INVALID, so a private extra cannot exist (measured). Records the migration cost: CI `-e ".[dev]"` / `-e ".[docs]"` installs break and need `--group` (uv, or pip >= 25.1), and scitex-dev's own `PS-210` auditor inverts into a false-positive storm. Supersedes the per-feature-extra prescriptions in 02 / 03 / 05 / 18 / 19 / 20.
tags: [scitex-general-ecosystem-the-only-extra-is-all]
---

# The Only Permitted Extra Is `[all]`

> **Operator ruling, 2026-08-31.** 「エクストラとして許されるのはオールのみ」 —
> *the only extra permitted is `all`.*

## 1. What to tell people

> 「基本的にはまぁ皆さんオール付けてくれれば大体動きますよ位かなぁ」 —
> *basically, if everyone just adds `all`, it mostly works — about that level.*

That sentence is the whole user-facing story, and it is the point of the
rule:

```bash
pip install "scitex[all]"
```

One thing to remember, and it works. READMEs, install docs, error messages
and onboarding all say exactly that and stop. There is no table of extras
to consult, because there is no table.

The mechanism below is the *how*. `scitex[all]` is the *what*, and it is
what a reader actually carries away.

## 2. The rule

> `[project.optional-dependencies]` declares **exactly one** extra, named
> `all`. No other extra may exist in any `scitex-*` package.

Target shape:

```toml
[project]
dependencies = [
    # MINIMAL. Only what the package cannot run without.
    "numpy>=1.21.0",
]

[project.optional-dependencies]
# The ONE permitted extra. Organise it with COMMENTS, not with extras.
all = [
    # --- I/O and persistence -------------------------------------
    "scitex-io[all]>=0.3.0",
    "scitex-db[all]>=0.2.0",
    # --- plotting ------------------------------------------------
    "scitex-plt[all]>=0.4.0",
]

[dependency-groups]          # PEP 735 — NOT published to consumers
dev = ["pytest>=7.0", "pytest-cov>=4.0", "ruff"]
docs = ["sphinx>=7.0", "furo"]
```

Three consequences worth stating plainly:

- **Neither `scitex-io` nor `scitex-db` has to be a hard dependency.**
  Operator, same ruling: 「IOがハードに入らなきゃいけないって言うわけでもない」
  「DBももちろんそうですね」. A leaf belongs in `dependencies` only when the
  package genuinely cannot run without it; otherwise it belongs in `all`.
- **The grouping that per-feature extras used to express becomes
  comments.** Comments cost the author nothing and cost the user nothing,
  because the user never reads them — they type `[all]`.
- **`dev` and `docs` are not extras.** They are dependency groups, and they
  are invisible to anyone installing the package.

## 3. Why per-feature extras are wrong by design

The operator's reasoning, not a re-derivation of it: specifying `[db,io]`
is 自己満足 — self-indulgence on the author's part.

- A user cannot be expected to remember which extra maps to which feature.
  The mapping lives in the author's head and in `pyproject.toml`, and
  nowhere the user is looking when they hit `ModuleNotFoundError`.
- Anyone who *can* read `pyproject.toml` to work out that saving to `.h5`
  needs `[h5]` could have installed the leaf package directly. The extra
  bought that reader nothing.
- So the extra serves neither audience. All-or-nothing is the natural,
  usable shape.

Scale of what this rule retires: `scitex-python` declares **77** extras,
**74** of them per-feature (measured 2026-08-31 from its `pyproject.toml`
— 42 hard dependencies, zero `[dependency-groups]`).

## 4. Three measured facts — cite these, do not re-derive them

Established by building probe packages on 2026-08-31.

### 4.1 An underscore-prefixed extra is INVALID — so a private extra cannot exist

A `_io`-style "private" group was proposed and does not build. A probe
package fails at build time with, verbatim:

```
Not a valid package or extra name: "_io". Names must start and end with a
letter or digit and may only contain -, _, ., and alphanumeric characters.
```

Underscores are legal *inside* a name, not leading. **Corollary, and it is
the load-bearing half:** every syntactically valid extra name is a name a
user can type after `pip install pkg[...]`. There is no such thing as an
extra that exists for the author but not for the user. An extra you declare
is an extra you have published and must support.

### 4.2 Extras propagate through a dependency spec

`all = ["scitex-io[all]"]` builds, and the wheel emits:

```
Requires-Dist: scitex-io[all]; extra == 'all'
```

So `pip install scitex[all]` pulls each leaf **with its own `all`**. One
extra at the umbrella recursively means "everything", which is why a single
extra is sufficient and why `all` must list leaves as `scitex-<x>[all]`,
never bare `scitex-<x>`.

### 4.3 PEP 735 `[dependency-groups]` is the mechanism for non-published groups

A probe with `[dependency-groups] docs=[...] dev=[...]` builds, and the
wheel's published metadata contains **only**:

```
Provides-Extra: all
```

`dev` and `docs` do **not** reach consumers. `uv pip compile --group docs`
still resolves them locally. This is what makes moving `dev`/`docs` out of
extras a strict improvement rather than a loss: contributors keep them,
users stop seeing them.

## 5. The migration cost — say it out loud

This rule breaks things that work today. Do not migrate a package without
handling all four.

| # | What breaks | Fix |
|---|---|---|
| 1 | `uv pip install --system -e ".[all,dev]"` — `scitex-python`'s pytest matrix, `pytest-matrix-on-ubuntu-py3-11-3-12-3-13.yml` line 54, with `".[dev]"` as its line-55 fallback | `uv pip install --system -e . --group dev` |
| 2 | `pip install -e ".[docs]"` — `rtd-sphinx-build-on-ubuntu-latest.yml` line 29 | `pip install -e . --group docs` |
| 3 | `--group` needs a resolver that speaks PEP 735 | `uv`, or **pip >= 25.1**. An older pip in a CI image is a hard blocker, not a warning. |
| 4 | `PS-210` (`audit-project`'s `[dev]`-completeness check) **inverts** | See below — fix the check before migrating a package it audits. |

**PS-210 inverts; it does not merely go quiet.** Read from source
(`_cli/audit/_project/_check_dev_extras_complete.py`): `_extras_index`
builds its `dev` set from `project.optional-dependencies["dev"]` and its
"other extras" set from every remaining extra. After migration
`optional-dependencies` holds only `all`, so the `dev` set is **empty**
while the other-extras set is **every leaf** — and the rule fires for each
`all` dep that any test imports unguarded. The natural expectation is that a
check reading a table that no longer exists falls silent; this one becomes a
false-positive storm instead. Silence and inversion look nothing alike, and
only one of them is what happens here.

**Ecosystem tooling assumes the old shape too**, and is unmigrated as of
this leaf: `_ecosystem/_umbrella.py` (documents "per-module extras"),
`_ecosystem/_release/pyproject_lint.py`,
`_cli/ecosystem/_cmds/_regen_umbrella.py` (regenerates
`[project.optional-dependencies].all` against per-module extras) and
`_release/rtd_onboard.py` (writes a `docs` **extra**). Migrating a package
before these move will fight the tooling.

## 6. What this supersedes

Amended in the same change; listed so nobody re-adopts a withdrawn rule
from a stale leaf:

| Leaf | Was | Now |
|---|---|---|
| [01_upstream-and-downstream.md](01_upstream-and-downstream.md) | Downstream/middle CI install `pip install -e ".[dev]"` | `pip install -e . --group dev` |
| [02_dependency-and-version-pinning.md](02_dependency-and-version-pinning.md) | "Heavy or rarely-used deps moved to **named extras** (`[imaging]`, `[scientific]`, `[mcp]`, …)"; a `scitex = [...]` optional pattern | Everything optional goes in `all`; `dev`/`docs` are groups |
| [03_modules-and-standalone-packages.md](03_modules-and-standalone-packages.md) §3, §8 | `scitex[session]` as the minimal monolith dep; "its named extra" per module | Bare `scitex>=X`; `all` is the only extra, and it must still transitively install every canonical package |
| [05_re-export.md](05_re-export.md) | "Optional peers stay OUT of `[all]`/`[dev]` … pin only in the targeted extra (`[cloud]`/`[hub]`/…)" | There is no targeted extra to park a heavy peer in; omit it from `all` until it ships |
| [18_version-pinning-rules.md](18_version-pinning-rules.md) | Runtime minima live inside a `[scitex]` extra; test minima under a `dev` extra | `all` and the `dev` group respectively |
| [19_dev-extras-completeness.md](19_dev-extras-completeness.md) | The whole leaf was built on `[dev]` being an extra | The same lesson, re-seated on the `dev` **group** — it did not stop being true |
| [20_re-export-patterns.md](20_re-export-patterns.md) | `pip install scitex[template]` install hint | `pip install scitex-template` |
| [../02_package/07_github-actions.md](../02_package/07_github-actions.md) | "install with the `[dev]` extra"; a separate `legacy = ["scitex"]` extra | `--group dev` (with the pip >= 25.1 floor); the umbrella fallback lives in `all` |
| [../03_interface/01_python-api/04_lazy-imports-and-optional-deps.md](../03_interface/01_python-api/04_lazy-imports-and-optional-deps.md) | `try_import_optional(..., extra="h5")`; "what goes in `extras_require`" | `extra="all"` always; the section is now "what goes in the `all` extra" |
| [../03_interface/03_mcp/02_server-registration.md](../03_interface/03_mcp/02_server-registration.md) + [10_audit-checklist.md](../03_interface/03_mcp/10_audit-checklist.md) | `<pkg>_not_available` hint printed `pip install scitex[<pkg>]` | `pip install scitex-<pkg>` |
| [../05_development/05_doc-surfaces.md](../05_development/05_doc-surfaces.md) | README Installation hid per-module extras (`[hdf5]`, `[parquet]`) in a `<details>` | One line, `uv pip install "<pkg>[all]"`, and nothing else |

The `[all]`-completeness rule in `03` §8 — `all` must transitively install
every canonical package — is **not** superseded. It is the load-bearing rule
now that it is the only one: a package missing from `all` is invisible to
every user, because `[all]` is the only thing anyone types.

## 7. Named, and deliberately NOT amended

These describe per-feature extras that **exist right now** in a shipped
`pyproject.toml`. Editing them to match the rule would make the docs
describe a package that does not exist yet, which is worse than a
documented lag. They are migration debt, and they are listed here so the
debt has a name rather than being rediscovered as a contradiction:

- `scitex-dev/01_installation.md`, `scitex-dev/16_docs-search.md`,
  `scitex-dev/17_test-runner.md`, `general/03_interface/02_cli/07_audit-cli.md`,
  `general/03_interface/03_mcp/08_audit-mcp-tools.md` — all document
  scitex-dev's own live extras (`[cli]`, `[mcp]`, `[dev]`, `[docs]`,
  `[cli-audit]`). Update them **in the same PR that migrates scitex-dev's
  `pyproject.toml`**, not before.
- `general/01_ecosystem/10_research-project-type.md` — a research repo is
  explicitly NOT a pip package and is carved out of the publish rules, so
  its `uv pip install -e ".[dev]"` line is out of this rule's scope. Left
  alone on purpose.
- `general/01_ecosystem/16_boundary-ports-and-producers.md` — mentions a
  `pip install <pkg>[<extra>]` hint only as a *description* of the
  optional-try-import pattern, not as a prescription of extra names.
  Harmless; left alone.

## Quick Checklist (extras)

- [ ] `[project.optional-dependencies]` declares `all` and nothing else.
- [ ] `all` lists each SciTeX leaf as `scitex-<x>[all]>=<min>`, never bare.
- [ ] `all` is organised with **comments**, not with additional extras.
- [ ] `[project] dependencies` holds only what the package cannot run without — a leaf is not hard-required merely because it is commonly used.
- [ ] `dev` and `docs` live in `[dependency-groups]`, not in extras.
- [ ] No underscore-prefixed extra anywhere — it does not build (§4.1).
- [ ] Every CI workflow installing `.[dev]` / `.[docs]` moved to `--group`, on uv or pip >= 25.1.
- [ ] Install instructions everywhere say `pip install "<pkg>[all]"` — no per-feature extra appears in any README, docstring, or `ImportError` hint.
