#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The verdict must hand back a SHA the merge command will accept.

Measured 2026-08-09, one command after the exit-code bug. ``render()``
printed an abbreviated head::

    ready: scitex-ai/scitex-dev#526 @ 5b39c44

and the pinned merge the hook documents rejected it::

    gh pr merge 526 --repo ... --match-head-commit 5b39c44
    GraphQL: ... invalid value for expectedHeadOid
             (Could not coerce value "5b39c44" to GitObjectID)

So the documented two-step handed the reader a value from step one that
step two refused. The pin is the ENTIRE safety mechanism here — it is what
stops a commit landing underneath a verified green — and a pin that errors
is a pin people stop passing.

The trap is sharper than an inconvenience: an abbreviated SHA LOOKS like
the value the flag wants. On this same day one was reconstructed by padding
a short form with invented hex, and GitHub rejecting it is the only reason
the fabrication was caught.
"""

from __future__ import annotations

from scitex_dev.ci._readiness import MergeReadiness, Readiness

FULL_SHA = "5b39c440d4e55b6c09d9e72a058d59c07737b544"
SHORT_SHA = "5b39c44"


def a_ready_verdict() -> MergeReadiness:
    return MergeReadiness(
        readiness=Readiness.READY,
        pr="scitex-ai/scitex-dev#526",
        head_sha=FULL_SHA,
    )


def a_not_ready_verdict() -> MergeReadiness:
    return MergeReadiness(
        readiness=Readiness.NOT_READY,
        pr="scitex-ai/scitex-dev#526",
        head_sha=FULL_SHA,
        reasons=("audit: FAILURE",),
    )


class TestTheRenderedHeadIsUsable:
    def test_render_prints_the_full_forty_character_head(self):
        # Arrange
        verdict = a_ready_verdict()
        # Act
        text = verdict.render()
        # Assert
        assert FULL_SHA in text

    def test_render_does_not_pass_off_an_abbreviation_as_the_head(self):
        """The short form may appear only as part of the full one."""
        # Arrange
        verdict = a_ready_verdict()
        # Act
        text = verdict.render().replace(FULL_SHA, "")
        # Assert
        assert SHORT_SHA not in text


class TestTheMergeCommandIsEmittedReadyToRun:
    def test_a_ready_verdict_emits_a_merge_command(self):
        # Arrange
        verdict = a_ready_verdict()
        # Act
        command = verdict.merge_command
        # Assert
        assert command is not None

    def test_the_command_pins_the_full_head(self):
        # Arrange
        verdict = a_ready_verdict()
        # Act
        command = verdict.merge_command
        # Assert
        assert f"--match-head-commit {FULL_SHA}" in command

    def test_the_command_names_the_repository(self):
        """A bare PR number identified the wrong repo once already."""
        # Arrange
        verdict = a_ready_verdict()
        # Act
        command = verdict.merge_command
        # Assert
        assert "--repo scitex-ai/scitex-dev" in command

    def test_the_command_carries_the_bare_pr_number(self):
        # Arrange
        verdict = a_ready_verdict()
        # Act
        command = verdict.merge_command
        # Assert
        assert "gh pr merge 526 " in command

    def test_the_command_appears_in_the_rendered_output(self):
        # Arrange
        verdict = a_ready_verdict()
        # Act
        text = verdict.render()
        # Assert
        assert verdict.merge_command in text


class TestNoMergeCommandWithoutAGreen:
    """Emitting a runnable merge next to a refusal is an invitation."""

    def test_a_not_ready_verdict_emits_no_command(self):
        # Arrange
        verdict = a_not_ready_verdict()
        # Act
        command = verdict.merge_command
        # Assert
        assert command is None

    def test_a_not_ready_render_contains_no_merge_invocation(self):
        # Arrange
        verdict = a_not_ready_verdict()
        # Act
        text = verdict.render()
        # Assert
        assert "gh pr merge" not in text

    def test_a_verdict_without_a_head_emits_no_command(self):
        # Arrange
        verdict = MergeReadiness(
            readiness=Readiness.CANNOT_DETERMINE,
            pr="scitex-ai/scitex-dev#526",
            head_sha=None,
            reasons=("the API did not report a head commit",),
        )
        # Act
        command = verdict.merge_command
        # Assert
        assert command is None


class TestTheDictCarriesWhatAScriptNeeds:
    def test_the_dict_exposes_the_merge_command(self):
        # Arrange
        verdict = a_ready_verdict()
        # Act
        payload = verdict.to_dict()
        # Assert
        assert payload["merge_command"] == verdict.merge_command

    def test_the_dict_exposes_the_numeric_exit_code(self):
        # Arrange
        verdict = a_ready_verdict()
        # Act
        payload = verdict.to_dict()
        # Assert
        assert payload["exit_code"] == 0

    def test_the_dict_exposes_the_full_head(self):
        # Arrange
        verdict = a_ready_verdict()
        # Act
        payload = verdict.to_dict()
        # Assert
        assert payload["head_sha"] == FULL_SHA


# EOF
