# -*- coding: utf-8 -*-
"""Tests for `_check_workflows_naming.py` (PS-164), pipeline carve-out.

PS-164 flags multi-job workflows whose job IDs share no stem — one
file per check. The (c') carve-out recognises a tag-driven release
pipeline (test → build → publish → release) as ONE concern: the test
matrix is the gate that must pass before anything is published, so
splitting it into its own file would decouple the safety check from
the release it guards.

Single assert per test (PA-307). Pure-function level: no repo needed.
"""

from scitex_dev._cli.audit._project._check_workflows_naming import (
    _share_stem,
)


class TestReleasePipelineCarveOut:
    def test_test_build_publish_release_share_a_stem(self) -> None:
        # Arrange — the tag-driven release pipeline's four jobs.
        # Act
        shared = _share_stem(
            ["test", "build", "publish", "release"], "pypi-publish-on-tag"
        )
        # Assert
        assert shared

    def test_unrelated_jobs_still_do_not_share_a_stem(self) -> None:
        # Arrange — negative control: genuinely unrelated concerns.
        # Act
        shared = _share_stem(["lint", "docs"], "pypi-publish-on-tag")
        # Assert
        assert not shared

    def test_release_pipeline_without_test_still_shares_a_stem(self) -> None:
        # Arrange — the pre-existing carve-out, unchanged by adding test.
        # Act
        shared = _share_stem(
            ["build", "publish", "release"], "pypi-publish-on-tag"
        )
        # Assert
        assert shared

    def test_test_job_outside_a_release_pipeline_still_fires(self) -> None:
        # Arrange — `test` alone does not license any multi-job file; the
        # filename must still declare the publish/release pipeline.
        # Act
        shared = _share_stem(["test", "lint"], "ci-matrix-on-ubuntu")
        # Assert
        assert not shared


# EOF
