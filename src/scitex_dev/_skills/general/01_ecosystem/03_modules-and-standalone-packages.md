---
description: |
  [TOPIC] Ecosystem Modules And Standalone Packages
  [DETAILS] How to decide whether a `scitex.<module>` should stay a submodule of scitex-python or split out as a standalone `scitex-<name>` package — decision rule (zero scitex deps + heavy standalone value → standalone; everything else → module), distinct `_skills/` directories and re-export bridges, lessons from splitting scitex-scholar/scitex-browser out of the scitex monolith (path-injection beats path-coupling, never hardcode `~/.scitex/<pkg>/`, always via `PathManager`, record failure outcomes in metadata), and when to merge a standalone back. Use when starting a new scitex-* repo or evaluating a submodule for extraction.
tags: [scitex-general-ecosystem-modules-and-standalone-packages]
---

# SciTeX Standalonization Lessons

Lessons from the April 2026 scitex-scholar + scitex-browser decoupling.

## 1. Audit reverse-direction imports

When splitting a child package out of the monolith, the obvious direction
(monolith → child) is usually clean. The danger is the **reverse**: the
child's standalone repo still has `from scitex.parent.x import Y` or even
`from scitex_child` inside the *parent* repo. Both make the decoupling
a lie — the child doesn't stand alone.

```bash
# From the child repo:
grep -rn "from scitex[._ ]" src --include="*.py" | grep -v "scitex_child"

# From the parent / sibling repos:
grep -rn "scitex_child" src --include="*.py"
```

Both directions must be clean before claiming loose coupling. Add a
regression test in the child's test suite that reads its own source and
asserts the parent's namespace does not appear.

## 2. `try: from .x import Y\nexcept ImportError: Y = None` is almost always wrong

Either `x` is a required dep — make it a direct import and let the
failure propagate; or `x` is a genuine optional extra — declare it in
`[project.optional-dependencies]` and use a clear gate:

```python
try:
    import scitex_clew as _clew
except ImportError:
    _clew = None
if _clew is not None:
    _clew.hash_file(path)   # real use, real failure surface
```

Silent `X = None` downgrades produce confusing `AttributeError` at
call-time and hide dep problems.

## 3. Depend on bare `scitex`, not a per-feature extra

*(Amended 2026-08-31. This section used to say "`scitex[session]` is the
minimal monolith dep" and to point at scitex-python's extras list as
canonical. The operator ruled that the only permitted extra is `all`
([26_the-only-extra-is-all.md](26_the-only-extra-is-all.md)), so
`scitex[session]`, `scitex[sh]`, `scitex[social]` and the other 74
per-feature extras are being retired. There is no narrower extra to ask
for.)*

`@stx.session` lives in `scitex-python` itself (not `scitex-core`). If a
standalone package only needs the session decorator, depend on bare
`"scitex>=2.0.0"`. The two remaining choices are the bare package and
`"scitex[all]>=2.0.0"` — pick the bare one unless you genuinely need the
whole cascade.

**Open migration item, owned by scitex-python, not settled here.** The
`[session]` extra existed so a caller could get the decorator without the
monolith's full dependency set. Retiring it only works once whatever
`@stx.session` actually imports sits in scitex-python's `[project]
dependencies`. Until that is done, bare `scitex` may not be sufficient for
`@stx.session` on a clean install. Verify against the release you pin
rather than assuming either way.

## 4. `scitex-logging` is its own package — prefer direct

```python
# NO  — pulls the monolith transitively:
from scitex.logging import getLogger
from scitex import logging

# YES — standalone:
from scitex_logging import getLogger
import scitex_logging as logging
```

`scitex-logging` is the **ecosystem-wide errors-and-logging tier** — it owns
both `getLogger` and the canonical typed exceptions every SciTeX package
raises (`SciTeXError`, `IOError`, `SaveError`, `LoadError`, `PathError`,
`ConfigurationError`, `AuthenticationError`, `ScholarError`, `ModelError`,
`PlottingError`, …). The `Scholar*` / `BibTeX*` / `PDF*` names are
scholar-domain *types* hosted in the central errors module; that's
intentional so any package can `raise ScholarError("...")` without
depending on `scitex-scholar`. Zero heavy deps.

## 5. Path injection beats path coupling

Child packages should not import the parent's config to find their own
cache/data dirs. Inject the path as a constructor arg:

```python
# scitex-browser BEFORE (reaches into scitex-scholar):
class ChromeProfileManager:
    def __init__(self, profile_name, config=None):
        self.config = config or ScholarConfig()           # bad
        self.profile_dir = self.config.get_cache_chrome_dir(profile_name)

# AFTER (pure path injection):
class ChromeProfileManager:
    def __init__(self, profile_name, chrome_cache_dir=None):
        self.profile_dir = Path(chrome_cache_dir or _DEFAULT) / profile_name
