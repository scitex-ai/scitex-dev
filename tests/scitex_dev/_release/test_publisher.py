"""Test the smart release publisher.

Each test sets up a temporary git repo + workflow file, then invokes
``publish_release`` in dry-run mode (so no actual git/gh side effects).
"""

from __future__ import annotations

import subprocess
from pathlib import Path


from scitex_dev._release.publisher import _detect_trigger, publish_release


def _mk_workflow(repo: Path, body: str) -> Path:
    wf = repo / ".github" / "workflows" / "publish-pypi.yml"
    wf.parent.mkdir(parents=True, exist_ok=True)
    wf.write_text(body)
    return wf


def _mk_git_repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "t@t.t"], check=True
    )
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "t"], check=True)
    (tmp_path / "README.md").write_text("# t\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "README.md"], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-q", "-m", "init"], check=True
    )
    return tmp_path


def test_detect_trigger_release(tmp_path):
    # Arrange
    # Act
    # Assert
    _mk_workflow(tmp_path, "name: Pub\non:\n  release:\n    types: [published]\n")
    assert _detect_trigger(tmp_path) == "release"


def test_detect_trigger_tags(tmp_path):
    # Arrange
    # Act
    # Assert
    _mk_workflow(tmp_path, "name: Pub\non:\n  push:\n    tags:\n      - 'v*'\n")
    assert _detect_trigger(tmp_path) == "tags"


def test_detect_trigger_missing(tmp_path):
    # Arrange
    # Act
    # Assert
    assert _detect_trigger(tmp_path) is None


def test_publish_dry_run_release_trigger_rep_trigger_release(tmp_path):
    # Arrange
    # Act
    # Assert
    _mk_git_repo(tmp_path)
    _mk_workflow(tmp_path, "name: Pub\non:\n  release:\n    types: [published]\n")
    rep = publish_release(tmp_path, "1.2.3", dry_run=True)
    assert rep.trigger == "release"
    # Tag would be created, push would run, gh release would be created.


def test_publish_dry_run_release_trigger_any_would_git_tag_v1_2_3_in_s_for_s_in_r(tmp_path):
    # Arrange
    # Act
    # Assert
    _mk_git_repo(tmp_path)
    _mk_workflow(tmp_path, "name: Pub\non:\n  release:\n    types: [published]\n")
    rep = publish_release(tmp_path, "1.2.3", dry_run=True)
    # Tag would be created, push would run, gh release would be created.
    assert any("would: git tag v1.2.3" in s for s in rep.steps_run)


def test_publish_dry_run_release_trigger_would_git_push_tags_in_rep_steps_run(tmp_path):
    # Arrange
    # Act
    # Assert
    _mk_git_repo(tmp_path)
    _mk_workflow(tmp_path, "name: Pub\non:\n  release:\n    types: [published]\n")
    rep = publish_release(tmp_path, "1.2.3", dry_run=True)
    # Tag would be created, push would run, gh release would be created.
    assert "would: git push --tags" in rep.steps_run


def test_publish_dry_run_tags_trigger_rep_trigger_tags(tmp_path):
    # Arrange
    # Act
    # Assert
    _mk_git_repo(tmp_path)
    _mk_workflow(tmp_path, "name: Pub\non:\n  push:\n    tags:\n      - 'v*'\n")
    rep = publish_release(tmp_path, "1.2.3", dry_run=True)
    assert rep.trigger == "tags"
    # No gh release create for tag-trigger workflows.
    # Should mention the trigger in the skipped list.


def test_publish_dry_run_tags_trigger_any_would_git_tag_v1_2_3_in_s_for_s_in_r(tmp_path):
    # Arrange
    # Act
    # Assert
    _mk_git_repo(tmp_path)
    _mk_workflow(tmp_path, "name: Pub\non:\n  push:\n    tags:\n      - 'v*'\n")
    rep = publish_release(tmp_path, "1.2.3", dry_run=True)
    assert any("would: git tag v1.2.3" in s for s in rep.steps_run)
    # No gh release create for tag-trigger workflows.
    # Should mention the trigger in the skipped list.


def test_publish_dry_run_tags_trigger_not_any_gh_release_create_in_s_for_s_in(tmp_path):
    # Arrange
    # Act
    # Assert
    _mk_git_repo(tmp_path)
    _mk_workflow(tmp_path, "name: Pub\non:\n  push:\n    tags:\n      - 'v*'\n")
    rep = publish_release(tmp_path, "1.2.3", dry_run=True)
    # No gh release create for tag-trigger workflows.
    assert not any("gh release create" in s for s in rep.steps_run)
    # Should mention the trigger in the skipped list.


def test_publish_dry_run_tags_trigger_any_tag_push_alone_fires_in_s_for_s_in_r(tmp_path):
    # Arrange
    # Act
    # Assert
    _mk_git_repo(tmp_path)
    _mk_workflow(tmp_path, "name: Pub\non:\n  push:\n    tags:\n      - 'v*'\n")
    rep = publish_release(tmp_path, "1.2.3", dry_run=True)
    # No gh release create for tag-trigger workflows.
    # Should mention the trigger in the skipped list.
    assert any("tag-push alone fires" in s for s in rep.skipped)


def test_publish_skips_existing_tag(tmp_path):
    # Arrange
    # Act
    # Assert
    _mk_git_repo(tmp_path)
    _mk_workflow(tmp_path, "name: Pub\non:\n  push:\n    tags:\n      - 'v*'\n")
    subprocess.run(["git", "-C", str(tmp_path), "tag", "v1.2.3"], check=True)
    rep = publish_release(tmp_path, "1.2.3", dry_run=True)
    assert any("already exists" in s for s in rep.skipped)
