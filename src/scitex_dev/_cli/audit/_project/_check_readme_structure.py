"""README structure rules — PS-141..144, PS-152..155.

PS-141: README.md must have a `## Demo` OR `## Quick Start` section,
and a visual element (markdown image, non-shield HTML `<img>`, or
fenced ```mermaid block) must appear in at least one of: that section,
or `## Architecture` (the "one diagram is enough" rule, adopted
2026-05).

PS-142: README.md must have a `## Architecture` (or equivalent
`## How it works` / `## How It Works`) section. Its body must contain
at least one of: ```mermaid fence, ASCII text diagram (fenced code
block ≥10 lines), file-tree characters (`├──`/`└──`/`│`), or
`<img>` tag — UNLESS the diagram requirement is already satisfied by
the Demo or Quick Start section (PS-141's visual-anywhere fallback).

PS-143: section H2 headers appear in canonical order. The expected
order (skipping any optional or omitted section) is:
    Problem and Solution → Quick Start / Demo → Installation →
    Architecture / How it works → <N> Interfaces → Part of SciTeX

PS-144: `## Problem and Solution` table cells must (a) contain at
least one `**bold**` span, (b) keep bold coverage ≤ 30% of cell
text, and (c) stay ≤ 200 characters per cell (one sentence per cell).

PS-152: split `## Problem` + `## Solution` headings detected — must
be merged into a single `## Problem and Solution` table (one row
per pain point); see scitex-io README for the canonical form.

PS-153: `## Architecture` (or `## How it works`) body contains a
file-tree (`├──`/`└──`/`│`) but no ```mermaid fence — the
file tree is duplicate information already in `_sphinx_html/` and
`autoapi`. Replace with a `mermaid flowchart` showing
logic/workflow.

PS-154: `## Installation` section must start with one
`uv pip install "<pkg>[all]"` fenced bash line; any per-module
extras matrix table must live inside a `<details>` block.

PS-155: badge row between `<!-- scitex-badges:start -->` and
`<!-- scitex-badges:end -->` must split into exactly two
`<p align="center">` rows (row 1: PyPI / Python / RTD; row 2:
Tests / Install Test / Coverage). See scitex-io README header for
the canonical form.
"""

from __future__ import annotations

import re
from pathlib import Path


_README_HEAD_BYTES = 16384
_MIN_README_BYTES = 200


# --- PS-141 / PS-142 / PS-143: section presence + content ---------------------

# Canonical H2 section names (lowercased keys), with the regex matching their
# header line (line starting with `##` and the section name).
_SECTION_PATTERNS: dict[str, re.Pattern[str]] = {
    "problem_and_solution": re.compile(
        r"^##\s+Problem(?:\s+and|s\s+and)\s+Solutions?\b",
        re.MULTILINE | re.IGNORECASE,
    ),
    "installation": re.compile(r"^##\s+Installation\b", re.MULTILINE | re.IGNORECASE),
    "architecture": re.compile(
        r"^##\s+(?:Architecture|How\s+it\s+works|How\s+It\s+Works)\b",
        re.MULTILINE | re.IGNORECASE,
    ),
    "interfaces": re.compile(
        r"^##\s+(?:Three|Four|Five|Six|\d+)\s+Interfaces\b",
        re.MULTILINE | re.IGNORECASE,
    ),
    "demo": re.compile(r"^##\s+Demo(?:s|nstration)?\b", re.MULTILINE | re.IGNORECASE),
    "quick_start": re.compile(
        r"^##\s+(?:Quick\s*Start|Quickstart)\b",
        re.MULTILINE | re.IGNORECASE,
    ),
    "part_of_scitex": re.compile(
        r"^##\s+Part\s+of\s+SciTeX\b", re.MULTILINE | re.IGNORECASE
    ),
    # PS-152: standalone `## Problem` / `## Solution` headings (NOT the
    # canonical merged `## Problem and Solution`). The negative lookahead
    # rules out the merged form so this only fires on the split variants.
    "problem_only": re.compile(
        r"^##\s+Problems?(?!\s+(?:and|s\s+and)\s+Solutions?)\b",
        re.MULTILINE | re.IGNORECASE,
    ),
    "solution_only": re.compile(
        r"^##\s+Solutions?\b",
        re.MULTILINE | re.IGNORECASE,
    ),
}

# Canonical order (skipped sections collapse — only the relative order matters).
# Updated 2026-05: Quick Start now sits between Problem-and-Solution and
# Installation (replaces the old role of the primary Demo block).
_CANONICAL_ORDER = [
    "problem_and_solution",
    "quick_start",
    "demo",
    "installation",
    "architecture",
    "interfaces",
    "part_of_scitex",
]

