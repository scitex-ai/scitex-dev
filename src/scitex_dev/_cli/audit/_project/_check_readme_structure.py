"""README structure rules — orchestrator for PS-141..144, PS-152..155,
PS-159..160, PS-162..163.

This module used to hold every rule in one 775-line file, over this
repo's own 512-line cap — which is precisely why the PS-142
false-positive below went unfixed for so long: anyone touching the file
was penalised by our own hook. The rule-families now live in focused
sibling modules (the `_cli/audit/_summary/_gui_group.py` shape) and this
file only reads the README once, resolves the shared sections, and
dispatches:

    `_readme_structure_shared`    section lookup + shared regexes/helpers
    `_readme_structure_sections`  PS-141, PS-142, PS-143, PS-152, PS-153
    `_readme_structure_content`   PS-144 (P&S table), PS-154 (Installation)
    `_readme_structure_badges`    PS-155, PS-157, PS-158, PS-162, PS-163
    `_readme_structure_captions`  PS-159, PS-160

Truncation fix (the PS-142 defect): the README was previously read as a
16 KiB head-slice, so a `## Architecture` section living past that
offset was reported as "missing mandatory `## Architecture`" — a check
that could not see the whole input reporting ABSENCE. Absence of
evidence is not evidence of absence. The README is now read whole; see
`_readme_structure_shared.README_MAX_BYTES` for the measurement (the cap
saved ~0.18 ms/repo, i.e. ~15 ms across the entire 84-repo fleet — it
bought nothing and cost correctness).

`check_readme_structure` remains the sole public entry point; the
helpers below are re-exported so any existing import of a private name
keeps working.
"""

from __future__ import annotations

from pathlib import Path

from ._readme_structure_badges import check_badges
from ._readme_structure_captions import (
    check_captions,
    count_captionable_figures as _count_captionable_figures,
    count_captionable_tables as _count_captionable_tables,
    numbering_issues as _numbering_issues,
)
from ._readme_structure_content import (
    cell_bold_problems as _cell_bold_problems,
    check_installation,
    check_problem_solution_table,
    table_rows as _table_rows,
)
from ._readme_structure_sections import (
    check_section_order as _check_section_order,
    check_sections,
)
from ._readme_structure_shared import (
    CANONICAL_ORDER as _CANONICAL_ORDER,
    MIN_README_BYTES as _MIN_README_BYTES,
    README_MAX_BYTES as _README_MAX_BYTES,
    SECTION_PATTERNS as _SECTION_PATTERNS,
    has_architecture_content as _has_architecture_content,
    has_visual_content as _has_visual_content,
    read_readme,
    section_body as _section_body,
    strip_badges_block as _strip_badges_block,
    strip_details_spans as _strip_details_spans,
)


# `check_readme_structure` is the entry point. Everything after it is a
# BACK-COMPAT re-export: these names lived in this module before the split
# and are listed explicitly so they read as intentional re-exports rather
# than unused imports.
__all__ = [
    "check_readme_structure",
    "_CANONICAL_ORDER",
    "_MIN_README_BYTES",
    "_README_MAX_BYTES",
    "_SECTION_PATTERNS",
    "_cell_bold_problems",
    "_check_section_order",
    "_count_captionable_figures",
    "_count_captionable_tables",
    "_has_architecture_content",
    "_has_visual_content",
    "_numbering_issues",
    "_section_body",
    "_strip_badges_block",
    "_strip_details_spans",
    "_table_rows",
]


def check_readme_structure(repo: Path, violation_cls: type, out: list) -> None:
    readme = repo / "README.md"
    text = read_readme(readme)
    if text is None:
        return
    readme_path = str(readme)

    # Sections resolved once and shared across the rule-families.
    demo = _section_body(text, "demo")
    quick = _section_body(text, "quick_start")
    arch = _section_body(text, "architecture")
    pas = _section_body(text, "problem_and_solution")
    install = _section_body(text, "installation")

    check_sections(
        text,
        readme_path,
        violation_cls,
        out,
        demo=demo,
        quick=quick,
        arch=arch,
        pas=pas,
        demo_has_visual=demo is not None and _has_visual_content(demo[0]),
        quick_has_visual=quick is not None and _has_visual_content(quick[0]),
        arch_has_visual=arch is not None and _has_architecture_content(arch[0]),
    )
    check_problem_solution_table(readme_path, violation_cls, out, pas=pas)
    check_installation(readme_path, violation_cls, out, install=install)
    check_badges(text, readme_path, violation_cls, out)
    check_captions(text, readme_path, violation_cls, out)
