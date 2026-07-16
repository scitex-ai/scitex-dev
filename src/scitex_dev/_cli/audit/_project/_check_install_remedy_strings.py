# -*- coding: utf-8 -*-
"""PS-215 — broken install-remedy string.

Companion source-side check for PS-214 (`_check_empty_extras.py`):
even a NON-empty extras table can still ship a broken remedy if the
source text (an error message, a CLI hint, a README line) names an
extra that doesn't exist, or is misspelled, or has since been emptied
/ renamed and the message never got updated.

Symptom this prevents (the "confident output that does nothing" bug
class): package code raises/prints something like

    "Install with: pip install scitex-writer[editor]"

but `[project.optional-dependencies]` either has no `editor` group at
all, or declares it as an empty list (`editor = []`, see PS-214). A
user who runs the suggested command either gets a resolver error (extra
doesn't exist) or a silent no-op (extra is empty) — in the empty case
`pip` exits 0 with nothing installed, so the user has no signal they've
been given a dead remedy. They believe they already tried the cure.

Reference incident: scitex-writer's `_server.py` / `apps.py` / CLI told
users to run `pip install scitex-writer[editor]` to get `scitex-app`
installed, while `editor = []` in pyproject.toml (see PS-214's
docstring and scitex-writer PR #322, the reference fix).

Decision rule the auditor enforces:

  Scan the repo's `.py` source and `.md` docs for any string matching
  the shape `[uv ]pip install <pkg>[<extra>]` (single- or
  double-quoted, or bare). For every match where `<pkg>` refers to THIS
  same package (by distribution name, hyphen/underscore-insensitive):

    - if `<extra>` is not a key in this repo's
      `[project.optional-dependencies]` → PS-215 (extra doesn't exist)
    - if `<extra>` IS a key but its list is empty → PS-215 (extra is
      empty; composes with PS-214 — the same empty group also fires
      PS-214 on its own, this rule catches every *quoted remedy* that
      names it)

  Remedies naming a DIFFERENT package (a peer's extra, e.g. "this repo's
  CLI recommends `pip install some-other-pkg[extra]`") are intentionally
  NOT checked — verifying a peer's pyproject is out of scope for a
  cheap, single-repo audit pass.

Heuristic notes
----------------

- Text-based regex scan (not AST) — deliberately simple, matching the
  shape of the remedy string itself rather than trying to prove it is
  reachable/executed. A regex miss is cheap; false negatives here are
  acceptable since PS-214 independently catches the empty-extra root
  cause even with zero source references.
- `<extra>` may be a comma-separated list inside the brackets
  (`pkg[a,b]`); each name is checked independently.
- Scans `.py` files under `src/` (skipping build/venv/cache dirs) and
  `.md` files at the repo root and under `docs/` — mirrors the existing
  README-scanning checks (e.g. `_check_readme_badges.py`), which already
  treat markdown as a text-scan surface, not just `.py` source.

Severity: new vs. pre-existing
-------------------------------

Same rationale and mechanism as PS-214 (see that module's docstring): a
flat `severity = "W"` made this rule invisible in practice. Every
violation is re-classified against a git baseline (default `develop`,
see `_new_vs_baseline.escalate_new_violations`) — genuinely NEW relative
to baseline → "E" (blocking); already present at baseline → stays at the
rule's registered default, "W" (warn, non-blocking).
"""

from __future__ import annotations

import re
from pathlib import Path

try:
    import tomllib  # 3.11+
except ImportError:  # pragma: no cover — 3.10 path
    import tomli as tomllib  # type: ignore[no-redef]

from ._new_vs_baseline import DEFAULT_BASELINE_REF, escalate_new_violations


_INSTALL_REMEDY_RE = re.compile(
    r"""(?:uv\s+)?pip\s+install\s+['"]?([A-Za-z0-9_.\-]+)\[\s*([A-Za-z0-9_,\-\s]+?)\s*\]"""
)

_SKIP_DIR_SEGMENTS = frozenset(
    {
        "__pycache__",
        "build",
        "dist",
        ".tox",
        "site-packages",
        ".venv",
        "venv",
        ".git",
        "node_modules",
    }
)


def _parse_pyproject(repo: Path) -> dict | None:
    pp = repo / "pyproject.toml"
    if not pp.is_file():
        return None
    try:
        return tomllib.loads(pp.read_text(encoding="utf-8"))
    except Exception:
        return None


def _normalize(name: str) -> str:
    return name.strip().lower().replace("_", "-")


