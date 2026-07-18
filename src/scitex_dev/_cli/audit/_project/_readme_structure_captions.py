"""README figure/table caption rules — PS-159, PS-160.

One rule-family per module (see `_readme_structure_shared` for the split
rationale).

PS-159: `<b>Figure N.</b>` and `<b>Table N.</b>` captions must
form `[1, 2, 3, ...]` — no gaps, no duplicates, starting at 1.
See scitex-stats README for the canonical caption form.

PS-160: every `<img>` data figure (excluding badges, the centered
logo, and the SciTeX icon footer) and every ```mermaid``` fenced
block must have a `<sub><b>Figure N.</b> ...</sub>` caption; every
pipe-table (except the `## Problem and Solution` table and any
table inside `<details>`) must have a `<sub><b>Table N.</b>
...</sub>` caption.
"""

from __future__ import annotations

import re

from ._readme_structure_shared import (
    RE_HTML_IMG,
    RE_MERMAID_FENCE,
    RE_PIPE_TABLE,
    section_body,
    strip_badges_block,
    strip_details_spans,
)


# Caption form (per scitex-stats README):
#     <p align="center"><sub><b>Figure 2.</b> caption ...</sub></p>
_RE_FIGURE_CAPTION = re.compile(
    r"<sub>\s*<b>\s*Figure\s+(\d+)\s*\.\s*</b>", re.IGNORECASE
)
_RE_TABLE_CAPTION = re.compile(r"<sub>\s*<b>\s*Table\s+(\d+)\s*\.\s*</b>", re.IGNORECASE)
# Skip-list for `<img>` tags that are not "data figures" — the centered
# header logo and the small icon footer.
_RE_IMG_LOGO_SKIP = re.compile(
    r"src\s*=\s*['\"][^'\"]*docs/scitex-(?:logo|icon)", re.IGNORECASE
)


def count_captionable_figures(text: str) -> int:
    """Count `<img>` data figures + ```mermaid``` fenced blocks in `text`.

    Excludes: badges block, the centered logo (`docs/scitex-logo*`), and
    the icon footer (`docs/scitex-icon*`).
    """
    body = strip_badges_block(text)
    n = 0
    for m in RE_HTML_IMG.finditer(body):
        # Pull the whole <img ...> tag back from the match offset to inspect
        # full attribute text for the logo/icon skip-list.
        tag_start = m.start()
        tag_end = body.find(">", tag_start)
        tag = body[tag_start : tag_end + 1] if tag_end != -1 else m.group(0)
        if _RE_IMG_LOGO_SKIP.search(tag):
            continue
        n += 1
    n += len(RE_MERMAID_FENCE.findall(body))
    return n


def count_captionable_tables(text: str) -> int:
    """Count pipe-tables outside `<details>` and outside `## Problem and Solution`."""
    # 1) Drop <details> spans.
    body = strip_details_spans(text)
    # 2) Drop the `## Problem and Solution` section body.
    pas = section_body(body, "problem_and_solution")
    if pas is not None:
        _b, s, e = pas
        body = body[:s] + body[e:]
    return len(RE_PIPE_TABLE.findall(body))


def numbering_issues(nums: list[int], kind: str) -> str | None:
    """Return a one-line description of the numbering problem, or None.

    `kind` is "Figure" or "Table".
    """
    if not nums:
        return None
    sorted_nums = sorted(nums)
    # Duplicates first (so "1, 2, 2" reports duplicate not gap).
    seen: set[int] = set()
    dups: list[int] = []
    for n in sorted_nums:
        if n in seen:
            dups.append(n)
        seen.add(n)
    if dups:
        dup_str = ", ".join(str(d) for d in sorted(set(dups)))
        return f"{kind} {dup_str} duplicated"
    if sorted_nums[0] != 1:
        return f"{kind} numbering starts at {sorted_nums[0]} (must start at 1)"
    expected = list(range(1, sorted_nums[-1] + 1))
    missing = sorted(set(expected) - set(sorted_nums))
    if missing:
        miss_str = ", ".join(str(m) for m in missing)
        return f"{kind} {miss_str} missing"
    return None


def check_captions(text: str, readme_path: str, violation_cls: type, out: list) -> None:
    """Emit PS-159 / PS-160 violations."""
    fig_nums = [int(n) for n in _RE_FIGURE_CAPTION.findall(text)]
    tab_nums = [int(n) for n in _RE_TABLE_CAPTION.findall(text)]

    # ---- PS-159: figure / table numbering must be 1, 2, 3, ... ----------
    if fig_nums or tab_nums:
        details_parts: list[str] = []
        f_issue = numbering_issues(fig_nums, "Figure")
        if f_issue:
            details_parts.append(f_issue)
        t_issue = numbering_issues(tab_nums, "Table")
        if t_issue:
            details_parts.append(t_issue)
        if details_parts:
            out.append(
                violation_cls(
                    "PS-159",
                    readme_path,
                    (
                        f"figure/table numbering is broken: "
                        f"{'; '.join(details_parts)}. Re-number "
                        f"sequentially starting at 1. See scitex-stats "
                        f"README for the caption style."
                    ),
                )
            )

    # ---- PS-160: every captionable figure/table needs a caption ---------
    n_fig_capt = len(fig_nums)
    n_tab_capt = len(tab_nums)
    n_fig = count_captionable_figures(text)
    n_tab = count_captionable_tables(text)
    if n_fig > n_fig_capt:
        out.append(
            violation_cls(
                "PS-160",
                readme_path,
                (
                    f"{n_fig} figures/mermaid blocks but {n_fig_capt} "
                    f"Figure captions — every figure must have a "
                    f"'<sub><b>Figure N.</b> ...</sub>' caption "
                    f"(exception: badges + logo + icon footer). See "
                    f"scitex-stats README for the caption style."
                ),
            )
        )
    if n_tab > n_tab_capt:
        out.append(
            violation_cls(
                "PS-160",
                readme_path,
                (
                    f"{n_tab} tables but {n_tab_capt} Table captions — "
                    f"every table must have a '<sub><b>Table N.</b> "
                    f"...</sub>' caption. Problem and Solution table is "
                    f"the only table exempt from this rule. See "
                    f"scitex-stats README for the caption style."
                ),
            )
        )
