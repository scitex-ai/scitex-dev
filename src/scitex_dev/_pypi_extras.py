#!/usr/bin/env python3
# Timestamp: 2026-04-27
# File: scitex_dev/_pypi_extras.py

"""Audit + repair `[project.optional-dependencies]` (extras) blocks.

Conventions for SciTeX-ecosystem packages:

1. **Always provide `all`.** Lets users do `pip install scitex-X[all]` to
   get every feature without having to know each extra's name.
2. **Always provide `dev` and `docs`.** Standard development + documentation
   bootstrap. Users don't need either on a regular install but the tooling
   (RTD, CI, contributors) expects them.
3. **`all` references every other extra.** So new extras get picked up
   automatically and don't drift.
4. **Extras are well-formed:** value is a list of strings; no
   classifiers/version/etc. accidentally placed in optional-dependencies.

This module reads the existing extras, reports issues, and provides a
``write_extras_to_pyproject()`` helper to rewrite the
``[project.optional-dependencies]`` block in canonical form.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# Default contents for the standard extras when missing. Conservative:
# only sphinx + theme + extensions for docs (no autodoc plugins beyond what
# RTD actually needs), and pytest + cov + ruff for dev.
DEFAULT_DEV = ["pytest", "pytest-cov", "ruff"]
DEFAULT_DOCS = [
    "sphinx>=7.0",
    "sphinx-rtd-theme>=2.0",
    "myst-parser>=2.0",
    "sphinx-copybutton>=0.5",
    "sphinx-autodoc-typehints>=1.25",
]


@dataclass
class ExtrasAuditReport:
    """Result of auditing a package's extras block."""

    package_name: str
    extras: dict[str, list[str]] = field(default_factory=dict)
    has_all: bool = False
    has_dev: bool = False
    has_docs: bool = False
    all_missing_refs: set[str] = field(default_factory=set)

    @property
    def is_clean(self) -> bool:
        return (
            self.has_all
            and self.has_dev
            and self.has_docs
            and not self.all_missing_refs
        )

    def __str__(self) -> str:
        if self.is_clean:
            return f"ExtrasAuditReport({self.package_name}) ✓"
        flags = []
        if not self.has_all:
            flags.append("missing-all")
        if not self.has_dev:
            flags.append("missing-dev")
        if not self.has_docs:
            flags.append("missing-docs")
        if self.all_missing_refs:
            flags.append(f"all-missing={sorted(self.all_missing_refs)}")
        return f"ExtrasAuditReport({self.package_name}) ✗ {', '.join(flags)}"


def audit_extras(package_dir: str | Path) -> ExtrasAuditReport:
    """Read the package's extras and report issues.

    Uses tomllib (or tomli on 3.10) so the parse is exact rather than regex.
    """
    package_dir = Path(package_dir).resolve()
    pyproject = package_dir / "pyproject.toml"
    if not pyproject.exists():
        raise FileNotFoundError(f"no pyproject.toml at {package_dir}")

    try:
        import tomllib  # type: ignore[import-not-found]
    except ImportError:
        import tomli as tomllib  # type: ignore[import-not-found]

    with open(pyproject, "rb") as f:
        data = tomllib.load(f)

    project = data.get("project", {}) or {}
    name = project.get("name", package_dir.name)
    extras = project.get("optional-dependencies", {}) or {}

    rep = ExtrasAuditReport(
        package_name=name,
        extras={k: list(v) for k, v in extras.items()},
        has_all="all" in extras,
        has_dev="dev" in extras,
        has_docs="docs" in extras,
    )

    if rep.has_all:
        all_str = " ".join(extras["all"])
        for ex in extras:
            if ex == "all":
                continue
            # Skip dev/docs in the all-ref check by default — many packages
            # intentionally don't pull dev tooling into a user-level "all".
            if ex in ("dev", "docs"):
                continue
            # Look for either `pkg[ex]` or bare `ex` reference. The first form
            # is canonical; the second is sometimes used for dist names that
            # match the extra name (rare).
            if f"[{ex}]" not in all_str and ex not in all_str:
                rep.all_missing_refs.add(ex)

    return rep


