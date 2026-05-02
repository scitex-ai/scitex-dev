"""README convention checks — PS107 / PS109 / PS110 / PS111 / PS112.

Codifies the SciTeX README template (see
``_skills/general/04_docs_01_readme.md`` and the literal template at
``_skills/general/04_docs_01_readme_template.md``). Detection mirrors
PS106 (``_check_readme_badges.py``): cheap substring/regex scans on the
first ~16 KB of README.md, warn-only.

False-positive guards:
- Skip every check when README is missing (PS101 covers that) or
  shorter than ``_MIN_README_BYTES`` (placeholder/scaffold READMEs).
- PS109/PS110/PS112 only scan the first 4 KB / 16 KB respectively, so
  late-document boilerplate doesn't get mis-detected as compliant.

Section names match the most common pattern across 8 surveyed READMEs
(scitex-python, scitex-io, scitex-stats, scitex-dev, figrecipe,
scitex-writer, scitex-scholar, scitex-git). See ``/tmp/readme_survey.md``
for the underlying analysis.
"""

from __future__ import annotations

import re
from pathlib import Path


_MIN_README_BYTES = 200
_HEAD_BYTES_BADGES = 4096
_HEAD_BYTES_SECTIONS = 16384


# PS107 — required H2 sections.
# Acceptable variants for "Quick Start" — both `## Quick Start` and
# `## Quickstart` are common in the wild.
_RE_INSTALLATION = re.compile(r"^##\s+Installation\b", re.MULTILINE | re.IGNORECASE)
_RE_QUICKSTART = re.compile(
    r"^##\s+(Quick\s*Start|Quickstart)\b", re.MULTILINE | re.IGNORECASE
)
_RE_PART_OF_SCITEX = re.compile(
    r"^##\s+Part\s+of\s+SciTeX\b", re.MULTILINE | re.IGNORECASE
)
# Accept "## Three Interfaces", "## Four Interfaces", "## Five Interfaces",
# "## Six Interfaces" — the count varies (Python+CLI+MCP+Skills+HTTP, with
# HTTP optional). Number-word OR plain digit accepted.
_RE_INTERFACES = re.compile(
    r"^##\s+(Three|Four|Five|Six|\d+)\s+Interfaces\b",
    re.MULTILINE | re.IGNORECASE,
)


# PS109 — PyPI version badge. Accepts badge.fury.io OR shields.io/pypi.
_RE_PYPI_BADGE = re.compile(
    r"(badge\.fury\.io/py/|img\.shields\.io/pypi/v/)", re.IGNORECASE
)


# PS110 — Four Freedoms blockquote. Tolerates the leading `>` with or
# without a space, and either `Four Freedoms for Research` or just
# `Four Freedoms` (most use the full phrase but stay forgiving).
_RE_FOUR_FREEDOMS = re.compile(
    r">\s*Four\s+Freedoms(?:\s+for\s+Research)?", re.IGNORECASE
)


# PS111 — banned personal email. The convention says READMEs should
# point at the community project, not a single maintainer's address.
_BANNED_EMAIL = "ywatanabe@scitex.ai"


# PS112 — SciTeX logo at top. Accepted forms (any one is enough):
#   - <img src=".../scitex-logo*.png" ...>
#   - <img src=".../scitex-logo-*.png" ...>
# inside the first 4 KB. We're permissive on path so both
# docs/assets/images/scitex-logo-*.png and docs/scitex-logo-*.png
# variants pass — both occur in the surveyed READMEs.
_RE_SCITEX_LOGO = re.compile(
    r"<img[^>]+src=[\"'][^\"']*scitex-logo[^\"']*\.(?:png|svg|jpg|jpeg)[\"']",
    re.IGNORECASE,
)


