# -*- coding: utf-8 -*-
"""PS-233 -- imported runtime distributions must be declared.

This closes the gap between dependency metadata and function-local imports.
Importing a library lazily is not optional-dependency handling: when the
default runtime path reaches that function, a minimal installation still
raises ``ModuleNotFoundError``.  Tests often hide this by injecting the
library-backed callable and by running in a developer environment where the
distribution happens to be installed transitively.

The rule scans Python shipped under ``src/`` without importing it.  It ignores
stdlib, this repository's own top-level packages, relative imports,
``TYPE_CHECKING`` blocks, and imports protected by a ``try`` that catches
``ImportError``.  Unguarded imports must resolve from ``project.dependencies``;
guarded imports may instead resolve from a consumer runtime extra.

Import-root to distribution mapping is intentionally closed and deterministic.
Declared requirements contribute their known roots, while undeclared imports
are reported only when the root has a stable mapping below.  Ambiguous
namespaces such as ``google`` and roots shared by alternative distributions
such as ``cv2`` are excluded rather than guessed.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

try:
    import tomllib
except ImportError:  # pragma: no cover -- Python 3.9/3.10
    import tomli as tomllib  # type: ignore[no-redef]

from ._check_optional_deps_guarded import _import_roots_for, _strip_version

_RULE = "PS-233"

# Roots whose owning distribution is stable and unambiguous.  This is a
# correctness boundary, not an attempt to mirror all of PyPI.
_KNOWN_IMPORT_TO_DIST: dict[str, str] = {
    "PIL": "pillow",
    "anthropic": "anthropic",
    "bs4": "beautifulsoup4",
    "click": "click",
    "dateutil": "python-dateutil",
    "django": "django",
    "fastmcp": "fastmcp",
    "filelock": "filelock",
    "flask": "flask",
    "h5py": "h5py",
    "httpx": "httpx",
    "jinja2": "jinja2",
    "joblib": "joblib",
    "lightning": "pytorch-lightning",
    "matplotlib": "matplotlib",
    "mne": "mne",
    "msgpack": "msgpack",
    "networkx": "networkx",
    "newb": "newb",
    "numpy": "numpy",
    "openai": "openai",
    "optuna": "optuna",
    "packaging": "packaging",
    "pandas": "pandas",
    "platformdirs": "platformdirs",
    "psutil": "psutil",
    "psycopg": "psycopg",
    "pydantic": "pydantic",
    "pytest": "pytest",
    "requests": "requests",
    "rich": "rich",
    "scipy": "scipy",
    "skimage": "scikit-image",
    "sklearn": "scikit-learn",
    "sqlalchemy": "sqlalchemy",
    "tenacity": "tenacity",
    "textual": "textual",
    "tomlkit": "tomlkit",
    "torch": "torch",
    "tqdm": "tqdm",
    "typing_extensions": "typing-extensions",
    "umap": "umap-learn",
    "uvicorn": "uvicorn",
    "yaml": "pyyaml",
    "zarr": "zarr",
}

_NON_RUNTIME_EXTRAS = frozenset({"dev", "test", "tests", "doc", "docs"})
_NORM_RE = re.compile(r"[-_.]+")


def _norm_dist(name: str) -> str:
    return _NORM_RE.sub("-", name).lower()


def _requirement_name(spec: str) -> str:
    """Return a normalized distribution name from a PEP 508 requirement."""
    return _norm_dist(_strip_version(spec))


def _declared_roots(specs: list[str]) -> dict[str, str]:
    """Map import roots to normalized distributions declared by *specs*."""
    out: dict[str, str] = {}
    for spec in specs:
        dist = _requirement_name(spec)
        if not dist:
            continue
        for root in _import_roots_for(dist):
            out.setdefault(root, dist)
        # A curated reverse mapping can be more precise than the shared
        # dist-to-root table (notably psycopg and typing-extensions).
        for root, owner in _KNOWN_IMPORT_TO_DIST.items():
            if _norm_dist(owner) == dist:
                out.setdefault(root, dist)
    return out


def _own_roots(src_root: Path) -> set[str]:
    """Top-level modules/packages provided by this source tree."""
    roots: set[str] = set()
    for child in src_root.iterdir():
        # PEP 420 namespace packages intentionally have no __init__.py.
        if child.is_dir() and child.name.isidentifier():
            roots.add(child.name)
        elif child.is_file() and child.suffix == ".py":
            roots.add(child.stem)
    return roots


def _type_checking_aliases(tree: ast.Module) -> tuple[set[str], set[str]]:
    names = {"TYPE_CHECKING"}
    modules = {"typing"}
    for stmt in tree.body:
        if isinstance(stmt, ast.ImportFrom) and stmt.module == "typing":
            for alias in stmt.names:
                if alias.name == "TYPE_CHECKING":
                    names.add(alias.asname or alias.name)
        elif isinstance(stmt, ast.Import):
            for alias in stmt.names:
                if alias.name == "typing":
                    modules.add(alias.asname or alias.name)
    return names, modules


def _is_type_checking_test(
    node: ast.AST, names: set[str], modules: set[str]
) -> bool:
    if isinstance(node, ast.Name):
        return node.id in names
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "TYPE_CHECKING"
        and isinstance(node.value, ast.Name)
        and node.value.id in modules
    )


def _catches_import_error(node: ast.Try) -> bool:
    for handler in node.handlers:
        exc = handler.type
        if exc is None:
            return True
        candidates = list(exc.elts) if isinstance(exc, ast.Tuple) else [exc]
        for candidate in candidates:
            name = None
            if isinstance(candidate, ast.Name):
                name = candidate.id
            elif isinstance(candidate, ast.Attribute):
                name = candidate.attr
            if name in {"ImportError", "ModuleNotFoundError", "Exception"}:
                return True
    return False


class _RuntimeImportVisitor(ast.NodeVisitor):
    def __init__(self, tree: ast.Module) -> None:
        self.type_names, self.type_modules = _type_checking_aliases(tree)
        self.guarded = 0
        self.found: list[tuple[str, int, str, bool]] = []

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        for alias in node.names:
            root = alias.name.split(".", 1)[0]
            self.found.append(
                (root, node.lineno, f"import {alias.name}", bool(self.guarded))
            )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        if node.level:
            return
        module = node.module or ""
        if module:
            root = module.split(".", 1)[0]
            self.found.append(
                (root, node.lineno, f"from {module} import ...", bool(self.guarded))
            )

    def _visit_deferred_body(self, node: ast.AST) -> None:
        """Visit a function body without inheriting a definition-time guard."""
        previous = self.guarded
        self.guarded = 0
        for stmt in getattr(node, "body", ()):
            self.visit(stmt)
        self.guarded = previous

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._visit_deferred_body(node)

    def visit_AsyncFunctionDef(  # noqa: N802
        self, node: ast.AsyncFunctionDef
    ) -> None:
        self._visit_deferred_body(node)

    def visit_If(self, node: ast.If) -> None:  # noqa: N802
        if _is_type_checking_test(node.test, self.type_names, self.type_modules):
            for stmt in node.orelse:
                self.visit(stmt)
            return
        if isinstance(node.test, ast.Constant) and node.test.value is False:
            for stmt in node.orelse:
                self.visit(stmt)
            return
        self.generic_visit(node)

    def visit_Try(self, node: ast.Try) -> None:  # noqa: N802
        guarded_here = _catches_import_error(node)
        if guarded_here:
            self.guarded += 1
        for stmt in node.body:
            self.visit(stmt)
        if guarded_here:
            self.guarded -= 1
        # Handler imports are fallback requirements, not protected by the
        # handler they live in. `else` and `finally` likewise always need the
        # surrounding guard state.
        for handler in node.handlers:
            for stmt in handler.body:
                self.visit(stmt)
        for stmt in (*node.orelse, *node.finalbody):
            self.visit(stmt)


def _known_distribution(root: str) -> str | None:
    if root.startswith("scitex_") and len(root) > len("scitex_"):
        return root.replace("_", "-")
    return _KNOWN_IMPORT_TO_DIST.get(root)


def _iter_source_files(src_root: Path):
    for path in sorted(src_root.rglob("*.py")):
        excluded = {"__pycache__", ".venv", "venv", "build", "dist"}
        if not any(part in excluded for part in path.parts):
            yield path


def check_ps233_runtime_dependencies(
    repo: Path,
    distribution: str,
    violation_cls: type,
    out: list,
) -> None:
    """Append findings for deterministically mapped undeclared runtime imports."""
    pyproject = repo / "pyproject.toml"
    src_root = repo / "src"
    if not pyproject.is_file() or not src_root.is_dir():
        return
    try:
        meta = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return

    project = meta.get("project", {}) or {}
    core_roots = _declared_roots(project.get("dependencies", []) or [])
    optional_roots: dict[str, tuple[str, str]] = {}
    extras = project.get("optional-dependencies", {}) or {}
    for extra in sorted(extras):
        if extra in _NON_RUNTIME_EXTRAS:
            continue
        for root, dist in _declared_roots(extras[extra] or []).items():
            optional_roots.setdefault(root, (extra, dist))

    ignored = set(getattr(sys, "stdlib_module_names", ())) | {"__future__"}
    ignored |= _own_roots(src_root)

    for source in _iter_source_files(src_root):
        try:
            tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        visitor = _RuntimeImportVisitor(tree)
        visitor.visit(tree)
        for root, lineno, statement, guarded in visitor.found:
            if root in ignored or root in core_roots:
                continue
            optional = optional_roots.get(root)
            expected = _known_distribution(root)
            if optional is None and expected is None:
                continue  # ambiguous/unknown mapping: do not guess
            if optional is not None and guarded:
                continue

            rel = source.relative_to(repo)
            if optional is not None:
                extra, dist = optional
                remedy = (
                    f"`{dist}` is declared only in optional extra `[{extra}]`, "
                    "but this import is unguarded. Move it to "
                    "`[project.dependencies]`, or guard the import with "
                    "`try/except ImportError` if the capability is genuinely optional."
                )
            else:
                dist = _norm_dist(expected or root)
                target = (
                    "a consumer runtime extra (with `try/except ImportError`)"
                    if guarded
                    else "`[project.dependencies]`"
                )
                remedy = f"`{dist}` is undeclared; add it to {target}."
            out.append(
                violation_cls(
                    _RULE,
                    f"{distribution}: {rel}:{lineno}",
                    f"`{statement}` is a runtime import. {remedy} "
                    "A developer/test environment may provide it transitively, "
                    "which does not make a fresh installation complete.",
                )
            )


RUNTIME_DEPENDENCY_RULES: list[tuple[str, str, str, str, str]] = [
    (
        _RULE,
        "§3",
        "shippable source imports a deterministically mapped runtime distribution "
        "that is missing from the dependency bucket required by its guard shape",
        "E",
        "runtime-import-dependency-undeclared",
    )
]


__all__ = ["RUNTIME_DEPENDENCY_RULES", "check_ps233_runtime_dependencies"]
