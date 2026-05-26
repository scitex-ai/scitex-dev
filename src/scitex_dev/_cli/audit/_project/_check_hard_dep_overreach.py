# -*- coding: utf-8 -*-
"""PS-149 — hard-dep overreach (heavy lib declared HARD, used feature-only).

Inverse / sibling of PS-148. Where PS-148 catches a lib declared *optional*
but imported *unguarded* in ``src/`` (minimal install breaks), PS-149 catches
the opposite mistake:

  A peer lists a heavy / niche integration lib under HARD
  ``[project.dependencies]`` — forcing every minimal install to pull it —
  yet the lib is imported ONLY in a feature / non-core part of ``src/``
  (never the public ``__init__`` surface, never the CLI entry, never the
  MCP-server entry). Such a dep should live in
  ``[project.optional-dependencies]`` (two-bucket convention: bare =
  minimal, ``[all]`` = batteries-included) and its import sites should be
  guarded with ``try_import_optional``.

Symptom this prevents:

  ``pip install <peer>`` over-pulls torch / tensorflow / figrecipe /
  scitex-app; container & sandbox builds bloat; the ecosystem dependency
  graph gets denser than it has to be — all so a feature most users never
  touch can ``from figrecipe import ...`` at module top of one helper.

Decision rule the auditor enforces (deliberately conservative — false
positives erode trust, so when in doubt we do NOT flag):

  For each lib declared in ``[project.dependencies]``:
    1. It must be in the curated ``_HEAVY_DISTS`` set (heavy / niche
       integration libs). Light, ubiquitous libs (numpy, requests, click,
       rich, pyyaml, …) are never flagged.
    2. It must NOT be in ``_NEVER_FLAG`` — the framework / foundational
       deps a package's PUBLIC surface legitimately needs as HARD
       (click, fastmcp, mcp, fastapi, uvicorn, starlette, scitex-dev,
       scitex-config). A CLI that cannot import its own framework is
       broken; an MCP server that cannot import ``fastmcp`` is broken.
       This is the PS-148-flavour-2 finding made explicit.
    3. It must be imported SOMEWHERE in ``src/`` (a HARD dep that is never
       imported at all is a *dead dep* — a different rule, out of scope).
    4. Every one of its import sites must be in a NON-CORE module — i.e.
       NOT ``<pkg>/__init__.py`` (public API), NOT under the CLI entry
       (``_cli/`` / ``cli/`` / ``_cli.py`` / ``cli.py``), NOT under the
       MCP-server entry (``_mcp/`` / ``mcp/`` / ``_mcp_server.py`` /
       ``mcp_server.py``). If even ONE import is in a core surface, the
       dep is genuinely needed there → do NOT flag.

When 1–4 all hold → PS-149 (severity W during adoption).

Why core-surface anchoring is the safety valve
-----------------------------------------------

The whole point of the nuance is that "heavy" alone is not enough to
demote a dep. ``figrecipe`` is heavy, but if a package's public
``__init__`` re-exports a figrecipe-backed API, it is a core dep and must
stay HARD. Only when the heavy lib is confined to feature modules
(plot helpers, integration shims, optional analysis paths) is it safe to
say "this should have been optional."

Heuristic notes
---------------

- pyproject is read for the HARD dep list only — the package is never
  imported, so the rule is safe on broken trees.
- Distribution name → import root mapping reuses the PS-148 table so the
  two rules agree on spellings (``scikit-learn`` → ``sklearn``, …). Both
  the mapped root AND the naive ``replace("-", "_")`` form count as a hit.
- Module-level AND function/class-scoped imports both count as "used"
  here (unlike PS-148): even a lazy import inside a feature module proves
  the dep is feature-only, which is exactly the signal we want.
- ``examples/`` / ``docs/`` / ``_skills/`` / ``migrations`` / ``_dev`` /
  ``.claude`` subtrees are skipped — not part of the importable package.
- ``_demo_*`` / ``demo_*`` files are skipped (runnable demos, not library
  surface).
"""

from __future__ import annotations

import ast
from pathlib import Path

try:
    import tomllib  # 3.11+
except ImportError:  # pragma: no cover — 3.10 path
    import tomli as tomllib  # type: ignore[no-redef]

from ._check_optional_deps_guarded import _import_roots_for, _strip_version

