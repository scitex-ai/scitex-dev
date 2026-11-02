"""Exercise the actual native worker policy under real process affinity."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / ".github/ci/run-in-sif.sh"


def worker_policy():
    """Extract the shipped shell block, including its actual Python command."""
    source = SCRIPT.read_text()
    return source[
        source.index("# Parallelise with pytest-xdist"):
        source.index("# Warm the matplotlib")
    ]


@pytest.mark.parametrize("configured,one_cpu", [
    ("", False), ("1", False), ("3", False), ("4", False), ("4", True),
])
def test_native_workers_respect_job_budget_and_actual_affinity(configured, one_cpu):
    # Arrange: this child changes only its own kernel CPU affinity.
    script = worker_policy() + '\nprintf "worker-result:%s\\n" "$WORKERS"\n'
    launcher = """import os,sys
if sys.argv[1] == 'one':
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
os.execv('/bin/bash', ['/bin/bash', '-ec', sys.argv[2]])
"""
    env = {
        "PATH": os.defpath,
        "VENV": str(Path(sys.executable).parent.parent),
        "CI_XDIST_WORKERS": configured,
    }
    allowed = 1 if one_cpu else len(os.sched_getaffinity(0))
    # Act
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-c", launcher,
         "one" if one_cpu else "all", script],
        env=env, capture_output=True, text=True, timeout=5,
    )
    value = (
        int(result.stdout.rsplit("worker-result:", 1)[1].strip())
        if result.returncode == 0 else None
    )
    # Assert: the old all-core/minimum-four policy violates both boundaries.
    assert (result.returncode == 0 and value is not None and
            1 <= value <= min(4, allowed, int(configured or "4"))), result.stderr


@pytest.mark.parametrize("configured", ["0", "-1", "auto", "5", "４", "4;touch forbidden"])
def test_native_worker_budget_rejects_invalid_configuration(configured):
    # Arrange
    env = {
        "PATH": os.defpath,
        "VENV": str(Path(sys.executable).parent.parent),
        "CI_XDIST_WORKERS": configured,
    }
    # Act
    result = subprocess.run(
        ["/bin/bash", "-ec", worker_policy()], env=env,
        capture_output=True, text=True, timeout=5,
    )
    # Assert
    assert result.returncode != 0 and "CI_XDIST_WORKERS" in result.stderr