```

Callers in the upstream package pass the resolved path explicitly. A
back-compat duck-typed `config` kwarg can bridge the transition without
reintroducing the import.

## 6. Local-state root — always via `PathManager`

Every package writes into exactly one subdirectory at each scope: `<project>/.scitex/<pkg-short>/` (project, wins) and `~/.scitex/<pkg-short>/` (user, fallback). Prefix-stripping: `scitex-scholar` → `scholar`. Full rules — filename conventions, forbidden locations, `SCITEX_DIR` relocation, migration — live in `01_ecosystem/06_dot_scitex_directory.md`.

Inside the package, never hardcode the absolute path — resolve through `PathManager`:

```python
# NO
screenshot_dir = Path.home() / ".scitex/scholar/workspace/screenshots"

# YES
screenshot_dir = (
    ScholarConfig().path_manager.get_cache_engine_dir() / "workspace" / "screenshots"
)
```

Hardcoded paths break when users set `SCITEX_DIR` or switch between project and user scope.

## 7. Scholar-specific extraction lessons — moved out

Five lessons from the scitex-scholar / scitex-browser extraction (failure-outcome metadata, artifact-count truthfulness, single-worker per publisher, Xvfb timeout handling, OpenAthens redirect semantics) were originally in this skill but are scholar-implementation lore, not general arch rules. They now live in:

- [`scitex-scholar/src/scitex_scholar/_skills/scitex-scholar/30_extraction-lessons.md`](../../../../scitex-scholar/src/scitex_scholar/_skills/scitex-scholar/30_extraction-lessons.md)

Read those if you're touching the scholar download / auth pipeline.

## 8. Every module MUST appear in `all` as its standalone package

*(Amended 2026-08-31. This section used to require a per-module extra
`<name> = ["scitex-<name>"]` in addition to `[all]`. Per-module extras are
retired — `all` is the only extra permitted
([26_the-only-extra-is-all.md](26_the-only-extra-is-all.md)) — so the rule
collapses onto `all` alone. The failure it prevents is unchanged, and gets
worse if ignored: `[all]` is now the only thing anyone types.)*

**Rule.** For every canonical ecosystem package `scitex-<name>` listed in
`scitex dev ecosystem list --json`, the umbrella's `pyproject.toml` MUST
list the standalone package itself in `all`:

```toml
[project.optional-dependencies]
all = [
    # --- paths ---------------------------------------------------
    "scitex-path[all]",              # the standalone, with its own extras
    # in-umbrella shims may add their own base deps alongside:
    "GitPython", "matplotlib",
]
```

**Why.** A bare `pip install scitex` gives a thin umbrella with shim
modules. `pip install "scitex[all]"` must actually install every
`scitex-<name>` — otherwise `stx.<name>.foo()` silently falls back to the
in-umbrella shim instead of the real standalone package. Observed failure
(2026-04-24 audit): `path = ["GitPython", "matplotlib"]` shipped GitPython
but NOT `scitex-path`, so `stx.path.find_git_root()` ran the umbrella shim
— a confusingly different codepath from the standalone. The same omission
inside `all` produces the same silent wrong codepath, for every user
instead of the few who typed `[path]`.

**TypeScript-only modules (e.g. `ui`).** Two acceptable patterns:

1. `all` still declares the pypi package so the Python re-export path
   resolves: `"scitex-ui"` appears in `all`.
2. The package is deliberately absent from `all` AND the umbrella shim
   raises a clear `ImportError` pointing the user at the standalone TS/JS
   project. Silent `None` re-exports are NOT acceptable (see §2).

**`all` completeness — the load-bearing rule.** `all` must transitively
install every canonical package: `all = [<every scitex-* pinned, each as
scitex-<x>[all]>]`. A package missing from `all` is invisible to users,
full stop — there is no second extra it could still be reachable through.

**Probe.** See `09_quality/02_checklist.md` §14.

## 9. Dead tests at collection break CI

After splitting a package, `pytest` collects ALL test files — including
ones that import modules that were removed. They fail at collection,
not at assertion, so they pollute failure counts. Delete or move them;
don't leave them hoping someone re-adds the module.

## Quick Checklist (modules vs standalone packages)

- [ ] Reverse-direction imports clean: child repo has no `from scitex.<parent>` and parent repo has no `from scitex_<child>` outside the umbrella bridge.
- [ ] No silent `try: import X\nexcept ImportError: X = None` downgrades — either declare the dep or guard at call site with a clear error message.
- [ ] If only `@stx.session` is needed, dep is bare `scitex>=X` — not `scitex[all]`, and not a per-feature extra ([26](26_the-only-extra-is-all.md); `[session]` is retired).
- [ ] All ecosystem-wide errors come from `scitex_logging` (not `scitex.logging` from the monolith).
- [ ] Path injection: child packages take cache/data dirs as constructor args; never reach into a parent's `Config` for them.
- [ ] All local-state paths resolve through `PathManager`; no hardcoded `Path.home() / ".scitex/..."`.
- [ ] Every canonical `scitex-<name>` listed by `scitex-dev ecosystem list` appears in the umbrella's `all` extra as `scitex-<name>[all]`.
- [ ] `all` transitively installs every canonical package — and is the ONLY extra declared.
- [ ] After a split, dead test files that import removed modules are deleted — `pytest` collects clean.