# Heavy / niche integration libs. A HARD dep is a *candidate* for overreach
# only if it appears here. Curated from the FUTURE spec examples + the
# "heavy" heuristic in
# `_skills/general/01_ecosystem/02_dependency-and-version-pinning.md`
# (multi-GB / native-build / large-transitive / scitex-app-class surface).
# Keyed by lowercased distribution name (hyphens preserved).
_HEAVY_DISTS: frozenset[str] = frozenset(
    {
        # Deep-learning / native multi-GB
        "torch",
        "pytorch",
        "torchvision",
        "torchaudio",
        "tensorflow",
        "tensorflow-cpu",
        "jax",
        "jaxlib",
        "transformers",
        "pytorch-lightning",
        "lightning",
        "onnx",
        "onnxruntime",
        # Heavy classical-ML / vector / search
        "scikit-learn",
        "scikit-image",
        "xgboost",
        "lightgbm",
        "catboost",
        "faiss-cpu",
        "faiss-gpu",
        "umap-learn",
        "hdbscan",
        "optuna",
        # Vision / media (native libs)
        "opencv-python",
        "opencv-python-headless",
        "pillow",
        "moviepy",
        "imageio",
        # Plotting / dashboards (large transitive)
        "figrecipe",
        "plotly",
        "bokeh",
        "seaborn",
        "dash",
        # Heavy scitex peers (large surface + transitive matplotlib/figrecipe)
        "scitex-app",
        "scitex-scholar",
        "scitex-hub",
        # Web automation (browser binaries)
        "playwright",
        "selenium",
        # Big data / array engines
        "dask",
        "polars",
        "pyarrow",
        "xarray",
        "zarr",
        "vaex",
        # Domain-specific heavy
        "mne",
        "nilearn",
        "biopython",
        "rdkit",
        "astropy",
    }
)

# Framework / foundational deps a package's PUBLIC surface legitimately
# needs as HARD. NEVER flag these even if they happen to be "heavy-ish".
# A CLI that can't import click, or an MCP server that can't import
# fastmcp, is broken — see PS-148 flavour-2 / the convention in
# `01_ecosystem/02_dependency-and-version-pinning.md`.
_NEVER_FLAG: frozenset[str] = frozenset(
    {
        "click",
        "typer",
        "fastmcp",
        "mcp",
        "fastapi",
        "uvicorn",
        "starlette",
        "pydantic",
        "scitex-dev",
        "scitex-config",
        "scitex-logging",
    }
)


def _heavy_hard_dist_roots(meta: dict) -> dict[str, str]:
    """Map each candidate import-root → distribution name, for HARD heavy deps.

    Only ``[project.dependencies]`` entries that are in ``_HEAVY_DISTS`` and
    NOT in ``_NEVER_FLAG``. When two dists share a root the first wins
    (deterministic via sorted iteration).
    """
    project = meta.get("project", {}) or {}
    hard = project.get("dependencies", []) or []
    out: dict[str, str] = {}
    for spec in sorted(hard):
        dist = _strip_version(spec)
        if not dist:
            continue
        if dist in _NEVER_FLAG:
            continue
        if dist not in _HEAVY_DISTS:
            continue
        for root in _import_roots_for(dist):
            out.setdefault(root, dist)
    return out


def _is_core_surface(rel_parts: tuple[str, ...]) -> bool:
    """True if the module path is part of the package's CORE public surface.

    Core surfaces (a heavy dep imported HERE is genuinely needed → do not
    flag):

    - ``__init__.py`` at any depth (public API / re-export shim).
    - The CLI entry: a path segment ``_cli`` / ``cli`` (dir form) or a file
      ``_cli.py`` / ``cli.py``.
    - The MCP-server entry: a path segment ``_mcp`` / ``mcp`` (dir form) or
      a file ``_mcp_server.py`` / ``mcp_server.py`` / ``_mcp.py`` /
      ``mcp.py``.
    """
    if not rel_parts:
        return False
    fname = rel_parts[-1]
    if fname == "__init__.py":
        return True
    dir_segs = set(rel_parts[:-1])
    if dir_segs & {"_cli", "cli", "_mcp", "mcp"}:
        return True
    if fname in (
        "_cli.py",
        "cli.py",
        "_mcp_server.py",
        "mcp_server.py",
        "_mcp.py",
        "mcp.py",
    ):
        return True
    return False


