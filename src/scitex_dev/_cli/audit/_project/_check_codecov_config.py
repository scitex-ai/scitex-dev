"""PS-171 — Codecov config present + canonically shaped.

Spec: ``_skills/general/02_package_11_ci-and-codecov.md``.

Every SciTeX package that uploads coverage from CI (a workflow whose
text references ``codecov``) must ship a repo-root ``codecov.yml`` so
the coverage gate, PR comment, and unbranched badge behave consistently
across the ecosystem. The canonical shape pins ``codecov.branch:
develop`` (because ``main`` is only a release-mirror that lags
``develop``) and ignores the non-executable surfaces
(``_sphinx_html/``, ``_skills/``, ``_completion.py``, ``tests/``,
``examples/``).

This rule is purely a *file* check on the repo working tree — it does
NOT touch GitHub state. The two GitHub-state facets of Codecov are
handled elsewhere:

- ``CODECOV_TOKEN`` repo secret — reported by the ecosystem
  ``audit-github-state`` command (informational; tokenless upload works
  for public repos).
- The Codecov GitHub App install — a user-web-only action; no PAT and
  no audit rule can install it. The "Please install the Codecov app"
  PR-comment warning is purely App-not-installed; the upload itself
  still succeeds.

Detection:

- ``codecov`` referenced by at least one ``.github/workflows/*.yml``
  (i.e. the package actually uploads coverage) AND
- no ``codecov.yml`` (or ``.codecov.yml``) at the repo root.

When the file exists, a light shape check warns when the canonical
``codecov.branch: develop`` line is missing — the most common drift
that points the unbranched badge at the stale ``main`` value.

Severity W during adoption — packages add the file gradually. Promote
to E once the ecosystem has converged.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# A workflow that uploads coverage almost always mentions "codecov"
# (the action `codecov/codecov-action@vN` or the service name). Match
# case-insensitively against the raw workflow text.
_CODECOV_REF_RE = re.compile(r"codecov", re.IGNORECASE)

# Canonical config pins develop as the badge/headline branch.
_BRANCH_DEVELOP_RE = re.compile(r"^\s*branch\s*:\s*develop\s*$", re.MULTILINE)


def _codecov_yml(repo: Path) -> Path | None:
    """Return the repo-root codecov config path if present, else None."""
    for name in ("codecov.yml", "codecov.yaml", ".codecov.yml", ".codecov.yaml"):
        p = repo / name
        if p.is_file():
            return p
    return None


def _uploads_coverage(repo: Path) -> bool:
    """True if any workflow text references codecov (i.e. uploads coverage)."""
    wf_dir = repo / ".github" / "workflows"
    if not wf_dir.is_dir():
        return False
    for p in wf_dir.iterdir():
        if not (p.is_file() and p.suffix in {".yml", ".yaml"}):
            continue
        try:
            txt = p.read_text(errors="ignore")
        except OSError:
            continue
        if _CODECOV_REF_RE.search(txt):
            return True
    return False


def check_ps171_codecov_config(repo: Path, violation_cls: type, out: list[Any]) -> None:
    """PS-171 — Codecov config present + canonically shaped.

    Emits a violation when a coverage-uploading package lacks a
    ``codecov.yml`` at the repo root, and (when present) when the
    canonical ``branch: develop`` pin is missing.
    """
    if not _uploads_coverage(repo):
        # No coverage upload → no codecov.yml required.
        return

    cfg = _codecov_yml(repo)
    if cfg is None:
        out.append(
            violation_cls(
                "PS-171",
                str(repo / "codecov.yml"),
                (
                    "CI uploads coverage to Codecov but no `codecov.yml` at "
                    "the repo root. Add the canonical config (pins "
                    "`codecov.branch: develop` so the unbranched badge "
                    "follows develop, and ignores _sphinx_html/ _skills/ "
                    "_completion.py tests/ examples/). See "
                    "_skills/general/02_package_11_ci-and-codecov.md."
                ),
            )
        )
        return

    try:
        txt = cfg.read_text(errors="ignore")
    except OSError:
        return

    if not _BRANCH_DEVELOP_RE.search(txt):
        out.append(
            violation_cls(
                "PS-171",
                str(cfg),
                (
                    "codecov.yml present but missing the canonical "
                    "`codecov.branch: develop` pin. Without it the "
                    "unbranched badge follows `main` (a release-mirror "
                    "that lags develop) and shows a stale number. See "
                    "_skills/general/02_package_11_ci-and-codecov.md."
                ),
            )
        )
