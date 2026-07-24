---
description: |
  [TOPIC] Package Src — bundling non-Python assets in the wheel
  [DETAILS] Where container recipes (Dockerfiles, Apptainer `.def`), Jinja2 templates, schema YAML, and any other non-Python asset the package reads at runtime must live — under `src/<pkg>/<asset-dir>/`, never at the repo root, so `pip install` actually ships them. Covers the repo-root anti-layout, the in-package layout auto-packaged by hatch, the `__file__`-relative resolution pattern that survives editable installs and `$SCITEX_DIR` relocation, the built-artifacts-are-user-state distinction, and the proposed audit grep. Companion to [02_project-structure-src.md](02_project-structure-src.md).
tags: [scitex-general-package-project-structure-src]
---

# `src/<pkg>/` — non-Python assets bundle in the wheel

> Parent leaf: [`./src`](02_project-structure-src.md).

## `containers/`, `templates/`, and other non-Python assets — bundle in the wheel

If your package ships container recipes (Dockerfiles, Apptainer
`.def` files), Jinja2 templates, schema YAML, or any other non-Python
asset that the package's own code reads at runtime, vendor it under
`src/<pkg>/<asset-dir>/` — never at the **repo root** (`./containers/`,
`./templates/`).

Repo-root layout:

```
❌ <repo>/containers/apptainer-base.def
❌ <repo>/templates/<thing>.j2
```

is invisible to `pip install`. Users without the repo (the typical
pip-only consumer) get the CLI but no recipes; commands like
`<pkg> image build` fail at runtime with "recipe not found".

In-package layout:

```
✓ src/<pkg>/containers/apptainer-base.def
✓ src/<pkg>/templates/<thing>.j2
```

is automatically packaged by `hatch.build.targets.wheel` (and the
equivalent for setuptools / poetry) when `packages = ["src/<pkg>"]`.
Verify with:

```bash
python -m build --wheel
unzip -l dist/<pkg>-*.whl | grep <asset-dir>
```

The package's runtime code resolves these via `__file__`-relative
paths:

```python
_RECIPES_DIR = Path(__file__).resolve().parent / "containers"
```

This survives `pip install` (the wheel ships into site-packages),
editable installs (`pip install -e .`), and `$SCITEX_DIR` relocation
(it's package-relative, not user-state-relative).

**Built artifacts** (SIFs, sandboxes, generated outputs) are user
state — they belong under `~/.scitex/<pkg-short>/runtime/<asset-dir>/`,
not in the wheel. See `01_ecosystem/06_dot_scitex_directory.md` §4b.

Audit (proposed PS code): grep for `<repo>/containers/` /
`<repo>/templates/` and flag if the package's own code reads them
(except for setup-time manifests like `pyproject.toml`).