# PS113 — SciTeX icon footer. Centered icon-link at the very bottom of
# the README per the canonical template, e.g.
#   <p align="center">
#     <a href="https://scitex.ai" target="_blank">
#       <img src="docs/scitex-icon-navy-inverted.png" alt="SciTeX" width="40"/>
#     </a>
#   </p>
# Detection: scitex-icon-* image referenced anywhere in the LAST ~2 KB
# (the footer area), permissive on path / variant just like PS112.
_RE_SCITEX_ICON = re.compile(
    r"<img[^>]+src=[\"'][^\"']*scitex-icon[^\"']*\.(?:png|svg|jpg|jpeg)[\"']",
    re.IGNORECASE,
)
_TAIL_BYTES_FOOTER = 2048


# PS114 — "Problem and Solution" must be presented as a table, not prose.
# Detection: an `## Problem` (or `## Problem and Solution`) heading must
# be followed within ~3 KB by a markdown table separator row
# (`| --- | --- |` style). Misses pure-prose treatments of the section.
_RE_PROBLEM_HEADING = re.compile(
    r"^##\s+Problem(\s+and\s+Solution)?\b", re.MULTILINE | re.IGNORECASE
)
_RE_TABLE_SEPARATOR = re.compile(
    r"^\s*\|\s*[-:]+\s*(\|\s*[-:]+\s*)+\|\s*$", re.MULTILINE
)
_TABLE_LOOKAHEAD_BYTES = 3072


# PS115 — `## Part of SciTeX` must open with the canonical "is part of
# [SciTeX]" sentence. Format: `\`<pkg>\` is part of [SciTeX](https://scitex.ai)`.
# Tolerant: allows the package name in backticks or plain, allows the
# SciTeX link to be either the canonical URL or the **bold** form.
_RE_PART_OF_OPENER = re.compile(
    r"is\s+part\s+of\s+\[\*{0,2}SciTeX\*{0,2}\]\(https?://scitex\.ai/?\)",
    re.IGNORECASE,
)
_PART_OF_LOOKAHEAD_BYTES = 1024


# PS116 — deprecated `> **Interfaces:**` callout (replaced 2026-05 by
# per-section star ratings).
_RE_INTERFACES_CALLOUT = re.compile(
    r"^>\s*\*\*\s*Interfaces\s*:\s*\*\*", re.MULTILINE | re.IGNORECASE
)


# PS117 — duplicate badge block. The canonical block is wrapped by
# `<!-- scitex-badges:start --> ... <!-- scitex-badges:end -->`. A second
# `<p align="center">` block whose body contains badge URLs (shields.io,
# badge.fury.io, readthedocs.org) is the duplicate we want to flag.
_RE_CANONICAL_BADGES_BLOCK = re.compile(
    r"<!--\s*scitex-badges:start\s*-->.*?<!--\s*scitex-badges:end\s*-->",
    re.DOTALL | re.IGNORECASE,
)
_RE_CENTERED_BADGE_ROW = re.compile(
    r"<p\s+align=[\"']center[\"']>\s*"
    r"(?:[^<]*<a[^>]*>\s*)?"
    r"<img[^>]+src=[\"'][^\"']*"
    r"(?:img\.shields\.io|badge\.fury\.io|readthedocs\.org)",
    re.IGNORECASE,
)


# PS118 — banned descriptors in interface section headers.
# Targets `<summary>` or `##`-style headings carrying parenthetical
# expansions like `(Application Programming Interface)` and trailing
# role descriptors like `-- for AI Agents`, `— for AI Agents`,
# `— for AI Agent Discovery`.
_BANNED_HEADER_PHRASES = [
    re.compile(
        r"<summary>[^<]*\((?:Application Programming Interface|"
        r"Command[\s-]?Line Interface|Model Context Protocol)[^<]*\)",
        re.IGNORECASE,
    ),
    re.compile(
        r"<summary>[^<]*(?:--|—|-)\s*for\s+AI\s+Agent",
        re.IGNORECASE,
    ),
    re.compile(
        r"^##\s+[^\n]*\((?:Application Programming Interface|"
        r"Command[\s-]?Line Interface|Model Context Protocol)[^\n]*\)",
        re.MULTILINE | re.IGNORECASE,
    ),
    re.compile(
        r"^##\s+[^\n]*(?:--|—|-)\s*for\s+AI\s+Agent",
        re.MULTILINE | re.IGNORECASE,
    ),
]


