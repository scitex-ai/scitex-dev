---
name: package-src
description: `./src/<pkg>/` layout for a SciTeX *package* — the production code that ships in the wheel. Covers the one-package-per-repo rule, absolute-import discipline, the cascade-direction rule (inter-scitex package imports along the cascade are healthy; only the umbrella `scitex` should not be imported from a scitex-* package's own `src/` because it re-exports the package itself, creating a real cycle), and the public/private filename convention (`_foo.py` for private, mirrored by `tests/<pkg>/test__foo.py`).
tags: [scitex-python, scitex-general, scitex-package, project-structure, src]
---

# `./src` — pip-installable package

> Sibling leaves: [`./root`](02_package_01_project-structure-root.md) · [`./scripts`](02_package_03_project-structure-scripts.md) · [`./scripts/makefile`](02_package_04_project-structure-makefile.md) · [`./examples`](02_package_05_project-structure-examples.md) · [`./tests`](02_package_06_project-structure-tests.md)

## Layout

- The production package — everything here ships in the wheel.
- One package per repo: `<repo>/src/<package_name>/...`.

```
<repo>/
├── src/
│   └── <package_name>/
│       ├── __init__.py
│       ├── <public_module>.py
│       ├── _<private_module>.py
│       └── <subpkg>/
│           ├── __init__.py
│           └── ...
```

## Subpackage clusters — keep `src/<pkg>/` navigable

Once `src/<pkg>/` accumulates **3+ flat `.py` files sharing a common
prefix** (`_cli_*.py`, `_skills_*.py`, `_mcp_*.py`, `sync_*.py`, …),
promote them into a subpackage. A common prefix on three files is a
reliable signal that the cluster wants to be a directory.

```
# Before — flat, hard to scan
src/<pkg>/
├── _cli.py
├── _cli_audit.py
├── _cli_audit_api.py
├── _cli_skills.py
├── _cli_stats.py

# After — grouped by responsibility
src/<pkg>/
└── _cli/
    ├── __init__.py
    ├── _root.py
    ├── _audit.py
    ├── _audit_api.py
    ├── _skills.py
    └── _stats.py
```

Group **by responsibility, not blind prefix-promotion** — if the CLI
surface (`<pkg> --help`) already groups commands into Ecosystem /
Development / Documentation / Interface / Shell sections, mirror those
same categories in the source layout. The CLI grouping is your
designed-in taxonomy; the source layout should match it.

`audit-project`'s **PS108** rule flags packages where prefix-clusters
have grown past the threshold and rolls all clusters into one
violation, so you land the reorganization in a single coherent pass
rather than fixing one prefix at a time across separate PRs.

When PS108 fires alongside PS204 (orphan tests), the orphan-test
hint also tells you where each test should be moved — refactor the
src and the tests in the same change.

## Imports

- **Absolute imports**: `from <package_name>.x.y import z`.
- **Never** `from src...` and **never** relative-across-package-boundaries (`from ..other_subpkg import …` outside of the same submodule).
- Within one submodule, relative imports (`from . import x`, `from ._helper import y`) are fine and preferred.

## Inter-package dependencies

Inter-scitex package deps follow the **cascade direction** (see [01_ecosystem_01_upstream-and-downstream.md](01_ecosystem_01_upstream-and-downstream.md)):

- A downstream package importing from an upstream one is fine and common — e.g. `scitex-stats` depends on `scitex-io` for save/load helpers; `scitex-cloud` depends on `scitex-config` for path resolution.
- Pyproject must declare every such dep. `E5C5_implicit_deps` flags missing declarations.

What `src/` should **not** import is the **umbrella `scitex` package itself** — that umbrella re-exports the package, which creates a real cycle on install. Tests, scripts, and examples are free to import from the umbrella.

```python
# src/scitex_io/__init__.py — GOOD
from .config import load_config       # local
import scitex_config                  # ecosystem peer — declared in pyproject

# src/scitex_io/__init__.py — BAD
import scitex                         # umbrella; would form a cycle
```

## Public / private filename convention

A leading underscore in a filename marks the module as **private** (not part of the public API). Test files mirror this with a **double underscore** between `test` and the basename:

| Source | Test |
| :--- | :--- |
| `src/<pkg>/foo.py` (public) | `tests/<pkg>/test_foo.py` |
| `src/<pkg>/_foo.py` (private) | `tests/<pkg>/test__foo.py` |

The double-underscore visually echoes the source's leading underscore, and PS205 of `audit-project` enforces it.

`__init__.py` is exempt — it doesn't get its own test file (use `tests/<pkg>/test___init__.py` only when you have a real reason to test package-level behavior, e.g. lazy-import wiring).

## What does NOT live in `src/`

- One-off analysis pipelines or maintenance scripts → [`./scripts/`](02_package_03_project-structure-scripts.md).
- Demo files → [`./examples/`](02_package_05_project-structure-examples.md).
- Tests → [`./tests/<pkg>/`](02_package_06_project-structure-tests.md).
- External material kept verbatim → not used in scitex (no `./references/`).

## `_skills/` — packaged skill assets

If your package ships agent-facing skills, vendor them at `src/<pkg>/_skills/<pkg>/`. The bundling is enforced by `E5C9_skill_bundling` in `scitex_dev._pyproject_lint`. See `_skills/general/03_interface_04_skills/` for the skill-authoring rules.

## `_sphinx_html/` — pre-built docs (production)

If your package wants its docs served at <https://scitex.ai/apps/docs/>, the pre-built HTML must ship under `src/<pkg>/_sphinx_html/`. See [02_package_01_project-structure-root.md](02_package_01_root.md#production-served-sphinx-html--bundled-in-srcpkg_sphinx_html) for the bundle pattern, and [04_docs_02_sphinx.md](04_docs_02_sphinx.md) for the release recipe.
