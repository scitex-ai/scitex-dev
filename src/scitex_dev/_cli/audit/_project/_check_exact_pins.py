"""PS-237 — exact `==` pin in publishable dependency metadata.

Symptom this prevents: a package declares a dependency in its
**publishable** `pyproject.toml` metadata with an exact pin
(`scitex-io==0.7.0`, `pkg===1.2`) instead of a minimum (`scitex-io>=0.4.0`).
Library metadata states which versions the code is *compatible with*; it is
not a lock file. An exact pin there:

- **downgrades** a newer, already-installed dependency whenever the package
  is installed or upgraded (`pip install -U 'scitex[all]'` once replaced
  scitex-dev 0.62.30 with 0.28.0 and scitex-scholar 1.29.2 with 1.4.2);
- makes the package **uninstallable** next to any other package that needs a
  different version of the same dependency;
- forces a **release of this package for every release of the dependency**,
  because the pin is wrong the moment the dependency publishes.

Exact versions belong in lock files and constraints files (`uv.lock`, a
`constraints.txt`, a container image) that pin a *deployment*, never in the
`Requires-Dist` of a distribution other projects install.

Decision rule the auditor enforces
----------------------------------

Scan `[project].dependencies` and every `[project.optional-dependencies]`
group. A requirement whose specifier set contains `==` or `===` is flagged
(PS-237). Wildcard equality (`==1.2.*`) is a range, not a pin, and is not
flagged. Environment markers are ignored; `!=` exclusions, `<` upper bounds
and `~=` compatible releases are not exact pins.

Fix: declare the oldest version that provides what the package actually
uses (`pkg>=X.Y`), add an upper bound only for a known breaking major, and
keep the floor honest with a CI job that installs the minimums (for example
`uv pip compile --resolution lowest-direct`).

Severity
--------

New-vs-baseline, like PS-214: a pin introduced by the change under audit is
escalated to "E" (blocking); a pin already present at the baseline ref keeps
the registered default "W", so the rule does not newly block a repo that
already carries pins. Without a resolvable baseline every finding stays "W".
"""

from __future__ import annotations

from pathlib import Path

try:
    import tomllib  # 3.11+
except ImportError:  # pragma: no cover — 3.10 path
    import tomli as tomllib  # type: ignore[no-redef]

from packaging.requirements import InvalidRequirement, Requirement

_EXACT_OPERATORS = ("==", "===")
# Mirrors `_new_vs_baseline.DEFAULT_BASELINE_REF`. That module is imported
# inside `check_ps237_exact_pins` only: the rule registry imports this module
# for EXACT_PIN_RULES while `_violation` is still initialising, so a top-level
# import of `_new_vs_baseline` (which imports `_violation`) would be circular.
_BASELINE_REF = "develop"


def _parse_pyproject(repo: Path) -> dict | None:
    pp = repo / "pyproject.toml"
    if not pp.is_file():
        return None
    try:
        return tomllib.loads(pp.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return None


def _iter_dep_tables(project: dict):
    """Yield `(table_label, [requirement, ...])` for every publishable table."""
    deps = project.get("dependencies")
    if isinstance(deps, list):
        yield "[project.dependencies]", deps
    groups = project.get("optional-dependencies", {}) or {}
    if isinstance(groups, dict):
        for extra_name in sorted(groups):
            group = groups[extra_name]
            if isinstance(group, list):
                yield f"[project.optional-dependencies.{extra_name}]", group


def exact_pin(requirement: str) -> str | None:
    """Return the exact-pin clause of ``requirement`` (e.g. ``==0.7.0``), else None.

    A wildcard equality (``==1.2.*``) matches a range of releases and is not
    an exact pin.
    """
    if not isinstance(requirement, str):
        return None
    try:
        parsed = Requirement(requirement)
    except InvalidRequirement:
        return None
    for spec in parsed.specifier:
        if spec.operator in _EXACT_OPERATORS and not spec.version.endswith(".*"):
            return f"{spec.operator}{spec.version}"
    return None


def _collect_ps237_violations(repo: Path, violation_cls: type) -> list:
    """Pure collection pass — no severity escalation (re-run on the baseline)."""
    found: list = []
    meta = _parse_pyproject(repo)
    if meta is None:
        return found
    project = meta.get("project", {}) or {}
    if not isinstance(project, dict):
        return found
    where = str(repo / "pyproject.toml")
    for table_label, requirements in _iter_dep_tables(project):
        for requirement in requirements:
            clause = exact_pin(requirement)
            if clause is None:
                continue
            name = Requirement(requirement).name
            found.append(
                violation_cls(
                    "PS-237",
                    where,
                    (
                        f"exact pin `{requirement}` in {table_label}. "
                        f"Publishable metadata declares compatibility, not a "
                        f"deployment: `{clause}` downgrades a newer installed "
                        f"{name}, conflicts with any package needing another "
                        f"version, and forces a release here for every "
                        f"{name} release. Declare the oldest version that "
                        f"provides what this package uses (`{name}>=X.Y`), "
                        f"cap only a known breaking major, and keep exact "
                        f"versions in a lock or constraints file."
                    ),
                )
            )
    return found


def check_ps237_exact_pins(
    repo: Path,
    violation_cls: type,
    out: list,
    *,
    baseline_ref: str = _BASELINE_REF,
) -> None:
    """Append PS-237 violations for exact pins in publishable dependency tables."""
    found = _collect_ps237_violations(repo, violation_cls)
    if not found:
        return
    from ._new_vs_baseline import escalate_new_violations

    escalate_new_violations(
        repo,
        found,
        ("PS-237",),
        lambda base_repo: _collect_ps237_violations(base_repo, violation_cls),
        baseline_ref=baseline_ref,
    )
    out.extend(found)


# Rule definition, CO-LOCATED with its check (merged by `_rules/__init__.py`
# on the same terms as URL_DEP_RULES). Default "W"; a pin new relative to the
# baseline ref is escalated to "E" by `check_ps237_exact_pins`.
#
# (code, section, message, severity, slug)
EXACT_PIN_RULES: list[tuple[str, str, str, str, str]] = [
    (
        "PS-237",
        "§3",
        (
            "exact `==`/`===` pin in publishable metadata: a requirement in "
            "`[project].dependencies` or a `[project.optional-dependencies]` "
            "group pins one version. It downgrades a newer installed "
            "dependency, conflicts with packages that need another version, "
            "and forces a release of this package for every dependency "
            "release. Declare the oldest version that provides what the "
            "package uses (`pkg>=X.Y`, plus an upper bound only for a known "
            "breaking major) and keep exact versions in lock/constraints "
            "files. New pins block (E); pins already on the baseline warn (W)."
        ),
        "W",
        "exact-pin-in-publishable-metadata",
    ),
]


# EOF
