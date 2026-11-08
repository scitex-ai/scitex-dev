"""Generated gates must inspect their Python environment, not shell PATH."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from scitex_dev._cli.ecosystem._cmds._gate_guard import render_conftest
from scitex_dev._cli.ecosystem._cmds._install_gate import render_audit_gate

SYSTEM_PATH = os.defpath
CONSOLE_PATH = os.pathsep.join((str(Path(sys.executable).parent), SYSTEM_PATH))


def _run_generated_gate(tmp_path, path, extra_env):
    project = tmp_path / "owned-invalid-project"
    gate = project / "tests" / "develop" / "test_audit.py"
    gate.parent.mkdir(parents=True)
    (project / "pyproject.toml").write_text(
        '[project]\nname = "scitex-dev"\nversion = "0.0.0"\n'
    )
    (project / "pytest.ini").write_text("[pytest]\ntestpaths = tests\n")
    gate.write_text(render_audit_gate("scitex-dev", gate, project))
    (project / "tests" / "conftest.py").write_text(render_conftest(None)[0])
    home = project / "home"
    home.mkdir()
    env = {
        key: os.environ[key]
        for key in ("LANG", "LC_ALL", "SSL_CERT_FILE", "SSL_CERT_DIR")
        if key in os.environ
    }
    env.update(PATH=path, HOME=str(home), SCITEX_DIR=str(project / "scitex"))
    env.update(extra_env)
    report = project / "results.xml"
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-m",
            "pytest",
            "-q",
            "-rs",
            "--junitxml=" + str(report),
            str(gate),
        ],
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    document = ET.parse(report).getroot()
    skips = document.findall(".//skipped")
    failures = document.findall(".//failure")
    failure_text = "\n".join("".join(node.itertext()) for node in failures)
    return {
        "console_found": shutil.which("scitex-dev", path=path) is not None,
        "exit": result.returncode,
        "skipped": len(skips),
        "real_audit_failure": "audit-all reported violations" in failure_text
        or "audit-all COULD NOT RUN" in failure_text,
        "explicit_opt_out": any(
            "audit-all skipped via SCITEX_DEV_SKIP_AUDIT=1" in node.get("message", "")
            for node in skips
        ),
    }


@pytest.mark.parametrize(
    "path,console_found", [(CONSOLE_PATH, True), (SYSTEM_PATH, False)]
)
def test_installed_module_runs_the_real_gate_without_a_console_script(
    tmp_path, path, console_found
):
    # Arrange
    expected = {
        "console_found": console_found,
        "exit": 1,
        "skipped": 0,
        "real_audit_failure": True,
        "explicit_opt_out": False,
    }
    # Act
    observed = _run_generated_gate(tmp_path, path, {})
    # Assert
    assert observed == expected


def test_missing_console_preserves_the_explicit_local_opt_out(tmp_path):
    # Arrange
    expected = {
        "console_found": False,
        "exit": 0,
        "skipped": 1,
        "real_audit_failure": False,
        "explicit_opt_out": True,
    }
    # Act
    observed = _run_generated_gate(
        tmp_path, SYSTEM_PATH, {"SCITEX_DEV_SKIP_AUDIT": "1"}
    )
    # Assert
    assert observed == expected
