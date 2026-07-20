# -*- coding: utf-8 -*-
"""PS-221 — `[all]`-closure on PUBLIC optional-dependency extras.

Anti-landmine this prevents (silent under-install of a public feature):
the operator policy is that a PUBLIC install extra must be `[all]` or bare
ONLY — `pip install pkg[all]` must pull in **everything public**, with no
fine-grained per-feature menu a user has to assemble by hand. When a
package instead ships public per-feature extras, every one of them must be
a SUBSET of `all`, so `[all]` remains the single "give me all of it"
switch. If a requirement lives in some public extra but is MISSING from
`all`, then `pip install pkg[all]` silently under-installs it: the user
did exactly the documented thing to "get everything" and is still missing
a feature, with nothing to signal the gap. That is the landmine.

Decision rule the auditor enforces
----------------------------------

For each package `pyproject.toml` `[project.optional-dependencies]`:

  1. Collect the PUBLIC groups: every extra whose name does NOT start with
     an underscore and is not `all` itself. Underscore-prefixed extras
     (`_ci`, `_docs`, …) are INTERNAL splits — deliberately exempt from
     closure (that is the sanctioned way to carve out a non-public group).
  2. If there are public groups but NO `all` group at all → PS-221
     (a package offering public extras must expose the `[all]` umbrella).
  3. Otherwise, every requirement (compared by CANONICALIZED distribution
     name — `Foo_Bar` == `foo-bar`) in each public group must also appear
     in `all`. Any requirement missing from `all` → PS-221.

Self-reference handling
-----------------------

The idiomatic way to write `all` is to reference the package's own other
extras, e.g. `all = ["mypkg[viz,editor]"]`. Such a self-reference is
expanded to the canonical requirement names of the referenced extras
before the subset test, so the idiom does NOT false-positive. Likewise a
self-reference appearing *inside* a public extra is skipped rather than
treated as an external requirement (the referenced extra, if public, is
closure-checked on its own).

Heuristic notes
---------------

- The auditor reads `pyproject.toml` only — it does not import the
  package, so it is safe to run on broken trees.
- A package with NO `[project.optional-dependencies]`, or with only
  underscore-prefixed internal extras, is not a violation.
- A requirement whose spec cannot be parsed as a PEP 508 requirement
  (e.g. a direct-URL reference — that is PS-216's job) is skipped here.

Severity
--------

Flat `severity = "E"` (blocking), mirroring PS-216: the rule carries a
concrete mechanical spec with no false-positive interpretation once
self-references are expanded, and a public requirement missing from `all`
is an unambiguous silent under-install. It gates the scitex-python
umbrella release, so warn-first would defeat the point.
"""

from __future__ import annotations

from pathlib import Path

try:
    import tomllib  # 3.11+
except ImportError:  # pragma: no cover — 3.10 / 3.9 path
    import tomli as tomllib  # type: ignore[no-redef]

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


def _parse_pyproject(repo: Path) -> dict | None:
    pp = repo / "pyproject.toml"
    if not pp.is_file():
        return None
    try:
        return tomllib.loads(pp.read_text(encoding="utf-8"))
    except Exception:
        return None


def _canon(spec: str) -> str | None:
    """Canonical distribution name of a PEP 508 requirement spec, or None.

    `canonicalize_name` folds case and `_`/`.`/`-` runs together, so
    `Foo_Bar` == `foo-bar`. A spec that is not a parseable PEP 508
    requirement (e.g. a direct-URL reference — PS-216's domain) yields
    None and is skipped by callers.
    """
    if not isinstance(spec, str):
        return None
    try:
        return str(canonicalize_name(Requirement(spec).name))
    except Exception:
        return None


def _public_groups(od: dict) -> dict[str, list]:
    """Public (non-underscore, non-`all`) extra groups with list values."""
    return {
        name: grp
        for name, grp in od.items()
        if isinstance(grp, list) and not name.startswith("_") and name != "all"
    }


def _all_closure_names(
    all_group: list, od: dict, proj_name: str | None
) -> set[str]:
    """Canonical requirement names covered by `all`, self-refs expanded.

    A self-reference (`<own-name>[<extra>,...]`) is replaced by the
    canonical requirement names of the referenced extras, so the idiomatic
    `all = ["mypkg[viz,editor]"]` shape resolves to the concrete union it
    is shorthand for.
    """
    names: set[str] = set()
    for spec in all_group:
        if not isinstance(spec, str):
            continue
        try:
            req = Requirement(spec)
        except Exception:
            continue
        cname = str(canonicalize_name(req.name))
        if proj_name and cname == proj_name and req.extras:
            for ref in req.extras:
                grp = od.get(ref)
                if isinstance(grp, list):
                    for r in grp:
                        c = _canon(r)
                        if c is not None:
                            names.add(c)
        else:
            names.add(cname)
    return names


