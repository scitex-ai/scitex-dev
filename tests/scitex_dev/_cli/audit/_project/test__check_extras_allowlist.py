# -*- coding: utf-8 -*-
"""PS-225 must flag every extra name outside {all, dev, docs}, and nothing else.

Each test asserts one thing. The negative direction is covered explicitly:
a conforming pyproject must produce ZERO findings, because a rule that fires
on everything is indistinguishable from a rule that fires on nothing.
"""

from pathlib import Path

import pytest

from scitex_dev._cli.audit._project._check_extras_allowlist import (
    ALLOWED_EXTRAS,
    check_ps225_extras_allowlist,
)
from scitex_dev._cli.audit._project._violation import Violation


def _write(tmp_path: Path, body: str) -> Path:
    (tmp_path / "pyproject.toml").write_text(body, encoding="utf-8")
    return tmp_path


CONFORMING = """
[project]
name = "demo"
[project.optional-dependencies]
dev = ["pytest"]
docs = ["sphinx"]
all = ["demo[dev,docs]"]
"""

WITH_MCP = """
[project]
name = "demo"
[project.optional-dependencies]
mcp = ["fastmcp"]
dev = ["pytest"]
all = ["demo[mcp,dev]"]
"""

THE_OUTAGE_SHAPE = """
[project]
name = "scitex-cards"
[project.optional-dependencies]
mcp = ["fastmcp"]
postgres = ["psycopg[binary]>=3.1"]
web = ["django>=4.2"]
currency = ["requests"]
dev = ["pytest"]
docs = ["sphinx"]
all = ["scitex-cards[mcp,postgres,web,currency,dev,docs]"]
"""


def test_conforming_pyproject_produces_no_findings(tmp_path):
    # Arrange
    repo = _write(tmp_path, CONFORMING)

    # Act
    out: list = []
    check_ps225_extras_allowlist(repo, Violation, out)

    # Assert
    assert out == []


def test_a_per_feature_extra_is_flagged(tmp_path):
    # Arrange
    repo = _write(tmp_path, WITH_MCP)

    # Act
    out: list = []
    check_ps225_extras_allowlist(repo, Violation, out)

    # Assert
    assert len(out) == 1


def test_the_flagged_name_is_the_offender_not_a_neighbour(tmp_path):
    # Arrange
    repo = _write(tmp_path, WITH_MCP)

    # Act
    out: list = []
    check_ps225_extras_allowlist(repo, Violation, out)

    # Assert
    assert "optional-dependencies.mcp" in out[0].detail


def test_every_offender_gets_its_own_finding(tmp_path):
    # Arrange — the exact shape scitex-cards shipped when the board went down
    repo = _write(tmp_path, THE_OUTAGE_SHAPE)

    # Act
    out: list = []
    check_ps225_extras_allowlist(repo, Violation, out)

    # Assert
    assert len(out) == 4


def test_dev_docs_and_all_are_never_flagged(tmp_path):
    # Arrange
    repo = _write(tmp_path, THE_OUTAGE_SHAPE)

    # Act
    out: list = []
    check_ps225_extras_allowlist(repo, Violation, out)
    flagged = {v.detail.split("optional-dependencies.")[1].split("`")[0] for v in out}

    # Assert
    assert flagged.isdisjoint(ALLOWED_EXTRAS)


def test_a_package_with_no_extras_at_all_is_clean(tmp_path):
    # Arrange
    repo = _write(tmp_path, '[project]\nname = "demo"\n')

    # Act
    out: list = []
    check_ps225_extras_allowlist(repo, Violation, out)

    # Assert
    assert out == []


def test_a_missing_pyproject_does_not_raise(tmp_path):
    # Arrange
    repo = tmp_path

    # Act
    out: list = []
    check_ps225_extras_allowlist(repo, Violation, out)

    # Assert
    assert out == []


def test_unparseable_pyproject_does_not_raise(tmp_path):
    # Arrange
    repo = _write(tmp_path, "this is not = valid toml [[[")

    # Act
    out: list = []
    check_ps225_extras_allowlist(repo, Violation, out)

    # Assert
    assert out == []


@pytest.mark.parametrize("name", sorted(ALLOWED_EXTRAS))
def test_each_allowlisted_name_alone_is_clean(tmp_path, name):
    # Arrange
    repo = _write(
        tmp_path,
        f'[project]\nname = "demo"\n'
        f'[project.optional-dependencies]\n{name} = ["x"]\n',
    )

    # Act
    out: list = []
    check_ps225_extras_allowlist(repo, Violation, out)

    # Assert
    assert out == []


# EOF