# Visual-content patterns inside a section body (PS-141).
_RE_MD_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
_RE_HTML_IMG = re.compile(r"<img\s+[^>]*\bsrc\s*=\s*['\"]([^'\"]+)['\"]", re.IGNORECASE)
_RE_MERMAID_FENCE = re.compile(r"```mermaid\b", re.IGNORECASE)
_RE_BADGE_HOST = re.compile(
    r"img\.shields\.io|badge\.fury\.io|codecov\.io/.*badge\.svg|readthedocs\.org.*/badge",
    re.IGNORECASE,
)

# Architecture content (PS-142) — wider net than PS-141.
_RE_TREE_CHARS = re.compile(r"[├└│]")
_RE_FENCED_BLOCK = re.compile(r"```([^\n]*)\n(.*?)```", re.DOTALL)

# PS-154 — Installation: detect `uv pip install …` fenced bash blocks.
_RE_UV_PIP_INSTALL = re.compile(
    r"```(?:bash|sh|shell|console)?\s*\n[^\n`]*?uv\s+pip\s+install\b",
    re.IGNORECASE,
)
_RE_DETAILS_OPEN = re.compile(r"<details\b", re.IGNORECASE)
_RE_DETAILS_CLOSE = re.compile(r"</details\s*>", re.IGNORECASE)
# PS-154: pipe-table detection (≥2 contiguous lines starting with `|`).
_RE_PIPE_TABLE = re.compile(r"^\|[^\n]*\n\|[\s\-:|]+\|", re.MULTILINE)

# PS-155 — canonical badge block markers and inner row count.
_RE_BADGES_BLOCK = re.compile(
    r"<!--\s*scitex-badges:start\s*-->(.*?)<!--\s*scitex-badges:end\s*-->",
    re.DOTALL | re.IGNORECASE,
)
_RE_P_CENTER_OPEN = re.compile(r"<p\s+align\s*=\s*['\"]center['\"]\s*>", re.IGNORECASE)


def _slice_section(text: str, start: int, end: int) -> str:
    return text[start:end]


def _section_body(text: str, name: str) -> tuple[str, int, int] | None:
    """Return (body_text, start_idx, end_idx) of `## <name>` section, or None.

    The body runs from end-of-header-line to the next H2 header (or EOF).
    """
    pat = _SECTION_PATTERNS.get(name)
    if pat is None:
        return None
    m = pat.search(text)
    if not m:
        return None
    body_start = text.find("\n", m.end())
    body_start = body_start + 1 if body_start != -1 else m.end()
    next_h2 = re.search(r"^##\s+\S", text[body_start:], re.MULTILINE)
    body_end = body_start + next_h2.start() if next_h2 else len(text)
    return text[body_start:body_end], m.start(), body_end


def _has_visual_content(body: str) -> bool:
    """PS-141 acceptance: at least one image / mermaid / non-badge <img>."""
    if _RE_MD_IMAGE.search(body):
        return True
    if _RE_MERMAID_FENCE.search(body):
        return True
    for m in _RE_HTML_IMG.finditer(body):
        src = m.group(1)
        if not _RE_BADGE_HOST.search(src):
            return True
    return False


def _has_architecture_content(body: str) -> bool:
    """PS-142 acceptance: mermaid / file tree / ≥10-line fenced block / <img>."""
    if _RE_MERMAID_FENCE.search(body):
        return True
    if _RE_TREE_CHARS.search(body):
        return True
    for m in _RE_FENCED_BLOCK.finditer(body):
        block = m.group(2)
        if block.count("\n") >= 10:
            return True
    if _RE_HTML_IMG.search(body) or _RE_MD_IMAGE.search(body):
        return True
    return False


def _check_section_order(text: str) -> list[str]:
    """PS-143: return list[str] of out-of-order section pairs found, or [].

    Each entry is `'<found_after> appears after <found_before> but should '
    'precede it'`.
    """
    found: list[tuple[int, str]] = []  # (offset, name)
    for name, pat in _SECTION_PATTERNS.items():
        # Only canonical-order sections participate in PS-143; auxiliary
        # patterns (e.g. PS-152 `problem_only` / `solution_only`) are
        # skipped here.
        if name not in _CANONICAL_ORDER:
            continue
        m = pat.search(text)
        if m:
            found.append((m.start(), name))
    # Order observed by file offset.
    by_offset = [n for _o, n in sorted(found)]
    # Project onto canonical index list.
    rank = {n: i for i, n in enumerate(_CANONICAL_ORDER)}
    last_rank = -1
    last_name: str | None = None
    issues: list[str] = []
    for n in by_offset:
        r = rank[n]
        if r < last_rank:
            issues.append(
                f"`## {n}` appears after `## {last_name}` but should precede it"
            )
        else:
            last_rank, last_name = r, n
    return issues


