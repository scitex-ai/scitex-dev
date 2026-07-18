"""README section-presence + ordering rules — PS-141..143, PS-152..153.

One rule-family per module (see `_readme_structure_shared` for the split
rationale).

PS-141: README.md must have a `## Demo` OR `## Quick Start` section,
and a visual element (markdown image, non-shield HTML `<img>`, or
fenced ```mermaid block) must appear in at least one of: that section,
or `## Architecture` (the "one diagram is enough" rule, adopted
2026-05).

PS-142: README.md must have a `## Architecture` (or equivalent
`## How it works` / `## How It Works`) section. Its body must contain
at least one of: ```mermaid fence, ASCII text diagram (fenced code
block >=10 lines), file-tree characters (`|--`/`\\--`/`|`), or
`<img>` tag — UNLESS the diagram requirement is already satisfied by
the Demo or Quick Start section (PS-141's visual-anywhere fallback).

PS-143: section H2 headers appear in canonical order. The expected
order (skipping any optional or omitted section) is:
    Problem and Solution -> Quick Start / Demo -> Installation ->
    Architecture / How it works -> <N> Interfaces -> Part of SciTeX

PS-152: split `## Problem` + `## Solution` headings detected — must
be merged into a single `## Problem and Solution` table (one row
per pain point); see scitex-io README for the canonical form.

PS-153: `## Architecture` (or `## How it works`) body contains a
file-tree but no ```mermaid fence — the file tree is duplicate
information already in `_sphinx_html/` and `autoapi`. Replace with a
`mermaid flowchart` showing logic/workflow.
"""

from __future__ import annotations

from ._readme_structure_shared import (
    CANONICAL_ORDER,
    RE_MERMAID_FENCE,
    RE_TREE_CHARS,
    SECTION_PATTERNS,
    has_architecture_content,
)


def check_section_order(text: str) -> list[str]:
    """PS-143: return list[str] of out-of-order section pairs found, or [].

    Each entry is `'<found_after> appears after <found_before> but should '
    'precede it'`.
    """
    found: list[tuple[int, str]] = []  # (offset, name)
    for name, pat in SECTION_PATTERNS.items():
        # Only canonical-order sections participate in PS-143; auxiliary
        # patterns (e.g. PS-152 `problem_only` / `solution_only`) are
        # skipped here.
        if name not in CANONICAL_ORDER:
            continue
        m = pat.search(text)
        if m:
            found.append((m.start(), name))
    # Order observed by file offset.
    by_offset = [n for _o, n in sorted(found)]
    # Project onto canonical index list.
    rank = {n: i for i, n in enumerate(CANONICAL_ORDER)}
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


def check_sections(
    text: str,
    readme_path: str,
    violation_cls: type,
    out: list,
    *,
    demo: tuple[str, int, int] | None,
    quick: tuple[str, int, int] | None,
    arch: tuple[str, int, int] | None,
    pas: tuple[str, int, int] | None,
    demo_has_visual: bool,
    quick_has_visual: bool,
    arch_has_visual: bool,
) -> None:
    """Emit PS-141 / PS-142 / PS-143 / PS-152 / PS-153 violations."""
    # ---- PS-141 / PS-142: visual content (one diagram is enough) ----------
    # Updated 2026-05: a top-level `## Quick Start` H2 counts as the "demo"
    # role — packages that ship Quick Start need not also ship `## Demo`.
    visual_anywhere = demo_has_visual or quick_has_visual or arch_has_visual

    if demo is None and quick is None:
        out.append(
            violation_cls(
                "PS-141",
                readme_path,
                "missing mandatory `## Demo` or `## Quick Start` section",
            )
        )
    elif not visual_anywhere:
        out.append(
            violation_cls(
                "PS-141",
                readme_path,
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
                readme_path,
                "missing mandatory `## Architecture` (or `## How it works`) section",
            )
        )
    else:
        body, _s, _e = arch
        # PS-142 satisfied if Architecture itself has a diagram OR a
        # diagram lives in the Demo or Quick Start sections.
        if (
            not has_architecture_content(body)
            and not demo_has_visual
            and not quick_has_visual
        ):
            out.append(
                violation_cls(
                    "PS-142",
                    readme_path,
                    (
                        "`## Architecture` section has no diagram, file "
                        "tree, mermaid fence, or `<img>`"
                    ),
                )
            )

    # ---- PS-143: section ordering ----------------------------------------
    for issue in check_section_order(text):
        out.append(violation_cls("PS-143", readme_path, issue))

    # ---- PS-152: split `## Problem` / `## Solution` headings -------------
    # Fire when either standalone heading appears WITHOUT a merged
    # `## Problem and Solution` already present.
    if pas is None:
        prob_only = SECTION_PATTERNS["problem_only"].search(text)
        sol_only = SECTION_PATTERNS["solution_only"].search(text)
        if prob_only is not None or sol_only is not None:
            out.append(
                violation_cls(
                    "PS-152",
                    readme_path,
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
        if RE_TREE_CHARS.search(body) and not RE_MERMAID_FENCE.search(body):
            out.append(
                violation_cls(
                    "PS-153",
                    readme_path,
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
