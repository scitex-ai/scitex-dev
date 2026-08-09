#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex-dev ci verify`` — the CLI surface, exit codes especially.

The exit code IS the interface here: a hook and any gating script branch on
it, and the printed text is only for the human who has to fix things. So
these test the numbers rather than the prose.

The command is exercised through Click's runner against a stubbed verdict,
so no network and no GitHub token: what is under test is the wiring from a
`MergeReadiness` to an exit status, not the readiness logic (that has its
own suite in `tests/scitex_dev/ci/`).
"""

from __future__ import annotations

import click
import pytest
from click.testing import CliRunner

from scitex_dev._cli.ci import register_ci_commands
from scitex_dev.ci import (
    EXIT_NOT_READY,
    EXIT_READY,
    EXIT_UNKNOWN,
    MergeReadiness,
    Readiness,
)

HEAD = "fdce9aae19bc44be244e7d85ca432c343149e698"


def _ready() -> MergeReadiness:
    return MergeReadiness(
        readiness=Readiness.READY, pr="o/r#1", head_sha=HEAD
    )


def _not_ready() -> MergeReadiness:
    return MergeReadiness(
        readiness=Readiness.NOT_READY,
        pr="o/r#1",
        head_sha=HEAD,
        reasons=("audit: FAILURE",),
    )


def _unknown() -> MergeReadiness:
    return MergeReadiness(
        readiness=Readiness.CANNOT_DETERMINE,
        pr="o/r#1",
        head_sha=HEAD,
        reasons=("no check runs exist for this head",),
    )


def _run(verdict, extra=()):
    """Invoke `ci verify` with `readiness` stubbed to return `verdict`."""
    import scitex_dev.ci._mergeable as module

    original = module.readiness
    module.readiness = lambda pr, repo: verdict

    @click.group()
    def root() -> None:
        pass

    register_ci_commands(root)
    try:
        return CliRunner().invoke(
            root, ["ci", "verify", "1", "--repo", "o/r", *extra]
        )
    finally:
        module.readiness = original


class TestTheExitCodeIsTheInterface:
    """A script branches on these; they must not collapse into each other."""

    def test_ready_exits_zero(self):
        # Arrange
        verdict = _ready()
        # Act
        result = _run(verdict)
        # Assert
        assert result.exit_code == EXIT_READY

    def test_not_ready_exits_two(self):
        # Arrange
        verdict = _not_ready()
        # Act
        result = _run(verdict)
        # Assert
        assert result.exit_code == EXIT_NOT_READY

    def test_cannot_determine_exits_three_not_two(self):
        """'I could not tell' must be distinguishable from 'no'."""
        # Arrange
        verdict = _unknown()
        # Act
        result = _run(verdict)
        # Assert
        assert result.exit_code == EXIT_UNKNOWN

    def test_cannot_determine_is_not_treated_as_ready(self):
        """Folding unknown into yes is the failure that ships the bug."""
        # Arrange
        verdict = _unknown()
        # Act
        result = _run(verdict)
        # Assert
        assert result.exit_code != EXIT_READY


class TestTheOutputNamesWhatIsWrong:
    """A refusal the caller cannot act on is only half-written."""

    def test_each_reason_is_printed(self):
        # Arrange
        verdict = _not_ready()
        # Act
        result = _run(verdict)
        # Assert
        assert "audit: FAILURE" in result.output

    def test_the_pull_request_is_named_with_its_repo(self):
        """A bare number is ambiguous across this fleet's repositories."""
        # Arrange
        verdict = _ready()
        # Act
        result = _run(verdict)
        # Assert
        assert "o/r#1" in result.output

    def test_json_mode_emits_the_readiness_field(self):
        # Arrange
        verdict = _not_ready()
        # Act
        result = _run(verdict, extra=("--json",))
        # Assert
        assert '"readiness": "not-ready"' in result.output


class TestRepoIsRequired:
    """Inferring it from the cwd is how a query hits the wrong repo."""

    def test_omitting_repo_is_a_usage_error(self):
        # Arrange
        @click.group()
        def root() -> None:
            pass

        register_ci_commands(root)
        # Act
        result = CliRunner().invoke(root, ["ci", "verify", "1"])
        # Assert
        assert result.exit_code != EXIT_READY


# EOF
