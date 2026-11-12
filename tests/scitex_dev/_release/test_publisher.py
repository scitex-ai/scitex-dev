"""Release publisher tests with real local Git repositories.

Non-dry-run cases push only to temporary local bare repositories and capture
card events in memory. No GitHub, PyPI or message provider is contacted.
"""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path


from scitex_dev._release.publisher import (
    _detect_trigger,
    _emit_released_event,
    publish_release,
)


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


def _add_origin(repo: Path, slug: str = "ywatanabe1989/scitex-testrepo") -> Path:
    origin = repo.parent / (repo.name + "-remote") / (slug + ".git")
    origin.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "--bare", "-q", str(origin)], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "remote", "add", "origin", str(origin)],
        check=True,
    )
    return origin


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


def test_publish_dry_run_describes_only_requested_tag(tmp_path):
    # Arrange
    # Act
    # Assert
    _mk_git_repo(tmp_path)
    _mk_workflow(tmp_path, "name: Pub\non:\n  release:\n    types: [published]\n")
    rep = publish_release(tmp_path, "1.2.3", dry_run=True)
    # Tag would be created, push would run, gh release would be created.
    assert "would: git push --no-follow-tags origin refs/tags/v1.2.3:refs/tags/v1.2.3" in rep.steps_run


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


# --- C7: `released` card-event producer -------------------------------


def test_emit_released_event_fires_with_recorded_envelope(tmp_path):
    # Arrange
    _mk_git_repo(tmp_path)
    _add_origin(tmp_path)
    from scitex_dev._release.publisher import PublishResult

    rep = PublishResult(repo=tmp_path, version="1.2.3", trigger="tags")
    rep.steps_run.append("git tag v1.2.3")
    fired: list[dict] = []

    def _fake_emit(repo_slug, version, *, card_id, actor):
        fired.append({"repo": repo_slug, "version": version, "card_id": card_id, "actor": actor})

    # Act
    _emit_released_event(rep, actor="scitex-dev", card_id="my-card", emit_fn=_fake_emit)

    # Assert
    assert fired == [
        {
            "repo": "ywatanabe1989/scitex-testrepo",
            "version": "1.2.3",
            "card_id": "my-card",
            "actor": "scitex-dev",
        }
    ]


def test_emit_released_event_is_silent_without_origin_remote(tmp_path):
    # Arrange — no `origin` remote configured, so no slug can be derived.
    _mk_git_repo(tmp_path)
    from scitex_dev._release.publisher import PublishResult

    rep = PublishResult(repo=tmp_path, version="1.2.3", trigger="tags")
    rep.steps_run.append("git tag v1.2.3")
    fired: list[dict] = []

    # Act
    _emit_released_event(rep, emit_fn=lambda *a, **k: fired.append((a, k)))

    # Assert
    assert fired == []


def _publish_real_tags_trigger(tmp_path, emit_fn):
    _mk_git_repo(tmp_path)
    _add_origin(tmp_path)
    _mk_workflow(tmp_path, "name: Pub\non:\n  push:\n    tags:\n      - 'v*'\n")
    # Exercise an actual push to the temporary local bare origin. Events
    # are injected into memory rather than a real notification provider.
    return publish_release(tmp_path, "1.2.3", dry_run=False, emit_fn=emit_fn)


def test_publish_release_creates_the_tag_for_real(tmp_path):
    # Arrange
    fired: list[dict] = []
    # Act
    rep = _publish_real_tags_trigger(tmp_path, lambda *a, **k: fired.append(1))
    # Assert
    assert "git tag v1.2.3" in rep.steps_run


def test_publish_release_emits_on_real_tag_creation(tmp_path):
    # Arrange
    fired: list[dict] = []

    def _fake_emit(repo_slug, version, *, card_id, actor):
        fired.append({"repo": repo_slug, "version": version, "card_id": card_id, "actor": actor})

    # Act
    _publish_real_tags_trigger(tmp_path, _fake_emit)

    # Assert
    assert fired == [
        {
            "repo": "ywatanabe1989/scitex-testrepo",
            "version": "1.2.3",
            "card_id": None,
            "actor": "scitex-dev",
        }
    ]


