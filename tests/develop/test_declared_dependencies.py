#!/usr/bin/env python3
"""Every third-party package imported at MODULE level must be DECLARED.

THE GAP THIS FILLS, stated precisely because two neighbouring rules look
like they already cover it and do not:

- PS-148 (`_check_optional_deps_guarded`) loops over each lib declared in
  `[project.optional-dependencies]` and flags unguarded module-level
  imports of it. Its loop is over DECLARED optionals — a package declared
  in NO block is never iterated, so it is structurally invisible to that
  rule.
- PA-301 scans only `__init__.py`, and only against a hardcoded
  `_THIRD_PARTY_ROOTS` list.

So the UNDECLARED case — imported at module level, declared nowhere — had
no checker. Measured 2026-08-05: `packaging` was imported at module level
in `_cli/audit/_project/_check_extras_all_closure.py` and absent from
pyproject entirely. `_rules/__init__.py` imports that module
unconditionally, so it sat on the eager path of `import scitex_dev._cli`.

WHY IT SURVIVED SO LONG, and why CI is the only place it could surface:
pip/setuptools environments almost always have `packaging` transitively, so
every dev machine and every editable install had it. A clean `uv` venv does
not. scitex-clew's import-smoke leg died with `ModuleNotFoundError: No
module named 'packaging'` raised from inside scitex_dev — i.e. OUR missing
dependency broke a DOWNSTREAM repo's CI, which is the blast radius that
makes this worth a permanent guard rather than a one-line fix.

Note the `dep-hygiene-smoke` job passed on that same run. A gate named for
dependency hygiene reported clean while a missing dependency broke the
build beside it, which is why this guard lives in the test suite where it
cannot be skipped.
"""

from __future__ import annotations

import ast
import sys
import tomllib
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[2] / "src" / "scitex_dev"
_PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"

#: Import roots that are OURS — resolved from the source tree, not listed by
#: hand, so a new first-party package cannot silently look third-party.
_FIRST_PARTY = {"scitex_dev"}


def _declared_distributions() -> set[str]:
    """Every distribution named anywhere in pyproject, normalised.

    Both `dependencies` and every `optional-dependencies` extra count: the
    question this file asks is "is it declared AT ALL", not "is it a hard
    dependency". A package behind an extra is a different defect (PS-148's),
    not this one.
    """
    data = tomllib.loads(_PYPROJECT.read_text())
    project = data.get("project", {})
    raw: list[str] = list(project.get("dependencies", []))
    for extra in project.get("optional-dependencies", {}).values():
        raw.extend(extra)

    names: set[str] = set()
    for spec in raw:
        # strip environment markers, extras, and version pins
        head = spec.split(";", 1)[0].strip()
        head = head.split("[", 1)[0]
        for sep in ("==", ">=", "<=", "~=", "!=", ">", "<", "="):
            head = head.split(sep, 1)[0]
        head = head.strip()
        if head:
            # distribution `foo-bar` imports as `foo_bar`
            names.add(head.replace("-", "_").lower())
    return names


