#!/usr/bin/env python3
# Timestamp: 2026-04-27
# File: scitex_dev/_pypi_deps.py

"""Audit declared runtime dependencies against actual imports.

A package can build, upload, and pass its own tests with all the wrong
``pyproject.toml`` dependencies. The bug only shows up when a fresh user
runs ``pip install <pkg>`` in a clean venv. This module catches that gap
locally before publish.

Two checks:

1. **External imports must be declared.** If `src/<pkg>/foo.py` does
   ``import requests``, then ``requests`` must appear in the
   ``[project].dependencies`` list (or in an optional extra).
2. **Scitex peer packages need version pins.** If ``scitex_decorators`` is
   imported, then ``scitex-decorators>=X.Y.Z`` (with a minimum version, not
   bare ``scitex-decorators``) must be declared. This prevents the resolver
   from picking an old release that lacks a needed feature.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

# Stdlib module names we should never flag as missing deps. Conservative: we
# include only the ones that show up in the SciTeX ecosystem rather than
# every stdlib module.
# Names that look like imports but should never be flagged as missing deps:
# - The umbrella ``scitex`` package (always optional, lazy-imported in
#   peer packages).
# - ``cProfile`` / ``cprofile`` (stdlib, lowercase variant).
# - ``git`` (when imported via ``GitPython``, the dist name doesn't match).
_NEVER_FLAG = {"scitex", "cprofile", "cprofile_", "utils"}

_STDLIB = {
    "__future__",
    "abc",
    "argparse",
    "array",
    "ast",
    "asyncio",
    "atexit",
    "base64",
    "binascii",
    "bisect",
    "builtins",
    "bz2",
    "calendar",
    "collections",
    "concurrent",
    "configparser",
    "contextlib",
    "copy",
    "copyreg",
    "csv",
    "ctypes",
    "dataclasses",
    "datetime",
    "decimal",
    "difflib",
    "dis",
    "doctest",
    "email",
    "encodings",
    "enum",
    "errno",
    "fcntl",
    "fnmatch",
    "functools",
    "gc",
    "genericpath",
    "getopt",
    "getpass",
    "gettext",
    "glob",
    "graphlib",
    "gzip",
    "hashlib",
    "heapq",
    "hmac",
    "html",
    "http",
    "importlib",
    "importlib_metadata",
    "inspect",
    "io",
    "ipaddress",
    "itertools",
    "json",
    "keyword",
    "linecache",
    "locale",
    "logging",
    "lzma",
    "math",
    "mimetypes",
    "multiprocessing",
    "netrc",
    "ntpath",
    "numbers",
    "operator",
    "os",
    "pathlib",
    "pdb",
    "pickle",
    "pkgutil",
    "platform",
    "plistlib",
    "posixpath",
    "pprint",
    "profile",
    "pstats",
    "pwd",
    "queue",
    "quopri",
    "random",
    "re",
    "readline",
    "reprlib",
    "resource",
    "runpy",
    "secrets",
    "select",
    "shelve",
    "shlex",
    "shutil",
    "signal",
    "site",
    "smtplib",
    "socket",
    "sqlite3",
    "ssl",
    "stat",
    "statistics",
    "string",
    "struct",
    "subprocess",
    "sys",
    "sysconfig",
    "syslog",
    "tarfile",
    "telnetlib",
    "tempfile",
    "termios",
    "test",
    "textwrap",
    "threading",
    "time",
    "timeit",
    "tkinter",
    "token",
    "tokenize",
    "trace",
    "traceback",
    "tracemalloc",
    "tty",
    "turtle",
    "types",
    "typing",
    "unittest",
    "unicodedata",
    "urllib",
    "uuid",
    "venv",
    "warnings",
    "weakref",
    "webbrowser",
    "wsgiref",
    "xml",
    "xmlrpc",
    "zipfile",
    "zipimport",
    "zlib",
    "zoneinfo",
}

# Map import names → PyPI distribution names where they differ.
_IMPORT_TO_DIST = {
    "cv2": "opencv-python",
    "PIL": "Pillow",
    "yaml": "PyYAML",
    "bs4": "beautifulsoup4",
    "sklearn": "scikit-learn",
    "google": "google-genai",
    "matplotlib": "matplotlib",
    "scipy": "scipy",
    "git": "GitPython",
    "docx": "python-docx",
}


@dataclass
class DepAuditReport:
    """Result of comparing imports vs declared deps."""

    package_dir: Path
    declared_runtime: set[str] = field(default_factory=set)
    declared_optional: set[str] = field(default_factory=set)
    imported_external: set[str] = field(default_factory=set)
    imported_scitex_peers: set[str] = field(default_factory=set)
    missing_external: set[str] = field(default_factory=set)
    missing_scitex_peers: set[str] = field(default_factory=set)
    scitex_peers_without_min_version: set[str] = field(default_factory=set)

    @property
    def is_clean(self) -> bool:
        return not (
            self.missing_external
            or self.missing_scitex_peers
            or self.scitex_peers_without_min_version
        )

    def __str__(self) -> str:
        lines = [f"DepAuditReport({self.package_dir.name})"]
        if self.is_clean:
            lines.append("  ✓ all dependencies declared correctly")
            return "\n".join(lines)
        if self.missing_external:
            lines.append(f"  ✗ missing external deps: {sorted(self.missing_external)}")
        if self.missing_scitex_peers:
            lines.append(
                f"  ✗ missing scitex peer deps: {sorted(self.missing_scitex_peers)}"
            )
        if self.scitex_peers_without_min_version:
            lines.append(
                f"  ⚠ scitex peers without min version: "
                f"{sorted(self.scitex_peers_without_min_version)}"
            )
        return "\n".join(lines)


def _find_src_dir(package_dir: Path) -> Path | None:
    """Return the package's source directory under ``src/<name>/``.

    Falls back to scanning for any ``src/<name>/__init__.py``.
    """
    src = package_dir / "src"
    if not src.is_dir():
        return None
    candidates = [
        d for d in src.iterdir() if d.is_dir() and (d / "__init__.py").is_file()
    ]
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        return None
    # Prefer one matching the package dir name (with - → _).
    expect = package_dir.name.replace("-", "_")
    for c in candidates:
        if c.name == expect:
            return c
    return candidates[0]


def _walk_imports(src_dir: Path) -> set[str]:
    """Return module-level, non-try-wrapped imports under `src_dir/**/*.py`.

    Excludes:
    - imports inside ``try`` / ``except ImportError`` blocks (optional deps)
    - imports inside function or class bodies (lazy / runtime-only)
    - imports inside ``if __name__ == '__main__'`` blocks (example scripts)
    - relative imports (intra-package)

    Why: an audit that flags every import — including
    ``try: import torch except ImportError: ...`` — produces noise. The
    point is to catch deps that *will* break ``import <pkg>`` in a fresh
    venv. Optional/lazy imports won't.
    """
    found: set[str] = set()
    for py in src_dir.rglob("*.py"):
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        except SyntaxError:
            continue
        # Walk only the top-level body of each module, skipping Try blocks
        # and __main__ guards.
        _collect_top_level_imports(tree.body, found, in_try=False)
    return found


def _collect_top_level_imports(
    body: list,
    found: set[str],
    in_try: bool,
) -> None:
    """Recursively collect imports from a list of statements."""
    for node in body:
        if isinstance(node, ast.Try):
            # Imports inside a Try block are optional (catches ImportError).
            _collect_top_level_imports(node.body, found, in_try=True)
            for handler in node.handlers:
                _collect_top_level_imports(handler.body, found, in_try=True)
            _collect_top_level_imports(node.orelse, found, in_try=True)
            _collect_top_level_imports(node.finalbody, found, in_try=True)
            continue
        if isinstance(node, ast.If):
            # Skip ``if __name__ == "__main__":`` blocks.
            test = node.test
            is_main_guard = (
                isinstance(test, ast.Compare)
                and isinstance(test.left, ast.Name)
                and test.left.id == "__name__"
                and len(test.comparators) == 1
                and isinstance(test.comparators[0], ast.Constant)
                and test.comparators[0].value == "__main__"
            )
            if is_main_guard:
                continue
            # Other ``if`` blocks at module top level are still mandatory.
            _collect_top_level_imports(node.body, found, in_try=in_try)
            _collect_top_level_imports(node.orelse, found, in_try=in_try)
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            # Imports inside functions/classes are lazy by definition.
            continue
        if isinstance(node, ast.Import) and not in_try:
            for alias in node.names:
                found.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and not in_try:
            if node.level > 0:
                continue
            if node.module:
                found.add(node.module.split(".")[0])


def _parse_declared_deps(
    pyproject_path: Path,
) -> tuple[set[str], dict[str, str], set[str]]:
    """Return (runtime_norm_names, runtime_specifier_by_name, optional_norm_names).

    Names are normalized to PEP 503: lowercased, with underscores → hyphens.
    """
    runtime: set[str] = set()
    runtime_spec: dict[str, str] = {}
    optional: set[str] = set()

    text = pyproject_path.read_text(encoding="utf-8")

    # [project].dependencies = [...]
    m = re.search(r"^dependencies\s*=\s*\[(.*?)\]", text, re.MULTILINE | re.DOTALL)
    if m:
        for entry in re.findall(r'"([^"]+)"', m.group(1)):
            spec = entry.strip()
            name = (
                re.split(r"[<>=!~\s\[]", spec, 1)[0].strip().lower().replace("_", "-")
            )
            if name:
                runtime.add(name)
                runtime_spec[name] = spec

    # [project.optional-dependencies] sections
    in_optional = False
    for line in text.splitlines():
        if line.strip().startswith("[project.optional-dependencies]"):
            in_optional = True
            continue
        if (
            in_optional
            and line.strip().startswith("[")
            and not line.strip().startswith("[project")
        ):
            in_optional = False
        if in_optional:
            for entry in re.findall(r"['\"]([^'\"]+)['\"]", line):
                name = (
                    re.split(r"[<>=!~\s\[]", entry, 1)[0]
                    .strip()
                    .lower()
                    .replace("_", "-")
                )
                if name and not name.startswith("scitex-"):
                    optional.add(name)

    return runtime, runtime_spec, optional


def audit_dependencies(package_dir: str | Path) -> DepAuditReport:
    """Run the import-vs-declared audit.

    Returns a :class:`DepAuditReport`. ``report.is_clean`` is True when the
    package's declared deps fully cover its module-level imports and every
    scitex peer dep has a minimum-version pin (``scitex-X>=...``).
    """
    package_dir = Path(package_dir).resolve()
    pyproject = package_dir / "pyproject.toml"
    if not pyproject.exists():
        raise FileNotFoundError(f"no pyproject.toml in {package_dir}")

    pkg_import_name = package_dir.name.replace("-", "_")
    src_dir = _find_src_dir(package_dir)
    if src_dir is None:
        return DepAuditReport(package_dir=package_dir)

    imports = _walk_imports(src_dir)
    declared_runtime, declared_spec, declared_optional = _parse_declared_deps(pyproject)

    rep = DepAuditReport(
        package_dir=package_dir,
        declared_runtime=declared_runtime,
        declared_optional=declared_optional,
    )

    for name in sorted(imports):
        if (
            name in _STDLIB
            or name.lower() in _NEVER_FLAG
            or name == pkg_import_name
            or name.startswith("_")
        ):
            continue
        if name.startswith("scitex_"):
            rep.imported_scitex_peers.add(name)
            dist = name.replace("_", "-")
            if dist not in declared_runtime:
                rep.missing_scitex_peers.add(dist)
            else:
                spec = declared_spec.get(dist, "")
                if ">=" not in spec and "==" not in spec and "~=" not in spec:
                    rep.scitex_peers_without_min_version.add(dist)
            continue
        # External import.
        rep.imported_external.add(name)
        dist = _IMPORT_TO_DIST.get(name, name).lower().replace("_", "-")
        if dist not in declared_runtime and dist not in declared_optional:
            rep.missing_external.add(dist)

    return rep


def audit_all(repo_dirs: list[str | Path]) -> list[DepAuditReport]:
    """Audit each package in ``repo_dirs``."""
    return [audit_dependencies(d) for d in repo_dirs]


__all__ = [
    "DepAuditReport",
    "audit_dependencies",
    "audit_all",
]
