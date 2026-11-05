"""The actual backend must ship the source-owned CLI dictionary."""

import subprocess
import sys
from pathlib import Path


def test_backend_copies_the_canonical_dictionary_to_the_installable_package(tmp_path):
    # Arrange
    root = Path(__file__).resolve().parents[2]
    target = tmp_path / "build" / "scitex_dev" / "_cli_audit_dict.yaml"
    canonical = root / ".scitex" / "dev" / "cli-audit-dict.yaml"
    # Act
    built = subprocess.run(
        [
            sys.executable,
            "-c",
            "from setuptools import setup; setup()",
            "egg_info",
            "--egg-base",
            str(tmp_path),
            "build_py",
            "--build-lib",
            str(tmp_path / "build"),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    # Assert
    assert (built.returncode, target.read_bytes() if target.exists() else None) == (
        0,
        canonical.read_bytes(),
    )
