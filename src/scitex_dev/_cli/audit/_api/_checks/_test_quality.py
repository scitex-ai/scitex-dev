"""PA-307 test-quality check for the Python API auditor.

Run the linter's STX-TQ001-007 detection across first-party tests and
conftests using the shared hidden-path and ignore-aware discovery contract.
Re-emit each finding as PA-307; re-export from `_audit` for existing imports.
"""

from __future__ import annotations

from pathlib import Path

from ..._fd import fd_find_files
from ._model import Violation


def _conftests_under(repo_root: Path):
    """Use the shared hidden-path and ignore-aware audit discovery contract."""
    yield from fd_find_files(repo_root, glob="conftest.py")


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
    # under the repo, using the shared ignore-aware discovery for both
    # roots. Fixtures often live in conftest.py and TQ004/TQ005
    # apply to them.
    tests_dir = repo_root / "tests"
    candidates: list[Path] = []
    if tests_dir.is_dir():
        candidates.extend(fd_find_files(tests_dir, glob="*.py"))
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
