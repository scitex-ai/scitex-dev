"""PS121 / PS122 — bundled Sphinx HTML + CI auto-refresh.

scitex-cloud (`apps/workspace/docs_app/`) serves per-package docs from
the in-wheel ``src/<pkg>/_sphinx_html/`` bundle. The canonical refresh
path is a GitHub Actions workflow (`.github/workflows/docs.yml`) that
rebuilds and auto-commits the bundle on every push to main/develop.

Both checks are warn-only and only fire when the package has a Sphinx
source tree (``docs/sphinx/conf.py``). Packages without docs simply
skip both rules — they're invisible in the docs site, which is fine
for low-doc utility packages.
"""

from __future__ import annotations

from pathlib import Path


def _has_sphinx_source(repo: Path) -> bool:
    return (repo / "docs" / "sphinx" / "conf.py").is_file()


def _src_pkg_with_html(repo: Path) -> Path | None:
    """Return the first ``src/<pkg>/`` dir whose ``_sphinx_html/index.html``
    exists, else None."""
    src = repo / "src"
    if not src.is_dir():
        return None
    for child in src.iterdir():
        if not child.is_dir():
            continue
        if (child / "_sphinx_html" / "index.html").is_file():
            return child / "_sphinx_html"
    return None


def check_sphinx_html(repo: Path, violation_cls: type, out: list) -> None:
    """Append PS121 / PS122 violations.

    PS121 — sphinx source exists but ``_sphinx_html/index.html`` is missing.
    PS122 — sphinx source exists but ``.github/workflows/docs.yml`` is missing.
    """
    if not _has_sphinx_source(repo):
        return

    if _src_pkg_with_html(repo) is None:
        out.append(
            violation_cls(
                "PS121",
                str(repo / "src"),
                (
                    "package has docs/sphinx/conf.py but no "
                    "src/<pkg>/_sphinx_html/index.html bundled. scitex-cloud "
                    "serves docs from the in-wheel _sphinx_html/ — without "
                    "it the package is invisible at "
                    "https://scitex.ai/apps/docs/. Refresh via the canonical "
                    "CI workflow (.github/workflows/docs.yml) or manually."
                ),
            )
        )

    docs_yml = repo / ".github" / "workflows" / "docs.yml"
    if not docs_yml.is_file():
        out.append(
            violation_cls(
                "PS122",
                str(docs_yml),
                (
                    "package has docs/sphinx/ but no docs.yml CI workflow. "
                    "Auto-refreshing _sphinx_html/ in CI is the canonical "
                    "pattern (see scitex-ssh as reference). Manual refresh "
                    "drifts; CI keeps the bundle fresh on every push to "
                    "main/develop."
                ),
            )
        )
