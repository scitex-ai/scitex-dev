"""Project-structure auditor — engine + rules.

Rules cover the automatable items from
`scitex-dev/src/scitex_dev/_skills/general/02_package/01_project-structure-root.md`
(and its sibling `scientific/02_research-project_01_project-structure.md`).

Numbering: ``PS<§><idx>`` (PS = Project Structure), e.g. PS-201 = §2 rule 01.
Mirrors the ``PA<n>`` / ``SK<n>`` / ``M<n>`` pattern of sibling auditors.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import click


@dataclass(frozen=True)
class Rule:
    code: str
    section: str
    message: str
    # Severity drives the audit's exit code:
    #   E (error)   — at least one E finding fails the audit (exit 1)
    #   W (warning) — printed but does not fail (exit 0 if no E findings)
    #   I (info)    — printed only with --severity info; never fails
    # Default W keeps existing rules backward-compatible until each is
    # explicitly tagged. Promote to E when the rule is well-tested and the
    # ecosystem has already been brought into compliance.
    severity: str = "W"
    # Short kebab-case human-readable name (e.g. "examples-need-finished-success").
    # Surfaces in `audit-all` output as `[CODE §X slug] …` so reviewers can
    # read intent without cross-referencing rule numbers.
    slug: str = ""


RULES: dict[str, Rule] = {
    r.code: r
    for r in [
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
                "`python /tmp/write-integration-tests.py <pkg-dir>` "
                "(or the equivalent scitex-dev subcommand)."
            ),
        ),
        # §2 src ↔ tests mirror -------------------------------------------------
        Rule(
            "PS-201",
            "§2",
            "src/<pkg>/ exists but tests/<pkg>/ is missing — every package needs the tests/<pkg>/ parent",
            slug="tests-pkg-parent-missing",
        ),
        Rule(
            "PS-202",
            "§2",
            "src/<pkg>/<sub>/ has files but tests/<pkg>/<sub>/ is missing",
            slug="src-tests-mirror-dir-missing",
        ),
        Rule(
            "PS-203",
            "§2",
            "loose test_*.py at tests/ root that should live inside tests/<pkg>/...",
            slug="loose-top-level-test",
        ),
        Rule(
            "PS-204",
            "§2",
            "orphan test file: tests/<pkg>/<path>/test_*.py with no matching src/<pkg>/<path>/*.py",
            slug="orphan-test-file",
        ),
        Rule(
            "PS-205",
            "§2",
            "wrong public/private prefix (private `_foo.py` must be tested by `test__foo.py`, not `test_foo.py`)",
            slug="test-name-prefix-mismatch",
        ),
        Rule(
            "PS-145",
            "§1",
            (
                "source reads another scitex package's user-state tree "
                "(`~/.scitex/<other-pkg>/...`) or `SCITEX_<OTHER>_*` env "
                "var directly. Cross-package state coupling breaks "
                "`SCITEX_DIR` relocation and standalone-ability. Use the "
                "plugin-port pattern: expose your own `SCITEX_<THIS>_*_DIRS` "
                "slot and let consumers populate it. See "
                "_skills/general/01_ecosystem/06_local-state-directories.md "
                "§9.5."
            ),
            slug="local-state-cross-package-read",
        ),
        Rule(
            "PS-146",
            "§1",
            (
                "pyproject.toml declares an install-time hook (hatch build "
                "hook or setuptools cmdclass) that creates `~/.scitex/"
                "<pkg-short>/` — `pip install` side-effects break wheel "
                "inertness, fresh-CI runs, and `$SCITEX_DIR` relocation. "
                "Drop the hook and rely on lazy `PathManager` mkdir on "
                "first write (§3.5)."
            ),
            slug="local-state-pip-install-side-effect",
        ),
        Rule(
            "PS-147",
            "§1",
            (
                "source writes an eval-form shell-completion line "
                '(`eval "$(_<NAME>_COMPLETE=bash_source <bin>)"`) into '
                "the user's rc file. The eval form re-invokes the binary "
                "on every shell start (~0.4s/binary). Use the cache-file "
                "pattern instead: generate the completion once into "
                "`~/.scitex/<pkg-short>/runtime/completion/<binary>` and "
                "have rc `source` it. See _skills/general/03_interface/02_"
                "cli/03_required-introspection-commands.md."
            ),
            slug="local-state-eval-completion",
        ),
        Rule(
            "PS-150",
            "§1",
            (
                "pyproject.toml `[project.optional-dependencies.dev]` does not "
                "declare `scitex-dev` (or `scitex-dev[cli-audit]`). "
                '`tests/develop/test_audit.py` calls `shutil.which("scitex-dev")` '
                "and pytest.skip()s when absent — i.e. the audit-conformance gate "
                "silently does NOT run in CI's fresh venv. Add `scitex-dev>=0.11.5` "
                "(or current latest) to `[dev]` so the gate fires."
            ),
        ),
        Rule(
            "PS-164",
            "§1",
            (
                "GitHub Actions workflow naming/structure violates convention "
                "(one file = one check, descriptive kebab-case filename; see "
                "_skills/general/02_package/12_workflows-naming.md). Three "
                "sub-checks: vague filename in denylist, multi-job file with "
                "unrelated job IDs, or `name:` field mismatching the filename."
            ),
            slug="workflow-naming",
        ),
        Rule(
            "PS-151",
            "§1",
            (
                "scitex-dev pin floor in `[dev]` is below the known-good version "
                "(currently 0.11.5). Older scitex-dev releases ship a smaller / "
                "differently-classified rule corpus, so the same package gets "
                "different audit verdicts depending on which scitex-dev wheel "
                "PyPI happens to surface. Bump the floor to the current minimum."
            ),
        ),
        Rule(
            "PS-206",
            "§2",
            "placeholder-only test (no `def test_` or `class Test`)",
        ),
        Rule(
            "PS-206b",
            "§2",
            (
                "import-smoke-only test (`def test_*` exists but the file "
                "has no assertion at all — `assert`, `pytest.raises`, "
                "`mock.assert_*`, `self.assertX`, etc.). Pure "
                "`importlib.import_module(...)` smokes pass PS-206 + PS-202 "
                "without exercising behaviour. Add a real assertion or "
                "delete the file."
            ),
        ),
        Rule(
            "PS-210",
            "§2",
            (
                "`[dev]` extras incomplete — an optional `[X]` extra dep is "
                "imported unguarded by the test suite but missing from `[dev]` "
                "(see _skills/general/01_ecosystem/02_dependency-and-version-"
                "pinning.md `[dev]` extras completeness — fastmcp lesson, "
                "2026-05-02). A bare `pip install -e .[dev]` will fail at "
                "test-collection."
            ),
        ),
        Rule(
            "PS-207",
            "§2",
            (
                "empty test directory (no `test_*.py` files, only `__pycache__/` "
                "or nothing) — created during a partial migration but never filled. "
                "Either move the corresponding `tests/<sub>/test_*.py` files in, "
                "or remove the empty dir."
            ),
        ),
        Rule(
            "PS-211",
            "§2",
            (
                "missing `tests/smoke/` layer (fast <60s subprocess-driven CLI "
                "happy-path tests). Every SciTeX package with a CLI should keep "
                "a small set of subprocess-level smoke tests that run on every "
                "PR. Required: ≥1 `tests/smoke/test_*.py` AND register the "
                "`smoke` pytest marker in `[tool.pytest.ini_options].markers`. "
                "Opt-out: `[tool.scitex_dev]\\nno_cli = true` in pyproject.toml. "
                "Severity W during ecosystem adoption — will promote to E."
            ),
            slug="tests-smoke-layer-missing",
        ),
        Rule(
            "PS-212",
            "§2",
            (
                "missing `tests/e2e/` layer (slow end-to-end workflows against "
                "real subsystems). Required: ≥1 `tests/e2e/test_*.py`, register "
                "the `e2e` pytest marker, and gate execution via the `RUN_E2E=1` "
                "env var so the suite is skipped by default. Opt-out: "
                "`[tool.scitex_dev]\\nno_e2e = true` in pyproject.toml. "
                "Severity W during ecosystem adoption — will promote to E."
            ),
            slug="tests-e2e-layer-missing",
        ),
        # §3 tests/ subdirectory convention -------------------------------------
        Rule(
            "PS-301",
            "§3",
            "top-level ./htmlcov/ exists — coverage reports should live in tests/coverage/ (gitignored)",
        ),
        Rule(
            "PS-302",
            "§3",
            "unrecognized subdir at tests/ root (must be tests/<pkg>/ or one of the known categories: scripts/examples/skills/agentic/integration/e2e/github_actions/coverage/results/logs/reports/custom)",
        ),
        Rule(
            "PS-303",
            "§3",
            "examples/<name>.{py,sh,ipynb} has no matching tests/examples/test_<name>.py",
        ),
        Rule(
            "PS-501",
            "§5",
            (
                "examples/<n>_*.py main() does not use @stx.session — the "
                "canonical pattern (see ~/proj/figrecipe/examples/ and "
                "~/proj/scitex-python/examples/01_session.py) decorates main "
                "with @stx.session for auto-CLI, auto-organized output "
                "(SDIR_RUN/FINISHED_SUCCESS/<id>/), config injection, and "
                "session reproducibility. Replace manual `OUTPUT_DIR = "
                "Path(__file__).parent / '<n>_out'` boilerplate with `OUT = "
                "Path(CONFIG.SDIR_RUN)` inside the decorated main()."
            ),
        ),
        Rule(
            "PS-502",
            "§5",
            (
                "examples/<n>_*_out/ exists but is empty (or contains only "
                "__pycache__) — the example was never run end-to-end. Either "
                "execute it once so SciTeX's session machinery populates the "
                "FINISHED_SUCCESS marker, or remove the empty _out/ if the "
                "example doesn't yet work."
            ),
        ),
        Rule(
            "PS-503",
            "§5",
            (
                "examples/<n>_*_out/ has no FINISHED_SUCCESS/<session_id>/ "
                "subdir — the demo's already-run artefacts must be tracked "
                "in git so users see them on GitHub. Run the example once "
                "with @stx.session and commit the FINISHED_SUCCESS dir."
            ),
            slug="examples-need-finished-success",
        ),
        Rule(
            "PS-504",
            "§5",
            (
                "examples/<n>.ipynb has no committed cell outputs — looks "
                "nbstripped. GitHub renders cell outputs inline, so the "
                "demo is invisible without them. Re-run the notebook and "
                "commit with outputs intact."
            ),
        ),
        Rule(
            "PS-505",
            "§5",
            (
                "examples/<n>.ipynb has a sibling test "
                "tests/examples/test_<n>.py but the test does not invoke "
                "`nbconvert --execute` or `pytest --nbval` — runpy/import "
                "tricks don't execute notebooks. Mirror the .py "
                "smoke-test convention with one of those commands."
            ),
        ),
        Rule(
            "PS-506",
            "§5",
            (
                "examples/<n>.ipynb imports matplotlib but lacks the "
                "`%matplotlib inline` cell magic — figure outputs won't "
                "embed in the notebook, so GitHub-rendered cells will be "
                "blank. Add `%matplotlib inline` near the top."
            ),
        ),
        Rule(
            "PS-507",
            "§5",
            (
                "examples/<n>.ipynb imports matplotlib but does not call "
                "`plt.show()` (or rely on inline auto-display) — figures "
                "may not appear in the rendered cell outputs. Call "
                "`plt.show()` explicitly after each plot."
            ),
        ),
        Rule(
            "PS-508",
            "§5",
            (
                "examples/<n>.ipynb contains warning output in committed "
                "cells (DeprecationWarning, UserWarning, FutureWarning, "
                "RuntimeWarning, or stderr-stream `Warning:` text). "
                "Demos must be clean — silence the warning at the source, "
                "filter it explicitly with `warnings.filterwarnings`, or "
                "fix the underlying cause before re-running and committing."
            ),
        ),
        # §4 docs/ structure ----------------------------------------------------
        Rule(
            "PS-401",
            "§4",
            "./docs/to_claude/ is tracked — must be gitignored (local-machine agent context, not part of the shipped repo)",
        ),
        Rule(
            "PS-402",
            "§4",
            "top-level ./assets/ exists — figures/screenshots belong under ./docs/assets/",
        ),
    ]
}

# Severity escalation table.
#
# Per 2026-05-06 directive: every rule that ships a concrete spec defaults to
# E (error → fails CI). Demote back to W only after a documented false
# positive lands on develop. New rules MAY start at W during their initial
# bake-in, but the bar for staying W is "active false-positive history",
# not "we haven't promoted it yet".
#
# E (error) — fails CI; the rule is well-tested and the fix is mechanical.
# W (warn)  — prints, doesn't fail; for rules with active false-positive
#             history that haven't been demoted yet.
# I (info)  — printed only with --severity info; never fails. Use for
#             purely advisory categorizations (no actionable violation).
_SEVERITY_OVERRIDES: dict[str, str] = {
    # Structural — must hold for any package
    "PS-101": "E",  # missing pyproject.toml
    "PS-102": "E",  # forbidden top-level dir (logs/, mgmt/, ...)
    "PS-103": "E",  # top-level junk file
    "PS-104": "E",  # uses .playground/
    "PS-105": "E",  # console_scripts present but no __main__.py
    # README content — every public package follows the convention
    "PS-106": "E",
    "PS-107": "E",
    "PS-108": "E",
    "PS-108b": "E",
    "PS-109": "E",
    "PS-110": "E",
    "PS-111": "E",
    "PS-112": "E",
    "PS-113": "E",
    "PS-114": "E",
    "PS-115": "E",
    "PS-116": "E",
    "PS-117": "E",
    "PS-118": "E",
    "PS-119": "E",
    # PS-120 retired 2026-05-18 (umbrella one-liner content rule).
    "PS-123": "E",
    "PS-129": "E",
    "PS-130": "E",
    "PS-131": "E",
    "PS-132": "E",
    # Sphinx / RTD bundle
    "PS-121": "E",
    "PS-122": "E",
    "PS-124": "E",
    "PS-125": "E",
    "PS-126": "E",
    "PS-127": "E",
    "PS-128": "E",
    # Community files — every public package needs them
    "PS-133": "E",  # CLA.md
    "PS-134": "E",  # CHANGELOG.md
    "PS-135": "E",  # CONTRIBUTING.md
    "PS-136": "E",  # examples/
    "PS-137": "E",  # README.md
    "PS-138": "E",  # LICENSE present
    "PS-138b": "E",  # LICENSE content matches SPDX (no stub)
    "PS-139": "E",  # pyproject.toml depends on scitex umbrella (anti-pattern)
    "PS-140": "E",  # missing/stale tests/integration/test_cross_package_imports.py
    "PS-141": "E",  # README missing `## Demo` with visual content
    "PS-142": "E",  # README missing `## Architecture` with diagram/tree
    "PS-145": "W",  # cross-package state read (bake-in: warn first)
    "PS-146": "E",  # pip-install side-effect (clear violation)
    "PS-147": "W",  # eval-form shell completion (bake-in: warn first)
    "PS-152": "W",  # README split Problem/Solution headings (warn)
    "PS-153": "W",  # README architecture file-tree, no mermaid (warn)
    "PS-154": "W",  # README installation not canonical (warn)
    "PS-155": "I",  # README badge row not two centered rows (info)
    "PS-156": "I",  # examples/ has .py but zero .ipynb (info)
    "PS-157": "W",  # codecov badge URL unbranched (warn)
    "PS-158": "I",  # RTD badge uses readthedocs.org baked label (info)
    "PS-159": "W",  # README figure/table numbering broken (warn)
    "PS-160": "W",  # README figure/table missing caption (warn)
    "PS-161": "W",  # codecov.yml coverage target below 90 (warn)
    "PS-162": "W",  # README missing Codecov badge (warn)
    "PS-163": "W",  # README missing Read-the-Docs badge (warn)
    "PS-150": "W",  # [dev] missing scitex-dev pin — audit gate silently skips
    "PS-151": "W",  # scitex-dev pin floor < known-good (rule corpus drift)
    "PS-164": "W",  # workflow naming/structure (warn-only during adoption)
    # src ↔ tests mirror — load-bearing for CI confidence
    "PS-201": "E",
    "PS-202": "E",
    "PS-203": "E",
    "PS-204": "E",
    "PS-205": "E",
    "PS-206": "E",  # placeholder-only test (no `def test_*` / `class Test*` at all)
    "PS-206b": "W",  # has `def test_*` but body has no assertion (import-smoke only)
    "PS-207": "E",  # empty test directory
    "PS-210": "E",  # [dev] extras incomplete
    "PS-211": "W",  # tests/smoke/ layer missing — W during ecosystem adoption
    "PS-212": "W",  # tests/e2e/ layer missing  — W during ecosystem adoption
    "PS-301": "E",  # top-level htmlcov/
    "PS-302": "E",  # unrecognized tests/ subdir
    "PS-303": "E",  # examples/<n>.py without tests/examples/test_<n>.py
    "PS-401": "E",  # docs/to_claude/ tracked
    "PS-402": "E",  # top-level assets/
    "PS-501": "E",  # examples missing @stx.session
    "PS-502": "E",  # empty examples/<n>_out/
    "PS-503": "E",  # examples/<n>_out/ missing FINISHED_SUCCESS/<id>/
    "PS-504": "E",  # .ipynb has no committed cell outputs
    "PS-505": "E",  # .ipynb test does not nbconvert / nbval
    "PS-506": "E",  # .ipynb missing %matplotlib inline
    "PS-507": "E",  # .ipynb missing plt.show()
    "PS-508": "E",  # .ipynb has warning output in committed cells
}

# Human-readable kebab-case slugs. Surfaced inline in audit output as
# `[CODE §X slug]` so reviewers can read intent without cross-referencing
# rule numbers. Backfilled in batches; missing entries render in the old
# `[CODE §X]` form (no breakage). New rules SHOULD include a slug from
# definition.
_SLUGS: dict[str, str] = {
    # §1 — top-level layout already slugged at definition (PS-101–PS-103)
    "PS-104": "uses-playground-dir",
    "PS-105": "main-py-missing",
    # README structure
    "PS-106": "readme-missing-coverage-badge",
    "PS-107": "readme-missing-h2-sections",
    # PS-108 / PS-108b detect flat-package-layout patterns in src/, NOT
    # README badges. (The badge-shaped slugs that used to sit here
    # described long-retired README rules and confused every reader.)
    "PS-108": "src-prefix-cluster-mess",
    "PS-108b": "src-flat-py-files-over-threshold",
    "PS-109": "readme-missing-pypi-version-badge",
    "PS-110": "readme-missing-four-freedoms",
    "PS-111": "readme-personal-email",
    "PS-112": "readme-missing-logo",
    "PS-113": "readme-banned-emoji",
    "PS-114": "readme-banned-marketing",
    "PS-115": "readme-missing-architecture",
    "PS-116": "readme-banned-buzzword",
    "PS-117": "readme-missing-quickstart",
    "PS-118": "readme-missing-installation",
    "PS-119": "readme-missing-part-of-scitex",
    # PS-120 retired 2026-05-18.
    "PS-123": "readme-banned-future-claim",
    "PS-129": "readme-banned-trademark-symbol",
    "PS-130": "readme-missing-related-projects",
    "PS-131": "readme-missing-citation",
    "PS-132": "readme-missing-roadmap",
    # Sphinx / RTD
    "PS-121": "rtd-onboarding-missing",
    "PS-122": "rtd-config-missing",
    "PS-124": "sphinx-conf-missing",
    "PS-125": "sphinx-makefile-missing",
    "PS-126": "sphinx-extensions-bad",
    "PS-127": "sphinx-theme-bad",
    "PS-128": "sphinx-build-broken",
    # Community files
    "PS-133": "missing-cla",
    "PS-134": "missing-changelog",
    "PS-135": "missing-contributing",
    "PS-136": "missing-examples-dir",
    "PS-137": "missing-readme",
    "PS-138": "missing-license",
    "PS-138b": "license-stub-mismatched",
    "PS-139": "pyproject-depends-on-umbrella",
    "PS-140": "cross-package-imports-test-missing",
    "PS-141": "readme-missing-demo",
    "PS-142": "readme-missing-architecture-diagram",
    "PS-143": "readme-missing-badge-row",
    "PS-144": "readme-missing-pypi-status",
    "PS-152": "readme-split-problem-solution",
    "PS-153": "readme-architecture-filetree-not-mermaid",
    "PS-154": "readme-installation-not-canonical",
    "PS-155": "readme-badge-row-not-two-rows",
    "PS-156": "examples-no-ipynb",
    "PS-157": "readme-codecov-badge-unbranched",
    "PS-158": "readme-rtd-badge-baked-label",
    "PS-159": "readme-figures-tables-numbering",
    "PS-160": "readme-figures-tables-missing-caption",
    "PS-161": "readme-codecov-coverage-target-too-low",
    "PS-162": "readme-missing-codecov-badge",
    "PS-163": "readme-missing-rtd-badge",
    "PS-150": "dev-extras-missing-scitex-dev",
    "PS-151": "dev-extras-scitex-dev-floor-too-old",
    # §2 src↔tests already slugged at definition (PS-201–PS-205)
    "PS-206": "test-placeholder-only",
    "PS-206b": "test-import-smoke-only",
    "PS-207": "empty-test-dir",
    "PS-210": "dev-extras-incomplete",
    # §3 docs / examples
    "PS-301": "top-level-htmlcov",
    "PS-302": "tests-unknown-subdir",
    "PS-303": "example-without-test",
    # §4 docs/to_claude
    "PS-401": "docs-to-claude-tracked",
    "PS-402": "top-level-assets",
    # §5 examples + notebooks (PS-503 already slugged)
    "PS-501": "example-without-stx-session",
    "PS-502": "examples-out-empty",
    "PS-504": "ipynb-no-cell-outputs",
    "PS-505": "ipynb-test-not-nbconvert",
    "PS-506": "ipynb-missing-matplotlib-inline",
    "PS-507": "ipynb-missing-plt-show",
    "PS-508": "ipynb-warning-in-output",
}


# Apply the overrides — replace each tagged Rule with a promoted copy that
# carries both the (optional) severity override and the (optional) slug.
def _patch(rule: Rule) -> Rule:
    sev = _SEVERITY_OVERRIDES.get(rule.code, rule.severity)
    slug = rule.slug or _SLUGS.get(rule.code, "")
    if sev == rule.severity and slug == rule.slug:
        return rule
    return Rule(rule.code, rule.section, rule.message, sev, slug)


RULES = {code: _patch(rule) for code, rule in RULES.items()}

# hook-bypass: line-limit
# Sidecar rule registration — see ._extra_rules / GITIGNORED/REFACTORING.md.
from ._extra_rules import EXTRA_RULES as _EXTRA_RULES  # noqa: E402

for _c, _sec, _msg, _sev, _slug in _EXTRA_RULES:
    RULES[_c] = Rule(_c, _sec, _msg, _sev, _slug)


@dataclass
class Violation:
    rule: str
    where: str
    detail: str

    def format(self) -> str:
        r = RULES.get(self.rule)
        section = r.section if r else "?"
        sev = r.severity if r else "W"
        slug = f" {r.slug}" if r and r.slug else ""
        return f"  [{sev}] [{self.rule} {section}{slug}] {self.where}: {self.detail}"

    @property
    def severity(self) -> str:
        r = RULES.get(self.rule)
        return r.severity if r else "W"


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Test-name patterns: split into private (test__name.py) and public (test_name.py).
# The leading-underscore in the source becomes a double underscore in the test.
# Captured group allows optional extra leading underscores so dunder sources
# like `__main__.py` (test `test___main__.py`) are recognised as having a
# valid src mirror.
_PRIVATE_TEST_RE = re.compile(r"^test__(_*[A-Za-z0-9][A-Za-z0-9_]*)\.py$")
_PUBLIC_TEST_RE = re.compile(r"^test_([A-Za-z0-9][A-Za-z0-9_]*)\.py$")

# Allowed at tests/ root. STRICT: only pytest infrastructure files —
# no test files. Module-mirror tests belong under tests/<pkg>/; cross-
# cutting tests belong in their category subdir (tests/integration/,
# tests/e2e/, tests/examples/, …). If a legitimate exception comes up,
# update this set rather than letting tests-at-root drift back in.
_META_TESTS_AT_ROOT = frozenset(
    {
        "__init__.py",
        "conftest.py",
    }
)

# Categories whose §2 (src ↔ tests mirror) checks are skipped.
# Templates are scaffolds; datasets are data-only; archived entries are
# read-only history. The §1, §3, §4 rules still apply.
_MIRROR_EXEMPT_CATEGORIES = frozenset({"template", "dataset"})

# Recognized test-category subdirectories at tests/ root.
# A repo's tests/ subdirs must come from this set (or be the package mirror
# tests/<pkg>/). Anything else is flagged as PS-207.
# See _skills/general/02_package/01_project-structure-root.md §"./tests".
_KNOWN_TEST_SUBDIRS = frozenset(
    {
        "scripts",  # mirror of ./scripts/ (research projects)
        "examples",  # one test per ./examples/ file
        "skills",  # structural tests for _skills/
        "agentic",  # agentic-trigger tests (LLM invokes the skill)
        "integration",  # cross-module / cross-package
        "smoke",  # fast (<60s) CLI happy-path subprocess tests (PS-211)
        "e2e",  # end-to-end pipelines (PS-212)
        "github_actions",
        "coverage",  # HTML / XML reports — gitignored
        "results",  # general test-run artifacts spanning topics
        # (coverage data files, fixtures output, captured payloads) — gitignored
        "logs",  # pytest run logs — gitignored
        "reports",  # agent-generated summaries — optional
        "custom",  # legacy: tests with no source counterpart
        "develop",  # dev-hygiene tests (audit conformance, etc.) —
        # generated by `scitex-dev ecosystem write-audit-test`
        "__pycache__",  # always present, never our concern
    }
)

# Path-substring blacklist for walks (mirrors the prior-art shell script's
# EXCLUDE_PATHS in scitex-python/tests/sync_tests_with_source.sh).
_WALK_BLACKLIST_RE = re.compile(
    r"(?:^|/)("
    r"\..*"  # hidden dirs (.old, .git, .pytest_cache, ...)
    r"|deprecated.*"
    r"|archive.*"
    r"|backup.*"
    r"|tmp.*"
    r"|temp.*"
    r"|RUNNING"
    r"|FINISHED"
    r"|FINISHED_SUCCESS"
    r"|2024Y.*"
    r"|2025Y.*"
    r"|2026Y.*"
    r"|__pycache__"
    r")(?:/|$)"
)


def _is_blacklisted(path: Path, root: Path) -> bool:
    """True if any path component below `root` is in the blacklist."""
    try:
        rel = path.relative_to(root).as_posix()
    except ValueError:
        return False
    return bool(_WALK_BLACKLIST_RE.search(rel))


# Forbidden top-level directories.
_FORBIDDEN_TOP_DIRS = {
    "mgmt": "no longer used in scitex (see _skills/general/02_package/01_project-structure-root.md)",
    "references": "no longer used in scitex",
    "htmlcov": "coverage reports should live in tests/coverage/",
    "assets": "use ./docs/assets/ instead",
    ".playground": "collapsed into .dev/ for easier typing",
    "logs": "runtime artifact — move to ./GITIGNORED/logs/ or ./tests/logs/ and add to .gitignore",
    "catboost_info": "CatBoost training artifact — must be gitignored (add `catboost_info/` to .gitignore)",
    "signatures": "scratch dir — move to ./GITIGNORED/signatures/ if needed locally",
    "scitex": "orphan module dir — the real package lives in src/<pkg>/. Use a hidden ./.scitex/ for runtime state, never a visible ./scitex/.",
    "unknown_out": "@stx.session output landed at repo root — re-run from a script directory or set CONFIG.SDIR_RUN. Move the dir aside if you need to keep it.",
}

# Top-level junk-file patterns (substring match on the basename).
_JUNK_FILE_RE = re.compile(
    r"^(tmp.*\.(py|ipynb)|quick.*\.py|scratch.*\.py|untitled.*\.(py|ipynb)|debug\.log|.*\.tmp)$"
)


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def _import_name(distribution: str) -> str:
    """Mirror sibling auditors: dist -> import name (`-` -> `_`)."""
    return distribution.replace("-", "_")


def _resolve_repo_root(distribution: str, repo: Path | None) -> Path | None:
    """Return the repo root Path or None if it can't be located.

    If `repo` is given, it's used directly. Otherwise we resolve the
    package via `importlib.util.find_spec` and walk up to the repo root
    (assumed to contain `pyproject.toml`). Falls back to None.
    """
    if repo is not None:
        return repo
    import importlib.util

    spec = importlib.util.find_spec(_import_name(distribution))
    if spec is None or not spec.submodule_search_locations:
        return None
    for loc in spec.submodule_search_locations:
        # src/<pkg>/__init__.py → walk up two levels for src layout
        candidate = Path(loc).parent.parent
        if (candidate / "pyproject.toml").is_file():
            return candidate
        # flat layout fallback
        candidate = Path(loc).parent
        if (candidate / "pyproject.toml").is_file():
            return candidate

    # Fallback: module is in site-packages (non-editable PyPI install).
    # Try common development checkout locations.
    proj_roots: list[Path] = []
    try:
        home_proj = Path.home() / "proj"
        if home_proj.is_dir():
            proj_roots.append(home_proj)
    except Exception:
        pass
    try:
        for home_dir in Path("/home").iterdir():
            p = home_dir / "proj"
            if p.is_dir() and p not in proj_roots:
                proj_roots.append(p)
    except Exception:
        pass
    for root in proj_roots:
        candidate = root / distribution
        if (candidate / "pyproject.toml").is_file():
            return candidate.resolve()

    return None


# ---------------------------------------------------------------------------
# Rule checks
# ---------------------------------------------------------------------------


def _check_top_level(repo: Path, out: list[Violation]) -> None:
    """PS-101 / PS-102 / PS-103 / PS-104 / PS-105 / PS-133-PS-135."""
    if not (repo / "pyproject.toml").is_file():
        out.append(Violation("PS-101", str(repo), "no pyproject.toml at repo root"))

    # PS-133-PS-138: required community files at repo root.
    # LICENSE has no extension (PEP-639 / ecosystem convention); accept LICENSE
    # or LICENSE.md or LICENSE.txt.
    for code, fname in (
        ("PS-133", "CLA.md"),
        ("PS-134", "CHANGELOG.md"),
        ("PS-135", "CONTRIBUTING.md"),
        ("PS-137", "README.md"),
    ):
        if not (repo / fname).is_file():
            out.append(Violation(code, str(repo), f"missing {fname}"))
    from ._check_license import (
        check_license_content,
        find_license,
        spdx_from_pyproject,
    )

    license_path = find_license(repo)
    if license_path is None:
        out.append(
            Violation("PS-138", str(repo), "missing LICENSE (or LICENSE.md/.txt)")
        )
    else:
        try:
            spdx_match = spdx_from_pyproject(repo)
        except Exception:
            spdx_match = None
        violation_msg = check_license_content(license_path, spdx_match)
        if violation_msg:
            out.append(Violation("PS-138b", str(repo), violation_msg))

    # PS-136: examples/ must exist and have at least one runnable file.
    examples = repo / "examples"
    if not examples.is_dir():
        out.append(Violation("PS-136", str(repo), "no examples/ directory"))
    else:
        runnable = [
            p
            for p in examples.rglob("*")
            if p.is_file()
            and p.suffix in {".py", ".ipynb", ".sh"}
            and not p.name.startswith("__")
            and "__pycache__" not in p.parts
        ]
        if not runnable:
            out.append(
                Violation(
                    "PS-136",
                    str(examples),
                    "examples/ exists but contains no .py/.ipynb/.sh",
                )
            )
        else:
            # PS-156: prefer .ipynb examples — fires only when examples/
            # has runnable .py files but zero .ipynb. Packages that mix
            # .py and .ipynb (or are pure-.ipynb) are silent.
            py_count = sum(1 for p in runnable if p.suffix == ".py")
            ipynb_count = sum(1 for p in runnable if p.suffix == ".ipynb")
            if py_count > 0 and ipynb_count == 0:
                out.append(
                    Violation(
                        "PS-156",
                        str(examples),
                        (
                            f"examples/ has {py_count} `.py` script(s) "
                            "and zero `.ipynb` notebooks — prefer "
                            "Jupyter notebooks (see "
                            "scitex-seizure-metrics/examples/). Mixed "
                            ".py + .ipynb is also fine."
                        ),
                    )
                )

    for dirname, why in _FORBIDDEN_TOP_DIRS.items():
        candidate = repo / dirname
        if candidate.is_dir():
            code = "PS-104" if dirname == ".playground" else "PS-102"
            out.append(Violation(code, str(candidate), why))

    # PS-103: anything at repo root that is not in the strict baseline,
    # not hidden, and not whitelisted via .scitex/dev/config.yaml.
    from ._root_whitelist import _suggest_relocation, list_violations

    for basename, kind in list_violations(repo):
        out.append(
            Violation(
                "PS-103",
                str(repo / basename),
                (
                    f"top-level {kind}: {basename} "
                    f"({_suggest_relocation(basename, kind)})"
                ),
            )
        )

    # PS-105: console_scripts present but no __main__.py — `python -m <pkg>`
    # would fail with "No module named <pkg>.__main__".
    pyp = repo / "pyproject.toml"
    if pyp.is_file():
        text = pyp.read_text(encoding="utf-8", errors="replace")
        has_console_scripts = "[project.scripts]" in text or "console_scripts" in text
        if has_console_scripts:
            # Find src/<pkg>/ candidates and check each top-level __main__.py.
            src = repo / "src"
            if src.is_dir():
                for pkg_dir in src.iterdir():
                    if not pkg_dir.is_dir() or pkg_dir.name.startswith("_"):
                        continue
                    if not (pkg_dir / "__init__.py").is_file():
                        continue
                    if not (pkg_dir / "__main__.py").is_file():
                        out.append(
                            Violation(
                                "PS-105",
                                str(pkg_dir),
                                f"missing {pkg_dir.name}/__main__.py — "
                                "`python -m " + pkg_dir.name + "` will fail. "
                                "Add a __main__.py that imports & calls the CLI entry.",
                            )
                        )


def _src_pkg_dir(repo: Path, distribution: str) -> Path | None:
    """Return `src/<pkg>/` if it exists, else None."""
    candidate = repo / "src" / _import_name(distribution)
    return candidate if candidate.is_dir() else None


def _tests_root(repo: Path) -> Path | None:
    candidate = repo / "tests"
    return candidate if candidate.is_dir() else None


def _check_mirror(
    repo: Path,
    distribution: str,
    out: list[Violation],
) -> None:
    """PS-201 / PS-202 / PS-203 / PS-204 / PS-205 — src ↔ tests mirror."""
    src_pkg = _src_pkg_dir(repo, distribution)
    tests_root = _tests_root(repo)
    if src_pkg is None or tests_root is None:
        # Without either side, mirror checks don't apply (a different rule
        # — PS-101 / future PS-105 — will catch missing structure).
        return

    import_name = _import_name(distribution)
    tests_pkg = tests_root / import_name

    # PS-201: tests/<pkg>/ must exist
    if not tests_pkg.is_dir():
        out.append(
            Violation(
                "PS-201",
                str(tests_root),
                f"missing `tests/{import_name}/` parent — needed even when most tests are flat",
            )
        )
        # Without the parent we can't run the deeper mirror checks meaningfully.
        # Still scan PS-203 / loose top-level test files.
        _check_loose_top_level_tests(tests_root, src_pkg, import_name, out)
        return

    # PS-203: any test_*.py at tests/ root that's not a known meta-test
    _check_loose_top_level_tests(tests_root, src_pkg, import_name, out)

    # Walk src/<pkg>/ — every directory with .py files needs a mirror.
    # Skip directories that aren't tracked in git (gitignored local-only
    # artifacts like src/<pkg>/app/ — they don't ship in the wheel and
    # don't need test coverage). The ignore-aware check is silent when
    # git isn't available so non-git checkouts still get flagged.
    for src_dir in [d for d in src_pkg.rglob("*") if d.is_dir() and _has_py(d)]:
        if _is_git_ignored(src_dir, repo):
            continue
        rel = src_dir.relative_to(src_pkg)
        mirror_dir = tests_pkg / rel
        if not mirror_dir.is_dir():
            out.append(
                Violation(
                    "PS-202",
                    str(src_dir),
                    f"no matching tests/{import_name}/{rel}/",
                )
            )

    # PS-205: per-file public/private prefix consistency.
    # For each src .py file, expected test name lives under tests/<pkg>/<rel>/.
    # When src has BOTH a public `foo.py` AND a private `_foo.py` in the
    # same directory (rare but legitimate — see scitex-dev dashboard), each
    # of `test_foo.py` / `test__foo.py` is the legitimate counterpart of one
    # of them. The naive "wrong_name exists" check then false-positives
    # because the OTHER variant's correct test looks misnamed for THIS one.
    # Skip the flag when both src variants exist.
    for src_file in src_pkg.rglob("*.py"):
        if src_file.name == "__init__.py":
            continue
        rel = src_file.relative_to(src_pkg)
        is_private = src_file.name.startswith("_")
        stem = src_file.stem
        if is_private:
            expected_name = f"test_{stem}.py"  # _foo.py → test__foo.py
        else:
            expected_name = f"test_{stem}.py"  # foo.py  → test_foo.py
        wrong_name = f"test_{stem.lstrip('_')}.py" if is_private else f"test__{stem}.py"
        target_dir = tests_pkg / rel.parent
        if not target_dir.is_dir():
            continue  # PS-202 already flagged this
        # Both-variant guard: if the "other" src file also exists, the file
        # at wrong_path is its legitimate test, not a misnamed copy of ours.
        if is_private:
            other_src = src_file.with_name(src_file.name[1:])  # strip leading _
        else:
            other_src = src_file.with_name(f"_{src_file.name}")
        if other_src.is_file():
            continue
        wrong_path = target_dir / wrong_name
        if wrong_path.is_file():
            out.append(
                Violation(
                    "PS-205",
                    str(wrong_path),
                    (
                        f"private `{rel.name}` should be tested by `{expected_name}` "
                        f"(double underscore), not `{wrong_name}`"
                        if is_private
                        else f"public `{rel.name}` should be `{expected_name}` "
                        f"(single underscore), not `{wrong_name}`"
                    ),
                )
            )

    # PS-204: orphan test files — every test_*.py under tests/<pkg>/ should
    # have a matching src counterpart. Hinter is built once and reused so
    # the basename index is amortized across all orphans in this package.
    from ._check_orphan_hint import build_orphan_hinter

    _hint = build_orphan_hinter(src_pkg, repo)
    for test_file in tests_pkg.rglob("test_*.py"):
        rel = test_file.relative_to(tests_pkg)
        if not _test_has_src_match(test_file, rel, src_pkg):
            out.append(Violation("PS-204", str(test_file), _hint(rel)))


def _has_py(d: Path) -> bool:
    """True iff this dir has at least one .py file (excluding __init__)."""
    if not d.is_dir():
        return False
    for child in d.iterdir():
        if child.is_file() and child.suffix == ".py" and child.name != "__init__.py":
            return True
    return False


def _is_git_ignored(path: Path, repo: Path) -> bool:
    """True iff `path` is gitignored relative to `repo`.

    Returns False when git is unavailable or the path isn't inside a git
    repo — non-git checkouts (sdist installs, tarball extracts) still
    get full PS-202 coverage. Used to skip src subdirs that exist locally
    but won't ship in the wheel (e.g. src/<pkg>/app/ if it's listed in
    .gitignore as a developer-only scratch area).
    """
    import shutil
    import subprocess

    git = shutil.which("git")
    if git is None or not (repo / ".git").exists():
        return False
    try:
        result = subprocess.run(
            [git, "-C", str(repo), "check-ignore", "--quiet", str(path)],
            capture_output=True,
            timeout=3,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    # check-ignore exits 0 when the path IS ignored, 1 when it isn't,
    # 128 on any other error. Only treat exit 0 as "ignored".
    return result.returncode == 0


def _check_loose_top_level_tests(
    tests_root: Path,
    src_pkg: Path,
    import_name: str,
    out: list[Violation],
) -> None:
    """PS-203 — loose test_*.py at tests/ root that should be under tests/<pkg>/."""
    for child in tests_root.iterdir():
        if not child.is_file() or not child.name.startswith("test_"):
            continue
        if child.name in _META_TESTS_AT_ROOT:
            continue
        # Try to find a src counterpart so we can suggest where to move it.
        suggestion = _suggest_test_location(child.name, src_pkg, import_name)
        out.append(
            Violation(
                "PS-203",
                str(child),
                suggestion or f"move under tests/{import_name}/...",
            )
        )


def _suggest_test_location(
    test_name: str, src_pkg: Path, import_name: str
) -> str | None:
    """Return a hint like 'move to tests/<pkg>/<rel>/<test>.py' if we can find
    a source counterpart, else None."""
    m = _PRIVATE_TEST_RE.match(test_name)
    if m:
        target_stem = "_" + m.group(1)
    else:
        m = _PUBLIC_TEST_RE.match(test_name)
        if not m:
            return None
        target_stem = m.group(1)
    for src_file in src_pkg.rglob(f"{target_stem}.py"):
        rel = src_file.relative_to(src_pkg).parent
        return f"move to tests/{import_name}/{rel}/{test_name}".rstrip("/")
    return None


def _test_has_src_match(test_file: Path, rel: Path, src_pkg: Path) -> bool:
    """Does the test name correspond to an existing src file under the
    same rel dir?

    Direct match: ``test__foo.py`` ↔ ``_foo.py``,
                  ``test_foo.py``  ↔  ``foo.py``.

    Descriptor suffix: ``test__foo_real.py``, ``test__foo_branches.py``,
    ``test__foo_round_trip.py`` etc. — when the literal candidate is
    missing, strip trailing ``_<descriptor>`` segments and try again so
    a single src file can host multiple themed test modules without
    tripping the orphan rule.
    """
    name = test_file.name

    def _direct(stem: str, prefix: str) -> bool:
        return (src_pkg / rel.parent / f"{prefix}{stem}.py").is_file()

    def _with_descriptor_strip(stem: str, prefix: str) -> bool:
        # Greedy strip from the right: foo_round_trip → foo_round → foo.
        parts = stem.split("_")
        while len(parts) > 1:
            parts.pop()
            if _direct("_".join(parts), prefix):
                return True
        return False

    m = _PRIVATE_TEST_RE.match(name)
    if m:
        stem = m.group(1)
        return _direct(stem, "_") or _with_descriptor_strip(stem, "_")
    m = _PUBLIC_TEST_RE.match(name)
    if m:
        stem = m.group(1)
        return _direct(stem, "") or _with_descriptor_strip(stem, "")
    return False  # malformed test name — caller may flag separately


def _check_tests_subdir_convention(
    repo: Path, distribution: str, out: list[Violation]
) -> None:
    """PS-301 / PS-302 / PS-303 — tests/ root layout."""
    # PS-301: top-level htmlcov/ should be tests/coverage/.
    if (repo / "htmlcov").is_dir():
        out.append(
            Violation(
                "PS-301",
                str(repo / "htmlcov"),
                "rename to tests/coverage/ and gitignore (replaces top-level ./htmlcov/)",
            )
        )

    tests_root = _tests_root(repo)
    if tests_root is None:
        return

    # PS-302: every subdir at tests/ root must be either tests/<pkg>/ (the
    # package mirror) or one of the known categories.
    import_name = _import_name(distribution)
    for child in tests_root.iterdir():
        if not child.is_dir():
            continue
        if child.name == import_name:
            continue
        if child.name in _KNOWN_TEST_SUBDIRS:
            continue
        if _is_blacklisted(child, tests_root):
            continue  # transient junk; ignore
        out.append(
            Violation(
                "PS-302",
                str(child),
                f"unrecognized: rename to tests/{import_name}/{child.name}/ "
                "or move to one of the known categories",
            )
        )

    # PS-303: every examples/<file> should have a matching tests/examples/test_<stem>.py.
    examples_dir = repo / "examples"
    tests_examples = tests_root / "examples"
    if examples_dir.is_dir():
        for ex in examples_dir.iterdir():
            if not ex.is_file():
                continue
            if ex.suffix not in {".py", ".sh", ".ipynb"}:
                continue
            if ex.name.startswith("00_run_all"):
                continue  # dispatcher — not a demo file
            if _is_blacklisted(ex, examples_dir):
                continue
            expected = tests_examples / f"test_{ex.stem}.py"
            if not expected.is_file():
                out.append(
                    Violation(
                        "PS-303",
                        str(ex),
                        f"missing matching tests/examples/test_{ex.stem}.py",
                    )
                )


def _check_placeholder_tests(repo: Path, out: list[Violation]) -> None:
    """PS-206 + PS-206b — placeholder-only / import-smoke-only test detection.

    PS-206 (ERROR): file has no `def test_*` / `class Test*` / `test_x = factory()`
    at all — pytest will not collect anything from it.

    PS-206b (WARN): file has a collectable test but no assertion-like call in
    the entire module. Catches the auto-generated importlib smoke pattern:

        def test_module_imports():
            importlib.import_module("scitex_db._foo")

    which passes PS-202 (mirror exists) + PS-206 (test fn present) without
    exercising any behaviour.
    """
    tests_root = _tests_root(repo)
    if tests_root is None:
        return
    has_def_or_class_re = re.compile(
        # Accept `def test_*`, `async def test_*`, or `class Test*`.
        r"^\s*(?:async\s+)?(def\s+test_|class\s+Test)",
        re.MULTILINE,
    )
    has_factory_assign_re = re.compile(r"^test_[A-Za-z0-9_]*\s*=", re.MULTILINE)
    # Any of these counts as "exercises behaviour":
    # - bare `assert ...`
    # - pytest.raises / pytest.warns
    # - unittest TestCase.assertX (assertEqual, assertTrue, etc.)
    # - mock assertions (.assert_called*, .assert_not_called)
    # - hypothesis property-test entry (`@given(...)` implies real assertions
    #   inside the function body, even when the assert keyword isn't used)
    has_assertion_re = re.compile(
        r"\bassert\b"
        r"|pytest\.raises\("
        r"|pytest\.warns\("
        r"|self\.assert[A-Z][A-Za-z]*\("
        r"|\.assert_called(_with|_once[A-Za-z_]*|_)?\("
        r"|\.assert_not_called\("
        r"|@given\("
    )
    # Opt-out marker for legitimate import-smoke tests (rare — e.g. .ipynb-only
    # examples mirrored as smoke). Place this comment anywhere in the file.
    optout_re = re.compile(r"#\s*PS-206b:\s*import-smoke-allowed", re.IGNORECASE)
    for test_file in tests_root.rglob("test_*.py"):
        if _is_blacklisted(test_file, tests_root):
            continue
        try:
            text = test_file.read_text(errors="ignore")
        except OSError:
            continue
        # Strip the legacy "source-as-comment" block so it doesn't count.
        marker = "# Start of Source Code from:"
        if marker in text:
            text = text.split(marker, 1)[0]
        has_test = has_def_or_class_re.search(text) or has_factory_assign_re.search(
            text
        )
        if not has_test:
            out.append(
                Violation(
                    "PS-206",
                    str(test_file),
                    "placeholder-only — add `def test_*`, `class Test*`, or `test_x = factory()`",
                )
            )
            continue
        # PS-206b: has a test fn, but no assertion anywhere in the module.
        if optout_re.search(text):
            continue
        if not has_assertion_re.search(text):
            out.append(
                Violation(
                    "PS-206b",
                    str(test_file),
                    (
                        "import-smoke-only — has `def test_*` but no assertion "
                        "(`assert`, `pytest.raises`, `mock.assert_*`, "
                        "`self.assertX`, `@given`). Add a real check or "
                        "delete the file. Opt-out: add a "
                        "`# PS-206b: import-smoke-allowed` comment."
                    ),
                )
            )


def _check_empty_test_dirs(repo: Path, distribution: str, out: list[Violation]) -> None:
    """PS-207 — empty test mirror directory.

    Flags a `tests/<pkg>/<sub>/` that exists but contains no `test_*.py`
    files, WHEN the corresponding `src/<pkg>/<sub>/` does have source
    files. This catches partial migrations (mirror dir created, never
    filled) without false-flagging fresh packages whose `tests/<pkg>/`
    is legitimately empty because no source has been written yet.
    """
    tests_root = repo / "tests"
    if not tests_root.is_dir():
        return

    src_pkg = _src_pkg_dir(repo, distribution)
    if src_pkg is None:
        return  # no src to mirror against

    skip = {"__pycache__", "coverage", "htmlcov", ".pytest_cache"}
    for sub in tests_root.rglob("*"):
        if not sub.is_dir():
            continue
        if any(part in skip for part in sub.parts):
            continue

        # Has any .py test file? (skip __init__.py — it's pytest infra)
        py_files = [
            p
            for p in sub.iterdir()
            if p.is_file() and p.suffix == ".py" and p.name != "__init__.py"
        ]
        if py_files:
            continue
        # Has child dirs? leaf-emptiness check propagates via recursion
        child_dirs = [c for c in sub.iterdir() if c.is_dir() and c.name not in skip]
        if child_dirs:
            continue

        # Only flag if a corresponding src/<pkg>/<sub>/ has source files.
        # Resolve sub's path relative to tests/<pkg>/.
        try:
            rel = sub.relative_to(tests_root / src_pkg.name)
        except ValueError:
            continue  # not under tests/<pkg>/, leave to other rules
        src_counterpart = src_pkg / rel
        if not src_counterpart.is_dir():
            continue
        if _is_git_ignored(src_counterpart, repo):
            continue  # src is gitignored — won't ship; no test mirror needed
        src_py = [
            p
            for p in src_counterpart.iterdir()
            if p.is_file() and p.suffix == ".py" and p.name != "__init__.py"
        ]
        if not src_py:
            continue  # nothing in src to mirror — empty test dir is fine

        out.append(
            Violation(
                "PS-207",
                str(sub),
                f"empty test directory mirrors {src_counterpart} ({len(src_py)} src "
                f"files) — move corresponding test_*.py files in or remove the dir.",
            )
        )


def _check_docs_structure(repo: Path, out: list[Violation]) -> None:
    """PS-401 / PS-402 — docs/ layout."""
    docs = repo / "docs"
    to_claude = docs / "to_claude"
    if to_claude.is_dir():
        # Tracked iff git knows about any file under it. Use a conservative
        # heuristic: if the dir exists AND .gitignore doesn't ignore it, flag.
        gitignore = repo / ".gitignore"
        ignored = False
        if gitignore.is_file():
            patterns = gitignore.read_text(errors="ignore").splitlines()
            for raw in patterns:
                pat = raw.strip()
                if not pat or pat.startswith("#"):
                    continue
                if pat in {"docs/to_claude", "docs/to_claude/", "**/to_claude/"}:
                    ignored = True
                    break
        if not ignored:
            out.append(
                Violation(
                    "PS-401",
                    str(to_claude),
                    "add `docs/to_claude/` (or `**/to_claude/`) to .gitignore",
                )
            )


def check_codecov_target(repo: Path, violation_cls: type, out: list) -> None:
    """PS-161: codecov.yml must pin a project/patch coverage target >= 90%.

    Skipped when codecov.yml is absent (separate rules cover codecov
    setup), when YAML parsing fails, or when the relevant key is missing.
    Fires once per below-threshold target ('project' and/or 'patch').
    """
    cfg = repo / "codecov.yml"
    if not cfg.is_file():
        return
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        return
    try:
        data = yaml.safe_load(cfg.read_text(encoding="utf-8", errors="replace"))
    except (OSError, yaml.YAMLError):
        return
    if not isinstance(data, dict):
        return
    try:
        status = data["coverage"]["status"]
    except (KeyError, TypeError):
        return
    if not isinstance(status, dict):
        return

    def _parse_target(raw):
        """Return (numeric_value, is_auto_or_unparseable)."""
        if isinstance(raw, (int, float)):
            return float(raw), False
        if isinstance(raw, str):
            s = raw.strip().rstrip("%").strip()
            if s.lower() in ("auto", "auto-target"):
                return None, True
            try:
                return float(s), False
            except ValueError:
                return None, False  # unparseable string → skip
        return None, False

    for kind in ("project", "patch"):
        block = status.get(kind)
        if not isinstance(block, dict):
            continue
        default = block.get("default")
        if not isinstance(default, dict):
            continue
        if "target" not in default:
            continue
        raw = default["target"]
        value, is_auto = _parse_target(raw)
        if is_auto:
            out.append(
                violation_cls(
                    "PS-161",
                    str(cfg),
                    (
                        f"codecov.yml {kind}/patch target is "
                        f"{raw!r} (< 90%) — set target: 90% so "
                        f"the bar is visible. See scitex-io "
                        f"codecov.yml for the canonical config."
                    ),
                )
            )
        elif value is not None and value < 90:
            out.append(
                violation_cls(
                    "PS-161",
                    str(cfg),
                    (
                        f"codecov.yml {kind}/patch target is "
                        f"{value:g} (< 90%) — set target: 90% so "
                        f"the bar is visible. See scitex-io "
                        f"codecov.yml for the canonical config."
                    ),
                )
            )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def audit_project(
    distribution: str,
    *,
    repo: Path | None = None,
    json_out: bool = False,
    rules: set[str] | None = None,
    severity: str = "error",
) -> int:
    """Audit `<distribution>` against the project-structure checklist.

    Parameters
    ----------
    distribution : str
        Distribution name (e.g. ``"scitex-io"``).
    repo : Path, optional
        Repo root. Defaults to the result of locating the installed package.
    json_out : bool
        Emit machine-readable output on stdout.
    rules : set of str, optional
        If given, only run these rule codes.
    severity : {"error","warning","info"}
        Minimum severity to print AND to drive the exit code.
        - ``"error"``  (default): print E findings only; exit 1 iff ≥1 E.
        - ``"warning"``: print E + W findings; exit 1 iff ≥1 E.
        - ``"info"``: print everything; exit 1 iff ≥1 E.
        W and I findings never fail CI on their own.

    Returns
    -------
    int
        Exit code: 0 = no E-level violations, 1 = ≥1 E violation, 2 = could not locate.
    """
    repo_root = _resolve_repo_root(distribution, repo)
    violations: list[Violation] = []

    if repo_root is None:
        if json_out:
            import json as _json

            click.echo(
                _json.dumps(
                    {
                        "distribution": distribution,
                        "repo": None,
                        "violations": [],
                    },
                    indent=2,
                )
            )
            return 2
        click.echo(
            f"audit-project: cannot locate repo root for '{distribution}' "
            "(is it installed in editable mode, or pass --repo PATH?)",
            err=True,
        )
        return 2

    # Category-aware skip — see `should_skip_audit` in _ecosystem._core.
    try:
        from ...._ecosystem import ECOSYSTEM, should_skip_audit
    except ImportError:
        ECOSYSTEM = {}
        should_skip_audit = lambda *_a, **_k: (False, "")  # noqa: E731
    skip, reason = should_skip_audit(distribution, "audit-project")
    if skip:
        if not json_out:
            from .._emit import emit as _emit_skip

            _emit_skip("skip", f"{distribution}: {reason}")
        return 0
    info = ECOSYSTEM.get(distribution, {})
    category = info.get("category", "library")
    skip_mirror = category in _MIRROR_EXEMPT_CATEGORIES

    _check_top_level(repo_root, violations)
    if not skip_mirror:
        _check_mirror(repo_root, distribution, violations)
        _check_placeholder_tests(repo_root, violations)
        _check_empty_test_dirs(repo_root, distribution, violations)
    _check_tests_subdir_convention(repo_root, distribution, violations)
    # hook-bypass: line-limit
    # RP-2xx: research projects mirror scripts/ ↔ tests/scripts/ instead of
    # src/<pkg>/ ↔ tests/<pkg>/. Fired only when `research` is in the
    # project-types; the PS package-publish rules drop for pure-research
    # (no `pip` ⇒ applies("PS-*") is False). See _check_research_mirror.
    from .._config import load_config as _load_cfg_for_research

    if "research" in _load_cfg_for_research(repo_root).project_types:
        from ._check_research_mirror import check_research_mirror

        check_research_mirror(repo_root, violations)
    _check_docs_structure(repo_root, violations)
    src_pkg = _src_pkg_dir(repo_root, distribution)
    if src_pkg is not None:
        from ._check_flat_layout import check_flat_layout, check_topical_clutter

        check_flat_layout(src_pkg, Violation, violations)
        check_topical_clutter(src_pkg, Violation, violations)
    from ._check_readme_badges import check_coverage_badge

    check_coverage_badge(repo_root, Violation, violations)
    from ._check_readme_badge_position import check_badge_position

    check_badge_position(repo_root, Violation, violations)
    from ._check_readme_sections import check_readme_sections

    check_readme_sections(repo_root, Violation, violations)
    from ._check_sphinx_html import check_sphinx_html

    check_sphinx_html(repo_root, Violation, violations)
    from ._check_env_example import check_env_example

    check_env_example(repo_root, Violation, violations)
    from ._check_examples import check_examples_conventions

    check_examples_conventions(repo_root, Violation, violations)
    from ._check_readme_structure import check_readme_structure

    check_readme_structure(repo_root, Violation, violations)
    check_codecov_target(repo_root, Violation, violations)
    from ._check_dev_extras_complete import check_dev_extras_complete

    check_dev_extras_complete(repo_root, Violation, violations)
    # hook-bypass: line-limit
    from ._check_optional_deps_guarded import check_ps148_optional_deps_guarded

    check_ps148_optional_deps_guarded(repo_root, distribution, Violation, violations)
    # hook-bypass: line-limit
    from ._check_hard_dep_overreach import check_ps149_hard_dep_overreach

    check_ps149_hard_dep_overreach(repo_root, distribution, Violation, violations)
    from ._check_umbrella_dep_and_integration import (
        check_ps139_umbrella_dep,
        check_ps140_integration_gate,
    )

    check_ps139_umbrella_dep(repo_root, Violation, violations)
    check_ps140_integration_gate(repo_root, distribution, Violation, violations)
    from ._check_audit_pin import check_audit_pin

    check_audit_pin(repo_root, Violation, violations)
    from ._check_workflows_naming import check_ps164_workflow_naming

    check_ps164_workflow_naming(repo_root, Violation, violations)
    # hook-bypass: line-limit
    from ._check_secret_env_prefix import check_ps168_secret_env_prefix

    check_ps168_secret_env_prefix(repo_root, distribution, Violation, violations)
    # hook-bypass: line-limit
    from ._check_workflow_presence import check_ps165_workflow_presence
    from ._check_readme_badge_labels import check_ps166_readme_badge_labels

    check_ps165_workflow_presence(repo_root, Violation, violations)
    check_ps166_readme_badge_labels(repo_root, Violation, violations)
    from ._check_readme_badge_layout import (  # hook-bypass: line-limit
        check_ps167_readme_badge_layout,
    )

    check_ps167_readme_badge_layout(repo_root, Violation, violations)
    from ._check_local_state import (
        check_ps145_cross_package_read,
        check_ps146_pip_install_side_effect,
        check_ps147_eval_form_completion,
    )

    check_ps145_cross_package_read(repo_root, distribution, Violation, violations)
    check_ps146_pip_install_side_effect(repo_root, Violation, violations)
    check_ps147_eval_form_completion(repo_root, Violation, violations)
    # PS-PATH / PS-CLEW / PS-AGENT — paper-scitex-clew MVP lint set.
    # Artifact-gated (only fire when PATH.yaml / clew.add_claim /
    # scripts/agent/ are present); safe to run on every project type.
    # See PR #97 and operator directive 2026-06-01.
    from ._check_path_yaml import (  # hook-bypass: line-limit
        check_ps_path_001_outer_wrapper,
        check_ps_path_002_bare_string_leaf,
    )
    from ._check_clew_claims import (  # hook-bypass: line-limit
        check_ps_agent_001_agent_script_no_claims_json,
        check_ps_clew_001_add_claim_without_self_verify,
    )

    check_ps_path_001_outer_wrapper(repo_root, Violation, violations)
    check_ps_path_002_bare_string_leaf(repo_root, Violation, violations)
    check_ps_clew_001_add_claim_without_self_verify(
        repo_root, Violation, violations
    )
    check_ps_agent_001_agent_script_no_claims_json(
        repo_root, Violation, violations
    )
    # hook-bypass: line-limit
    # PS-173: ADR format — only fires when docs/adr/ exists (presence is
    # recommended, not mandated). Scope = all project kinds.
    from ._check_adr import check_ps173_adr_format

    check_ps173_adr_format(repo_root, violations)
    if not skip_mirror:
        from ._check_smoke_e2e_layers import (
            check_ps211_smoke_layer,
            check_ps212_e2e_layer,
        )

        check_ps211_smoke_layer(repo_root, Violation, violations)
        check_ps212_e2e_layer(repo_root, Violation, violations)

    if rules:
        violations = [v for v in violations if v.rule in rules]

    # Project-type dispatch: drop findings for rule families that don't
    # apply to this project (PS rules only fire for `pip` projects, RP
    # rules only for `research`). Honours the user's `audit.skip` list too.
    from .._config import load_config

    cfg = load_config(repo_root)
    # Track findings that the project-type filter would have dropped —
    # specifically PS-103 violations on `deferred`-type projects. The
    # auditor doesn't fire them (deferred opts out) but we surface a
    # one-line warning so the operator has a visible TODO list when
    # revisiting cleanup.
    deferred_dropped: list[Violation] = (
        [v for v in violations if v.rule == "PS-103"]
        if "deferred" in cfg.project_types
        else []
    )
    violations = [
        v for v in violations if cfg.applies(v.rule) and v.rule not in cfg.skip
    ]

    # Severity filtering: print everything ≥ the requested floor.
    _floor = {"error": {"E"}, "warning": {"E", "W"}, "info": {"E", "W", "I"}}
    visible_set = _floor.get(severity, _floor["error"])
    visible = [v for v in violations if v.severity in visible_set]
    n_errors = sum(1 for v in violations if v.severity == "E")
    exit_code = 1 if n_errors > 0 else 0

    if json_out:
        import json as _json

        click.echo(
            _json.dumps(
                {
                    "distribution": distribution,
                    "repo": str(repo_root),
                    "violations": [
                        {
                            "rule": v.rule,
                            "where": v.where,
                            "detail": v.detail,
                            "severity": v.severity,
                        }
                        for v in visible
                    ],
                    "exit_code": exit_code,
                    "errors": n_errors,
                },
                indent=2,
            )
        )
        return exit_code

    from ...._audit_disclaimer import emit_disclaimer, emit_skill_hints

    def _emit_deferred_reminder() -> None:
        if not deferred_dropped:
            return
        click.echo(
            f"  [defer] {distribution}: {len(deferred_dropped)} PS-103 "
            f"finding(s) suppressed by `project-type: deferred`. "
            f"Re-review when time permits — entries currently at root "
            f"that the strict baseline would flag:",
            err=True,
        )
        for v in deferred_dropped[:10]:
            basename = Path(v.where).name
            click.echo(f"    - {basename}", err=True)
        if len(deferred_dropped) > 10:
            click.echo(
                f"    … +{len(deferred_dropped) - 10} more (run with "
                f"`--severity warning` against a non-deferred config to see all)",
                err=True,
            )

    from .._emit import emit as _emit

    if not visible:
        # No findings at the requested severity floor.
        _emit("success", f"{distribution}: no project-structure violations")
        _emit_deferred_reminder()
        emit_disclaimer()
        return exit_code

    n_w = sum(1 for v in visible if v.severity == "W")
    n_i = sum(1 for v in visible if v.severity == "I")
    headline_level = "error" if exit_code else "warning"
    summary = f"{distribution} ({repo_root}): {n_errors} error(s)"
    if n_w:
        summary += f", {n_w} warning(s)"
    if n_i:
        summary += f", {n_i} info"
    _emit(headline_level, summary)
    for v in visible:
        sev = (
            "error"
            if getattr(v, "severity", "W") == "E"
            else ("warning" if getattr(v, "severity", "W") == "W" else "info")
        )
        _emit(sev, v.format())
    _emit_deferred_reminder()
    emit_disclaimer()
    emit_skill_hints()
    return exit_code