# PS119 — banned `> **SciTeX users**: pip install scitex` blockquote.
_RE_SCITEX_USERS_HINT = re.compile(
    r"^>\s*\*\*\s*SciTeX\s+users?\s*\*\*\s*:\s*[^\n]*pip\s+install\s+scitex",
    re.MULTILINE | re.IGNORECASE,
)


# PS120 — standardized "Part of SciTeX" umbrella one-liner. After the
# PS115 opener, the section must mention all three: the umbrella install
# (`pip install scitex[<extra>]`), the Python alias (`scitex.<module>`),
# and the CLI alias (`scitex <subcommand>`). We check for each token
# independently inside the section window so wording can vary.
_RE_UMBRELLA_INSTALL = re.compile(r"pip\s+install\s+scitex\[[^\]]+\]", re.IGNORECASE)
_RE_UMBRELLA_PYTHON = re.compile(r"`scitex\.[a-zA-Z_]\w*`")
_RE_UMBRELLA_CLI = re.compile(r"`scitex\s+[a-zA-Z][\w-]*", re.IGNORECASE)
_PART_OF_UMBRELLA_LOOKAHEAD = 1024


# PS123 — `Full X` link must deep-link, not bare RTD root.
_RE_FULL_X_LINK = re.compile(
    r"\[\s*Full\s+[\w\s]+?\s*\]\((?P<url>[^\)]+)\)", re.IGNORECASE
)
_RE_BARE_RTD_ROOT = re.compile(
    r"^https?://[\w-]+\.readthedocs\.io/?(?:en/[\w.-]+/?)?$", re.IGNORECASE
)


# PS132 — banned standalone `## Modules` H2 (drift; duplicate of autoapi).
_RE_MODULES_H2 = re.compile(r"^##\s+Modules\b", re.MULTILINE | re.IGNORECASE)


# PS131 — exactly one interface `<details>` block must be `<details open>`
# (the primary). Counted only inside the `## <N> Interfaces` section.
_RE_INTERFACES_HEADING = re.compile(
    r"^##\s+(Three|Four|Five|Six|\d+)\s+Interfaces\b",
    re.MULTILINE | re.IGNORECASE,
)
_RE_DETAILS_OPEN_TAG = re.compile(r"<details\s+open\b", re.IGNORECASE)
_RE_NEXT_H2 = re.compile(r"^##\s+", re.MULTILINE)


def _read_head(readme: Path, n: int) -> str | None:
    """Return the first `n` bytes of `readme` as text, or None on error/missing."""
    if not readme.is_file():
        return None
    try:
        text = readme.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return text[:n]


def _readme_is_substantive(readme: Path) -> bool:
    """True iff README exists and is at least ``_MIN_README_BYTES`` bytes."""
    if not readme.is_file():
        return False
    try:
        return readme.stat().st_size >= _MIN_README_BYTES
    except OSError:
        return False


def _is_external_lib_repo(repo: Path) -> bool:
    """True iff ``repo``'s absolute path matches an ECOSYSTEM entry whose
    category is ``external-lib`` (figrecipe, socialia, newb,
    crossref-local, openalex-local, …) — packages that intentionally
    sit outside the ``scitex.<module>`` umbrella and so shouldn't be
    held to PS120's umbrella one-liner.
    """
    try:
        from scitex_dev._ecosystem._core import ECOSYSTEM
    except Exception:
        return False
    target = str(Path(repo).expanduser().resolve())
    for info in ECOSYSTEM.values():
        if info.get("category") != "external-lib":
            continue
        local = info.get("local_path")
        if not local:
            continue
        if str(Path(local).expanduser().resolve()) == target:
            return True
    return False


