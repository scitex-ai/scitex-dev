#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Every third-party module we import must be declared as a dependency.

TWO INSTANCES OF THIS DEFECT IN FIVE DAYS, both found by someone else's
CI rather than ours:

    2026-08-05  `packaging`  undeclared, imported at module level on the
                eager path of `import scitex_dev._cli`
    2026-08-10  `rich`       undeclared, imported in EIGHT modules, two of
                them at module level

Both went unnoticed for the same reason, and it is not carelessness: these
distributions arrive TRANSITIVELY in nearly every pip/setuptools
environment. They are present exactly where developers look and absent
exactly where CI runs, so the failure appears only on somebody else's
machine — scitex-hub's, in both cases, days after the fact.

WHY DEFERRED IMPORTS DO NOT COUNT AS OPTIONAL. Six of the eight `rich`
imports are function-local, which reads like optional-dependency handling.
It is not: there is no `try/except ImportError` anywhere in the tree.
Deferring an import moves the crash from load time to call time and
changes nothing about whether the dependency is required. This test
therefore looks at ALL imports, not just module-level ones.

This is the mechanical barrier for a rule that was already known and
written down — the `packaging` entry in pyproject.toml carries a comment
explaining this precise failure mode, dated five days before `rich` was
found doing the same thing. A rule that must be remembered is forgotten
exactly when it matters.
"""

from __future__ import annotations

import ast
import sys
import tomllib
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
SRC = PACKAGE_ROOT / "src" / "scitex_dev"

#: Import names that differ from their distribution name on PyPI.
_IMPORT_TO_DISTRIBUTION = {
    "yaml": "pyyaml",
    "PIL": "pillow",
    "tomli": "tomli",
}

#: Modules that are ours, so they need no declaration.
_FIRST_PARTY_PREFIXES = ("scitex_dev",)


def _declared_distributions() -> set[str]:
    """Every distribution named in pyproject, base or extra, normalised."""
    data = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text())
    project = data.get("project", {})
    specs: list[str] = list(project.get("dependencies", []))
    for extra_specs in (project.get("optional-dependencies", {}) or {}).values():
        specs.extend(extra_specs)
    names = set()
    for spec in specs:
        # "name>=1.2 ; marker" / "name[extra]>=1" -> "name"
        head = spec.split(";", 1)[0].strip()
        for stop in ("[", ">", "<", "=", "!", "~", " "):
            head = head.split(stop, 1)[0]
        if head:
            names.add(head.strip().lower().replace("_", "-"))
    return names


def _imported_top_level_modules() -> dict[str, str]:
    """Top-level module name -> the first file that imports it."""
    found: dict[str, str] = {}
    for path in sorted(SRC.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):  # pragma: no cover
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name.split(".", 1)[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                # level > 0 is a relative import — ours by construction.
                if node.level or not node.module:
                    continue
                names = [node.module.split(".", 1)[0]]
            else:
                continue
            for name in names:
                found.setdefault(name, str(path.relative_to(PACKAGE_ROOT)))
    return found


def _third_party_imports() -> dict[str, str]:
    """Imports that are neither stdlib nor ours."""
    stdlib = set(sys.stdlib_module_names)
    out = {}
    for name, where in _imported_top_level_modules().items():
        if name in stdlib or name.startswith("_"):
            continue
        if name.startswith(_FIRST_PARTY_PREFIXES):
            continue
        out[name] = where
    return out


#: UNDECLARED TODAY, EACH AWAITING A JUDGEMENT. This list may only SHRINK.
#:
#: Turning this check on surfaced nine, and they are not one thing. Four are
#: sibling scitex packages that are plausibly deliberate soft integrations;
#: five are optional backends. Each needs an individual ruling — declare it,
#: guard the import with a real `try/except ImportError` and a usable
#: message, or establish that the module is genuinely never reached without
#: it. That is triage work, not a one-line fix.
#:
#: It is listed BY NAME rather than as a count on purpose. A count says "we
#: allow nine problems"; names say WHICH nine, so removing one is an obvious
#: diff and adding a tenth is impossible without editing this list in a
#: review. The same reason a masked-violation ceiling is a worse instrument
#: than an explicit skip list.
_KNOWN_UNDECLARED: "frozenset[str]" = frozenset(
    {
        # sibling scitex packages — likely optional integrations, unconfirmed
        "scitex",
        "scitex_cards",
        "scitex_events",
        "scitex_todo",
        # optional backends / surfaces
        "flask",       # dashboard/_app.py
        "psycopg",     # store/_dialect/_postgres.py
        "websockets",  # _cli/_doctor.py
        "ruamel",      # _cli/cron/_cred_distribute.py
        "numpy",       # _core/imports.py
    }
)


def _undeclared() -> dict[str, str]:
    declared = _declared_distributions()
    missing = {}
    for module, where in _third_party_imports().items():
        dist = _IMPORT_TO_DISTRIBUTION.get(module, module)
        if dist.lower().replace("_", "-") not in declared:
            missing[module] = where
    return missing


class TestNoNewUndeclaredImportAppears:
    """The barrier. `packaging` and `rich` would both have failed this.

    Deliberately NOT asserting the list is empty. Nine pre-existing entries
    each need a judgement, and dumping nine untriaged findings into a
    blocking gate at once is how a gate gets disabled rather than paid down
    — the exact advice I gave scitex-hub about their masked-violation
    ceiling hours before writing this.
    """

    def test_no_undeclared_import_outside_the_known_list(self):
        # Arrange
        known = _KNOWN_UNDECLARED
        # Act
        surprises = {m: w for m, w in _undeclared().items() if m not in known}
        # Assert
        assert surprises == {}, (
            "imported but declared in no dependency or extra: "
            + ", ".join(f"{m} (first seen in {w})" for m, w in sorted(surprises.items()))
            + ". A transitively-available distribution is present where you "
            "develop and absent where CI runs; declare it, or guard the "
            "import with a real try/except ImportError and a usable message."
        )

    def test_the_known_list_only_shrinks(self):
        """An entry that got declared must be removed from the list."""
        # Arrange
        still_undeclared = set(_undeclared())
        # Act
        stale = _KNOWN_UNDECLARED - still_undeclared
        # Assert
        assert stale == set(), (
            f"these are now declared and must be dropped from "
            f"_KNOWN_UNDECLARED: {sorted(stale)}"
        )


class TestTheKnownRegressionsStayDeclared:
    """Both were found by someone else's CI. Neither comes back quietly."""

    @pytest.mark.parametrize("distribution", ["packaging", "rich"])
    def test_the_previously_undeclared_distribution_is_declared(self, distribution):
        # Arrange
        declared = _declared_distributions()
        # Act
        present = distribution in declared
        # Assert
        assert present


class TestTheCheckCanActuallyFail:
    """A barrier that cannot fail is decoration."""

    def test_an_undeclared_name_is_reported_as_missing(self):
        # Arrange
        declared = _declared_distributions()
        # Act
        invented = "definitely-not-a-real-distribution" in declared
        # Assert
        assert not invented

    def test_declared_distributions_are_actually_found(self):
        """Guards against the parser returning an empty set and passing."""
        # Arrange
        declared = _declared_distributions()
        # Act
        has_click = "click" in declared
        # Assert
        assert has_click

    def test_third_party_imports_are_actually_found(self):
        """Guards against the AST walk returning nothing and passing."""
        # Arrange
        imports = _third_party_imports()
        # Act
        count = len(imports)
        # Assert
        assert count > 0


# EOF
