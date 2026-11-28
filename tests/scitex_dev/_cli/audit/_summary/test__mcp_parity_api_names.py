"""`_python_api_names` counts one operation once across flat + nested exports.

A real importable package is written to `tmp_path`; a subprocess with that
directory as cwd reads the names the way §6 reads them (no mocks).
"""

from __future__ import annotations

import json
import subprocess
import sys

_INIT = (
    "from . import descriptive\n"
    "from .descriptive import describe\n"
    "def run_test():\n"
    "    return None\n"
    "__all__ = ['descriptive', 'describe', 'run_test']\n"
)
_NESTED = (
    "def describe():\n"
    "    return None\n"
    "def nested_only():\n"
    "    return None\n"
    "__all__ = ['describe', 'nested_only']\n"
)
_PROBE = (
    "import json\n"
    "from scitex_dev._cli.audit._summary._mcp_parity import _python_api_names\n"
    "print(json.dumps(sorted(_python_api_names('scitex-names-fixture'))))\n"
)


def _names(tmp_path) -> set[str]:
    root = tmp_path / "scitex_names_fixture"
    root.mkdir()
    (root / "__init__.py").write_text(_INIT)
    (root / "descriptive.py").write_text(_NESTED)
    out = subprocess.run(
        [sys.executable, "-c", _PROBE],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    return set(json.loads(out.stdout))


def test_function_exported_flat_and_nested_is_counted_once(tmp_path):
    # Arrange
    root = tmp_path
    # Act
    names = _names(root)
    # Assert
    assert "descriptive_describe" not in names


def test_nested_only_function_is_still_counted(tmp_path):
    # Arrange
    root = tmp_path
    # Act
    names = _names(root)
    # Assert
    assert names == {"describe", "run_test", "descriptive_nested_only"}
