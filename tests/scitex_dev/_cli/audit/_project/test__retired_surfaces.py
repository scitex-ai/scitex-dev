# -*- coding: utf-8 -*-
"""Tests for `_retired_surfaces` — the ADR-0012-retired `cron` surface.

One predicate, shared by the PS-227 and PS-145 carve-outs: files under
``src/<pkg>/_cli/cron/`` are frozen pending removal, so forward-looking
convention migrations do not apply to them.

No mocks — real ``tmp_path`` trees. Single assert per test (PA-307).
"""

from pathlib import Path

from scitex_dev._cli.audit._project._retired_surfaces import (
    is_retired_cron_surface,
)


def _repo_with(*relpaths: str, tmp_path: Path) -> Path:
    """Materialise an empty file per relpath under tmp_path; return it."""
    for rel in relpaths:
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x = 1\n", encoding="utf-8")
    return tmp_path


def test_a_file_under_cli_cron_is_retired(tmp_path: Path) -> None:
    # Arrange
    repo = _repo_with("src/scitex_dev/_cli/cron/_jobs.py", tmp_path=tmp_path)
    # Act
    retired = is_retired_cron_surface(repo / "src/scitex_dev/_cli/cron/_jobs.py", repo)
    # Assert
    assert retired


def test_a_sibling_cli_module_is_not_retired(tmp_path: Path) -> None:
    # Arrange — same `_cli/` parent, different leaf: still migrated.
    repo = _repo_with("src/scitex_dev/_cli/ecosystem/_cmds/_gui.py", tmp_path=tmp_path)
    # Act
    retired = is_retired_cron_surface(
        repo / "src/scitex_dev/_cli/ecosystem/_cmds/_gui.py", repo
    )
    # Assert
    assert not retired


def test_a_path_with_cron_elsewhere_is_not_retired(tmp_path: Path) -> None:
    # Arrange — `cron` must follow `_cli/` consecutively; a job-schedule
    # module deeper in the tree is not the retired surface.
    repo = _repo_with("src/scitex_dev/jobs/cron.py", tmp_path=tmp_path)
    # Act
    retired = is_retired_cron_surface(repo / "src/scitex_dev/jobs/cron.py", repo)
    # Assert
    assert not retired


def test_a_path_outside_the_repo_is_not_retired(tmp_path: Path) -> None:
    # Arrange — the exemption never leaks onto files the audit grades
    # from another tree.
    repo = _repo_with("src/scitex_dev/_cli/cron/_jobs.py", tmp_path=tmp_path)
    # Act
    retired = is_retired_cron_surface(Path("/elsewhere/_cli/cron/x.py"), repo)
    # Assert
    assert not retired


def test_an_unresolvable_relative_path_fails_closed(tmp_path: Path) -> None:
    # Arrange — a relative path cannot resolve against an absolute repo
    # root, so it must fail closed (False), never leak the exemption.
    repo = _repo_with("src/scitex_dev/_cli/cron/_jobs.py", tmp_path=tmp_path)
    # Act
    retired = is_retired_cron_surface(Path("src/scitex_dev/_cli/cron/_jobs.py"), repo)
    # Assert
    assert not retired


# EOF
