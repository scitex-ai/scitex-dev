"""§1 top-level layout: structure, README content, Sphinx/RTD, community files.

Rule literals extracted verbatim from `_registry.py` (1286 lines, cap 512)
— pure move, no behaviour change. The corpus ASSEMBLY (severity/slug
tables, co-located merges, the final `_patch` apply) deliberately stays
together in `_rules/__init__.py`. See GITIGNORED/REFACTORING.md.
"""

from __future__ import annotations

from ._rule import Rule

RULES_S1_LAYOUT: list[Rule] = [
        # §1 Top-level layout ---------------------------------------------------
        Rule(
            "PS-101",
            "§1",
            "missing pyproject.toml at repo root",
            slug="pyproject-missing",
        ),
        Rule(
            "PS-102",
            "§1",
            "forbidden top-level dir present (use the canonical location instead)",
            slug="top-level-forbidden-dir",
        ),
        Rule(
            "PS-103",
            "§1",
            "top-level junk file (move to ./.dev/<category>/ or delete)",
            slug="top-level-junk-file",
        ),
        Rule(
            "PS-104",
            "§1",
            "uses `.playground/` — collapsed into `.dev/` for easier typing",
        ),
        Rule(
            "PS-105",
            "§1",
            (
                "package registers console_scripts but has no `__main__.py` — "
                "`python -m <pkg>` will fail with 'No module named <pkg>.__main__'. "
                "Add `src/<pkg>/__main__.py` that imports and calls the CLI entry "
                "(usually `from . import _cli; _cli.main()`) so both `<pkg>` and "
                "`python -m <pkg>` work."
            ),
        ),
        Rule(
            "PS-106",
            "§1",
            (
                "README.md is missing a coverage badge — every scitex-* "
                "package should surface its current test coverage at the "
                "top of the README so reviewers and downstream consumers "
                "can see at a glance whether the package is well-tested. "
                "Add a `[![coverage](https://img.shields.io/...)](url)` "
                "or `![codecov](https://codecov.io/...)` line near the "
                "title. The badge must be in README.md (not a sub-doc)."
            ),
        ),
        Rule(
            "PS-107",
            "§1",
            (
                "README.md is missing required H2 sections "
                "(## Installation / ## Quick Start / ## Part of SciTeX) — "
                "see _skills/general/04_docs/01_readme_template.md for the "
                "canonical layout."
            ),
        ),
        Rule(
            "PS-109",
            "§1",
            (
                "README.md is missing a PyPI version badge "
                "(badge.fury.io/py/<pkg> or img.shields.io/pypi/v/<pkg>) "
                "in the first ~4 KB."
            ),
        ),
        Rule(
            "PS-110",
            "§1",
            (
                "README.md is missing the Four Freedoms for Research "
                "blockquote — the SciTeX community-license footer."
            ),
        ),
        Rule(
            "PS-111",
            "§1",
            (
                "README.md contains a banned personal email "
                "(ywatanabe@scitex.ai) — SciTeX is a community project."
            ),
        ),
        Rule(
            "PS-112",
            "§1",
            (
                "README.md is missing a SciTeX logo image at the top "
                "(docs/scitex-logo-*.png or docs/assets/images/scitex-logo-*.png)."
            ),
        ),
        Rule(
            "PS-113",
            "§1",
            (
                "README.md is missing a SciTeX icon footer — centered "
                "scitex-icon image link in the last ~2 KB of the file."
            ),
        ),
        Rule(
            "PS-114",
            "§1",
            (
                "README.md `## Problem and Solution` section is prose-only — "
                "convention is a markdown table with columns "
                "`| # | Problem | Solution |`."
            ),
        ),
        Rule(
            "PS-115",
            "§1",
            (
                "README.md `## Part of SciTeX` section does not open with "
                "the canonical `<pkg> is part of [SciTeX](https://scitex.ai)` "
                "sentence. Synergy code is optional; the opener is required."
            ),
        ),
        Rule(
            "PS-108",
            "§1",
            (
                "flat package layout: ≥3 sibling `.py` files at `src/<pkg>/` "
                "share a common prefix (e.g. `_cli_*.py`, `_skills_*.py`) — "
                "promote them to a `<prefix>/` subpackage for navigability. "
                "A common prefix on 3+ flat files is a reliable signal that "
                "the cluster wants to be a directory."
            ),
        ),
        Rule(
            "PS-108b",
            "§1",
            (
                "topical clutter: >15 flat `.py` files at `src/<pkg>/` root "
                "(or any subpackage) without shared prefix. PS-108 only "
                "catches prefix clusters; this catches the second mess "
                "pattern — many flat files sharing a topic but no prefix. "
                "Group into `_release/`, `_docs/`, `_core/`, `_quality/` "
                "subpackages by topical responsibility (single-file "
                "orphans stay flat). See "
                "general/02_package/02_project-structure-src.md."
            ),
        ),
        Rule(
            "PS-116",
            "§1",
            (
                "README.md uses the deprecated `> **Interfaces:** ...` "
                "summary callout. Per 2026-05 convention, put star ratings "
                "directly on each interface section header instead "
                "(e.g. `## Python API ⭐⭐⭐`)."
            ),
        ),
        Rule(
            "PS-117",
            "§1",
            (
                'README.md has a duplicate badge block: a `<p align="center">` '
                "row of img.shields.io / badge.fury.io / readthedocs badges "
                "appears in addition to the canonical "
                "`<!-- scitex-badges:start --> ... :end -->` block. Keep "
                "only the canonical block."
            ),
        ),
        Rule(
            "PS-118",
            "§1",
            (
                "README.md interface section header carries a banned "
                "descriptor like `(Application Programming Interface)`, "
                "`-- for AI Agents`, or `— for AI Agent Discovery`. The "
                "section names themselves carry meaning — strip the prose."
            ),
        ),
        Rule(
            "PS-119",
            "§1",
            (
                "README.md contains a `> **SciTeX users**: pip install scitex "
                "already includes ...` install hint. These belong in the "
                "umbrella `scitex` README, not in sub-package READMEs "
                "(extras like `pip install scitex[ssh]` drift)."
            ),
        ),
        # PS-120 retired 2026-05-18 — the umbrella one-liner content
        # check (pip install scitex[…] + scitex.<module> + scitex <subcmd>
        # tokens) was too strict and clashed with the `uv pip install`
        # recommendation. PS-116 already guards `## Part of SciTeX`
        # section presence; that's sufficient for the surface contract.
        Rule(
            "PS-121",
            "§1",
            (
                "package has `docs/sphinx/conf.py` but no "
                "`src/<pkg>/_sphinx_html/index.html` bundled. scitex-cloud "
                "serves docs from the in-wheel `_sphinx_html/` — without it "
                "the package is invisible at https://scitex.ai/apps/docs/. "
                "Refresh via the canonical CI workflow "
                "(`.github/workflows/docs.yml`)."
            ),
        ),
        Rule(
            "PS-122",
            "§1",
            (
                "package has `docs/sphinx/` but no "
                "`.github/workflows/docs.yml` CI workflow. Auto-refreshing "
                "`_sphinx_html/` in CI is the canonical pattern (see "
                "scitex-ssh as reference). Manual refresh drifts; CI keeps "
                "the bundle fresh on every push to main/develop."
            ),
        ),
        Rule(
            "PS-123",
            "§1",
            (
                "README.md interface section has a `Full X reference` link "
                "pointing at the bare RTD root (e.g. "
                "`https://<pkg>.readthedocs.io/`) instead of a deep-link "
                "anchor page. Use the canonical deep-link per interface — "
                "see `_skills/general/04_docs/01_readme.md` 'Canonical Full "
                "X reference deep-link patterns'."
            ),
        ),
        Rule(
            "PS-124",
            "§1",
            (
                "package has `docs/sphinx/` but no `.readthedocs.yaml` (or "
                "`.readthedocs.yml`) at the repo root. Without it, RTD won't "
                "build the docs. Use the canonical config — see "
                "`_skills/general/04_docs/02_sphinx.md`."
            ),
        ),
        Rule(
            "PS-125",
            "§1",
            (
                "`.readthedocs.yaml` deviates from the canonical SciTeX "
                "shape (version: 2, build.os: ubuntu-22.04, "
                "build.tools.python: '3.11', sphinx.configuration: "
                "docs/sphinx/conf.py). Drift breaks the cross-package "
                "uniformity scitex-cloud relies on."
            ),
        ),
        Rule(
            "PS-126",
            "§1",
            (
                "`docs/sphinx/requirements.txt` is missing or doesn't pin "
                "the canonical SciTeX docs deps (sphinx>=7.0, "
                "sphinx-rtd-theme>=2.0, myst-parser>=2.0, "
                "sphinx-copybutton>=0.5, sphinx-autodoc-typehints>=1.25). "
                "Pinned versions keep RTD builds reproducible across the "
                "ecosystem."
            ),
        ),
        Rule(
            "PS-127",
            "§1",
            (
                "`pyproject.toml [project.urls]` has no "
                '`Documentation = "https://<pkg>.readthedocs.io"` entry '
                "(or it points elsewhere). PyPI surfaces this URL on the "
                "project page; missing it makes the docs invisible to new "
                "users."
            ),
        ),
        Rule(
            "PS-128",
            "§1",
            (
                "`.gitignore` excludes `src/<pkg>/_sphinx_html/` but the "
                "convention requires committing the bundle. scitex-cloud "
                "serves from the in-wheel HTML; CI's hatchling "
                "force-include will fail with `FileNotFoundError: Forced "
                "include not found`. Remove the line."
            ),
        ),
        Rule(
            "PS-129",
            "§1",
            (
                "package source references `SCITEX_<MODULE>_*` env vars "
                "but documents them in NEITHER a README "
                "`## Environment Variables` section NOR a `.env.example` "
                "at repo root. Pick one — see "
                "`_skills/general/04_docs/03_env-vars-and-state.md`."
            ),
        ),
        Rule(
            "PS-130",
            "§1",
            (
                "README has `## Environment Variables` AND `.env.example` "
                "exists at repo root — the two will drift. Pick one: keep "
                "the README table (small lists), OR keep `.env.example` "
                "and reference it from the `## Installation` section."
            ),
        ),
        Rule(
            "PS-131",
            "§1",
            (
                "README.md `## <N> Interfaces` section must have at least "
                "one `<details open>` block — the primary interface, or "
                "all top-rated interfaces when several tie at the highest "
                "star count. The primary's minimal example doubles as "
                "the quick-start (no separate `## Quick Start` H2)."
            ),
        ),
        Rule(
            "PS-132",
            "§1",
            (
                "README.md has a standalone `## Modules` H2 (a hand-curated "
                "table of Python modules + functions). This duplicates the "
                "Python API `<details>` block AND the autoapi page on RTD, "
                "and drifts as the package evolves. Drop the section — "
                "the Python API block + Full API reference deep-link "
                "cover this."
            ),
        ),
        Rule(
            "PS-133",
            "§1",
            (
                "missing CLA.md at repo root — every public scitex-* package "
                "needs a Contributor License Agreement so external PRs can be "
                "merged without legal ambiguity. Use the canonical CLA.md "
                "from any current sibling package as the template."
            ),
        ),
        Rule(
            "PS-134",
            "§1",
            (
                "missing CHANGELOG.md at repo root — every shipping package "
                "needs a Keep-a-Changelog-style file so consumers can see "
                "what changed across versions. New packages start with an "
                "[Unreleased] section."
            ),
        ),
        Rule(
            "PS-135",
            "§1",
            (
                "missing CONTRIBUTING.md at repo root — every public package "
                "needs contributor guidance (branch naming, test workflow, "
                "PR conventions). Use the canonical CONTRIBUTING.md from "
                "any current sibling package as the template."
            ),
        ),
        Rule(
            "PS-136",
            "§1",
            (
                "missing or empty examples/ directory at repo root — every "
                "scitex-* package must show working code: at least one "
                "runnable `examples/<NN_>name.py` (or `.ipynb`) demonstrating "
                "the primary use case. Without examples, agents and humans "
                "have to grep tests/ to learn the API. See `_skills/general/"
                "02_package/01_project-structure-root.md`."
            ),
        ),
        Rule(
            "PS-137",
            "§1",
            (
                "missing README.md at repo root — every package's first-touch "
                "documentation surface. Use the canonical template at "
                "`_skills/general/04_docs/01_readme_template.md`."
            ),
        ),
        Rule(
            "PS-138",
            "§1",
            (
                "missing LICENSE at repo root — every public scitex-* "
                "package must declare its license. Accepted: `LICENSE`, "
                "`LICENSE.md`, or `LICENSE.txt`. The umbrella ships AGPL-3.0 "
                "with the Four-Freedoms-for-Research footer."
            ),
        ),
        Rule(
            "PS-138b",
            "§1",
            (
                "LICENSE file exists but content does not match SPDX "
                "declaration `AGPL-3.0-only` — likely a copyright stub "
                "instead of the full AGPL-3.0 text. The on-disk license "
                "must contain the full GNU AGPL v3 license, not just a "
                "title + copyright line. See "
                "`_skills/general/01_ecosystem/07_license-and-cla.md`."
            ),
        ),
        Rule(
            "PS-139",
            "§1",
            (
                "pyproject.toml lists `scitex` (the umbrella) as a dependency "
                "or extras member. This creates a circular drag: the umbrella "
                "depends on standalones, so a standalone depending on the "
                "umbrella means installing one pulls the entire ecosystem and "
                "every `import scitex_<pkg>` traverses the umbrella's lazy "
                "re-export __init__. Replace with the specific peer "
                "standalone(s) (e.g. `scitex-session>=0.1.0`). See "
                "`_skills/general/03_interface/01_python-api/"
                "11_import-conventions.md`."
            ),
        ),
        Rule(
            "PS-141",
            "§1",
            (
                "README.md is missing a mandatory `## Demo` section "
                "containing at least one visual element. Accepted (inside "
                "the section body): Markdown image `![alt](path.png)`, "
                'HTML `<img src="…">` pointing at a non-shields.io URL, '
                "or a fenced ```mermaid block. Demos drive discovery; "
                "every package must show what it does, not just describe "
                "it."
            ),
        ),
        Rule(
            "PS-142",
            "§1",
            (
                "README.md is missing a mandatory `## Architecture` "
                "section. Accepted body forms: a fenced ```mermaid block, "
                "an ASCII text diagram (fenced code block ≥10 lines), a "
                "file-tree listing (lines containing `├──`/`└──`/`│`), or "
                "an `<img>` tag. Even small packages should sketch their "
                "module layout so readers see structure at a glance."
            ),
        ),
        Rule(
            "PS-143",
            "§1",
            (
                "README.md sections do not appear in canonical order. The "
                "expected order (skipping any section the package omits) "
                "is: `Problem and Solution` → `Installation` → "
                "`Architecture` → `<N> Interfaces` → `Demo` → "
                "`Quick Start` (optional) → `Part of SciTeX`. Re-order "
                "the H2 headers; drift accumulates fast across packages "
                "if order is left to taste."
            ),
        ),
        Rule(
            "PS-144",
            "§1",
            (
                "README.md `## Problem and Solution` table cells violate "
                "bold-emphasis rules. A cell must (a) contain at least "
                "one `**bold**` span, (b) bold ≤ 30 % of the cell's text "
                "(bolding entire sentences defeats emphasis), and (c) be "
                "≤ 200 characters per cell (long prose belongs in section "
                "body, not a row). Bold the key noun phrase only."
            ),
        ),
]

# EOF
