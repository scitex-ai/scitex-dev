"""Core dependencies already cover optional imports in a dev installation."""

from pathlib import Path

import pytest

from scitex_dev._cli.audit._project._check_dev_extras_complete import (
    check_dev_extras_complete,
)
from scitex_dev._cli.audit._project._violation import Violation


@pytest.mark.parametrize(
    "core",
    (
        '"scitex-logging==0.2.4"',
        '"SCITEX-Logging[all]>=0.2.4"',
        "'scitex-logging; python_version >= \"3.9\"'",
    ),
)
def test_core_logging_does_not_need_a_duplicate_dev_entry(tmp_path: Path, core: str):
    # Arrange
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="owned-package"\ndependencies=[' + core + "]\n"
        '[project.optional-dependencies]\nall=["scitex-logging==0.2.4"]\n'
        'dev=["pytest"]\n'
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_owned.py").write_text(
        "from scitex_logging import getLogger\n"
    )
    findings = []
    # Act
    check_dev_extras_complete(tmp_path, Violation, findings)
    # Assert
    assert findings == []


def test_an_optional_only_unguarded_dependency_still_requires_dev(tmp_path: Path):
    # Arrange
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="owned-package"\ndependencies=[]\n'
        '[project.optional-dependencies]\nall=["scitex-logging==0.2.4"]\n'
        'dev=["pytest"]\n'
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_owned.py").write_text(
        "from scitex_logging import getLogger\n"
    )
    findings = []
    # Act
    check_dev_extras_complete(tmp_path, Violation, findings)
    # Assert
    assert [finding.rule for finding in findings] == ["PS-210"]