def write_extras_to_pyproject(
    package_dir: str | Path,
    *,
    add_all_if_missing: bool = True,
    add_dev_if_missing: bool = True,
    add_docs_if_missing: bool = True,
    refresh_all_refs: bool = True,
) -> bool:
    """Rewrite the package's extras block to satisfy SciTeX conventions.

    Returns True if pyproject.toml was modified.

    The rewrite preserves existing extras' contents — it only:
    - Adds `dev`, `docs`, `all` when missing.
    - Refreshes `all` to reference every non-`dev`/non-`docs` extra.

    Strategy: locate the ``[project.optional-dependencies]`` table by line,
    rewrite that section as a canonical block, leave the rest of the file
    untouched.
    """
    package_dir = Path(package_dir).resolve()
    pyproject = package_dir / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")

    rep = audit_extras(package_dir)
    extras = dict(rep.extras)
    name = rep.package_name

    changed = False
    if add_dev_if_missing and "dev" not in extras:
        extras["dev"] = list(DEFAULT_DEV)
        changed = True
    if add_docs_if_missing and "docs" not in extras:
        extras["docs"] = list(DEFAULT_DOCS)
        changed = True

    feature_extras = sorted(e for e in extras if e not in ("all", "dev", "docs"))
    if add_all_if_missing and "all" not in extras:
        extras["all"] = [f"{name}[{e}]" for e in feature_extras] or [
            f"{name}[dev,docs]"
        ]
        changed = True
    elif refresh_all_refs and "all" in extras:
        canonical_all = [f"{name}[{e}]" for e in feature_extras] or [
            f"{name}[dev,docs]"
        ]
        if list(extras["all"]) != canonical_all:
            extras["all"] = canonical_all
            changed = True

    if not changed:
        return False

    # Render the new block.
    lines = ["[project.optional-dependencies]"]
    # Preserve a stable order: alphabetical, with all/dev/docs last.
    feature_keys = sorted(k for k in extras if k not in ("all", "dev", "docs"))
    ordered_keys = feature_keys + [k for k in ("dev", "docs", "all") if k in extras]
    for key in ordered_keys:
        items = extras[key]
        if not items:
            lines.append(f"{key} = []")
            continue
        lines.append(f"{key} = [")
        for item in items:
            lines.append(f'    "{item}",')
        lines.append("]")
    new_block = "\n".join(lines) + "\n"

    # Splice in place of the existing [project.optional-dependencies] block.
    # Regex isn't safe here because dep specifiers contain ``[extras]`` —
    # walk lines and find the section by header.
    lines_in = text.splitlines(keepends=True)
    out: list[str] = []
    i = 0
    found = False
    while i < len(lines_in):
        line = lines_in[i]
        stripped = line.strip()
        if not found and stripped == "[project.optional-dependencies]":
            # Skip everything until the next ``[section]`` (a header line
            # that starts with ``[`` after optional whitespace and is *not*
            # a continuation of an existing list).
            found = True
            i += 1
            while i < len(lines_in):
                nxt = lines_in[i].lstrip()
                if nxt.startswith("[") and not nxt.startswith("[]"):
                    break
                i += 1
            # Emit the rebuilt block in place of the skipped one.
            out.append(new_block)
            out.append("\n")
            continue
        out.append(line)
        i += 1

    if not found:
        # No existing section. Append after the [project] table.
        # Find the end of [project] (first line that's a fresh table header).
        new_lines: list[str] = []
        in_project = False
        inserted = False
        for ln in lines_in:
            s = ln.strip()
            if not inserted and in_project and s.startswith("[") and s != "[project]":
                new_lines.append("\n" + new_block + "\n")
                inserted = True
            new_lines.append(ln)
            if s == "[project]":
                in_project = True
        if not inserted:
            new_lines.append("\n" + new_block)
        new_text = "".join(new_lines)
    else:
        new_text = "".join(out)

    pyproject.write_text(new_text, encoding="utf-8")
    return True


__all__ = [
    "DEFAULT_DEV",
    "DEFAULT_DOCS",
    "ExtrasAuditReport",
    "audit_extras",
    "write_extras_to_pyproject",
]
