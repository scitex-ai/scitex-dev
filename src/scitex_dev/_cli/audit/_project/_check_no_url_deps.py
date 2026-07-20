# -*- coding: utf-8 -*-
"""PS-216 — direct-URL / VCS dependency in publishable metadata.

Symptom this prevents (a recurring, silent release blocker): a package
declares a dependency in its **publishable** `pyproject.toml` metadata
using a PEP 508 *direct reference* — a VCS URL (`pkg @ git+https://...`),
a plain URL (`pkg @ https://.../x.whl`), or a `file://` reference. Such
requirements are perfectly installable with `pip`, so they pass local
testing and CI — but **PyPI/twine REJECT them on upload** (direct
references are forbidden in distributions; see PEP 440 / the "Invalid
value for requires_dist. Can't have direct dependency" upload error).
The rejection happens at publish time, silently blocking the release of
an otherwise-green package.

Crucially this holds even when the offending requirement lives inside an
`[project.optional-dependencies]` extra (`foo = ["x @ git+https://..."]`)
— twine validates every requirement across every table, so an extra is
NOT a safe harbour for a direct reference.

Reference incident: a leaf package pinned a peer via `pkg @ git+https://`
inside an extra; local installs worked, the PyPI publish job failed on
upload, and the release stalled until the dep was re-pinned to a
published version. This rule is the systemic guard for that class.

Decision rule the auditor enforces
----------------------------------

Scan BOTH `[project].dependencies` AND every group in
`[project.optional-dependencies]`. For each PEP 508 requirement string,
flag it (PS-216) if it carries a direct reference, i.e. ANY of:

  - a VCS scheme: `git+`, `hg+`, `svn+`, `bzr+`
  - a URL scheme: `http://`, `https://`, `file://`
  - the PEP 508 `name @ <url>` direct-reference separator (` @ `)

Do NOT flag ordinary version specifiers (`>=`, `==`, `~=`, `!=`),
extras (`pkg[foo]`), or environment markers (`; python_version >= ...`).
The environment marker is stripped before scanning so a marker's own
text can never trigger a false positive. A local *editable* path is not
expressible in these dependency tables, so there is nothing to ignore
there.

Heuristic notes
---------------

- The auditor reads `pyproject.toml` only — it does not import the
  package, so it is safe to run on broken trees.
- A missing `[project]` table or dependency tables is not a violation.
- Severity is a flat "E" (blocking): a direct reference is an
  unambiguous, hard release blocker — there is no interpretation under
  which a distribution carrying one uploads successfully — so unlike the
  warn-first empty-extra rules (PS-214/PS-215) there is no baseline
  escalation to soften the first sighting.
"""

from __future__ import annotations

from pathlib import Path

try:
    import tomllib  # 3.11+
except ImportError:  # pragma: no cover — 3.10 / 3.9 path
    import tomli as tomllib  # type: ignore[no-redef]

# VCS + URL schemes that make a PEP 508 requirement a direct reference.
_URL_SCHEMES = (
    "git+",
    "hg+",
    "svn+",
    "bzr+",
    "http://",
    "https://",
    "file://",
)


def _parse_pyproject(repo: Path) -> dict | None:
    pp = repo / "pyproject.toml"
    if not pp.is_file():
        return None
    try:
        return tomllib.loads(pp.read_text(encoding="utf-8"))
    except Exception:
        return None


def _direct_reference(req: str) -> str | None:
    """Return the offending token if `req` is a direct reference, else None.

    The environment marker (everything after `;`) is stripped first so a
    marker's own text (e.g. `python_version`) can never trip detection.
    """
    if not isinstance(req, str):
        return None
    core = req.split(";", 1)[0].strip()
    for scheme in _URL_SCHEMES:
        if scheme in core:
            return scheme
    # PEP 508 direct-reference form: `name @ <url>`. The ` @ ` separator is
    # reserved for URL requirements — a normal specifier never contains it.
    if " @ " in core:
        return "@"
    return None


