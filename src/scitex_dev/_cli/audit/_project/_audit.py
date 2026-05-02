"""Project-structure auditor — engine + rules.

Rules cover the automatable items from
`scitex-dev/src/scitex_dev/_skills/general/02_package_01_project-structure.md`
(and its sibling `scientific/02_research-project_01_project-structure.md`).

Numbering: ``PS<§><idx>`` (PS = Project Structure), e.g. PS201 = §2 rule 01.
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


RULES: dict[str, Rule] = {
    r.code: r
    for r in [
        # §1 Top-level layout ---------------------------------------------------
        Rule("PS101", "§1", "missing pyproject.toml at repo root"),
        Rule(
            "PS102",
            "§1",
            "forbidden top-level dir present (use the canonical location instead)",
        ),
        Rule(
            "PS103",
            "§1",
            "top-level junk file (move to ./.dev/<category>/ or delete)",
        ),
        Rule(
            "PS104",
            "§1",
            "uses `.playground/` — collapsed into `.dev/` for easier typing",
        ),
        Rule(
            "PS105",
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
            "PS106",
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
            "PS107",
            "§1",
            (
                "README.md is missing required H2 sections "
                "(## Installation / ## Quick Start / ## Part of SciTeX) — "
                "see _skills/general/04_docs_01_readme_template.md for the "
                "canonical layout."
            ),
        ),
        Rule(
            "PS109",
            "§1",
            (
                "README.md is missing a PyPI version badge "
                "(badge.fury.io/py/<pkg> or img.shields.io/pypi/v/<pkg>) "
                "in the first ~4 KB."
            ),
        ),
        Rule(
            "PS110",
            "§1",
            (
                "README.md is missing the Four Freedoms for Research "
                "blockquote — the SciTeX community-license footer."
            ),
        ),
        Rule(
            "PS111",
            "§1",
            (
                "README.md contains a banned personal email "
                "(ywatanabe@scitex.ai) — SciTeX is a community project."
            ),
        ),
        Rule(
            "PS112",
            "§1",
            (
                "README.md is missing a SciTeX logo image at the top "
                "(docs/scitex-logo-*.png or docs/assets/images/scitex-logo-*.png)."
            ),
        ),
        Rule(
            "PS113",
            "§1",
            (
                "README.md is missing a SciTeX icon footer — centered "
                "scitex-icon image link in the last ~2 KB of the file."
            ),
        ),
        Rule(
            "PS114",
            "§1",
            (
                "README.md `## Problem and Solution` section is prose-only — "
                "convention is a markdown table with columns "
                "`| # | Problem | Solution |`."
            ),
        ),
        Rule(
            "PS115",
            "§1",
            (
                "README.md `## Part of SciTeX` section does not open with "
                "the canonical `<pkg> is part of [SciTeX](https://scitex.ai)` "
                "sentence. Synergy code is optional; the opener is required."
            ),
        ),
        Rule(
            "PS108",
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
            "PS116",
            "§1",
            (
                "README.md uses the deprecated `> **Interfaces:** ...` "
                "summary callout. Per 2026-05 convention, put star ratings "
                "directly on each interface section header instead "
                "(e.g. `## Python API ⭐⭐⭐`)."
            ),
        ),
        Rule(
            "PS117",
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
            "PS118",
            "§1",
            (
                "README.md interface section header carries a banned "
                "descriptor like `(Application Programming Interface)`, "
                "`-- for AI Agents`, or `— for AI Agent Discovery`. The "
                "section names themselves carry meaning — strip the prose."
            ),
        ),
        Rule(
            "PS119",
            "§1",
            (
                "README.md contains a `> **SciTeX users**: pip install scitex "
                "already includes ...` install hint. These belong in the "
                "umbrella `scitex` README, not in sub-package READMEs "
                "(extras like `pip install scitex[ssh]` drift)."
            ),
        ),
        Rule(
            "PS120",
            "§1",
            (
                "README.md `## Part of SciTeX` section is missing the "
                "standardized umbrella one-liner. After the `is part of "
                "[SciTeX]` opener, mention `pip install scitex[<extra>]` "
                "AND `scitex.<module>` AND `scitex <subcommand>` so users "
                "see how the package fits the umbrella."
            ),
        ),
        Rule(
            "PS121",
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
            "PS122",
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
            "PS123",
            "§1",
            (
                "README.md interface section has a `Full X reference` link "
                "pointing at the bare RTD root (e.g. "
                "`https://<pkg>.readthedocs.io/`) instead of a deep-link "
                "anchor page. Use the canonical deep-link per interface — "
                "see `_skills/general/04_docs_01_readme.md` 'Canonical Full "
                "X reference deep-link patterns'."
            ),
        ),
        Rule(
            "PS124",
            "§1",
            (
                "package has `docs/sphinx/` but no `.readthedocs.yaml` (or "
                "`.readthedocs.yml`) at the repo root. Without it, RTD won't "
                "build the docs. Use the canonical config — see "
                "`_skills/general/04_docs_02_sphinx.md`."
            ),
        ),
        Rule(
            "PS125",
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
            "PS126",
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
            "PS127",
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
            "PS128",
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
            "PS129",
            "§1",
            (
                "package source references `SCITEX_<MODULE>_*` env vars "
                "but documents them in NEITHER a README "
                "`## Environment Variables` section NOR a `.env.example` "
                "at repo root. Pick one — see "
                "`_skills/general/04_docs_03_env-vars-and-state.md`."
            ),
        ),
        Rule(
            "PS130",
            "§1",
            (
                "README has `## Environment Variables` AND `.env.example` "
                "exists at repo root — the two will drift. Pick one: keep "
                "the README table (small lists), OR keep `.env.example` "
                "and reference it from the `## Installation` section."
            ),
        ),
        Rule(
            "PS131",
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
            "PS132",
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
        # §2 src ↔ tests mirror -------------------------------------------------
        Rule(
            "PS201",
            "§2",
            "src/<pkg>/ exists but tests/<pkg>/ is missing — every package needs the tests/<pkg>/ parent",
        ),
        Rule(
            "PS202",
            "§2",
            "src/<pkg>/<sub>/ has files but tests/<pkg>/<sub>/ is missing",
        ),
        Rule(
            "PS203",
            "§2",
            "loose test_*.py at tests/ root that should live inside tests/<pkg>/...",
        ),
        Rule(
            "PS204",
            "§2",
            "orphan test file: tests/<pkg>/<path>/test_*.py with no matching src/<pkg>/<path>/*.py",
        ),
        Rule(
            "PS205",
            "§2",
            "wrong public/private prefix (private `_foo.py` must be tested by `test__foo.py`, not `test_foo.py`)",
        ),
        Rule(
            "PS206",
            "§2",
            "placeholder-only test (no `def test_` or `class Test`)",
        ),
        Rule(
            "PS207",
            "§2",
            (
                "empty test directory (no `test_*.py` files, only `__pycache__/` "
                "or nothing) — created during a partial migration but never filled. "
                "Either move the corresponding `tests/<sub>/test_*.py` files in, "
                "or remove the empty dir."
            ),
        ),
        # §3 tests/ subdirectory convention -------------------------------------
        Rule(
            "PS301",
            "§3",
            "top-level ./htmlcov/ exists — coverage reports should live in tests/coverage/ (gitignored)",
        ),
        Rule(
            "PS302",
            "§3",
            "unrecognized subdir at tests/ root (must be tests/<pkg>/ or one of the known categories: scripts/examples/skills/agentic/integration/e2e/github_actions/coverage/logs/reports/custom)",
        ),
        Rule(
            "PS303",
            "§3",
            "examples/<name>.{py,sh,ipynb} has no matching tests/examples/test_<name>.py",
        ),
        Rule(
            "PS501",
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
            "PS502",
            "§5",
            (
                "examples/<n>_*_out/ exists but is empty (or contains only "
                "__pycache__) — the example was never run end-to-end. Either "
                "execute it once so SciTeX's session machinery populates the "
                "FINISHED_SUCCESS marker, or remove the empty _out/ if the "
                "example doesn't yet work."
            ),
        ),
        # §4 docs/ structure ----------------------------------------------------
        Rule(
            "PS401",
            "§4",
            "./docs/to_claude/ is tracked — must be gitignored (local-machine agent context, not part of the shipped repo)",
        ),
        Rule(
            "PS402",
            "§4",
            "top-level ./assets/ exists — figures/screenshots belong under ./docs/assets/",
        ),
    ]
}


@dataclass
class Violation:
    rule: str
    where: str
    detail: str

    def format(self) -> str:
        r = RULES.get(self.rule)
        section = r.section if r else "?"
        return f"  [{self.rule} {section}] {self.where}: {self.detail}"


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Test-name patterns: split into private (test__name.py) and public (test_name.py).
# The leading-underscore in the source becomes a double underscore in the test.
_PRIVATE_TEST_RE = re.compile(r"^test__([A-Za-z0-9][A-Za-z0-9_]*)\.py$")
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
# tests/<pkg>/). Anything else is flagged as PS207.
# See _skills/general/02_package_01_project-structure.md §"./tests".
_KNOWN_TEST_SUBDIRS = frozenset(
    {
        "scripts",  # mirror of ./scripts/ (research projects)
        "examples",  # one test per ./examples/ file
        "skills",  # structural tests for _skills/
        "agentic",  # agentic-trigger tests (LLM invokes the skill)
        "integration",  # cross-module / cross-package
        "e2e",  # end-to-end pipelines
        "github_actions",
        "coverage",  # HTML / XML reports — gitignored
        "logs",  # pytest run logs — gitignored
        "reports",  # agent-generated summaries — optional
        "custom",  # legacy: tests with no source counterpart
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
    "mgmt": "no longer used in scitex (see _skills/general/02_package_01_project-structure.md)",
    "references": "no longer used in scitex",
    "htmlcov": "coverage reports should live in tests/coverage/",
    "assets": "use ./docs/assets/ instead",
    ".playground": "collapsed into .dev/ for easier typing",
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
    return None


# ---------------------------------------------------------------------------
# Rule checks
# ---------------------------------------------------------------------------


def _check_top_level(repo: Path, out: list[Violation]) -> None:
    """PS101 / PS102 / PS103 / PS104 / PS105."""
    if not (repo / "pyproject.toml").is_file():
        out.append(Violation("PS101", str(repo), "no pyproject.toml at repo root"))

    for dirname, why in _FORBIDDEN_TOP_DIRS.items():
        candidate = repo / dirname
        if candidate.is_dir():
            code = "PS104" if dirname == ".playground" else "PS102"
            out.append(Violation(code, str(candidate), why))

    for child in repo.iterdir():
        if child.is_file() and _JUNK_FILE_RE.match(child.name):
            out.append(
                Violation(
                    "PS103",
                    str(child),
                    f"top-level junk file: {child.name}",
                )
            )

    # PS105: console_scripts present but no __main__.py — `python -m <pkg>`
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
                                "PS105",
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
    """PS201 / PS202 / PS203 / PS204 / PS205 — src ↔ tests mirror."""
    src_pkg = _src_pkg_dir(repo, distribution)
    tests_root = _tests_root(repo)
    if src_pkg is None or tests_root is None:
        # Without either side, mirror checks don't apply (a different rule
        # — PS101 / future PS105 — will catch missing structure).
        return

    import_name = _import_name(distribution)
    tests_pkg = tests_root / import_name

    # PS201: tests/<pkg>/ must exist
    if not tests_pkg.is_dir():
        out.append(
            Violation(
                "PS201",
                str(tests_root),
                f"missing `tests/{import_name}/` parent — needed even when most tests are flat",
            )
        )
        # Without the parent we can't run the deeper mirror checks meaningfully.
        # Still scan PS203 / loose top-level test files.
        _check_loose_top_level_tests(tests_root, src_pkg, import_name, out)
        return

    # PS203: any test_*.py at tests/ root that's not a known meta-test
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
                    "PS202",
                    str(src_dir),
                    f"no matching tests/{import_name}/{rel}/",
                )
            )

    # PS205: per-file public/private prefix consistency.
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
            continue  # PS202 already flagged this
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
                    "PS205",
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

    # PS204: orphan test files — every test_*.py under tests/<pkg>/ should
    # have a matching src counterpart. Hinter is built once and reused so
    # the basename index is amortized across all orphans in this package.
    from ._check_orphan_hint import build_orphan_hinter

    _hint = build_orphan_hinter(src_pkg, repo)
    for test_file in tests_pkg.rglob("test_*.py"):
        rel = test_file.relative_to(tests_pkg)
        if not _test_has_src_match(test_file, rel, src_pkg):
            out.append(Violation("PS204", str(test_file), _hint(rel)))


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
    get full PS202 coverage. Used to skip src subdirs that exist locally
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
    """PS203 — loose test_*.py at tests/ root that should be under tests/<pkg>/."""
    for child in tests_root.iterdir():
        if not child.is_file() or not child.name.startswith("test_"):
            continue
        if child.name in _META_TESTS_AT_ROOT:
            continue
        # Try to find a src counterpart so we can suggest where to move it.
        suggestion = _suggest_test_location(child.name, src_pkg, import_name)
        out.append(
            Violation(
                "PS203",
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
    """Does the test name correspond to an existing src file under the same rel dir?"""
    name = test_file.name
    m = _PRIVATE_TEST_RE.match(name)
    if m:
        candidate = src_pkg / rel.parent / f"_{m.group(1)}.py"
        return candidate.is_file()
    m = _PUBLIC_TEST_RE.match(name)
    if m:
        candidate = src_pkg / rel.parent / f"{m.group(1)}.py"
        return candidate.is_file()
    return False  # malformed test name — caller may flag separately


def _check_tests_subdir_convention(
    repo: Path, distribution: str, out: list[Violation]
) -> None:
    """PS301 / PS302 / PS303 — tests/ root layout."""
    # PS301: top-level htmlcov/ should be tests/coverage/.
    if (repo / "htmlcov").is_dir():
        out.append(
            Violation(
                "PS301",
                str(repo / "htmlcov"),
                "rename to tests/coverage/ and gitignore (replaces top-level ./htmlcov/)",
            )
        )

    tests_root = _tests_root(repo)
    if tests_root is None:
        return

    # PS302: every subdir at tests/ root must be either tests/<pkg>/ (the
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
                "PS302",
                str(child),
                f"unrecognized: rename to tests/{import_name}/{child.name}/ "
                "or move to one of the known categories",
            )
        )

    # PS303: every examples/<file> should have a matching tests/examples/test_<stem>.py.
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
                        "PS303",
                        str(ex),
                        f"missing matching tests/examples/test_{ex.stem}.py",
                    )
                )


def _check_placeholder_tests(repo: Path, out: list[Violation]) -> None:
    """PS206 — placeholder-only test (no `def test_` / `class Test` / `test_x = factory()`).

    Recognises three pytest-collectable shapes:
    - `def test_*` at module level
    - `class Test*` at module level
    - `test_*` module-level assignment (e.g. `test_foo = make_tests(...)`) —
      pytest collects any module-level callable named `test_*`.
    """
    tests_root = _tests_root(repo)
    if tests_root is None:
        return
    has_def_or_class_re = re.compile(r"^\s*(def\s+test_|class\s+Test)", re.MULTILINE)
    has_factory_assign_re = re.compile(r"^test_[A-Za-z0-9_]*\s*=", re.MULTILINE)
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
        if has_def_or_class_re.search(text):
            continue
        if has_factory_assign_re.search(text):
            continue
        out.append(
            Violation(
                "PS206",
                str(test_file),
                "placeholder-only — add `def test_*`, `class Test*`, or `test_x = factory()`",
            )
        )


def _check_empty_test_dirs(repo: Path, distribution: str, out: list[Violation]) -> None:
    """PS207 — empty test mirror directory.

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
                "PS207",
                str(sub),
                f"empty test directory mirrors {src_counterpart} ({len(src_py)} src "
                f"files) — move corresponding test_*.py files in or remove the dir.",
            )
        )