def test_publish_release_does_not_emit_on_dry_run(tmp_path):
    # Arrange
    _mk_git_repo(tmp_path)
    _add_origin(tmp_path)
    _mk_workflow(tmp_path, "name: Pub\non:\n  push:\n    tags:\n      - 'v*'\n")
    fired: list[dict] = []

    # Act
    publish_release(tmp_path, "1.2.3", dry_run=True, emit_fn=lambda *a, **k: fired.append(1))

    # Assert
    assert fired == []


def _publish_real_with_preexisting_tag(tmp_path, emit_fn):
    # Tag already exists before the call, so this run is a no-op.
    _mk_git_repo(tmp_path)
    _add_origin(tmp_path)
    _mk_workflow(tmp_path, "name: Pub\non:\n  push:\n    tags:\n      - 'v*'\n")
    subprocess.run(["git", "-C", str(tmp_path), "tag", "v1.2.3"], check=True)
    return publish_release(tmp_path, "1.2.3", dry_run=False, emit_fn=emit_fn)


def test_publish_release_skips_the_preexisting_tag_as_a_noop(tmp_path):
    # Arrange
    fired: list[dict] = []
    # Act
    rep = _publish_real_with_preexisting_tag(tmp_path, lambda *a, **k: fired.append(1))
    # Assert
    assert any("already exists" in s for s in rep.skipped)


def test_publish_release_does_not_emit_on_idempotent_rerun(tmp_path):
    # Arrange
    fired: list[dict] = []

    # Act
    _publish_real_with_preexisting_tag(tmp_path, lambda *a, **k: fired.append(1))

    # Assert
    assert fired == []


def _install_pre_push_hook(repo: Path, exit_code: int) -> Path:
    hooks = repo / ".git" / "publisher-test-hooks"
    hooks.mkdir()
    marker = repo / "pre-push-refs"
    hook = hooks / "pre-push"
    hook.write_text(
        "#!/bin/sh\ncat > " + shlex.quote(str(marker)) + "\nexit " + str(exit_code) + "\n"
    )
    hook.chmod(0o755)
    subprocess.run(
        ["git", "-C", str(repo), "config", "core.hooksPath", str(hooks)], check=True
    )
    return marker


def _remote_tags(origin: Path) -> list[str]:
    return subprocess.check_output(
        ["git", "--git-dir=" + str(origin), "for-each-ref", "--format=%(refname)", "refs/tags"],
        text=True,
    ).splitlines()


def test_real_publish_honors_pre_push_hook_and_only_requested_tag(tmp_path):
    # Arrange
    repo = _mk_git_repo(tmp_path)
    origin = _add_origin(repo)
    _mk_workflow(repo, "on:\n  push:\n    tags:\n      - 'v*'\n")
    subprocess.run(
        ["git", "-C", str(repo), "tag", "-a", "-m", "unrelated fixture", "v9.9.9"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "push.followTags", "true"], check=True
    )
    marker = _install_pre_push_hook(repo, 0)
    events = []
    # Act
    result = publish_release(repo, "1.2.3", emit_fn=lambda *a, **k: events.append((a, k)))
    hook_refs = marker.read_text().splitlines() if marker.exists() else []
    observed = {
        "failed": result.failed,
        "remote_tags": _remote_tags(origin),
        "hook_local_refs": [line.split()[0] for line in hook_refs],
    }
    # Assert
    assert observed == {
        "failed": [],
        "remote_tags": ["refs/tags/v1.2.3"],
        "hook_local_refs": ["refs/tags/v1.2.3"],
    }


def test_real_publish_refuses_pre_push_failure_without_emitting(tmp_path):
    # Arrange
    repo = _mk_git_repo(tmp_path)
    origin = _add_origin(repo)
    _mk_workflow(repo, "on:\n  push:\n    tags:\n      - 'v*'\n")
    marker = _install_pre_push_hook(repo, 1)
    events = []
    # Act
    result = publish_release(repo, "1.2.3", emit_fn=lambda *a, **k: events.append((a, k)))
    observed = {
        "push_failed": bool(result.failed),
        "hook_ran": marker.exists(),
        "remote_tags": _remote_tags(origin),
        "events": events,
    }
    # Assert
    assert observed == {
        "push_failed": True,
        "hook_ran": True,
        "remote_tags": [],
        "events": [],
    }
