"""§1 continued: README form rules, dev-extras floor, the cross-package gate.

Rule literals extracted verbatim from `_registry.py` (1286 lines, cap 512)
— pure move, no behaviour change. The corpus ASSEMBLY (severity/slug
tables, co-located merges, the final `_patch` apply) deliberately stays
together in `_rules/__init__.py`. See GITIGNORED/REFACTORING.md.
"""

from __future__ import annotations

from ._rule import Rule

RULES_S1_README_EXTENDED: list[Rule] = [
        Rule(
            "PS-152",
            "§1",
            (
                "README.md has separate `## Problem` and/or `## Solution` "
                "H2 sections instead of a single merged "
                "`## Problem and Solution` table (one row per pain "
                "point). See scitex-io README for the canonical form."
            ),
            slug="readme-split-problem-solution",
        ),
        Rule(
            "PS-153",
            "§1",
            (
                "README.md `## Architecture` (or `## How it works`) "
                "section contains a file tree (`├──`/`└──`/`│`) but "
                "no ```mermaid fence. The directory tree is duplicate "
                "information already in `_sphinx_html/` and `autoapi`. "
                "Replace it with a `mermaid flowchart` showing the "
                "logic/workflow — see scitex-io README §1."
            ),
            slug="readme-architecture-filetree-not-mermaid",
        ),
        Rule(
            "PS-154",
            "§1",
            (
                "README.md `## Installation` section must start with one "
                '`uv pip install "<pkg>[all]"` fenced bash line; any '
                "per-module extras matrix table must live inside a "
                "`<details>` block. See scitex-io README §Installation."
            ),
            slug="readme-installation-not-canonical",
        ),
        Rule(
            "PS-155",
            "§1",
            (
                "README.md badge row between `<!-- scitex-badges:start "
                "-->` and `<!-- scitex-badges:end -->` should split "
                'into exactly two `<p align="center">` rows — row 1: '
                "PyPI / Python / Read the Docs; row 2: Tests / Install "
                "Test / Coverage. See scitex-io README header for the "
                "canonical form."
            ),
            slug="readme-badge-row-not-two-rows",
        ),
        Rule(
            "PS-156",
            "§1",
            (
                "examples/ directory contains only `.py` scripts and no "
                "`.ipynb` notebooks — prefer Jupyter notebooks for "
                "examples so users can read prose + code + output side "
                "by side and execute in-place. Reference: "
                "https://github.com/ywatanabe1989/scitex-seizure-metrics/"
                "tree/develop/examples (every example is .ipynb). Some "
                "packages (e.g. scitex-io) document a script-style "
                "examples set in their README and may keep .py files; "
                "mix .py and .ipynb freely — the rule only fires when "
                "examples/ has .py files and ZERO .ipynb files."
            ),
            slug="examples-no-ipynb",
        ),
        Rule(
            "PS-157",
            "§1",
            (
                "README.md codecov badge URL is unbranched "
                "(`codecov.io/<owner>/<pkg>/graph/badge.svg`) — pin a "
                "branch so the badge doesn't render 'unknown' when "
                "uploads only land on develop. Use "
                "`codecov.io/<owner>/<pkg>/branch/develop/graph/"
                "badge.svg`. See scitex-io README header for the "
                "canonical form."
            ),
            slug="readme-codecov-badge-unbranched",
        ),
        Rule(
            "PS-158",
            "§1",
            (
                "README.md Read-the-Docs badge uses readthedocs.org's "
                "own /badge endpoint which bakes the literal label "
                "'docs' into the SVG. Switch to the shields.io proxy "
                "so the visible label matches the project: "
                "`img.shields.io/readthedocs/<pkg>?label=Read%20the%20"
                "Docs`. See scitex-io README header."
            ),
            slug="readme-rtd-badge-baked-label",
        ),
        Rule(
            "PS-159",
            "§1",
            (
                "README.md figure / table caption numbering is broken — "
                "`<b>Figure N.</b>` and `<b>Table N.</b>` captions must "
                "form [1, 2, 3, ...] with no gaps, no duplicates, "
                "starting at 1. See scitex-stats README for the "
                "canonical caption form: "
                '`<p align="center"><sub><b>Figure N.</b> caption '
                "...</sub></p>`."
            ),
            slug="readme-figures-tables-numbering",
        ),
        Rule(
            "PS-160",
            "§1",
            (
                "README.md has a figure or table without a caption — "
                "every `<img>` data figure (excluding badges, the "
                "centered logo, and the icon footer) and every "
                "```mermaid``` fenced block must have a "
                "`<sub><b>Figure N.</b> ...</sub>` caption; every "
                "pipe-table (except the Problem and Solution table and "
                "tables inside `<details>`) must have a "
                "`<sub><b>Table N.</b> ...</sub>` caption. See "
                "scitex-stats README for the canonical caption form."
            ),
            slug="readme-figures-tables-missing-caption",
        ),
        Rule(
            "PS-161",
            "§1",
            (
                "codecov.yml project/patch coverage target is below 90% "
                "(or set to `auto`/`auto-target`) — pin a fixed `target: "
                "90%` so the coverage bar is visible. See scitex-io "
                "codecov.yml for the canonical config."
            ),
            slug="readme-codecov-coverage-target-too-low",
        ),
        Rule(
            "PS-162",
            "§1",
            (
                "README.md badge block (`<!-- scitex-badges:start -->...`) "
                "is missing a Codecov coverage badge — every public "
                "scitex package should expose CI coverage. See scitex-io "
                "README header for the canonical form."
            ),
            slug="readme-missing-codecov-badge",
        ),
        Rule(
            "PS-163",
            "§1",
            (
                "README.md badge block (`<!-- scitex-badges:start -->...`) "
                "is missing a Read-the-Docs badge — every scitex package "
                "shipping RTD docs should expose the build status. See "
                "scitex-io README header for the canonical form."
            ),
            slug="readme-missing-rtd-badge",
        ),
        Rule(
            "PS-140",
            "§2",
            (
                "package source has cross-package imports (`scitex_<X>` "
                "peer or `scitex.<X>` umbrella) but no "
                "`tests/integration/test_cross_package_imports.py` runtime "
                "gate, OR the gate's `CROSS_PACKAGE_IMPORTS` list is "
                "stale (missing some imports / contains removed ones). "
                "Without this gate, renames in peer standalones surface "
                "as silent ModuleNotFoundError at user runtime — the "
                "scitex_io._load_cache rename was undetected for weeks "
                "because of this gap. Regenerate via "
                "`scitex-dev ecosystem install-cross-package-gate "
                "<distribution> --force`."
            ),
        ),
]

# EOF