# --- PS-144: Problem and Solution table cell quality -----------------------

_RE_BOLD_SPAN = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_BOLD_MAX_RATIO = 0.30
_CELL_MAX_CHARS = 200


def _table_rows(body: str) -> list[list[str]]:
    """Extract data rows (skipping header + separator) from the first
    pipe-table found in `body`. Returns a list[list[str]] of cells."""
    rows: list[list[str]] = []
    in_table = False
    for line in body.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            if in_table:
                break
            continue
        in_table = True
        # Skip separator (`|---|---|`).
        if re.fullmatch(r"\|[\s\-:|]+\|", s):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        rows.append(cells)
    return rows[1:] if rows else []  # drop header row


def _cell_bold_problems(cell: str) -> list[str]:
    """Return list of PS-144 sub-issues for a single cell."""
    out: list[str] = []
    if len(cell) > _CELL_MAX_CHARS:
        out.append(f"cell length {len(cell)} > {_CELL_MAX_CHARS} chars")
    bolds = _RE_BOLD_SPAN.findall(cell)
    if not bolds:
        out.append("no `**bold**` span")
        return out
    bold_chars = sum(len(b) for b in bolds)
    plain_chars = max(len(cell), 1)
    ratio = bold_chars / plain_chars
    if ratio > _BOLD_MAX_RATIO:
        out.append(f"bold covers {ratio * 100:.0f}% > {int(_BOLD_MAX_RATIO * 100)}%")
    return out


# --- Entry point -----------------------------------------------------------


