# -*- coding: utf-8 -*-
"""PS-221 exempts the `dev`/`docs` TOOLING class from `[all]`-closure.

Not a new exception — a clause of the operator directive PS-221 implements
and had dropped. PS-217 quotes it verbatim in its own finding text:
`dev`/`docs` extras are exempt from the all-or-nothing shape.

The reductio: closing them under `all` means `all = ["pkg[dev,docs]"]`,
which puts pytest and sphinx into every `pip install pkg[all]`. Someone
typing `[all]` wants all FEATURES, not the maintainer's toolchain.

Measured fleet-wide before the change (2026-08-11): 49 of 113 packages had
PS-221 findings; 426 of 449 came from `dev`/`docs`, 23 from real feature
extras. 95% noise at severity `E`, gating the umbrella release.

Every test builds a REAL temp `pyproject.toml` (no mocks, NM001-003).
One assert per test (STX-TQ007), Arrange/Act/Assert markers (STX-TQ002).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scitex_dev._cli.audit._project._check_extras_all_closure import (
    check_ps221_extras_all_closure,
)


@dataclass
class _StubViolation:
    rule: str
    where: str
    detail: str


def _run(repo: Path, body: str) -> list:
    """Write `body` as the repo's pyproject and return PS-221's findings."""
    repo.joinpath("pyproject.toml").write_text(body, encoding="utf-8")
    out: list = []
    check_ps221_extras_all_closure(repo, _StubViolation, out)
    return out


def test_dev_extra_not_closed_under_all_is_not_a_violation(tmp_path):
    # Arrange — pytest lives only in `dev`; `all` does not cover it. Before
    # this change that was one PS-221 error per uncovered dev requirement.
    body = (
        '[project]\nname = "scitex-fake"\ndependencies = ["numpy>=1.0"]\n'
        "[project.optional-dependencies]\n"
        'dev = ["pytest>=8.0", "pytest-cov>=5.0"]\n'
        'viz = ["matplotlib>=3.0"]\n'
        'all = ["matplotlib>=3.0"]\n'
    )
    # Act
    found = _run(tmp_path, body)
    # Assert
    assert found == []


def test_docs_extra_not_closed_under_all_is_not_a_violation(tmp_path):
    # Arrange — sphinx in `docs` only; `[all]` must not drag it in.
    body = (
        '[project]\nname = "scitex-fake"\ndependencies = ["numpy>=1.0"]\n'
        "[project.optional-dependencies]\n"
        'docs = ["sphinx>=7.0"]\n'
        'viz = ["matplotlib>=3.0"]\n'
        'all = ["matplotlib>=3.0"]\n'
    )
    # Act
    found = _run(tmp_path, body)
    # Assert
    assert found == []


def test_a_feature_extra_still_fires_alongside_exempt_tooling(tmp_path):
    # Arrange — POSITIVE CONTROL. The three tests above pass both when the
    # exemption works and when the rule stopped firing entirely; on their
    # own they cannot tell "dev/docs exempted" from "PS-221 broken". Here a
    # real FEATURE requirement is uncovered in the same file, so the rule
    # must still report exactly it.
    body = (
        '[project]\nname = "scitex-fake"\ndependencies = ["numpy>=1.0"]\n'
        "[project.optional-dependencies]\n"
        'dev = ["pytest>=8.0"]\n'
        'docs = ["sphinx>=7.0"]\n'
        'viz = ["matplotlib>=3.0", "seaborn>=0.12"]\n'
        'all = ["seaborn>=0.12"]\n'
    )
    # Act
    found = _run(tmp_path, body)
    # Assert
    assert [v.rule for v in found] == ["PS-221"]


def test_the_surviving_finding_names_the_feature_dep_not_a_tooling_one(tmp_path):
    # Arrange — same file; the detail must point at matplotlib, never at
    # pytest or sphinx. A rule that exempts the class but still blames it in
    # prose would send the reader to fix the wrong extra.
    body = (
        '[project]\nname = "scitex-fake"\ndependencies = ["numpy>=1.0"]\n'
        "[project.optional-dependencies]\n"
        'dev = ["pytest>=8.0"]\n'
        'docs = ["sphinx>=7.0"]\n'
        'viz = ["matplotlib>=3.0"]\n'
        'all = []\n'
    )
    # Act
    detail = " ".join(v.detail for v in _run(tmp_path, body))
    # Assert
    assert "matplotlib" in detail and "pytest" not in detail


def test_a_package_whose_only_extras_are_tooling_needs_no_all_group(tmp_path):
    # Arrange — with dev/docs exempt there are no public FEATURE extras, so
    # the "offers public extras but no `[all]` umbrella" arm must not fire
    # either. Forcing `[all]` on a package that ships only a toolchain is
    # the same mis-scoping one step up.
    body = (
        '[project]\nname = "scitex-fake"\ndependencies = ["numpy>=1.0"]\n'
        "[project.optional-dependencies]\n"
        'dev = ["pytest>=8.0"]\n'
        'docs = ["sphinx>=7.0"]\n'
    )
    # Act
    found = _run(tmp_path, body)
    # Assert
    assert found == []


def test_missing_all_group_still_fires_when_a_feature_extra_exists(tmp_path):
    # Arrange — second POSITIVE CONTROL, for the arm above: add one feature
    # extra and the missing-`[all]` error must return. Otherwise the
    # previous test is indistinguishable from having disabled that arm.
    body = (
        '[project]\nname = "scitex-fake"\ndependencies = ["numpy>=1.0"]\n'
        "[project.optional-dependencies]\n"
        'dev = ["pytest>=8.0"]\n'
        'viz = ["matplotlib>=3.0"]\n'
    )
    # Act
    found = _run(tmp_path, body)
    # Assert
    assert [v.rule for v in found] == ["PS-221"]


# EOF