def check_readme_sections(repo: Path, violation_cls: type, out: list) -> None:
    """Append PS107 / PS109 / PS110 / PS111 / PS112 violations.

    Each rule is independent; a missing README short-circuits all five
    (PS101 already flags missing pyproject and a future check could flag
    missing README — we don't double-flag here).
    """
    readme = repo / "README.md"
    if not _readme_is_substantive(readme):
        return

    head_sections = _read_head(readme, _HEAD_BYTES_SECTIONS)
    head_badges = _read_head(readme, _HEAD_BYTES_BADGES)
    if head_sections is None or head_badges is None:
        return

    # PS107 — required sections. NOTE (2026-05): `## Quick Start` is no
    # longer required — the primary `<details open>` interface block
    # doubles as the quick-start (PS131). If a Quick Start H2 is present,
    # it's tolerated but PS107 doesn't enforce it anymore.
    missing: list[str] = []
    if not _RE_INSTALLATION.search(head_sections):
        missing.append("## Installation")
    if not _RE_INTERFACES.search(head_sections):
        missing.append("## <N> Interfaces")
    if not _RE_PART_OF_SCITEX.search(head_sections):
        missing.append("## Part of SciTeX")
    if missing:
        out.append(
            violation_cls(
                "PS107",
                str(readme),
                (
                    "README.md is missing required H2 section(s): "
                    + ", ".join(missing)
                    + ". See _skills/general/04_docs_01_readme_template.md "
                    "for the canonical layout."
                ),
            )
        )

    # PS109 — PyPI version badge
    if not _RE_PYPI_BADGE.search(head_badges):
        out.append(
            violation_cls(
                "PS109",
                str(readme),
                (
                    "README.md is missing a PyPI version badge in the first ~4 KB. "
                    "Add a `[![PyPI](https://badge.fury.io/py/<pkg>.svg)]"
                    "(https://pypi.org/project/<pkg>/)` or "
                    "`[![PyPI](https://img.shields.io/pypi/v/<pkg>.svg)](...)` line "
                    "near the title."
                ),
            )
        )

    # PS110 — Four Freedoms footer (search the whole readable text for the
    # blockquote line — it lives near the bottom of the file).
    full = readme.read_text(encoding="utf-8", errors="replace")
    if not _RE_FOUR_FREEDOMS.search(full):
        out.append(
            violation_cls(
                "PS110",
                str(readme),
                (
                    "README.md does not contain the Four Freedoms for Research "
                    "blockquote. Append the canonical block under "
                    "`## Part of SciTeX` (see _skills/general/"
                    "04_docs_01_readme_template.md)."
                ),
            )
        )

    # PS111 — banned personal email
    if _BANNED_EMAIL in full:
        out.append(
            violation_cls(
                "PS111",
                str(readme),
                (
                    f"README.md contains the banned personal email "
                    f"`{_BANNED_EMAIL}`. SciTeX is a community project; "
                    "remove the address (use the project URL or GitHub "
                    "issues for contact)."
                ),
            )
        )

    # PS112 — SciTeX logo at top
    if not _RE_SCITEX_LOGO.search(head_badges):
        out.append(
            violation_cls(
                "PS112",
                str(readme),
                (
                    "README.md is missing a SciTeX logo image in the first ~4 KB. "
                    'Add a centered `<img src="docs/scitex-logo-blue-cropped.png" '
                    "...>` (or `docs/assets/images/scitex-logo-blue-cropped.png`) "
                    "near the title."
                ),
            )
        )

    # PS113 — SciTeX icon footer (centered link at the very bottom).
    tail = full[-_TAIL_BYTES_FOOTER:] if len(full) > _TAIL_BYTES_FOOTER else full
    if not _RE_SCITEX_ICON.search(tail):
        out.append(
            violation_cls(
                "PS113",
                str(readme),
                (
                    "README.md is missing a SciTeX icon footer (centered "
                    "scitex-icon image in the last ~2 KB). Add the canonical "
                    "footer block — see _skills/general/04_docs_01_readme_template.md."
                ),
            )
        )

    # PS115 — "## Part of SciTeX" must open with the canonical
    # "is part of [SciTeX](https://scitex.ai)" sentence. The synergy
    # code block under it is OPTIONAL — standalone packages can skip
    # the example as long as the opener is present.
    pos_part = _RE_PART_OF_SCITEX.search(full)
    if pos_part is not None:
        window = full[pos_part.end() : pos_part.end() + _PART_OF_LOOKAHEAD_BYTES]
        if not _RE_PART_OF_OPENER.search(window):
            out.append(
                violation_cls(
                    "PS115",
                    str(readme),
                    (
                        "README.md '## Part of SciTeX' section does not open "
                        "with the canonical '<pkg> is part of "
                        "[SciTeX](https://scitex.ai)' sentence. The synergy "
                        "code block is optional for standalone packages, but "
                        "the opener is required so consumers know how the "
                        "package fits into the ecosystem."
                    ),
                )
            )

    # PS114 — "Problem and Solution" must be presented as a markdown table.
    # When the heading is present but no table separator follows within
    # ~3 KB, the section is prose-only — flag it.
    m = _RE_PROBLEM_HEADING.search(full)
    if m is not None:
        window = full[m.end() : m.end() + _TABLE_LOOKAHEAD_BYTES]
        if not _RE_TABLE_SEPARATOR.search(window):
            out.append(
                violation_cls(
                    "PS114",
                    str(readme),
                    (
                        "README.md '## Problem and Solution' (or '## Problem') "
                        "section is prose-only. SciTeX convention is a "
                        "markdown table with columns | # | Problem | Solution | "
                        "— see _skills/general/04_docs_01_readme_template.md."
                    ),
                )
            )

    # PS116 — deprecated `> **Interfaces:**` summary callout.
    if _RE_INTERFACES_CALLOUT.search(full):
        out.append(
            violation_cls(
                "PS116",
                str(readme),
                (
                    "README.md uses the deprecated '> **Interfaces:** ...' "
                    "summary callout. Per 2026-05 convention, drop this "
                    "line and put star ratings on each interface section "
                    "header instead (e.g. '## Python API ⭐⭐⭐'). See "
                    "_skills/general/99_quality_02_checklist.md §6."
                ),
            )
        )

    # PS117 — duplicate badge block. The canonical
    # `<!-- scitex-badges:start --> ... :end -->` block lives at the top;
    # any extra `<p align="center">` row containing badge URLs is the
    # duplicate flagged here.
    canonical_match = _RE_CANONICAL_BADGES_BLOCK.search(full)
    if canonical_match is not None:
        # Search the area AFTER the canonical block for a centered badge row.
        after = full[canonical_match.end() :]
        if _RE_CENTERED_BADGE_ROW.search(after):
            out.append(
                violation_cls(
                    "PS117",
                    str(readme),
                    (
                        "README.md has a duplicate badge row "
                        '(`<p align="center">` with shields.io / '
                        "badge.fury / readthedocs badges) below the canonical "
                        "`<!-- scitex-badges:* -->` block. Keep only the "
                        "canonical block."
                    ),
                )
            )

    # PS118 — banned descriptors in interface section headers.
    for pat in _BANNED_HEADER_PHRASES:
        if pat.search(full):
            out.append(
                violation_cls(
                    "PS118",
                    str(readme),
                    (
                        "README.md interface section header carries a banned "
                        "descriptor — e.g. '(Application Programming "
                        "Interface)', '-- for AI Agents', or '— for AI Agent "
                        "Discovery'. Strip the prose; the section name itself "
                        "carries meaning."
                    ),
                )
            )
            break  # one violation per file is enough

    # PS119 — banned `> **SciTeX users**: pip install scitex ...` hint.
    if _RE_SCITEX_USERS_HINT.search(full):
        out.append(
            violation_cls(
                "PS119",
                str(readme),
                (
                    "README.md contains a `> **SciTeX users**: pip install "
                    "scitex ...` install hint. These belong in the umbrella "
                    "`scitex` README, not in sub-package READMEs. Remove the "
                    "line; if the umbrella relationship needs surfacing, the "
                    "standardized 'Part of SciTeX' one-liner already covers it."
                ),
            )
        )

    # PS132 — `## Modules` H2 (hand-curated function table) is banned.
    if _RE_MODULES_H2.search(full):
        out.append(
            violation_cls(
                "PS132",
                str(readme),
                (
                    "README.md has a standalone '## Modules' H2 — a "
                    "hand-curated table of Python modules + functions. "
                    "This duplicates the Python API <details> block and "
                    "the autoapi page; it drifts as the package evolves. "
                    "Drop the section — the Python API block + Full API "
                    "reference deep-link cover this."
                ),
            )
        )

    # PS131 — exactly one `<details open>` inside `## <N> Interfaces`.
    iface_h = _RE_INTERFACES_HEADING.search(full)
    if iface_h is not None:
        # Slice out the interfaces section (until next H2 or EOF).
        section_start = iface_h.end()
        next_h = _RE_NEXT_H2.search(full, pos=section_start)
        section = full[section_start : next_h.start() if next_h else len(full)]
        n_open = len(_RE_DETAILS_OPEN_TAG.findall(section))
        if n_open < 1:
            out.append(
                violation_cls(
                    "PS131",
                    str(readme),
                    (
                        "README.md `## <N> Interfaces` section has 0 "
                        "`<details open>` block(s); expected at least 1 "
                        "(the primary interface, or all top-rated "
                        "interfaces when tied). The primary's minimal "
                        "example doubles as the quick-start, so it must "
                        "be expanded by default."
                    ),
                )
            )

    # PS123 — `Full X reference` links must deep-link, not bare RTD root.
    bad_links: list[str] = []
    for m in _RE_FULL_X_LINK.finditer(full):
        url = m.group("url").strip()
        if _RE_BARE_RTD_ROOT.match(url):
            bad_links.append(url)
    if bad_links:
        out.append(
            violation_cls(
                "PS123",
                str(readme),
                (
                    "README.md interface section has 'Full X reference' "
                    "link(s) pointing at bare RTD root: "
                    + ", ".join(sorted(set(bad_links))[:3])
                    + ". Use a deep-link to the relevant anchor page (e.g. "
                    "`/en/latest/api/<import>.html`) — see _skills/general/"
                    "04_docs_01_readme.md 'Canonical Full X reference "
                    "deep-link patterns'."
                ),
            )
        )

    # PS120 — standardized 'Part of SciTeX' umbrella one-liner. Within the
    # ~1 KB after `## Part of SciTeX`, expect all three tokens:
    #   - `pip install scitex[<extra>]`
    #   - a `scitex.<module>` Python alias in backticks
    #   - a `scitex <subcommand>` CLI alias in backticks
    #
    # Skip for `external-lib` category packages (figrecipe, socialia,
    # newb, crossref-local, openalex-local, …) — they intentionally
    # don't fold under the `scitex.<module>` umbrella; demanding the
    # tokens produces false positives. Built-in `library` and `umbrella`
    # entries still get checked.
    if pos_part is not None and not _is_external_lib_repo(repo):
        window = full[pos_part.end() : pos_part.end() + _PART_OF_UMBRELLA_LOOKAHEAD]
        missing_bits: list[str] = []
        if not _RE_UMBRELLA_INSTALL.search(window):
            missing_bits.append("`pip install scitex[<extra>]`")
        if not _RE_UMBRELLA_PYTHON.search(window):
            missing_bits.append("`scitex.<module>`")
        if not _RE_UMBRELLA_CLI.search(window):
            missing_bits.append("`scitex <subcommand>`")
        if missing_bits:
            out.append(
                violation_cls(
                    "PS120",
                    str(readme),
                    (
                        "README.md '## Part of SciTeX' is missing the "
                        "standardized umbrella one-liner — needs: "
                        + ", ".join(missing_bits)
                        + ". See _skills/general/04_docs_01_readme.md "
                        "for the canonical sentence."
                    ),
                )
            )
