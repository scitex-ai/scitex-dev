#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PS-231 — the rule must flag copies, and must NOT flag callers or definitions.

The second half is the part that decides whether the rule is usable. A check
that flagged callers would punish exactly the repos that already did the right
thing, and one that flagged reusable definitions would fail the org's own
repository — which is where the workflows it defends actually live.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scitex_dev._cli.audit._project._check_workflow_duplication import (
    ORG_REUSABLE_WORKFLOWS,
    WORKFLOW_DUPLICATION_RULES,
    calls_org,
    check_ps231_workflow_duplication,
    defines_reusable,
    duplicated_org_workflow,
    is_duplicate,
    iter_workflow_files,
)


class _Violation:
    """A real collector. The auditor passes its own class in the same shape."""

    def __init__(self, code: str, where: str, detail: str) -> None:
        self.code = code
        self.where = where
        self.detail = detail


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    for name, body in files.items():
        (workflows / name).write_text(body, encoding="utf-8")
    return tmp_path


_A_COPY = "on:\n  push:\njobs:\n  test:\n    runs-on: ubuntu-latest\n"
_A_CALLER = (
    "on:\n  push:\njobs:\n  pytest-matrix:\n"
    "    uses: scitex-ai/.github/.github/workflows/pytest-matrix.yml@main\n"
)
_A_DEFINITION = "on:\n  workflow_call:\n    inputs:\n      runs_on:\n"


def test_an_exact_name_match_is_a_duplicate() -> None:
    # Arrange
    stem = "cla"
    # Act
    org = duplicated_org_workflow(stem)
    # Assert
    assert org == "cla"


def test_the_fleets_on_runner_naming_convention_is_a_duplicate() -> None:
    """`<org>-on-<where>` is how this fleet names its copies.

    A leaf that renamed the file while copying the contents duplicated it more
    thoroughly, not less.
    """
    # Arrange
    stem = "pytest-matrix-on-ubuntu-py3-11-3-12-3-13"
    # Act
    org = duplicated_org_workflow(stem)
    # Assert
    assert org == "pytest-matrix"


def test_an_unrelated_workflow_is_not_a_duplicate() -> None:
    """The negative control.

    Without it, a matcher that returned an org name for everything would pass
    every other test here.
    """
    # Arrange
    stem = "pypi-publish-and-github-release-on-tag"
    # Act
    org = duplicated_org_workflow(stem)
    # Assert
    assert org is None


def test_a_prefix_that_is_not_followed_by_on_is_not_a_duplicate() -> None:
    """`cla-signature-bot` starts with `cla` and is not a copy of it."""
    # Arrange
    stem = "cla-signature-bot"
    # Act
    org = duplicated_org_workflow(stem)
    # Assert
    assert org is None


def test_a_caller_is_never_flagged_however_it_is_named() -> None:
    """Callers are the TARGET STATE and may be named anything."""
    # Arrange
    text = _A_CALLER
    # Act
    org = is_duplicate(text, "pytest-matrix")
    # Assert
    assert org is None


def test_a_reusable_definition_is_never_flagged() -> None:
    """This is how `scitex-ai/.github` passes without a name-based exemption.

    A self-exemption keyed on the repo NAME would stop working the moment that
    repo were checked out under a different directory — which it is, locally.
    """
    # Arrange
    text = _A_DEFINITION
    # Act
    org = is_duplicate(text, "pytest-matrix")
    # Assert
    assert org is None


def test_a_comment_naming_the_org_does_not_exempt_a_copy() -> None:
    """THE FALSE NEGATIVE THIS RULE ALMOST SHIPPED WITH — measured, not imagined.

    The first draft tested `"scitex-ai/.github" in text`. Against the fleet it
    cleared two of `sac`'s genuine local copies, because each carries a comment
    explaining why it does NOT call the reusable:

        # (scitex-ai/.github/.github/workflows/import-smoke.yml). That reusable
        # stops ...

    So the check exempted a file for DOCUMENTING its own duplication, and the
    better-documented the divergence, the more certainly it went unflagged.
    """
    # Arrange
    text = (
        "# see scitex-ai/.github/.github/workflows/import-smoke.yml — we do\n"
        "# not use it because our entry point differs\n"
        "on:\n  push:\njobs:\n  smoke:\n    runs-on: ubuntu-latest\n"
    )
    # Act
    org = is_duplicate(text, "import-smoke")
    # Assert
    assert org == "import-smoke"


