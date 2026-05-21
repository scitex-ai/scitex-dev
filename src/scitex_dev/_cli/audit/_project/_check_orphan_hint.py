"""PS-204 enrichment — derive an actionable hint when a test is orphaned.

Strategy (no git, no history walking):

1. **Same-basename match.** Refactors usually preserve the leaf filename
   (`_cli_audit.py` → `_cli/audit.py` keeps `audit`). If exactly one src
   file under `src/<pkg>/` matches the test's expected basename, suggest
   moving the test to mirror it.

2. **Sibling listing (fallback).** If no unique basename match, list the
   `.py` files that *do* live under `src/<pkg>/<test's-mirror-dir>/` so
   the agent can correlate manually. An empty mirror dir is itself a
   useful signal.

Pure stdlib, deterministic, works on uncommitted file moves.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from .._fd import fd_find_files


_DEFAULT_DETAIL = "no matching src file (orphan test)"
_MAX_SIBLINGS = 6


def _expected_src_basename(test_filename: str) -> str | None:
    """test_foo.py → foo.py; test__foo.py → _foo.py; else None."""
    if not test_filename.startswith("test_") or not test_filename.endswith(".py"):
        return None
    return test_filename[len("test_") :]  # keeps the leading "_" for private tests


def _index_src_basenames(src_pkg: Path) -> dict[str, list[Path]]:
    """{basename: [absolute paths]} for every .py under src_pkg (excl. __init__)."""
    index: dict[str, list[Path]] = defaultdict(list)
    for p in fd_find_files(src_pkg, glob="*.py"):
        if p.name == "__init__.py":
            continue
        index[p.name].append(p)
    return index


def build_orphan_hinter(src_pkg: Path, repo: Path):
    """Return a `hint(test_file, test_relpath) -> str` closure.

    Indexing happens once per audit so the per-orphan call is O(1).
    """
    index = _index_src_basenames(src_pkg)
    pkg_rel = src_pkg.relative_to(repo)

    def hint(test_relpath: Path) -> str:
        expected_basename = _expected_src_basename(test_relpath.name)
        if expected_basename is None:
            return _DEFAULT_DETAIL

        matches = index.get(expected_basename, [])
        if len(matches) == 1:
            new_src = matches[0]
            new_src_rel = new_src.relative_to(src_pkg)
            suggested_test = (
                Path("tests") / src_pkg.name / new_src_rel.parent / test_relpath.name
            )
            return (
                f"src likely moved to `{pkg_rel / new_src_rel}` "
                f"(same basename); move this test to `{suggested_test}`"
            )

        if len(matches) > 1:
            sample = ", ".join(
                str(m.relative_to(src_pkg)) for m in sorted(matches)[:_MAX_SIBLINGS]
            )
            return (
                f"no exact src match; {len(matches)} files share basename "
                f"`{expected_basename}` ({sample}) — pick the right one and "
                "relocate this test to mirror its directory"
            )

        # No basename match → list what *is* in the mirror directory.
        mirror_dir = src_pkg / test_relpath.parent
        if mirror_dir.is_dir():
            siblings = sorted(
                p.name
                for p in mirror_dir.iterdir()
                if p.is_file() and p.suffix == ".py" and p.name != "__init__.py"
            )
            if siblings:
                shown = ", ".join(siblings[:_MAX_SIBLINGS])
                more = (
                    ""
                    if len(siblings) <= _MAX_SIBLINGS
                    else f", +{len(siblings) - _MAX_SIBLINGS} more"
                )
                return (
                    f"{_DEFAULT_DETAIL}; mirror dir `{pkg_rel / test_relpath.parent}` "
                    f"contains: {shown}{more} — none match expected `{expected_basename}`"
                )
            return (
                f"{_DEFAULT_DETAIL}; mirror dir `{pkg_rel / test_relpath.parent}` "
                "exists but is empty (src may have been deleted or moved away)"
            )
        return f"{_DEFAULT_DETAIL}; mirror dir `{pkg_rel / test_relpath.parent}` does not exist"

    return hint
