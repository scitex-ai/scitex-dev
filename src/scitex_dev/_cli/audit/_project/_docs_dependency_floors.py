"""Prove unconditional PEP440 lower bounds for the canonical docs stack."""
from __future__ import annotations

import re

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

DOCS_FLOORS = {
    "sphinx": Version("7.0"),
    "sphinx-rtd-theme": Version("2.0"),
    "myst-parser": Version("2.0"),
    "sphinx-copybutton": Version("0.5"),
    "sphinx-autodoc-typehints": Version("1.25"),
}


def missing_docs_floors(text: str) -> list[str]:
    """Require a sufficient positive bound, without attempting package resolution.

    An unconditional >=, >, exact or compatible requirement at/above the floor
    proves the bound even with other intersecting constraints. Upper bounds and
    exclusions alone do not prove a minimum. Conditional/direct-URL declarations
    cannot establish this always-installed version contract. Normal dependency
    resolution remains responsible for availability and contradictory constraints.
    """
    proven = set()
    for raw in text.splitlines():
        line = re.split(r"\s+#", raw, maxsplit=1)[0].strip()
        try:
            requirement = Requirement(line)
        except InvalidRequirement:
            continue
        name = canonicalize_name(requirement.name)
        if name not in DOCS_FLOORS or requirement.marker is not None or requirement.url:
            continue
        for bound in requirement.specifier:
            if bound.operator not in {">=", ">", "==", "===", "~="}:
                continue
            version = bound.version
            if bound.operator == "==" and version.endswith(".*"):
                version = version[:-2] + ".dev0"
            try:
                sufficient = Version(version) >= DOCS_FLOORS[name]
            except InvalidVersion:
                continue
            if sufficient:
                proven.add(name)
                break
    return [name for name in DOCS_FLOORS if name not in proven]