def check_readme_structure(repo: Path, violation_cls: type, out: list) -> None:
    readme = repo / "README.md"
    if not readme.is_file():
        return
    try:
        text = readme.read_text(encoding="utf-8", errors="replace")[:_README_HEAD_BYTES]
    except OSError:
        return
    if len(text) < _MIN_README_BYTES:
        return

    # ---- PS-141 / PS-142: visual content (one diagram is enough) ----------
    # Updated 2026-05: a top-level `## Quick Start` H2 counts as the "demo"
    # role — packages that ship Quick Start need not also ship `## Demo`.
    # The "one diagram" rule: README must have a visual somewhere among
    # Demo / Quick Start / Architecture. At least one of {Demo, Quick Start}
    # must be present, and `## Architecture` (or its alias `## How it
    # works`) is still required.
    demo = _section_body(text, "demo")
    quick = _section_body(text, "quick_start")
    arch = _section_body(text, "architecture")
    demo_has_visual = demo is not None and _has_visual_content(demo[0])
    quick_has_visual = quick is not None and _has_visual_content(quick[0])
    arch_has_visual = arch is not None and _has_architecture_content(arch[0])
    visual_anywhere = demo_has_visual or quick_has_visual or arch_has_visual

    if demo is None and quick is None:
        out.append(
            violation_cls(
                "PS-141",
                str(readme),
                "missing mandatory `## Demo` or `## Quick Start` section",
            )
        )
    elif not visual_anywhere:
        out.append(
            violation_cls(
                "PS-141",
                str(readme),
                (
                    "no visual content found in `## Demo`, `## Quick "
                    "Start`, or `## Architecture` — add a markdown image, "
                    "mermaid fence, or `<img>` to at least one"
                ),
            )
        )

    # ---- PS-142: ## Architecture + diagram/tree content -------------------
    if arch is None:
        out.append(
            violation_cls(
                "PS-142",
                str(readme),
                "missing mandatory `## Architecture` (or `## How it works`) section",
            )
        )
    else:
        body, _s, _e = arch
        # PS-142 satisfied if Architecture itself has a diagram OR a
        # diagram lives in the Demo or Quick Start sections.
        if (
            not _has_architecture_content(body)
            and not demo_has_visual
            and not quick_has_visual
        ):
            out.append(
                violation_cls(
                    "PS-142",
                    str(readme),
                    (
                        "`## Architecture` section has no diagram, file "
                        "tree, mermaid fence, or `<img>`"
                    ),
                )
            )

    # ---- PS-143: section ordering ----------------------------------------
    order_issues = _check_section_order(text)
    for issue in order_issues:
        out.append(violation_cls("PS-143", str(readme), issue))

    # ---- PS-144: ## Problem and Solution table cell rules ----------------
    pas = _section_body(text, "problem_and_solution")
    if pas is not None:
        body, _s, _e = pas
        rows = _table_rows(body)
        for row_idx, cells in enumerate(rows, start=1):
            # Convention: `| # | Problem | Solution |` — index col + 2 data cols.
            if len(cells) < 3:
                continue
            for col_label, cell in (("Problem", cells[1]), ("Solution", cells[2])):
                for issue in _cell_bold_problems(cell):
                    out.append(
                        violation_cls(
                            "PS-144",
                            str(readme),
                            f"row {row_idx} {col_label}: {issue}",
                        )
                    )

    # ---- PS-152: split `## Problem` / `## Solution` headings -------------
    # Fire when either standalone heading appears WITHOUT a merged
    # `## Problem and Solution` already present.
    if pas is None:
        prob_only = _SECTION_PATTERNS["problem_only"].search(text)
        sol_only = _SECTION_PATTERNS["solution_only"].search(text)
        if prob_only is not None or sol_only is not None:
            out.append(
                violation_cls(
                    "PS-152",
                    str(readme),
                    (
                        "split `## Problem` + `## Solution` sections "
                        "detected — merge into one `## Problem and "
                        "Solution` table (one row per pain point); see "
                        "scitex-io README for the canonical form"
                    ),
                )
            )

    # ---- PS-153: Architecture file-tree without mermaid fence ------------
    if arch is not None:
        body, _s, _e = arch
        if _RE_TREE_CHARS.search(body) and not _RE_MERMAID_FENCE.search(body):
            out.append(
                violation_cls(
                    "PS-153",
                    str(readme),
                    (
                        "Architecture/How-it-works section contains a "
                        "file tree but no mermaid diagram — replace the "
                        "file tree with a `mermaid flowchart` that shows "
                        "logic / workflow; see scitex-io README §1. The "
                        "directory tree is duplicate information already "
                        "in `_sphinx_html/` and `autoapi`"
                    ),
                )
            )

    # ---- PS-154: Installation section structure --------------------------
    install = _section_body(text, "installation")
    if install is not None:
        body, _s, _e = install
        has_uv_pip = bool(_RE_UV_PIP_INSTALL.search(body))
        if not has_uv_pip:
            out.append(
                violation_cls(
                    "PS-154",
                    str(readme),
                    (
                        "Installation section should start with one "
                        '`uv pip install "<pkg>[all]"` line; per-module '
                        "extras matrix must live inside a `<details>` "
                        "block. See scitex-io README §Installation"
                    ),
                )
            )
        else:
            # Check: any pipe-table outside of <details>...</details>?
            # Build a "stripped" body with <details>…</details> regions
            # blanked, then look for pipe-tables in the remainder.
            stripped = body
            # Naive but safe: repeatedly remove the first <details>...</details>.
            while True:
                m_open = _RE_DETAILS_OPEN.search(stripped)
                if not m_open:
                    break
                m_close = _RE_DETAILS_CLOSE.search(stripped, m_open.end())
                if not m_close:
                    # Unterminated <details> — blank to end of section.
                    stripped = stripped[: m_open.start()]
                    break
                stripped = stripped[: m_open.start()] + stripped[m_close.end() :]
            if _RE_PIPE_TABLE.search(stripped):
                out.append(
                    violation_cls(
                        "PS-154",
                        str(readme),
                        (
                            "Installation section has an extras matrix "
                            "table outside a `<details>` block — wrap "
                            "the matrix in `<details><summary>…</summary>"
                            "…</details>`. See scitex-io README "
                            "§Installation"
                        ),
                    )
                )

    # ---- PS-155: badge row must be two <p align="center"> rows -----------
    m_block = _RE_BADGES_BLOCK.search(text)
    if m_block is not None:
        inner = m_block.group(1)
        p_count = len(_RE_P_CENTER_OPEN.findall(inner))
        if p_count != 2:
            out.append(
                violation_cls(
                    "PS-155",
                    str(readme),
                    (
                        f"badge row should split into two centered rows "
                        f'(found {p_count} `<p align="center">` blocks)'
                        f" — row 1: PyPI / Python / Read the Docs, row "
                        f"2: Tests / Install Test / Coverage. See "
                        f"scitex-io README header for the canonical form"
                    ),
                )
            )