def _iter_dep_tables(project: dict):
    """Yield `(table_label, [requirement, ...])` for every scannable table.

    Covers `[project].dependencies` and each `[project.optional-dependencies]`
    group. Non-list values (e.g. a `dynamic` marker) are skipped.
    """
    deps = project.get("dependencies")
    if isinstance(deps, list):
        yield "[project.dependencies]", deps

    od = project.get("optional-dependencies", {}) or {}
    if isinstance(od, dict):
        for extra_name in sorted(od):
            group = od[extra_name]
            if isinstance(group, list):
                yield f"[project.optional-dependencies.{extra_name}]", group


def check_ps216_no_url_deps(
    repo: Path,
    violation_cls: type,
    out: list,
) -> None:
    """Append PS-216 violations for direct-URL/VCS deps in publishable metadata.

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

    where = str(repo / "pyproject.toml")
    for table_label, requirements in _iter_dep_tables(project):
        for req in requirements:
            token = _direct_reference(req)
            if token is None:
                continue
            out.append(
                violation_cls(
                    "PS-216",
                    where,
                    (
                        f"direct-reference dependency `{req}` in "
                        f"{table_label} carries a URL/VCS reference "
                        f"(`{token}`). PyPI/twine REJECT direct references "
                        f"on upload — even inside "
                        f"`[project.optional-dependencies]` — so this "
                        f"silently blocks the PyPI publish of an otherwise "
                        f"green package (the release fails with \"Invalid "
                        f"value for requires_dist. Can't have direct "
                        f"dependency\"). Fix: pin a PUBLISHED version "
                        f"instead (e.g. `pkg>=X.Y`), or move the URL/VCS "
                        f"dependency into a non-published, dev-only context "
                        f"(a requirements-dev.txt / constraints file) that "
                        f"is never part of the built distribution."
                    ),
                )
            )


# Rule definition, CO-LOCATED with its check.
#
# `_extra_rules.py` (the sidecar that exists because `_registry.py` blew the
# 512-line cap) is now itself over the cap, so — following the precedent set by
# `_check_precommit_hooks.HOOK_RULES` — this rule ships co-located with its
# check module. `_registry.py` merges `URL_DEP_RULES` exactly as it merges
# `EXTRA_RULES` / `HOOK_RULES`.
#
# Severity E (error): the `_SEVERITY_OVERRIDES` doctrine defaults a rule with a
# concrete mechanical spec to E; warn-first is for rules carrying
# false-positive risk. A direct reference is unambiguously release-breaking (no
# distribution carrying one uploads to PyPI), and the check strips environment
# markers before scanning so a marker's text cannot cause a false positive. No
# scitex-* package carries a direct-URL dep in its dependency tables today, so
# shipping at E wedges nobody's publish.
#
# (code, section, message, severity, slug)
URL_DEP_RULES: list[tuple[str, str, str, str, str]] = [
    (
        "PS-216",
        "§3",
        (
            "direct-URL/VCS dependency in publishable metadata: a "
            "requirement in `[project].dependencies` or a "
            "`[project.optional-dependencies]` group carries a PEP 508 "
            "direct reference — a VCS URL (`pkg @ git+https://...`), a "
            "plain `http(s)://` / `file://` URL, or the `name @ <url>` "
            "form. PyPI/twine REJECT direct references on upload (even "
            "inside an extra), so it silently blocks the PyPI publish of "
            "an otherwise-green package (\"Invalid value for "
            "requires_dist. Can't have direct dependency\"). Fix: pin a "
            "PUBLISHED version (`pkg>=X.Y`), or move the URL/VCS dep into "
            "a non-published dev-only context (requirements-dev.txt / "
            "constraints file) never built into the distribution."
        ),
        "E",
        "direct-url-dep-in-publishable-metadata",
    ),
]


# EOF
