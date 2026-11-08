"""Only an explicit opt-out may permit omission of a real audit gate."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from scitex_dev._cli.ecosystem._cmds._gate_guard import render_conftest

FLAG = "SCITEX_DEV_ALLOW_PARTIAL_RUN"
NON_OPT_OUTS = [
    {},
    {FLAG: ""},
    {FLAG: "0"},
    {FLAG: "false"},
    {FLAG: "off"},
    {FLAG: "no"},
    {FLAG: "true"},
    {FLAG: "yes"},
]


def _partial_run(tmp_path: Path, overrides: dict[str, str]):
    root = tmp_path / "owned-package"
    unit = root / "tests" / "unit"
    gate = root / "tests" / "develop" / "test_audit.py"
    unit.mkdir(parents=True)
    gate.parent.mkdir()
    (root / "pytest.ini").write_text("[pytest]\ntestpaths = tests\n")
    (root / "tests" / "conftest.py").write_text(render_conftest(None)[0])
    gate.write_text(
        "from pathlib import Path\n"
        "from scitex_dev.testing import audit_all_for_package\n"
        "ROOT = Path(__file__).resolve().parents[2]\n"
        "(ROOT / 'gate-imported.marker').touch()\n"
        "def test_audit_all_clean():\n"
        "    audit_all_for_package('scitex-dev', path=ROOT)\n"
    )
    (unit / "test_file.py").write_text(
        "from pathlib import Path\n"
        "def test_owned_file_roundtrip():\n"
        "    path = Path('unit-evidence.bin')\n"
        "    path.write_bytes(b'owned real file roundtrip')\n"
        "    assert path.read_bytes() == b'owned real file roundtrip'\n"
    )
    env = {
        k: v
        for k, v in os.environ.items()
        if k
        not in (
            "SCITEX_DEV_SKIP_AUDIT",
            FLAG,
            "PYTEST_ADDOPTS",
        )
    }
    env.update(overrides)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/unit", "-q"],
        check=False,
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return {
        "unit_ran": (root / "unit-evidence.bin").read_bytes()
        == b"owned real file roundtrip",
        "gate_omitted": not (root / "gate-imported.marker").exists(),
        "one_test_reported": "1 passed" in result.stdout,
        "exit": result.returncode,
        "missing_gate_reported": "AUDIT GATE DID NOT RUN" in result.stdout,
    }


@pytest.mark.parametrize("overrides", NON_OPT_OUTS)
def test_false_values_keep_the_omitted_gate_failure(tmp_path, overrides):
    # Arrange
    expected = {
        "unit_ran": True,
        "gate_omitted": True,
        "one_test_reported": True,
        "exit": 1,
        "missing_gate_reported": True,
    }
    # Act
    observed = _partial_run(tmp_path, overrides)
    # Assert
    assert observed == expected


def test_literal_one_explicitly_allows_a_partial_run(tmp_path):
    # Arrange
    expected = {
        "unit_ran": True,
        "gate_omitted": True,
        "one_test_reported": True,
        "exit": 0,
        "missing_gate_reported": False,
    }
    # Act
    observed = _partial_run(tmp_path, {FLAG: "1"})
    # Assert
    assert observed == expected