def test_a_comment_mentioning_workflow_call_does_not_exempt_a_copy() -> None:
    """The same hole on the other marker, closed at the same time."""
    # Arrange
    text = "# this is not a workflow_call definition\non:\n  push:\njobs: {}\n"
    # Act
    org = is_duplicate(text, "cla")
    # Assert
    assert org == "cla"


def test_a_real_uses_line_still_exempts() -> None:
    """The positive control for the tightened matcher.

    Without it, a matcher that rejected EVERY marker would satisfy both
    false-negative tests above and break every conforming repo in the fleet.
    """
    # Arrange
    text = _A_CALLER
    # Act
    called = calls_org(text)
    # Assert
    assert called is True


def test_a_real_workflow_call_line_still_exempts() -> None:
    # Arrange
    text = _A_DEFINITION
    # Act
    defines = defines_reusable(text)
    # Assert
    assert defines is True


def test_a_local_copy_is_flagged() -> None:
    # Arrange
    text = _A_COPY
    # Act
    org = is_duplicate(text, "cla")
    # Assert
    assert org == "cla"


def test_the_check_reports_one_finding_per_copy(tmp_path: Path) -> None:
    # Arrange
    repo = _repo(
        tmp_path,
        {
            "cla.yml": _A_COPY,
            "rtd-sphinx-build-on-ubuntu-latest.yml": _A_COPY,
            "release.yml": _A_COPY,
        },
    )
    out: list[_Violation] = []
    # Act
    check_ps231_workflow_duplication(repo, _Violation, out)
    # Assert
    assert len(out) == 2


def test_the_finding_names_the_org_workflow_to_call(tmp_path: Path) -> None:
    """A finding that does not say WHAT to call is a chore, not a fix."""
    # Arrange
    repo = _repo(tmp_path, {"cla.yml": _A_COPY})
    out: list[_Violation] = []
    # Act
    check_ps231_workflow_duplication(repo, _Violation, out)
    # Assert
    assert "scitex-ai/.github/.github/workflows/cla.yml" in out[0].detail


def test_the_finding_offers_the_exemption_route(tmp_path: Path) -> None:
    """The operator's caveat was `unless ... unique to the leaf`.

    A rule that states no escape invites the blanket flag instead.
    """
    # Arrange
    repo = _repo(tmp_path, {"cla.yml": _A_COPY})
    out: list[_Violation] = []
    # Act
    check_ps231_workflow_duplication(repo, _Violation, out)
    # Assert
    assert "audit.exemptions" in out[0].detail


def test_a_repo_of_callers_yields_nothing(tmp_path: Path) -> None:
    # Arrange
    repo = _repo(tmp_path, {"cla.yml": _A_CALLER, "ci.yml": _A_CALLER})
    out: list[_Violation] = []
    # Act
    check_ps231_workflow_duplication(repo, _Violation, out)
    # Assert
    assert out == []


def test_a_repo_with_no_workflows_directory_is_not_an_error(tmp_path: Path) -> None:
    # Arrange
    out: list[_Violation] = []
    # Act
    check_ps231_workflow_duplication(tmp_path, _Violation, out)
    # Assert
    assert out == []


def test_findings_come_out_in_a_stable_order(tmp_path: Path) -> None:
    """An unstable order turns a re-run into a diff."""
    # Arrange
    repo = _repo(tmp_path, {"cla.yml": _A_COPY, "auto-merge-to-develop.yml": _A_COPY})
    out: list[_Violation] = []
    # Act
    check_ps231_workflow_duplication(repo, _Violation, out)
    # Assert
    assert [Path(v.where).name for v in out] == [
        "auto-merge-to-develop.yml",
        "cla.yml",
    ]