def _scan_files(repo: Path) -> list[Path]:
    files: list[Path] = []
    src_root = repo / "src"
    if src_root.is_dir():
        for py_file in sorted(src_root.rglob("*.py")):
            if any(seg in py_file.parts for seg in _SKIP_DIR_SEGMENTS):
                continue
            files.append(py_file)
    for md_file in sorted(repo.glob("*.md")):
        files.append(md_file)
    docs_root = repo / "docs"
    if docs_root.is_dir():
        for md_file in sorted(docs_root.rglob("*.md")):
            if any(seg in md_file.parts for seg in _SKIP_DIR_SEGMENTS):
                continue
            files.append(md_file)
    return files


def _collect_ps215_violations(
    repo: Path,
    distribution: str,
    violation_cls: type,
) -> list:
    """Pure collection pass — no severity escalation.

    Split out of `check_ps215_broken_install_remedy` so the escalation
    helper can re-run the SAME detection logic against a
    `worktree_at`-staged baseline checkout without recursing into
    escalation itself.
    """
    found: list = []
    meta = _parse_pyproject(repo)
    if meta is None:
        return found

    project = meta.get("project", {}) or {}
    od = project.get("optional-dependencies", {}) or {}
    if not isinstance(od, dict):
        od = {}

    self_norm = _normalize(distribution)
    seen: set[tuple[str, str, int]] = set()

    for path in _scan_files(repo):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for m in _INSTALL_REMEDY_RE.finditer(line):
                pkg, extras_blob = m.group(1), m.group(2)
                if _normalize(pkg) != self_norm:
                    continue  # peer's extra — out of scope, can't verify cheaply
                for extra_name in (e.strip() for e in extras_blob.split(",")):
                    if not extra_name:
                        continue
                    key = (str(path), extra_name, lineno)
                    if key in seen:
                        continue
                    seen.add(key)
                    try:
                        rel = path.relative_to(repo)
                    except ValueError:
                        rel = path
                    if extra_name not in od:
                        found.append(
                            violation_cls(
                                "PS-215",
                                f"{rel}:{lineno}",
                                (
                                    f"install-remedy string names "
                                    f"`{pkg}[{extra_name}]`, but "
                                    f"`{extra_name}` is not a declared "
                                    f"`[project.optional-dependencies]` extra "
                                    f"in this package's pyproject.toml. A user "
                                    f"who runs this exact command gets a "
                                    f"resolver error, not the promised fix. "
                                    f"Fix the extra name (or add the extra). "
                                    f"See scitex-writer PR #322 (reference "
                                    f"incident + fix) and PS-214."
                                ),
                            )
                        )
                    elif isinstance(od[extra_name], list) and len(od[extra_name]) == 0:
                        found.append(
                            violation_cls(
                                "PS-215",
                                f"{rel}:{lineno}",
                                (
                                    f"install-remedy string names "
                                    f"`{pkg}[{extra_name}]`, but "
                                    f"`[project.optional-dependencies."
                                    f"{extra_name}]` is an EMPTY list in this "
                                    f"package's pyproject.toml. `pip install "
                                    f"{pkg}[{extra_name}]` installs ZERO "
                                    f"packages — the user runs the suggested "
                                    f"fix, pip exits 0, and nothing changes; "
                                    f"they now believe they already tried the "
                                    f"cure. Populate the extra with its real "
                                    f"dependency (see PS-214). Reference "
                                    f"incident: scitex-writer PR #322."
                                ),
                            )
                        )
    return found


def check_ps215_broken_install_remedy(
    repo: Path,
    distribution: str,
    violation_cls: type,
    out: list,
    *,
    baseline_ref: str = DEFAULT_BASELINE_REF,
) -> None:
    """Append PS-215 violations for self-referential dead install remedies.

    Parameters
    ----------
    repo : Path
        Repository root (the dir containing `pyproject.toml`).
    distribution : str
        Distribution name, e.g. ``"scitex-writer"``.
    violation_cls : type
        The auditor's ``Violation`` dataclass ``(rule, where, detail)``.
    out : list
        Violations are appended in place (project-auditor convention).
    baseline_ref : str
        Git ref to diff against for new-vs-existing severity escalation
        (default ``"develop"``; falls back to ``"origin/<baseline_ref>"``
        — see `_new_vs_baseline.escalate_new_violations`).
    """
    found = _collect_ps215_violations(repo, distribution, violation_cls)
    if not found:
        return

    escalate_new_violations(
        repo,
        found,
        ("PS-215",),
        lambda base_repo: _collect_ps215_violations(
            base_repo, distribution, violation_cls
        ),
        baseline_ref=baseline_ref,
    )
    out.extend(found)


# EOF
