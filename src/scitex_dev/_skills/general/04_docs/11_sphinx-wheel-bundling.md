---
description: |
  [TOPIC] Bundling pre-built Sphinx HTML in the wheel
  [DETAILS] How a SciTeX package ships its rendered docs for production serving — `scitex_dev.docs.get_docs`, the `docs/sphinx/_build/html` → `src/<pkg>/_sphinx_html/` convention, the GitHub Actions refresh workflow with strict `sphinx-build -W`, the manual fallback, and the hatchling `force-include` pyproject wiring the wheel needs. Use when making a package's docs appear on scitex.ai after `pip install`.
tags: [scitex-general-docs-sphinx]
---

# Bundling pre-built Sphinx HTML in the wheel (SciTeX)

## Bundling pre-built HTML in the wheel (production serving)

`scitex_dev.docs.get_docs(package=..., format="html")` resolves to a pre-built HTML directory; `scitex-cloud/apps/workspace/docs_app/` consumes that to serve per-package docs at <https://scitex.ai/apps/docs/>. For a package's docs to appear there after `pip install <pkg>`, the HTML must ship in the wheel.

Convention:

```
docs/sphinx/_build/html/        # local Sphinx output; gitignored
src/<pkg>/_sphinx_html/         # bundled in the wheel; refreshed at release
```

**Canonical refresh path: GitHub Actions** (`.github/workflows/docs.yml`).
The workflow:
1. Builds Sphinx HTML on every push/PR.
2. Every build uses `sphinx-build -W --keep-going` (warnings-as-errors
   on BOTH PRs and `main`/`develop` pushes → a warning can never land).
3. `main`/`develop` pushes additionally copy the output to
   `src/<pkg>/_sphinx_html/` and auto-commit when it changes (the
   commit-message guard, not a skip-ci token, prevents rebuild loops).

Reference workflow: `scitex-ssh/.github/workflows/docs.yml`.

**Keeping `-W` strict without whack-a-moling docstrings:** `sphinx-build
-W` is correct but bites on benign failure modes (autodoc docstring reST
noise, `_sphinx_html` commit-back GH006, missing-peer autodoc imports,
math renderer). The canonical `conf.py` + workflow defenses for each —
`suppress_warnings = ["docutils"]`, `continue-on-error` commit-back,
`autodoc_mock_imports`, `sphinx.ext.mathjax` — live in
[`04_docs/04_robust-ci.md`](04_robust-ci.md). Reference
implementation: `scitex-seizure-metrics` (PR #6).

Manual fallback (if CI is unavailable):

```bash
sphinx-build -b html docs/sphinx docs/sphinx/_build/html
rm -rf src/<pkg>/_sphinx_html
cp -rf docs/sphinx/_build/html src/<pkg>/_sphinx_html
```

`pyproject.toml` must include the directory in the wheel. Hatchling
needs `force-include` (a plain include glob is dropped because
`_sphinx_html/` lives under `src/<pkg>/` which is already a package
dir):

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/<pkg>"]

[tool.hatch.build.targets.wheel.force-include]
"src/<pkg>/_sphinx_html" = "<pkg>/_sphinx_html"
```

If a package has no Sphinx tree, omit `_sphinx_html/`; `get_docs(format="html")` returns `None` and the docs site skips that package gracefully. See [`02_package/01_project-structure.md`](../02_package/01_project-structure-root.md) for the broader project-structure context.
