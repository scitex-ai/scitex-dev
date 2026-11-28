"""§6 parity ratchet, exercised through REAL `audit-mcp-tools` runs.

Each test builds a real importable package with a real FastMCP server in
`tmp_path`, then runs the installed auditor as a subprocess (cwd = the
fixture tree, so the package imports from there). No mocks: the exit
code and the printed findings are what a CI job would see.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

PACKAGE = "scitex-ratchet-fixture"
BASELINE = Path(".scitex") / "dev" / "mcp-parity-baseline.yaml"

_SERVER = (
    "from fastmcp import FastMCP\n"
    "mcp = FastMCP('scitex-ratchet-fixture')\n"
    "{tools}"
    "@mcp.tool()\n"
    "def skills_list() -> str:\n"
    "    return '[]'\n"
    "@mcp.tool()\n"
    "def skills_get(name: str = '') -> str:\n"
    "    return ''\n"
)
_TOOL = "@mcp.tool()\ndef {name}() -> str:\n    return 'ok'\n"


def _build(root: Path, apis: list[str], tools: list[str]) -> None:
    """(Re)write the fixture package: public `apis`, MCP `tools`."""
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "{PACKAGE}"\nversion = "0.0.0"\n'
    )
    pkg = root / "scitex_ratchet_fixture"
    (pkg / "_mcp").mkdir(parents=True, exist_ok=True)
    body = "".join(f"def {a}():\n    return None\n" for a in apis)
    (pkg / "__init__.py").write_text(body + f"__all__ = {apis!r}\n")
    server = _SERVER.format(tools="".join(_TOOL.format(name=t) for t in tools))
    (pkg / "_mcp" / "__init__.py").write_text(server)


def _audit(root: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "scitex_dev",
            "ecosystem",
            "audit-mcp-tools",
            PACKAGE,
            "--path",
            str(root),
            *extra,
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _apis() -> list[str]:
    return ["read_status", "write_status", "list_items"]


def test_without_baseline_the_majority_gap_fails(tmp_path):
    # Arrange
    _build(tmp_path, _apis(), ["read_status"])
    # Act
    result = _audit(tmp_path)
    # Assert
    assert (
        result.returncode,
        "2/3 Python APIs have no matching MCP tool" in result.stderr,
    ) == (1, True)


def test_write_parity_baseline_records_exactly_the_missing_apis(tmp_path):
    # Arrange
    _build(tmp_path, _apis(), ["read_status"])
    # Act
    _audit(tmp_path, "--write-parity-baseline")
    # Assert
    recorded = yaml.safe_load((tmp_path / BASELINE).read_text())
    assert recorded == {
        "version": 1,
        "missing_mcp_tools": ["list_items", "write_status"],
    }


def test_recorded_backlog_passes_and_prints_its_count(tmp_path):
    # Arrange
    _build(tmp_path, _apis(), ["read_status"])
    _audit(tmp_path, "--write-parity-baseline")
    # Act
    result = _audit(tmp_path)
    # Assert
    assert (result.returncode, "§6 parity backlog 2/3" in result.stderr) == (0, True)


def test_new_api_without_tool_fails_against_baseline(tmp_path):
    # Arrange
    _build(tmp_path, _apis(), ["read_status"])
    _audit(tmp_path, "--write-parity-baseline")
    _build(tmp_path, _apis() + ["delete_item"], ["read_status"])
    # Act
    result = _audit(tmp_path)
    # Assert
    assert (result.returncode, "not in the parity baseline" in result.stderr) == (
        1,
        True,
    )


def test_closed_gap_must_be_removed_from_baseline(tmp_path):
    # Arrange
    _build(tmp_path, _apis(), ["read_status"])
    _audit(tmp_path, "--write-parity-baseline")
    _build(tmp_path, _apis(), ["read_status", "write_status"])
    # Act
    result = _audit(tmp_path)
    # Assert
    assert (result.returncode, "['write_status'] — delete them" in result.stderr) == (
        1,
        True,
    )


def test_shrunk_baseline_passes_after_entry_removed(tmp_path):
    # Arrange
    _build(tmp_path, _apis(), ["read_status"])
    _audit(tmp_path, "--write-parity-baseline")
    _build(tmp_path, _apis(), ["read_status", "write_status"])
    (tmp_path / BASELINE).write_text(
        yaml.safe_dump({"version": 1, "missing_mcp_tools": ["list_items"]})
    )
    # Act
    result = _audit(tmp_path)
    # Assert
    assert (result.returncode, "§6 parity backlog 1/3" in result.stderr) == (0, True)


def test_malformed_baseline_fails_loudly(tmp_path):
    # Arrange
    _build(tmp_path, _apis(), ["read_status"])
    (tmp_path / BASELINE).parent.mkdir(parents=True)
    (tmp_path / BASELINE).write_text("missing_mcp_tools: not-a-list\n")
    # Act
    result = _audit(tmp_path)
    # Assert
    assert (result.returncode, "malformed parity baseline" in result.stderr) == (
        1,
        True,
    )
