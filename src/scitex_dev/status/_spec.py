#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Locate and load the language-independent spec files.

``spec/`` is the SOURCE OF TRUTH and this module is how Python reads it, so
the Python tables are DERIVED rather than authored. A hand-typed copy of a
hundred HTTP codes is a copy with a typo in it, and worse, a copy that can
drift from the spec without anything noticing.

The files ship INSIDE the package rather than at the repository root. That is
deliberate: a root-level ``spec/`` would not travel in the wheel, so an
installed consumer would need a second copy — and two copies of a single
source of truth is the defect the SSoT rule exists to prevent. Other
languages read the same files out of the installed package, or out of the
repository; either way there is exactly one of them.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

__all__ = [
    "SPEC_DIR",
    "SPEC_VERSION",
    "load_boundaries",
    "load_kinds",
    "load_schema",
    "load_scitex_codes",
    "load_verdicts",
    "spec_path",
]

SPEC_DIR = Path(__file__).with_name("spec")

#: The only spec version this implementation understands. A reader that meets
#: another version must REFUSE it rather than best-effort parse it: partially
#: understanding a protocol message is how a field's absence is read as a value.
SPEC_VERSION = "1"


def spec_path(*parts: str) -> Path:
    """Return an absolute path inside the packaged spec directory."""
    return SPEC_DIR.joinpath(*parts)


def _load_yaml(name: str) -> dict[str, Any]:
    """Parse one packaged YAML spec file.

    Raises rather than returning a default when the file is missing: an
    implementation that cannot read its own source of truth must not carry on
    with an empty table, because an empty table VALIDATES NOTHING and every
    malformed value would then pass.

    Parsed with stdlib ``yaml`` rather than ``stx.io.load`` (STX-IO010), for
    two reasons. These are the PACKAGE'S OWN bundled spec files, not user data,
    so there is no provenance to track — the provenance is the git history of
    this repository. And ``scitex_dev.status`` is imported by every leaf that
    reports a status, so it must not drag ``scitex_io`` into their runtime.
    ``scitex_dev._branding`` reads its packaged YAML the same way.
    """
    import yaml  # local: keeps the import cost off callers that never validate

    path = spec_path(name)
    if not path.is_file():
        raise FileNotFoundError(
            f"spec file {name!r} is missing from {SPEC_DIR}. The Python "
            f"implementation is DERIVED from it and cannot validate without "
            f"it. If this is an installed package, the spec/ directory was "
            f"not shipped — check `[tool.setuptools.package-data]` in "
            f"pyproject.toml for the `status/spec/**/*` entry."
        )
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def load_kinds() -> dict[str, Any]:
    """The kind registry: per-kind code domains, reserved codes, message rules."""
    return _load_yaml("kinds.yaml")


@lru_cache(maxsize=None)
def load_scitex_codes() -> dict[str, Any]:
    """The closed enumeration of ``kind="scitex"`` codes."""
    return _load_yaml("scitex-codes.yaml")


@lru_cache(maxsize=None)
def load_boundaries() -> dict[str, Any]:
    """Which kind each declared call boundary borrows."""
    return _load_yaml("boundaries.yaml")


@lru_cache(maxsize=None)
def load_verdicts() -> dict[str, Any]:
    """The closed three-valued verdict set, its check rules and its rollup policies."""
    return _load_yaml("verdicts.yaml")


@lru_cache(maxsize=None)
def load_schema(name: str) -> dict[str, Any]:
    """One packaged JSON Schema, by file name."""
    path = spec_path("schema", name)
    if not path.is_file():
        raise FileNotFoundError(f"schema {name!r} is missing from {path.parent}.")
    return json.loads(path.read_text(encoding="utf-8"))


# EOF