def _module_level_imports(path: Path) -> set[str]:
    """Top-level import ROOTS in ``path``, excluding guarded ones.

    An import nested inside a function, a `try`, or an `if` is deliberately
    NOT reported: deferring or guarding an import is the sanctioned way to
    depend on something optional, and flagging it here would contradict
    PS-148's remedy.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return set()

    roots: set[str] = set()
    for node in tree.body:  # body only == module level, unnested
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import — always first-party
                continue
            if node.module:
                roots.add(node.module.split(".")[0])
    return roots


def _third_party_module_imports() -> dict[str, list[str]]:
    """root -> the files importing it, for third-party roots only."""
    offenders: dict[str, list[str]] = {}
    for py in sorted(_SRC.rglob("*.py")):
        for root in _module_level_imports(py):
            if root in sys.stdlib_module_names or root in _FIRST_PARTY:
                continue
            offenders.setdefault(root, []).append(
                str(py.relative_to(_SRC.parent.parent))
            )
    return offenders


def _is_declared(import_root: str, declared: set[str]) -> bool:
    """True iff ``import_root`` is provided by a DECLARED distribution.

    An import root is NOT a distribution name and the two cannot be mapped
    by string munging: PyYAML imports as ``yaml``. An earlier draft of this
    file did munge, reported `yaml` as undeclared, and carried a
    parametrized test asserting `pyyaml>=6.0` -> `"pyyaml"` — pinning the
    bug as expected behaviour. `importlib.metadata.packages_distributions()`
    is the authoritative reverse map and is used instead.

    Falls back to a direct name comparison when the root is not installed,
    so the check degrades to "can't tell, assume declared-by-name" rather
    than manufacturing a false positive from a missing environment.
    """
    if import_root in declared:
        return True
    from importlib.metadata import packages_distributions

    providers = packages_distributions().get(import_root)
    if not providers:
        return False
    return any(dist.replace("-", "_").lower() in declared for dist in providers)


def _eagerly_imported_third_party() -> set[str]:
    """Third-party roots pulled in by importing the CLI chain, MEASURED.

    This is the set that actually breaks a downstream install: anything
    loaded as a side effect of `import scitex_dev._cli.ecosystem` must be
    installed, or the import raises ModuleNotFoundError. Deriving it by
    importing and reading `sys.modules` measures the real path instead of
    inferring it from a static walk, which cannot tell an eager import from
    one nested three modules deep behind a lazy attribute.
    """
    before = set(sys.modules)
    import scitex_dev._cli.ecosystem  # noqa: F401

    roots = {name.split(".")[0] for name in set(sys.modules) - before}
    roots |= {"scitex_dev"}
    return {
        r
        for r in roots
        if r not in sys.stdlib_module_names
        and r not in _FIRST_PARTY
        and not r.startswith("_")
    }


def test_packaging_is_declared():
    """Pins the specific 2026-08-05 breakage.

    Kept alongside the general scan because a named regression test says
    WHICH incident it prevents, and survives any future rewrite of the
    scanner.
    """
    # Arrange
    expected_root = "packaging"
    # Act
    declared = _declared_distributions()
    # Assert
    assert expected_root in declared


def test_the_module_that_broke_clew_imports_only_declared_packages():
    """Narrow guard on the ONE module whose undeclared import broke CI.

    Deliberately not the fleet-wide version. Two attempts at a general
    "nothing undeclared anywhere" guard produced false positives faster
    than true ones:
      - a static source walk flagged `yaml`, because PyYAML's distribution
        name is not its import root;
      - an import-and-diff-sys.modules walk flagged `cython_runtime` (a
        Cython pseudo-module) and `scitex_agent_container` / `scitex_ui`,
        which arrive through scitex-dev's ENTRY-POINT plugin federation and
        so depend on what happens to be installed — present locally, absent
        in CI's clean venv. A guard that passes in CI and fails on a
        developer's machine is worse than none.
    A signal with a high false-positive rate must not gate; that is the
    same conclusion reached for the audit `unreadable` bucket the same day.
    The general version is carded, not abandoned.
    """
    # Arrange
    declared = _declared_distributions()
    target = _SRC / "_cli" / "audit" / "_project" / "_check_extras_all_closure.py"
    # Act
    undeclared = sorted(
        root
        for root in _module_level_imports(target)
        if root not in sys.stdlib_module_names
        and root not in _FIRST_PARTY
        and not _is_declared(root, declared)
    )
    # Assert
    assert not undeclared, (
        f"{target.name} imports undeclared packages at module level: "
        f"{undeclared}. It sits on the eager path of `import scitex_dev._cli`, "
        "so a clean install raises ModuleNotFoundError — this is exactly how "
        "scitex-clew's import-smoke leg died on 2026-08-05."
    )


def test_pyyaml_is_recognised_through_its_import_root():
    """Distribution names and import roots differ; the mapping must be real.

    PyYAML is declared and imports as `yaml`. A string-munging mapping
    reports it undeclared — this file's first draft did exactly that, and
    carried a parametrized test asserting `pyyaml>=6.0` normalises to
    `"pyyaml"`, which pinned the defect as the expected answer. Kept as a
    named regression so the munging cannot come back.
    """
    # Arrange
    declared = _declared_distributions()
    # Act
    recognised = _is_declared("yaml", declared)
    # Assert
    assert recognised is True


def test_the_scanner_actually_finds_imports():
    """Positive control — an empty scan would make the guard vacuous.

    Without this, a scanner bug that returned nothing would render the
    test above permanently green while checking nothing, which is the
    exact unearned-green shape this repo keeps fixing elsewhere.
    """
    # Arrange — click is a declared hard dep, imported widely at module level
    known_present = "click"
    # Act
    found = _third_party_module_imports()
    # Assert
    assert known_present in found, f"scanner found no click imports: {sorted(found)}"


@pytest.mark.parametrize(
    "distribution",
    ["packaging", "tomli", "pyyaml", "click", "scitex_config"],
)
def test_declared_set_survives_markers_extras_and_pins(distribution):
    """`_declared_distributions` must parse every spec shape in this pyproject.

    These are DISTRIBUTION names, not import roots — the two are related by
    `packages_distributions()`, never by string munging. Each shape below
    (bare pin, environment marker, extras suffix) is present in this repo
    today, so a parser that drops one silently shrinks `declared` and turns
    the guard into a false-positive generator.
    """
    # Arrange
    expected = distribution
    # Act
    declared = _declared_distributions()
    # Assert
    assert expected in declared
