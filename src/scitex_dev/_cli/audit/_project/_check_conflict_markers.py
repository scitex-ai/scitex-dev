"""PS-148 — unresolved git conflict markers.

Implements the rule filed 2026-05-20 after a real near-miss: an aborted
rebase left conflict markers inside a triple-quoted SQL string in
`_state/state_db.py`. ruff/pyright did not flag them (the file parsed
as a valid string literal) and neither did the existing audit rules —
the markers were nearly merged to develop.

A conflict marker can hide in any text file: `.py` (inside triple
strings or comments), `.md`/`.rst` (inside fenced code blocks),
`.yaml`/`.json`/`.toml`/`.sh`. So this rule is text-based and applies
to every source/doc/test/example file, anchored on the strict 7-char
git-conflict forms so it never false-positives on legitimate markdown
horizontal rules (`---`, `***`) or `====` underlines/dividers in
docstrings.

The three markers git writes are: an open line (seven ``<`` then a
space then the ours-label, e.g. ``HEAD``), a sole divider line (seven
``=`` and nothing else), and a close line (seven ``>`` then a space
then the theirs-label).

Detection anchors (one match → violation):

  * a line that is exactly 7 ``<`` followed by a space:    ``^<{7} ``
  * a line that is exactly 7 ``=`` and nothing else:        ``^={7}$``
  * a line that is exactly 7 ``>`` followed by a space:    ``^>{7} ``

The middle ``=======`` anchor is the strict 7-char form only — a 3-char
``---`` / ``***`` markdown rule, a longer ``========`` table divider, or
``====`` ASCII art in a docstring all fall outside ``^={7}$`` and are
NOT flagged.

Severity is E (error) — an unresolved conflict marker is never
intentional; the audit must fail loudly so the agent (or CI) catches
it pre-push, not post-merge.
"""

from __future__ import annotations

import re
from pathlib import Path

# Directories under the repo that this rule scans.
_SCAN_DIRS = ("src", "tests", "docs", "examples")

# File extensions worth scanning. Conflict markers can hide in any of
# these; binary/asset extensions are excluded.
_SCAN_SUFFIXES = frozenset(
    {".py", ".md", ".rst", ".yaml", ".yml", ".toml", ".json", ".sh"}
)

# Path components that mark vendored / generated trees — never scanned.
_EXCLUDE_PARTS = frozenset(
    {"_sphinx_html", "build", "dist", "node_modules", "__pycache__", ".git"}
)

# The three git-conflict-marker anchors, built from the strict 7-char
# forms. The regexes use repetition counts (`{7}`) so this module's own
# source never contains the literal marker lines — scanning scitex-dev
# itself stays clean.
_OPEN = re.compile(r"^<{7} ")  # `<<<<<<< <label>`
_MID = re.compile(r"^={7}$")  # sole `=======` divider line
_CLOSE = re.compile(r"^>{7} ")  # `>>>>>>> <label>`


def _scan_files(repo: Path):
    """Yield candidate text files under the scanned dirs."""
    for top in _SCAN_DIRS:
        base = repo / top
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix not in _SCAN_SUFFIXES:
                continue
            if _EXCLUDE_PARTS & set(path.parts):
                continue
            yield path


def _conflict_lines(text: str) -> list[tuple[int, str]]:
    """Return (line_no, kind) for every conflict-marker line in `text`."""
    hits: list[tuple[int, str]] = []
    for idx, line in enumerate(text.splitlines(), start=1):
        if _OPEN.match(line):
            hits.append((idx, "open"))
        elif _MID.match(line):
            hits.append((idx, "divider"))
        elif _CLOSE.match(line):
            hits.append((idx, "close"))
    return hits


def check_ps148_conflict_markers(
    repo: Path,
    violation_cls: type,
    out: list,
) -> None:
    """PS-148 — flag unresolved git conflict markers in any text file."""
    for path in sorted(_scan_files(repo)):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        hits = _conflict_lines(text)
        if not hits:
            continue
        sample = ", ".join(f"line {ln} ({kind})" for ln, kind in hits[:3])
        more = f" (+{len(hits) - 3} more)" if len(hits) > 3 else ""
        out.append(
            violation_cls(
                "PS-148",
                str(path),
                (
                    f"unresolved git conflict marker(s): {sample}{more}. "
                    f"Resolve the merge/rebase conflict and remove the "
                    f"<<<<<<< / ======= / >>>>>>> lines before committing."
                ),
            )
        )
