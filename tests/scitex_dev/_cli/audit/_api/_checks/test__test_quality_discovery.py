"""Exercise PA-307 discovery against real Git ignore rules and source files."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import scitex_dev


def _write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def source_tree(tmp_path: Path) -> Path:
    """Keep tracked and untracked first-party failures beside ignored caches."""
    root = tmp_path / "project"
    bad_test = "def test_addition_has_result():\n    print(1)\n"
    bad_fixture = (
        "import pytest\n\n@pytest.fixture\n"
        "def resource():\n    return open('input.txt')\n"
    )
    _write(root, "src/example/__init__.py", "")
    _write(root, "tests/test_tracked.py", bad_test)
    _write(root, "tests/test_untracked.py", bad_test)
    _write(root, "conftest.py", bad_fixture)
    _write(root, "checks/conftest.py", bad_fixture)
    _write(root, "tests/selected/test_keep.py", bad_test)
    _write(root, "tests/selected/test_ignored.py", bad_test)
    _write(root, "tests/selected/.gitignore", "*.py\n!test_keep.py\n")
    _write(root, "GITIGNORED/uv/archive/pandas/tests/io/conftest.py", bad_fixture)
    _write(root, ".hidden/conftest.py", bad_fixture)
    _write(root, "tests/.hidden/test_archived.py", bad_test)
    _write(root, ".gitignore", "GITIGNORED/\n")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(
        ["git", "-C", str(root), "add", "tests/test_tracked.py"], check=True
    )
    return root


def _audit_source_tree(
    source_tree: Path, tmp_path: Path, force_fallback: bool
) -> tuple[list[str], bool]:
    env = dict(os.environ)
    source = str(Path(scitex_dev.__file__).resolve().parent.parent)
    # Native CI installs dependencies in a job-owned --target directory.
    # Preserve that import path when selecting this checkout in the child.
    env["PYTHONPATH"] = os.pathsep.join(
        [source, *filter(None, env.get("PYTHONPATH", "").split(os.pathsep))]
    )
    if force_fallback:
        binary_dir = tmp_path / "bin"
        binary_dir.mkdir()
        (binary_dir / "git").symlink_to(shutil.which("git"))
        env["PATH"] = str(binary_dir)
    program = """
import json
import sys
from pathlib import Path
from scitex_dev._cli.audit._api._checks._test_quality import _audit_test_quality
root = Path(sys.argv[1])
findings = _audit_test_quality(
    root / 'src/example/__init__.py', 'example', 'example', repo_root=root
)
print(json.dumps(sorted({item.where.split(': ')[1].rsplit(':', 1)[0]
                         for item in findings})))
"""
    try:
        result = subprocess.run(
            [sys.executable, "-c", program, str(source_tree)],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"Source discovery child failed ({exc.returncode}):\n"
            f"stdout: {exc.stdout}\nstderr: {exc.stderr}"
        ) from exc
    return (
        json.loads(result.stdout),
        not force_fallback or "falling back to the stdlib scan" in result.stderr,
    )


def _expected_findings() -> tuple[list[str], bool]:
    return (
        [
            "checks/conftest.py",
            "conftest.py",
            "tests/selected/test_keep.py",
            "tests/test_tracked.py",
            "tests/test_untracked.py",
        ],
        True,
    )


def test_quality_discovery_preserves_source_and_excludes_cache(source_tree, tmp_path):
    # Arrange
    expected = _expected_findings()
    # Act
    observed = _audit_source_tree(source_tree, tmp_path, False)
    # Assert
    assert observed == expected


def test_quality_fallback_preserves_source_and_excludes_cache(source_tree, tmp_path):
    # Arrange
    expected = _expected_findings()
    # Act
    observed = _audit_source_tree(source_tree, tmp_path, True)
    # Assert
    assert observed == expected
