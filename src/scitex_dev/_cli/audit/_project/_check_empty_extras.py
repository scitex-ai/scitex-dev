# -*- coding: utf-8 -*-
"""PS-214 — empty pyproject extra.

Symptom this prevents (the "confident remedy that installs nothing" bug
class): a package declares a `[project.optional-dependencies]` extra
group with an EMPTY dependency list — e.g. `editor = []` — while the
package it's meant to gate (say, an optional companion app) appears in
NO dependency list anywhere in the project. The package's own code then
tells users to run `pip install <pkg>[<extra>]` to fix a missing-feature
error. The user follows the remedy, `pip` happily installs zero packages
(an empty extra is a no-op), and the user is left exactly as broken —
but now believes they already tried the cure.

Reference incident: scitex-writer declared `editor = []` while
`_server.py` / `apps.py` / the CLI told users "Install with:
pip install scitex-writer[editor]" to get scitex-app. See scitex-writer
PR #322 (the fix — populate the extra with the actual dependency) and
its companion source-side check PS-215 (`_check_install_remedy_strings.py`)
which flags any `pip install <pkg>[<extra>]` string naming an empty or
nonexistent extra.

Decision rule the auditor enforces:

  For each extra declared in `[project.optional-dependencies]`, if its
  dependency list is empty (`extra = []`) → PS-214.

This is intentionally the cheapest possible check — a bare TOML parse,
no source scanning, no AST — because an empty list is unambiguous: there
is no interpretation under which `pip install <pkg>[<extra>]` installing
zero packages is the intended behaviour for a *named* extra. (Compare to
`[dev]` / `[docs]` extras, which are fine — the operator directive scopes
the all-or-nothing packaging rule to *consumer-facing* extras; `[dev]`
existing-but-currently-empty is a much rarer, lower-stakes shape and
still gets flagged here since "empty" is unambiguous regardless of
extra name.)

Heuristic notes
----------------

- The auditor reads `pyproject.toml` only — it does not import the
  package, so it is safe to run on broken trees.
- A missing `[project.optional-dependencies]` table entirely is not a
  violation of this rule (that's a design choice the package is free to
  make); only a table that DECLARES an extra with an empty list fires.
"""

from __future__ import annotations

from pathlib import Path

try:
    import tomllib  # 3.11+
except ImportError:  # pragma: no cover — 3.10 path
    import tomli as tomllib  # type: ignore[no-redef]


def _parse_pyproject(repo: Path) -> dict | None:
    pp = repo / "pyproject.toml"
    if not pp.is_file():
        return None
    try:
        return tomllib.loads(pp.read_text(encoding="utf-8"))
    except Exception:
        return None


def check_ps214_empty_extras(repo: Path, violation_cls: type, out: list) -> None:
    """Append PS-214 violations for empty `[project.optional-dependencies]` groups.

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
    od = project.get("optional-dependencies", {}) or {}
    if not isinstance(od, dict):
        return

    for extra_name in sorted(od):
        deps = od[extra_name]
        if isinstance(deps, list) and len(deps) == 0:
            out.append(
                violation_cls(
                    "PS-214",
                    str(repo / "pyproject.toml"),
                    (
                        f"`[project.optional-dependencies.{extra_name}]` is an "
                        f"empty list (`{extra_name} = []`). A `pip install "
                        f"<pkg>[{extra_name}]` remedy for this extra installs "
                        f"ZERO packages — anyone who runs it stays exactly as "
                        f"broken and believes they already tried the fix. "
                        f"Either populate the extra with its real dependency, "
                        f"or delete the extra (and any source text that "
                        f"recommends installing it). See scitex-writer PR #322 "
                        f"for the reference incident + fix, and the operator "
                        f"directive: extras should be ALL-OR-NOTHING (one "
                        f"`[all]` extra, no fine-grained per-feature menu; "
                        f"`dev`/`docs` extras are exempt from the "
                        f"all-or-nothing shape but still must not be empty)."
                    ),
                )
            )


# EOF
