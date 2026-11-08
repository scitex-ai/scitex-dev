"""False opt-outs must still dispatch the real native audit command."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

FLAG = "SCITEX_DEV_SKIP_AUDIT"
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


def _run_real_audit(tmp_path: Path, overrides: dict[str, str]):
    missing = tmp_path / "owned-missing-project"
    env = {k: v for k, v in os.environ.items() if k != FLAG}
    env.update(overrides)
    code = (
        "import sys\nfrom pathlib import Path\n"
        "from scitex_dev.testing import audit_all_for_package\n"
        "audit_all_for_package('scitex-dev', path=Path(sys.argv[1]))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code, str(missing)],
        check=False,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return missing, result


@pytest.mark.parametrize("overrides", NON_OPT_OUTS)
def test_false_values_preserve_real_unknown_audit_failure(tmp_path, overrides):
    # Arrange
    expected = {"exit": 1, "real_unknown": True, "owned_path": True, "skipped": False}
    # Act
    missing, result = _run_real_audit(tmp_path, overrides)
    observed = {
        "exit": result.returncode,
        "real_unknown": "AssertionError: audit-all COULD NOT RUN" in result.stderr,
        "owned_path": str(missing) in result.stderr,
        "skipped": "Skipped: audit-all skipped" in result.stderr,
    }
    # Assert
    assert observed == expected


def test_literal_one_preserves_explicit_skip_result(tmp_path):
    # Arrange
    expected = {"exit": 1, "explicit_skip": True, "real_unknown": False}
    # Act
    _, result = _run_real_audit(tmp_path, {FLAG: "1"})
    observed = {
        "exit": result.returncode,
        "explicit_skip": "Skipped: audit-all skipped via SCITEX_DEV_SKIP_AUDIT=1"
        in result.stderr,
        "real_unknown": "audit-all COULD NOT RUN" in result.stderr,
    }
    # Assert
    assert observed == expected
