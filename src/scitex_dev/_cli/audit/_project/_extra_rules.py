"""Sidecar registry for newly-added audit rules.

`_audit.py` is over the 512-line file cap, so further Rule definitions
land here and are merged at import time. Each entry is the same shape
``_audit.RULES`` expects: ``(code, section, message, severity, slug)``.

Today's contents:

- PS-165 — workflow-presence (per category)
- PS-166 — readme-badge-label-mismatch
- PS-167 — readme-badge-layout
- PS-168 — workflow-secret-env-prefix-missing

When `_audit.py` is split per-rule (see GITIGNORED/REFACTORING.md), this
sidecar can be removed and each rule co-located with its check module.
"""

from __future__ import annotations

from typing import List, Tuple

# (code, section, message, severity, slug)
EXTRA_RULES: List[Tuple[str, str, str, str, str]] = [
    (
        "PS-165",
        "§2",
        (
            "missing required GitHub Actions workflow for the package's "
            "category. Every SciTeX package must ship a baseline set of "
            "workflows (cla, pytest matrix, import-smoke, pypi publish, "
            "scitex-dev quality audit, sync-main-to-release-tag; plus "
            "rtd-sphinx-build if docs/ ships, plus runtime CLI smoke for "
            'category = "cli-tool"). Declare the category in '
            'pyproject.toml under `[tool.scitex_dev] category = "..."` '
            "(defaults to `library`). Severity W during adoption — see "
            "_skills/general/02_package_07b_workflow-presence.md."
        ),
        "W",
        "workflow-presence-missing",
    ),
    (
        "PS-166",
        "§1",
        (
            "README shields.io badge uses a non-standard label. The "
            "ecosystem standardizes on short labels: pypi, python, docs, "
            "tests, install-check, quality, cov. Add `?label=<short>` to "
            "each shields.io badge URL. Reference: scitex-agent-container "
            "README badge block. Severity W during adoption — see "
            "_skills/general/02_package_12_workflows-naming.md "
            "§Standardized badge labels."
        ),
        "W",
        "readme-badge-label-mismatch",
    ),
    (
        "PS-167",
        "§1",
        (
            "README badge block does not match the canonical SAC "
            "layout. Every SciTeX package README MUST wrap its badges "
            "in `<!-- scitex-badges:start -->...<!-- scitex-badges:end "
            '-->` markers containing exactly TWO `<p align="center">` '
            "rows: row 1 = package-metadata badges "
            "(pypi/python/docs), row 2 = CI/health badges "
            "(tests/install-check/quality/cov). All badge images must "
            "be served from `img.shields.io/...` so they carry "
            "explicit `?label=<short>` labels (see PS-166). Reference: "
            "scitex-agent-container/README.md. Severity W during "
            "adoption — see _skills/general/04_docs_01_readme.md and "
            "_skills/general/04_docs_01_readme_template.md."
        ),
        "W",
        "readme-badge-layout",
    ),
    (
        "PS-168",
        "§1",
        (
            "GitHub Actions workflow references a `${{ secrets.<NAME> }}` "
            "or `${{ env.<NAME> }}` whose <NAME> is per-project but does "
            "not carry the package's `<PKG>_` prefix (and is not in the "
            "cross-cutting exception list — CLAUDE_CODE_CREDENTIALS_JSON, "
            "GH_TOKEN, CODECOV_TOKEN, GHCR_PAT, GITHUB_TOKEN, NPM_TOKEN, "
            "PYPI_API_TOKEN, ACTIONS_*_DEBUG). Without the prefix, "
            "`scitex-dev creds rotate-all` cannot distinguish the secret "
            "from the ecosystem-wide rotate target and silently skips it. "
            "Rename via `gh secret set <PKG>_<NAME>` + workflow `sed`. See "
            "_skills/general/02_package_14_workflow-secret-env-prefix.md."
        ),
        "E",
        "secret-env-prefix-missing",
    ),
]
