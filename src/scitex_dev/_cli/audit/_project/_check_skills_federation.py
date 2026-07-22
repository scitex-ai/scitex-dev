"""PS-217 — ``skills`` CLI federation conformance.

Part of the CLI-normalization effort: the ecosystem's plumbing verbs
(``skills`` / ``mcp`` / ``completion``) were copy-pasted into ~20 leaf
packages instead of being federated. scitex-dev now ships a shared
builder — ``scitex_dev.cli.skills_click_group(package=...)`` — that
gives a leaf its entire ``skills`` verb in one line::

    from scitex_dev.cli import skills_click_group
    cli.add_command(skills_click_group(package="scitex-io"))

The reference primitive it mirrors is ``docs_click_group`` (same
module, ``scitex_dev._core.dispatch``).

Invariant
---------
A leaf package that ships a hand-rolled ``src/<pkg>/_cli/_skills.py``
(the copy-paste shape — a self-contained Click group that re-implements
list/get/export) but does NOT import the shared ``skills_click_group``
primitive is carrying duplicated plumbing. PS-217 flags it so the
fan-out (each leaf importing the primitive) stays trackable.

Severity is **W** (warning), not E: the leaves are not migrated yet, so
an error would red every leaf's ``develop``. The rule is a tracking
signal for the migration, not a gate.

Scope note
----------
scitex-dev itself is NOT flagged — it OWNS the primitive and exposes its
own ``skills`` group under ``_cli/skills/`` (a package dir), never a flat
``_cli/_skills.py``, so the file-shape probe below never matches it.

Rule shape mirrors sibling ``_check_*.py`` modules — a single public
``check_skills_federation(repo, violation_cls, out)`` that appends one
``violation_cls("PS-217", where, detail)`` per offending package.
"""

from __future__ import annotations

from pathlib import Path

# Co-located rule registration (same shape `_registry.RULES` expects:
# ``(code, section, message, severity, slug)``). Merged in `_registry.py`
# on the same terms as HOOK_RULES / URL_DEP_RULES — the target
# architecture named in `_extra_rules.py`'s docstring: each rule lives
# with its check module.
SKILLS_FEDERATION_RULES = [
    (
        "PS-217",
        "§3",
        (
            "skills-cli-federation: a leaf ships a hand-rolled "
            "`src/<pkg>/_cli/_skills.py` that re-implements the `skills` "
            "verb (list / get / export) instead of importing scitex-dev's "
            "shared `skills_click_group` primitive. Replace the copy-pasted "
            "Click group with one line: `from scitex_dev.cli import "
            "skills_click_group` then `cli.add_command("
            "skills_click_group(package=\"<pkg>\"))`. The primitive mirrors "
            "the `docs_click_group` federation pattern "
            "(`scitex_dev._core.dispatch`) and reads the package's own "
            "`_skills/` dir, so behaviour is unchanged. Severity W during "
            "the CLI-normalization fan-out — leaves are not migrated yet, "
            "and the dep-free trio (todo/sac/cct) is intentionally out of "
            "scope (it must not import scitex-dev). See "
            "scitex_dev._core.dispatch._skills_click."
        ),
        "W",
        "skills-cli-federation",
    ),
]

# The token a migrated leaf necessarily contains: it imports and calls
# the shared builder by name. Its ABSENCE in a hand-rolled `_skills.py`
# is the discriminator between a federated leaf and a copy-paste one.
_PRIMITIVE_MARKER = "skills_click_group"

# The dep-free trio (todo / sac / cct). These packages MUST NOT import
# scitex-dev — they are deliberately standalone so a bare
# `pip install <pkg>` yields a fully working CLI with no ecosystem
# dependency (operator directive: standalone-independence over DRY).
# Federating their `skills` verb would make the verb require scitex-dev
# at CLI-import time, which is exactly what that rule forbids.
#
# The exemption was documented in this module's rule text from the start
# ("the dep-free trio (todo/sac/cct) is intentionally out of scope") but
# was never IMPLEMENTED, so the check flagged the trio anyway and the
# reported count overstated the real debt. Keyed on the source-package
# directory name (``src/<pkg>/``), which is the only identity available
# here — the repo may be checked out under any directory name.
_DEP_FREE_TRIO_PKG_DIRS = frozenset(
    {
        "scitex_cards",  # scitex-todo / scitex-cards
        "scitex_todo",  # legacy module name for the same package
        "scitex_agent_container",  # sac
        "claude_code_telegrammer",  # cct
    }
)


def _src_pkg_dirs(repo: Path) -> list[Path]:
    """Return every ``src/<pkg>/`` directory under ``repo``.

    A package is any direct subdirectory of ``src/`` (skips dunder dirs
    like ``__pycache__``). Returns ``[]`` if ``src/`` is missing.
    """
    src = repo / "src"
    if not src.is_dir():
        return []
    out: list[Path] = []
    for child in src.iterdir():
        if not child.is_dir():
            continue
        if child.name.startswith("__"):
            continue
        out.append(child)
    return out


def _reads_primitive(skills_py: Path) -> bool:
    """True iff the file references the shared ``skills_click_group``."""
    try:
        text = skills_py.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return _PRIMITIVE_MARKER in text


def check_skills_federation(
    repo: Path,
    violation_cls: type,
    out: list,
) -> None:
    """Append PS-217 violations.

    PS-217 — a leaf ships a hand-rolled ``src/<pkg>/_cli/_skills.py`` that
    does NOT import the shared ``skills_click_group`` primitive. Federate
    it: replace the copy-pasted Click group with a one-liner
    ``cli.add_command(skills_click_group(package="<pkg>"))``.
    """
    for pkg_dir in _src_pkg_dirs(repo):
        # The dep-free trio must not import scitex-dev — federating its
        # `skills` verb is forbidden, so flagging it is a false positive.
        if pkg_dir.name in _DEP_FREE_TRIO_PKG_DIRS:
            continue
        skills_py = pkg_dir / "_cli" / "_skills.py"
        if not skills_py.is_file():
            continue
        if _reads_primitive(skills_py):
            continue
        pkg_name = pkg_dir.name
        out.append(
            violation_cls(
                "PS-217",
                str(skills_py),
                (
                    f"`src/{pkg_name}/_cli/_skills.py` hand-rolls a `skills` "
                    f"CLI instead of importing the shared federation "
                    f"primitive. Replace the copy-pasted Click group with "
                    f"one line: `from scitex_dev.cli import "
                    f"skills_click_group` then "
                    f"`cli.add_command(skills_click_group(package="
                    f"\"{pkg_name.replace('_', '-')}\"))`. The primitive "
                    f"(mirroring `docs_click_group`) exposes the same "
                    f"list / get / export|install verbs reading this "
                    f"package's own `_skills/` dir, so behaviour is "
                    f"unchanged. Severity W during the CLI-normalization "
                    f"fan-out — leaves are not migrated yet. The dep-free "
                    f"trio (todo/sac/cct) is intentionally out of scope "
                    f"(it must not import scitex-dev). See "
                    f"scitex_dev._core.dispatch._skills_click."
                ),
            )
        )
