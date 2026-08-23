"""PA-307 test-quality check for the Python API auditor.

Split out of `_audit.py` — pure refactor, no behaviour change. Re-runs the
linter's STX-TQ001-007 detection across the repo's `tests/` tree (and every
`conftest.py`) and re-emits each finding as a PA-307 violation. Re-exported
from `_audit` so existing imports keep resolving.
"""

from __future__ import annotations

import os
from pathlib import Path

from ._model import Violation


def _conftests_under(repo_root: Path):
    """Every conftest.py under repo_root, WITHOUT descending dot-directories.

    This was `repo_root.rglob("conftest.py")`, which walks `.git` — and the
    audit itself creates and destroys linked checkouts while it runs
    (`audit/_diff_worktree.py` shells out to git for add / remove / prune), so
    `.git/worktrees` appears and vanishes mid-traversal. A walk that entered
    `.git` could therefore scandir a directory that had just been pruned:

        FileNotFoundError: [Errno 2] No such file or directory: …/.git/worktrees

    MEASURED 2026-08-23: that killed the v0.56.5 release run's 3.11 leg while
    3.12 and 3.13 passed on the SAME commit and the SAME host — a race, not a
    Python-version or host difference. The directory was absent at rest on BOTH
    runners, which is what shows it is transient rather than a static difference
    between them; measured on the hosts by scitex-cards, who also refuted the
    re-run as evidence, since it landed on the other runner and so could not
    distinguish "transient" from "host-local".

    The old code filtered `__pycache__`, `build`, `dist` and `.tox` AFTER the
    walk. Filtering results does not stop the traversal, so both the wasted
    descent and the exposure were still paid. `_fd.py` already states the rule
    this should have followed: descend into no dot-directory.
    """
    for dirpath, dirnames, filenames in os.walk(repo_root):
        # Prune IN PLACE: this is what stops the descent. A filter applied to
        # the results cannot, which is exactly how `.git` came to be walked.
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        if "conftest.py" in filenames:
            yield Path(dirpath) / "conftest.py"


def _audit_test_quality(
    init_path: Path,
    distribution: str,
    import_name: str,
    *,
    repo_root: Path | None = None,
) -> list[Violation]:
    """PA-307 — run the linter's STX-TQ001-007 detection across the
    repo's `tests/` (and `conftest.py`) and re-emit each finding as a
    PA-307 violation. Avoids duplicating the AST detection logic that
    already lives in `scitex_dev.linter.checker`.

    ``repo_root`` (the ``--path`` target that ``resolve_target_tree`` already
    resolved: --path > current checkout > registry local_path) is PREFERRED
    for locating the ``tests/`` tree. Tests live in the REPO, not the installed
    wheel — deriving the tree from an import-resolved ``init_path`` scans the
    wrong tree (a site-packages install has no ``tests/``), finds zero
    candidates, and would report a SILENT 0 indistinguishable from a clean
    pass. When no test files are found, a loud skip-warning is emitted so a
    "0" is never mistaken for "the gate ran and passed" — the same visible-skip
    discipline the IO/PA category already has.
    """
    out: list[Violation] = []
    if repo_root is None:
        pkg_root = init_path.parent  # <repo>/src/<pkg>/
        src_parent = pkg_root.parent
        repo_root = src_parent.parent if src_parent.name == "src" else src_parent

    # Scope: tests/ tree (recursively, all *.py) + every conftest.py
    # under the repo, WITHOUT descending dot-directories (see
    # _conftests_under). Fixtures often live in conftest.py and TQ004/TQ005
    # apply to them.
    tests_dir = repo_root / "tests"
    candidates: list[Path] = []
    if tests_dir.is_dir():
        candidates.extend(sorted(tests_dir.rglob("*.py")))
    for conftest in _conftests_under(repo_root):
        # Skip site-packages and venvs.
        parts = conftest.parts
        if any(
            seg in parts
            for seg in (
                "__pycache__",
                "build",
                "dist",
                ".tox",
                "site-packages",
                ".venv",
                "venv",
            )
        ):
            continue
        if conftest not in candidates:
            candidates.append(conftest)

    if not candidates:
        # LOUD skip — never a silent 0. A quality gate that returns "clean"
        # without having scanned anything is worse than one that errors: it
        # reads as a pass. Make the not-run visible (stderr, like the other
        # audit-api warnings) so it cannot be mistaken for zero violations.
        import click

        click.echo(
            f"WARN: audit-api: STX-TQ (PA-307) found no test files under "
            f"{tests_dir} — the test-quality gate did NOT run (skipped, not "
            f"clean). If tests exist, pass --path <repo checkout> so the "
            f"repo's tests/ tree is scanned instead of the installed package.",
            err=True,
        )
        return out

    # Re-use the linter's detection rather than duplicate the AST logic.
    try:
        from scitex_dev.linter.checker import lint_file
    except ImportError:
        return out

    rel_anchor = repo_root
    for py_file in candidates:
        parts = py_file.parts
        if any(
            seg in parts
            for seg in (
                "__pycache__",
                "build",
                "dist",
                ".tox",
                "site-packages",
                ".venv",
                "venv",
            )
        ):
            continue
        try:
            issues = lint_file(str(py_file))
        except Exception:
            continue
        for issue in issues:
            rule_id = getattr(issue.rule, "id", "") or ""
            if not rule_id.startswith("STX-TQ"):
                continue
            try:
                rel = py_file.relative_to(rel_anchor)
            except ValueError:
                rel = py_file
            out.append(
                Violation(
                    "PA-307",
                    f"{distribution}: {rel}:{issue.line}",
                    f"{rule_id}: {issue.rule.message[:160]}",
                )
            )
    return out


__all__ = ["_audit_test_quality"]