def test_yaml_and_yml_are_both_collected(tmp_path: Path) -> None:
    """The fleet uses both, and `auto-merge-to-develop.yaml` is the common one."""
    # Arrange
    repo = _repo(tmp_path, {"auto-merge-to-develop.yaml": _A_COPY})
    # Act
    collected = [p.name for p in iter_workflow_files(repo)]
    # Assert
    assert collected == ["auto-merge-to-develop.yaml"]


def test_the_org_inventory_is_not_empty() -> None:
    """A stale-to-empty inventory would flag NOTHING and read as `no duplicates`.

    The set is a measurement with an expiry date, so the failure that matters
    is it silently shrinking, not it being wrong about one name.
    """
    # Arrange
    inventory = ORG_REUSABLE_WORKFLOWS
    # Act
    size = len(inventory)
    # Assert
    assert size >= 7


def test_self_test_is_not_listed_as_callable() -> None:
    """It declares no `workflow_call`, so "call it instead" cannot be done.

    A finding whose remedy is impossible is worse than no finding: it sends
    someone to do a thing that does not work, and the rule loses its standing.
    """
    # Arrange
    inventory = ORG_REUSABLE_WORKFLOWS
    # Act
    listed = "self-test" in inventory
    # Assert
    assert listed is False


def test_the_provider_repo_is_exempt_as_a_whole(tmp_path: Path) -> None:
    """The org repository must not be flagged for holding its own workflows.

    Detected by COUNTING definitions rather than by directory name: the org
    repo is checked out locally as `scitex-org-github`, so a name test would
    flag the very repo whose workflows this rule defends.
    """
    # Arrange
    repo = _repo(
        tmp_path,
        {
            "cla.yml": _A_DEFINITION,
            "pytest-matrix.yml": _A_DEFINITION,
            "self-test.yml": _A_COPY,
        },
    )
    out: list[_Violation] = []
    # Act
    check_ps231_workflow_duplication(repo, _Violation, out)
    # Assert
    assert out == []


def test_a_leaf_with_one_reusable_of_its_own_is_still_audited(tmp_path: Path) -> None:
    """One definition is a leaf that factored something; several is the org.

    Without this boundary a leaf could exempt its whole repo by declaring a
    single `workflow_call` — turning the provider test into the blanket flag
    the operator rejected.
    """
    # Arrange
    repo = _repo(tmp_path, {"cla.yml": _A_DEFINITION, "import-smoke.yml": _A_COPY})
    out: list[_Violation] = []
    # Act
    check_ps231_workflow_duplication(repo, _Violation, out)
    # Assert
    assert [Path(v.where).name for v in out] == ["import-smoke.yml"]


def test_the_rule_ships_at_severity_e() -> None:
    """No W, no ratchet — the operator settled this shape on PS-224.

    「昔だろうが今だろうが問題点は問題点」. Pinned by test because a
    severity quietly relaxed to W would make the rule fire forever and never
    fail anything, which is indistinguishable from it working.
    """
    # Arrange
    (_code, _section, _message, severity, _slug) = WORKFLOW_DUPLICATION_RULES[0]
    # Act
    shipped = severity
    # Assert
    assert shipped == "E"


def test_the_rule_code_is_ps231() -> None:
    # Arrange
    (code, *_rest) = WORKFLOW_DUPLICATION_RULES[0]
    # Act
    shipped = code
    # Assert
    assert shipped == "PS-231"


@pytest.mark.parametrize("org", sorted(ORG_REUSABLE_WORKFLOWS))
def test_every_declared_org_workflow_is_matched_by_its_own_name(org: str) -> None:
    """Guards a typo in the inventory, which fails silently in the safe-looking
    direction: an entry nothing can match flags nothing and reads as clean."""
    # Arrange
    stem = org
    # Act
    matched = duplicated_org_workflow(stem)
    # Assert
    assert matched == org


# EOF
