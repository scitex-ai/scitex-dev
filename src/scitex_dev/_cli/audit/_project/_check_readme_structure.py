"""README structure rules — PS-141, PS-142, PS-143, PS-144.

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
