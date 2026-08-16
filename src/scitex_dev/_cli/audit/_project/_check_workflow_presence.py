"""PS-165 — `.github/workflows/` presence rules.

Every SciTeX package must ship a baseline set of GitHub Actions
workflows so the ecosystem-wide audit dashboard, badges, and branch
protection have consistent rows to gate on.

Spec: ``_skills/general/02_package/07b_workflow-presence.md``.

Severity W during adoption — packages can rename existing workflows
gradually. Promote to E once the ecosystem has converged.

Retired: this check used to key its required set on a per-package
``[tool.scitex_dev] category`` declaration in ``pyproject.toml``
(``library`` / ``cli-tool`` / ``infrastructure``, defaulting to
``library``). A census of the ecosystem found ZERO repos declaring
that key, so the branch never fired and every package was audited
against the ``library`` baseline anyway. The read path and its
``cli-tool`` branch were removed rather than left as decoration.

Note this is unrelated to two other, live classification channels:
``project-type`` in ``<repo>/.scitex/dev/config.yaml`` (consumed by
the auditor's loader) and the ``category`` field on
``scitex_dev._ecosystem.ECOSYSTEM`` (a hardcoded registry with its own
``umbrella`` / ``external-lib`` / ``dataset`` vocabulary).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Required workflow patterns (filename stem regex → human description)
# ---------------------------------------------------------------------------

# Each requirement is a regex matched against the basename (lower-case).
# A workflow is considered "present" if at least one file matches.
#
# Patterns are deliberately permissive of the matrix/runtime suffix
# documented in PS-164 (e.g. `pytest-matrix-on-ubuntu-py3-11-3-12-3-13.yml`
# OR `pytest-on-ubuntu-latest.yml`).
_BASELINE_REQUIREMENTS: list[tuple[str, re.Pattern[str], str]] = [
    (
        "cla",
        re.compile(r"^cla\.ya?ml$"),
        "CLA Assistant (`cla.yml`)",
    ),
    (
        "pytest",
        re.compile(r"^pytest-.*\.ya?ml$"),
        "pytest matrix (`pytest-*-on-*.yml`)",
    ),
    (
        "import-smoke",
        re.compile(r"^import-smoke-.*\.ya?ml$"),
        "import smoke (`import-smoke-*-on-*.yml`)",
    ),
    (
        "pypi-publish",
        re.compile(r"^pypi-publish-.*\.ya?ml$"),
        "PyPI publish on tag (`pypi-publish-*-on-tag.yml`)",
    ),
    # NEUTRAL NAME, NOT A PACKAGE NAME. The pattern used to demand
    # `scitex-dev-(quality-audit|audit-all)-*`, which NOTHING matched: a census
    # of the ecosystem found EIGHT packages shipping a quality-audit workflow
    # and ZERO satisfying the rule, across three competing spellings —
    #
    #     quality-audit-on-ubuntu-latest.yml            scitex-app, scitex-writer
    #     quality-audit.yml                             scitex-org-github
    #     <something>-quality-audit-on-ubuntu-latest.yml scitex-ssh, scitex-hub,
    #                                                    scitex-todo, scitex-cards
    #
    # so the rule warned every package while the reference implementations
    # violated it. A rule nobody satisfies is not a standard, it is noise that
    # trains readers to skip the whole check.
    #
    # WHY NEUTRAL RATHER THAN PER-PACKAGE, which is the tempting fix: a package
    # name in the filename is copied wrong the first time someone clones a
    # workflow. Measured — scitex-cloud ships
    # `scitex-hub-quality-audit-on-ubuntu-latest.yml`, named after a DIFFERENT
    # package, because it was copied from scitex-hub. The filename now lies
    # about which repo it belongs to, and nothing catches it because the name
    # is decoration. Inside `<repo>/.github/workflows/` the repo is already
    # unambiguous; repeating it can only ever be redundant or wrong.
    # (Operator, 2026-08-16: 「少なくともパッケージネームではありえない」.)
    (
        "quality-audit",
        re.compile(r"^(quality-audit|audit-all)([-.].*)?\.ya?ml$"),
        "quality audit (`quality-audit-on-*.yml`)",
    ),
    (
        "sync-main",
        re.compile(r"^sync-main-.*\.ya?ml$"),
        "sync main → release tag (`sync-main-to-release-tag-on-push.yml`)",
    ),
]

# Only required if the repo ships docs/ (i.e. has Sphinx)
_RTD_REQUIREMENT: tuple[str, re.Pattern[str], str] = (
    "rtd-sphinx",
    re.compile(r"^rtd-(sphinx-)?build-.*\.ya?ml$"),
    "RTD Sphinx build (`rtd-sphinx-build-on-*.yml`)",
)

def _workflow_filenames(repo: Path) -> list[str]:
    wf_dir = repo / ".github" / "workflows"
    if not wf_dir.is_dir():
        return []
    return [
        p.name.lower()
        for p in wf_dir.iterdir()
        if p.is_file() and p.suffix in {".yml", ".yaml"}
    ]


def _has_docs_dir(repo: Path) -> bool:
    """True if the repo ships a Sphinx-style docs/ tree."""
    docs = repo / "docs"
    if not docs.is_dir():
        return False
    # Heuristic: docs/ with conf.py OR docs/source/conf.py
    return (docs / "conf.py").is_file() or (docs / "source" / "conf.py").is_file()


def check_ps165_workflow_presence(
    repo: Path, violation_cls: type, out: list[Any]
) -> None:
    """PS-165 — required workflows are present.

    Emits one Violation per missing required workflow.
    """
    filenames = _workflow_filenames(repo)

    if not filenames:
        # No .github/workflows/ at all — surface a single violation rather
        # than spamming one-per-pattern; PS-101/PS-104-class checks should
        # already complain about a repo without CI.
        out.append(
            violation_cls(
                "PS-165",
                str(repo / ".github" / "workflows"),
                (
                    "no GitHub Actions workflows found — every SciTeX package "
                    "must ship the baseline workflow set. See "
                    "_skills/general/02_package/07b_workflow-presence.md."
                ),
            )
        )
        return

    requirements = list(_BASELINE_REQUIREMENTS)
    if _has_docs_dir(repo):
        requirements.append(_RTD_REQUIREMENT)

    for _key, pattern, label in requirements:
        if not any(pattern.match(name) for name in filenames):
            out.append(
                violation_cls(
                    "PS-165",
                    str(repo / ".github" / "workflows"),
                    (
                        f"missing required workflow: {label}. See "
                        f"_skills/general/02_package/07b_workflow-presence.md."
                    ),
                )
            )