def check_ps221_extras_all_closure(
    repo: Path,
    violation_cls: type,
    out: list,
) -> None:
    """Append PS-221 violations for public extras not closed under `[all]`.

    Parameters
    ----------
    repo : Path
        Repository root (the dir containing `pyproject.toml`).
    violation_cls : type
        The auditor's `Violation` dataclass `(rule, where, detail)`.
    out : list
        Violations are appended in place (project-auditor convention).
    """
    meta = _parse_pyproject(repo)
    if meta is None:
        return
    project = meta.get("project", {}) or {}
    if not isinstance(project, dict):
        return
    od = project.get("optional-dependencies", {}) or {}
    if not isinstance(od, dict):
        return

    public = _public_groups(od)
    if not public:
        return

    where = str(repo / "pyproject.toml")
    raw_name = project.get("name")
    proj_name = (
        str(canonicalize_name(raw_name)) if isinstance(raw_name, str) else None
    )

    all_group = od.get("all")
    if not isinstance(all_group, list):
        out.append(
            violation_cls(
                "PS-221",
                where,
                (
                    "package declares PUBLIC optional-dependency extras "
                    f"({', '.join(sorted(public))}) but NO `all` group. Policy: "
                    "a public extra must be `[all]` or bare only — "
                    "`pip install <pkg>[all]` must pull EVERYTHING public. "
                    "Add an `all` extra that is a SUPERSET of every public "
                    "extra (e.g. `all = [\"<pkg>[" + ",".join(sorted(public))
                    + "]\"]`), or make the non-`all` groups INTERNAL by "
                    "underscore-prefixing their names (`_ci`, `_docs`), which "
                    "are exempt from this closure rule."
                ),
            )
        )
        return

    all_names = _all_closure_names(all_group, od, proj_name)
    for name in sorted(public):
        for req in public[name]:
            canon = _canon(req)
            if canon is None:
                continue
            # A self-reference to the package's own (public) extra is not an
            # external requirement; the referenced extra is closure-checked
            # on its own, so skip it here.
            if proj_name is not None and canon == proj_name:
                continue
            if canon not in all_names:
                out.append(
                    violation_cls(
                        "PS-221",
                        where,
                        (
                            f"requirement `{req}` in PUBLIC extra "
                            f"`[project.optional-dependencies.{name}]` is "
                            "MISSING from the `all` extra. Policy: every "
                            "public extra must be a SUBSET of `all`, so "
                            "`pip install <pkg>[all]` pulls EVERYTHING public "
                            "— a public requirement absent from `all` silently "
                            "under-installs (the user runs the documented "
                            "\"give me everything\" install and is still "
                            "missing this feature). Fix: add this requirement "
                            "to `all` (or reference the extra from `all` via "
                            f"`<pkg>[{name}]`). If this group is meant to be "
                            "INTERNAL, rename it with an underscore prefix "
                            f"(`_{name}`), which is exempt from closure."
                        ),
                    )
                )


# Rule definition, CO-LOCATED with its check (same pattern as PS-216's
# `URL_DEP_RULES` / PS-hook's `HOOK_RULES`). `_registry.py` merges
# `ALL_CLOSURE_RULES` on identical terms.
#
# Severity E (error): a concrete mechanical spec with no false-positive
# interpretation once `all` self-references are expanded; a public
# requirement missing from `all` is an unambiguous silent under-install.
# Gates the scitex-python umbrella release.
#
# (code, section, message, severity, slug)
ALL_CLOSURE_RULES: list[tuple[str, str, str, str, str]] = [
    (
        "PS-221",
        "§3",
        (
            "public optional-dependency extra not closed under `[all]`: a "
            "PUBLIC extra (non-underscore, not `all`) in "
            "`[project.optional-dependencies]` carries a requirement that is "
            "MISSING from the `all` group — or the package ships public "
            "extras with no `all` group at all. Policy: a public install "
            "extra must be `[all]` or bare ONLY, so `pip install <pkg>[all]` "
            "pulls EVERYTHING public; every public extra must be a SUBSET of "
            "`all`. A public requirement absent from `all` silently "
            "under-installs. Fix: add the requirement to `all` (or reference "
            "the extra from `all`), or make the group INTERNAL by "
            "underscore-prefixing its name (`_ci`, `_docs`) — underscore "
            "extras are exempt from closure."
        ),
        "E",
        "public-extra-not-closed-under-all",
    ),
]


# EOF
