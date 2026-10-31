"""PS-207 inspects source mirrors without walking volatile test output."""

import os
from pathlib import Path

from scitex_dev._cli.audit._project._checks import _check_empty_test_dirs


def test_empty_mirror_audit_ignores_unreadable_test_results(tmp_path, monkeypatch):
    # Arrange
    source = tmp_path / "src/scitex_demo/feature"
    source.mkdir(parents=True)
    (source / "implementation.py").write_text("VALUE = 1\n")
    mirror = tmp_path / "tests/scitex_demo/feature"
    mirror.mkdir(parents=True)
    results = tmp_path / "tests/results/live-profile"
    results.mkdir(parents=True)
    scan = os.scandir

    def guarded_scandir(path):
        if Path(path) == results.parent:
            raise FileNotFoundError("concurrent runtime fixture removed")
        return scan(path)

    monkeypatch.setattr(os, "scandir", guarded_scandir)
    violations = []
    # Act
    _check_empty_test_dirs(tmp_path, "scitex-demo", violations)
    # Assert
    assert [(v.rule, v.where) for v in violations] == [("PS-207", str(mirror))]