def _imports_in_module(tree: ast.Module, roots: dict[str, str]) -> set[str]:
    """Return the set of import-roots from ``roots`` imported anywhere in tree.

    Walks the WHOLE tree (module-level AND function/class-scoped) — for this
    rule a lazy import inside a feature module still proves feature-only use.
    Relative imports are first-party and ignored.
    """
    hits: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if root in roots:
                    hits.add(root)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                continue
            mod = node.module or ""
            root = mod.split(".", 1)[0] if mod else ""
            if root in roots:
                hits.add(root)
    return hits


_SKIP_SEGMENTS = frozenset(
    {
        "__pycache__",
        "build",
        "dist",
        ".tox",
        "site-packages",
        ".venv",
        "venv",
        "examples",
        "docs",
        "_dev",
        ".claude",
        "_skills",
        "migrations",
    }
)


def check_ps149_hard_dep_overreach(
    repo: Path,
    distribution: str,
    violation_cls: type,
    out: list,
) -> None:
    """Append PS-149 violations for heavy HARD deps used feature-only in ``src/``.

    Parameters
    ----------
    repo : Path
        Repository root (dir containing ``pyproject.toml`` and ``src/``).
    distribution : str
        Distribution name, e.g. ``"scitex-stats"``.
    violation_cls : type
        The auditor's ``Violation`` dataclass ``(rule, where, detail)``.
    out : list
        Violations are appended in place (project-auditor convention).
    """
    import_name = distribution.replace("-", "_")

    pp = repo / "pyproject.toml"
    if not pp.is_file():
        return
    try:
        meta = tomllib.loads(pp.read_text(encoding="utf-8"))
    except Exception:
        return

    roots = _heavy_hard_dist_roots(meta)
    if not roots:
        return

    src_root = repo / "src"
    scan_root = src_root if src_root.is_dir() else (repo / import_name)
    if not scan_root.is_dir():
        return

    # For each candidate root, track: was it imported at all? was it ever
    # imported in a core surface?
    used_anywhere: set[str] = set()
    used_in_core: set[str] = set()
    feature_site: dict[str, str] = {}  # root -> first feature-module rel path

    for py_file in sorted(scan_root.rglob("*.py")):
        if any(seg in py_file.parts for seg in _SKIP_SEGMENTS):
            continue
        if py_file.name.startswith("_demo_") or py_file.name.startswith("demo_"):
            continue
        try:
            text = py_file.read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            tree = ast.parse(text, filename=str(py_file))
        except SyntaxError:
            continue
        if not isinstance(tree, ast.Module):
            continue
        hits = _imports_in_module(tree, roots)
        if not hits:
            continue
        try:
            rel = py_file.relative_to(repo)
        except ValueError:
            rel = py_file
        is_core = _is_core_surface(py_file.relative_to(scan_root).parts)
        for root in hits:
            used_anywhere.add(root)
            if is_core:
                used_in_core.add(root)
            elif root not in feature_site:
                feature_site[root] = str(rel)

    for root, dist in sorted(roots.items()):
        # Flag only when: imported somewhere, but NEVER in a core surface.
        if root not in used_anywhere:
            continue  # dead dep — out of scope (different rule)
        if root in used_in_core:
            continue  # genuinely needed by the public/CLI/MCP surface — keep HARD
        site = feature_site.get(root, "?")
        out.append(
            violation_cls(
                "PS-149",
                f"{distribution}: {site}",
                (
                    f"`{dist}` is a heavy/niche lib declared HARD via "
                    f"`[project.dependencies]` but imported ONLY in feature "
                    f"module(s) (e.g. `{site}`) — never the public "
                    f"`__init__`, CLI, or MCP-server surface. Every minimal "
                    f"`pip install {distribution}` over-pulls it. Move `{dist}` "
                    f"to `[project.optional-dependencies]` (two-bucket: bare = "
                    f"minimal, `[all]` = batteries-included) and guard each "
                    f'import with `try_import_optional("...", pkg="{distribution}")`. '
                    f"Inverse of PS-148. See _skills/general/"
                    f"01_ecosystem/02_dependency-and-version-pinning.md and "
                    f"03_interface/01_python-api/"
                    f"04_lazy-imports-and-optional-deps.md."
                ),
            )
        )


# EOF
