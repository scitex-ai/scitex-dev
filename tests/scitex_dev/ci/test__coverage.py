#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A green PR is not a checked PR, and GitHub renders the two identically.

Green means "nothing required FAILED". It does not mean "everything required
REPORTED". A pull request whose workflows never triggered shows no red, because
there is nothing to be red — the information is absent rather than wrong, which
is the harder kind to notice.

Measured 2026-08-15 on this repository: PR #591 was based on a TOPIC BRANCH, and
the workflows filter `pull_request: branches: [main, develop]`. `branches:`
filters the BASE, so nothing matched and no workflow ran. It sat three days
showing only its CLA check, and I read it as green every time I looked.
"""

from __future__ import annotations

import pytest

from scitex_dev.ci._coverage import (
    Coverage,
    classify_pr_coverage,
    render,
)

REQUIRED = ("tests", "import-smoke", "sphinx", "call / CLAssistant")


def test_a_pr_with_every_required_check_reported_is_covered() -> None:
    # Arrange
    ran = REQUIRED
    # Act
    verdict = classify_pr_coverage("develop", REQUIRED, ran)
    # Assert
    assert verdict.coverage is Coverage.COVERED


def test_a_pr_missing_a_required_check_is_uncovered() -> None:
    """THE #591 CASE, and nothing on the PR page says it."""
    # Arrange
    ran = ("call / CLAssistant",)
    # Act
    verdict = classify_pr_coverage("feat/some-topic", REQUIRED, ran)
    # Assert
    assert verdict.coverage is Coverage.UNCOVERED


def test_the_verdict_names_the_checks_that_never_ran() -> None:
    """"Something is missing" sends nobody anywhere. Name them."""
    # Arrange
    ran = ("call / CLAssistant",)
    # Act
    verdict = classify_pr_coverage("feat/some-topic", REQUIRED, ran)
    # Assert
    assert verdict.missing == ("tests", "import-smoke", "sphinx")


def test_an_unreachable_base_is_reported_as_the_cause() -> None:
    """Two absences with different fixes must not read the same.

    A base the filter does not name means NO RUN WAS QUEUED — retarget the
    PR. A configured check that did not run means something failed to start
    — go find out why. Same symptom, opposite investigations.
    """
    # Arrange
    ran = ("call / CLAssistant",)
    # Act
    verdict = classify_pr_coverage("feat/some-topic", REQUIRED, ran)
    # Assert
    assert verdict.unreachable_base == "feat/some-topic"


def test_a_reachable_base_reports_no_base_cause() -> None:
    """POSITIVE CONTROL for the field above: a develop-based PR missing a
    check has a DIFFERENT problem, and blaming the base would send the
    reader to retarget a PR that is already targeted correctly."""
    # Arrange
    ran = ("call / CLAssistant",)
    # Act
    verdict = classify_pr_coverage("develop", REQUIRED, ran)
    # Assert
    assert verdict.unreachable_base is None


def test_an_unreachable_base_with_nothing_required_is_still_covered() -> None:
    """Do not invent a finding where nothing was prevented.

    If no check is required, an unreachable base cost the PR nothing — and
    flagging it would fire on every draft and stacked branch in the fleet,
    which is how a signal becomes noise and then becomes ignored.
    """
    # Arrange
    required: tuple[str, ...] = ()
    # Act
    verdict = classify_pr_coverage("feat/some-topic", required, ())
    # Assert
    assert verdict.coverage is Coverage.COVERED


@pytest.mark.parametrize(
    ("required", "ran"),
    [(None, REQUIRED), (REQUIRED, None), (None, None)],
)
def test_an_unreadable_input_is_unknown_not_a_verdict(required, ran) -> None:
    """THE THIRD VALUE. `None` is "could not read"; `()` is "read, empty".

    Collapsing them either restores the silence this exists to break, or
    cries wolf on every API hiccup until the reader stops looking.
    """
    # Arrange
    given = (required, ran)
    # Act
    verdict = classify_pr_coverage("develop", *given)
    # Assert
    assert verdict.coverage is Coverage.UNKNOWN


def test_unknown_does_not_block() -> None:
    """A broken instrument is not a defect in the thing measured."""
    # Arrange
    verdict = classify_pr_coverage("develop", None, None)
    # Act
    blocks = verdict.blocks
    # Assert
    assert blocks is False


def test_an_uncovered_pr_blocks() -> None:
    """The control for the test above — a guard that never blocks is not a
    guard, and would pass every other assertion in this file."""
    # Arrange
    verdict = classify_pr_coverage("develop", REQUIRED, ())
    # Act
    blocks = verdict.blocks
    # Assert
    assert blocks is True


def test_duplicate_required_contexts_are_not_double_reported() -> None:
    """Branch protection can list a context twice; the reader should not
    read it twice and wonder which one is which."""
    # Arrange
    required = ("tests", "tests", "sphinx")
    # Act
    verdict = classify_pr_coverage("develop", required, ())
    # Assert
    assert verdict.missing == ("tests", "sphinx")


def test_the_render_explains_the_base_filter_rather_than_only_naming_it() -> None:
    """Whoever reads this has just learned their PR was never tested. Tell
    them why and what to do, not only that it happened."""
    # Arrange
    verdict = classify_pr_coverage("feat/some-topic", REQUIRED, ())
    # Act
    text = render(verdict)
    # Assert
    assert "Retarget the PR" in text


def test_the_render_says_plainly_when_it_could_not_judge() -> None:
    # Arrange
    verdict = classify_pr_coverage("develop", None, None)
    # Act
    text = render(verdict)
    # Assert
    assert "COULD NOT BE JUDGED" in text


def test_a_covered_render_carries_no_alarm() -> None:
    """Positive control: a renderer that always warned would satisfy both
    tests above and teach every reader to skip the line."""
    # Arrange
    verdict = classify_pr_coverage("develop", REQUIRED, REQUIRED)
    # Act
    text = render(verdict)
    # Assert
    assert "NEVER RAN" not in text


# EOF
