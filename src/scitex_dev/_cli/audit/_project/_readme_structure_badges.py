"""README badge-block rules — PS-155, PS-157..158, PS-162..163.

One rule-family per module (see `_readme_structure_shared` for the split
rationale). Every rule here is scoped to the canonical
`<!-- scitex-badges:start -->...<!-- scitex-badges:end -->` block and is
skipped entirely when that block is absent.

PS-155: the badge row must split into exactly two `<p align="center">`
rows (row 1: PyPI / Python / RTD; row 2: Tests / Install Test /
Coverage). See scitex-io README header for the canonical form.

PS-157: the codecov badge URL must pin a branch.

PS-158: the RTD badge should use the shields.io proxy so the label can
be customised.

PS-162: the block must contain a Codecov coverage badge.

PS-163: the block must contain a Read-the-Docs badge. Acceptable:
`readthedocs.org/projects/<pkg>/badge` OR `img.shields.io/readthedocs/<pkg>`.
"""

from __future__ import annotations

import re

from ._readme_structure_shared import RE_BADGES_BLOCK


_RE_P_CENTER_OPEN = re.compile(r"<p\s+align\s*=\s*['\"]center['\"]\s*>", re.IGNORECASE)

# PS-157 — codecov badge URL must pin a branch.
# Bad shape: codecov.io/gh/<owner>/<pkg>/graph/badge.svg
# Good shape: codecov.io/gh/<owner>/<pkg>/branch/<name>/graph/badge.svg
_RE_CODECOV_BADGE_UNBRANCHED = re.compile(
    r"codecov\.io/gh/[^/\s]+/[^/\s]+/graph/badge\.svg",
    re.IGNORECASE,
)
_RE_CODECOV_BADGE_BRANCHED = re.compile(
    r"codecov\.io/gh/[^/\s]+/[^/\s]+/branch/[^/\s]+/graph/badge\.svg",
    re.IGNORECASE,
)

# PS-158 — RTD badge should use shields.io proxy for the "Read the Docs"
# label. readthedocs.org's own /badge endpoint bakes "docs" into the
# SVG and can't be customized.
_RE_RTD_BADGE_OWN = re.compile(
    r"readthedocs\.org/projects/[^/\s]+/badge",
    re.IGNORECASE,
)
_RE_RTD_BADGE_SHIELDS = re.compile(
    r"img\.shields\.io/readthedocs/[^?\s\"']+",
    re.IGNORECASE,
)

# PS-162 — Codecov badge presence inside the canonical badges block.
_RE_CODECOV_BADGE_PRESENT = re.compile(
    r"codecov\.io/gh/[^/\s\"']+/[^/\s\"']+",
    re.IGNORECASE,
)

# PS-163 — Read-the-Docs badge presence inside the canonical badges block.
_RE_RTD_BADGE_PRESENT = re.compile(
    r"readthedocs\.org/projects/[^/\s\"']+/badge"
    r"|img\.shields\.io/readthedocs/[^?\s\"']+",
    re.IGNORECASE,
)


def check_badges(text: str, readme_path: str, violation_cls: type, out: list) -> None:
    """Emit PS-155 / PS-157 / PS-158 / PS-162 / PS-163 violations."""
    m_block = RE_BADGES_BLOCK.search(text)
    if m_block is None:
        return
    inner = m_block.group(1)

    # ---- PS-155: badge row must be two <p align="center"> rows -----------
    p_count = len(_RE_P_CENTER_OPEN.findall(inner))
    if p_count != 2:
        out.append(
            violation_cls(
                "PS-155",
                readme_path,
                (
                    f"badge row should split into two centered rows "
                    f'(found {p_count} `<p align="center">` blocks)'
                    f" — row 1: PyPI / Python / Read the Docs, row "
                    f"2: Tests / Install Test / Coverage. See "
                    f"scitex-io README header for the canonical form"
                ),
            )
        )

    # ---- PS-157: codecov badge URL should pin a branch ---------
    # codecov.io/.../graph/badge.svg defaults to the repo's codecov-side
    # default branch (usually 'main'). If coverage is only uploaded to
    # 'develop', the badge resolves as 'unknown'. Pin
    # /branch/<name>/graph/badge.svg to follow a known branch.
    if _RE_CODECOV_BADGE_UNBRANCHED.search(
        inner
    ) and not _RE_CODECOV_BADGE_BRANCHED.search(inner):
        out.append(
            violation_cls(
                "PS-157",
                readme_path,
                (
                    "codecov badge URL is unbranched "
                    "(`codecov.io/.../graph/badge.svg`) — pin a "
                    "branch to avoid 'unknown' when uploads only "
                    "go to develop: `codecov.io/.../branch/develop"
                    "/graph/badge.svg`. See scitex-io README "
                    "header."
                ),
            )
        )

    # ---- PS-158: RTD badge should use shields.io proxy --------
    # readthedocs.org/projects/<pkg>/badge?version= bakes the literal
    # label 'docs' into the SVG. The shields.io proxy supports a
    # `?label=Read%20the%20Docs` param so the visible label matches the
    # project name users actually look for.
    if _RE_RTD_BADGE_OWN.search(inner) and not _RE_RTD_BADGE_SHIELDS.search(inner):
        out.append(
            violation_cls(
                "PS-158",
                readme_path,
                (
                    "RTD badge uses readthedocs.org/.../badge which "
                    "bakes the label 'docs' into the SVG — switch "
                    "to the shields.io proxy with a 'Read the Docs' "
                    "label: "
                    "`img.shields.io/readthedocs/<pkg>?label=Read"
                    "%20the%20Docs`. See scitex-io README header."
                ),
            )
        )

    # ---- PS-162: Codecov badge presence ---------------------------
    if not _RE_CODECOV_BADGE_PRESENT.search(inner):
        out.append(
            violation_cls(
                "PS-162",
                readme_path,
                (
                    "README badge block is missing a Codecov coverage "
                    "badge — every public scitex package should expose "
                    "CI coverage. Add: "
                    "<a href='https://codecov.io/gh/<owner>/<pkg>'>"
                    "<img src='https://codecov.io/gh/<owner>/<pkg>/"
                    "branch/develop/graph/badge.svg' alt='Coverage'>"
                    "</a>. See scitex-io README header."
                ),
            )
        )

    # ---- PS-163: Read-the-Docs badge presence ---------------------
    if not _RE_RTD_BADGE_PRESENT.search(inner):
        out.append(
            violation_cls(
                "PS-163",
                readme_path,
                (
                    "README badge block is missing a Read-the-Docs "
                    "badge — every scitex package shipping RTD docs "
                    "should expose the build status. Add: "
                    "<a href='https://<pkg>.readthedocs.io/en/latest/'>"
                    "<img src='https://img.shields.io/readthedocs/"
                    "<pkg>?label=Read%20the%20Docs' alt='Read the "
                    "Docs'></a>. See scitex-io README header."
                ),
            )
        )