def _check_docs_structure(repo: Path, out: list[Violation]) -> None:
    """PS401 / PS402 — docs/ layout."""
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
                    "PS401",
                    str(to_claude),
                    "add `docs/to_claude/` (or `**/to_claude/`) to .gitignore",
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
) -> int:
    """Audit `<distribution>` against the project-structure checklist. Warn-only.

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

    Returns
    -------
    int
        Exit code: 0 = no violations, 1 = violations, 2 = could not locate.
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

    # Look up the registry entry to decide which rules apply.
    try:
        from ...._ecosystem import ECOSYSTEM
    except ImportError:
        ECOSYSTEM = {}
    info = ECOSYSTEM.get(distribution, {})
    if info.get("archived"):
        # Archived entries are read-only history — don't flag.
        if not json_out:
            click.echo(f"skip  {distribution}: archived")
        return 0
    category = info.get("category", "library")
    skip_mirror = category in _MIRROR_EXEMPT_CATEGORIES

    _check_top_level(repo_root, violations)
    if not skip_mirror:
        _check_mirror(repo_root, distribution, violations)
        _check_placeholder_tests(repo_root, violations)
        _check_empty_test_dirs(repo_root, distribution, violations)
    _check_tests_subdir_convention(repo_root, distribution, violations)
    _check_docs_structure(repo_root, violations)
    src_pkg = _src_pkg_dir(repo_root, distribution)
    if src_pkg is not None:
        from ._check_flat_layout import check_flat_layout

        check_flat_layout(src_pkg, Violation, violations)
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

    if rules:
        violations = [v for v in violations if v.rule in rules]

    if json_out:
        import json as _json

        click.echo(
            _json.dumps(
                {
                    "distribution": distribution,
                    "repo": str(repo_root),
                    "violations": [
                        {"rule": v.rule, "where": v.where, "detail": v.detail}
                        for v in violations
                    ],
                },
                indent=2,
            )
        )
        return 0 if not violations else 1

    if not violations:
        click.echo(f"ok  {distribution}: no project-structure violations")
        return 0

    click.echo(f"warn  {distribution} ({repo_root}): {len(violations)} violation(s)")
    for v in violations:
        click.echo(v.format())
    return 1
