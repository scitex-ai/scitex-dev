"""PS-182 — rolled-own local-state path resolver.

Implements the resolution-by-data-nature standard from
`_skills/general/01_ecosystem/12_local-state-resolution.md`:

  PS-182 — a package ships its own `src/<pkg>/**/_paths.py` (or
           `paths.py`) that RE-IMPLEMENTS the project-scope / git-root
           precedence walk — a `.git` sentinel walk plus a
           `.scitex/<pkg-short>` project-scope literal — WITHOUT
           importing the canonical
           `scitex_config._ecosystem.local_state` helper.

           Rolling your own precedence is the CONFIG-vs-DATA footgun:
           `local_state.path()` legitimately lets a project scope shadow
           the user scope for *config*, but a hand-rolled resolver
           applies the same "project wins" rule to *data / state stores*
           too. That is exactly how a week-stale
           `<repo>/.scitex/todo/tasks.yaml` silently shadowed the
           canonical `~/.scitex/todo/tasks.yaml` task store when a
           process ran with its cwd inside the repo (2026-07 incident).

           Fix: adopt `scitex_config._ecosystem.local_state` and pick the
           resolver by DATA NATURE — `path()` for config,
           `user_path()` for DATA/STATE stores (user-canonical, never
           project-shadowed), `runtime_path()` for ephemera. See the
           standard doc + PS-182 detail string.

Deterministic + low-false-positive by design: the finding needs BOTH a
git-root walk signal AND a `.scitex` project-scope literal in a file
named `_paths.py` / `paths.py`, and is suppressed when the file already
imports the canonical helper. A resolver that keys off a plain
`$SCITEX_<PKG>_DIR` / `$SCITEX_BASE_DIR` env var without a `.git` walk
(e.g. `scitex-app/paths.py`) is NOT flagged.

b2 (a resolver whose chain orders project-scope ABOVE user-scope for a
`.yaml`/`.db`/`.json` DATA store specifically) is intentionally DEFERRED:
detecting store-nature + chain-order cleanly enough to stay
low-false-positive is a separate refinement. PS-182 (b1) already flags
the root cause — the rolled-own resolver — so b2 buys little today. See
the standard doc §"Future refinement (b2)".
"""

from __future__ import annotations

import re
from pathlib import Path

__all__ = ["check_ps182_rolled_own_path_resolver"]


# A git-root walk: a named helper (`find_project_scope` / `_find_git_root`
# / `_project_root`) OR a bare `.git` sentinel probe `(... / ".git").exists()`
# / `.is_dir()`. Any one is enough — combined with the `.scitex` literal below
# it is an unambiguous "I re-implemented project-scope resolution" signal.
_GIT_WALK_RE = re.compile(
    r"""(?:
        find_project_scope
      | _find_git_root
      | _project_root
      | ["']\.git["']\s*\)\s*\.\s*(?:exists|is_dir)
    )""",
    re.VERBOSE,
)

# A `.scitex` project-scope path literal (the `<repo>/.scitex/<pkg>` join).
_SCITEX_LITERAL_RE = re.compile(r"""["']\.scitex["']""")

# The canonical helper — its presence means the file delegates precedence
# to `local_state` rather than rolling its own. Match the import/attribute
# form so a stray mention in a comment is unlikely to exempt a real offender
# (we require BOTH tokens).
_CANONICAL_HELPER_RE = re.compile(r"\blocal_state\b")
_CANONICAL_PKG_RE = re.compile(r"\bscitex_config\b")


def _candidate_resolver_files(repo: Path) -> list[Path]:
    """`src/**/_paths.py` and `src/**/paths.py` (gitignore-naive, cache-skip)."""
    src = repo / "src"
    if not src.is_dir():
        return []
    out: list[Path] = []
    for p in src.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        if p.name in ("_paths.py", "paths.py"):
            out.append(p)
    return sorted(out)


def _uses_canonical_helper(text: str) -> bool:
    """True iff the file references `scitex_config` AND `local_state`.

    Both tokens are required so a package that merely mentions one word in
    an unrelated string does not get a free pass.
    """
    return bool(_CANONICAL_HELPER_RE.search(text) and _CANONICAL_PKG_RE.search(text))


def check_ps182_rolled_own_path_resolver(
    repo: Path,
    violation_cls: type,
    out: list,
) -> None:
    """Append one PS-182 violation per rolled-own local-state resolver file.

    Fires when a `_paths.py` / `paths.py` under `src/`:
      * shows a git-root walk signal (`_GIT_WALK_RE`), AND
      * builds a `.scitex` project-scope path (`_SCITEX_LITERAL_RE`), AND
      * does NOT import the canonical `scitex_config._ecosystem.local_state`
        helper (`_uses_canonical_helper`).
    """
    for py in _candidate_resolver_files(repo):
        try:
            text = py.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if _uses_canonical_helper(text):
            continue
        if not _GIT_WALK_RE.search(text):
            continue
        if not _SCITEX_LITERAL_RE.search(text):
            continue
        out.append(
            violation_cls(
                "PS-182",
                str(py),
                (
                    "rolls its own local-state precedence (a `.git`-root walk "
                    "+ `.scitex/<pkg>` project-scope literal) instead of the "
                    "canonical `scitex_config._ecosystem.local_state` helper. "
                    "Project-scope shadowing is legitimate for CONFIG but a "
                    "footgun for DATA/STATE stores: it silently shadowed the "
                    "canonical `~/.scitex/todo/tasks.yaml` with a week-stale "
                    "`<repo>/.scitex/todo/tasks.yaml` (2026-07). Adopt "
                    "`local_state` and resolve by DATA NATURE — `path()` for "
                    "config, `user_path()` for DATA/STATE stores "
                    "(user-canonical, never project-shadowed), "
                    "`runtime_path()` for ephemera. See _skills/general/"
                    "01_ecosystem/12_local-state-resolution.md."
                ),
            )
        )


# EOF
