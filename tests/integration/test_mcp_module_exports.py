"""Discover actual FastMCP exports across supported package layouts."""

import json
import subprocess
import sys

import pytest


SERVER = (
    "from fastmcp import FastMCP\n"
    "mcp = FastMCP({name!r})\n"
    "@mcp.tool()\n"
    "def fixture_read_status() -> str:\n"
    "    \"\"\"Return fixture status.\"\"\"\n"
    "    return 'ready'\n"
)

PROBE = (
    "import json\n"
    "from scitex_dev._cli.audit._summary._mcp_bridge import _resolve_mcp_server\n"
    "from scitex_dev._ecosystem._mcp import get_tools_sync\n"
    "server = _resolve_mcp_server('scitex-discovery-fixture')\n"
    "print(json.dumps({'name': server.name if server else None, "
    "'tools': sorted(get_tools_sync(server)) if server else []}))\n"
)


LAZY_EXPORT = ('def __getattr__(name):\n'
 "    if name == 'mcp':\n"
 '        from .._server import mcp\n'
 '        return mcp\n'
 '    raise AttributeError(name)\n')

OPTIONAL_EXPORT = ('def __getattr__(name):\n'
 "    if name == 'mcp':\n"
 "        raise ImportError('Optional fixture dependency is unavailable')\n"
 '    raise AttributeError(name)\n')

EXIT_EXPORT = ('def __getattr__(name):\n'
 "    if name == 'mcp':\n"
 '        raise SystemExit(2)\n'
 '    raise AttributeError(name)\n')

CASES = [
    pytest.param(
        {
            '_mcp_server.py': SERVER.format(name='legacy'),
        },
        {'name': 'legacy', 'tools': ['fixture_read_status']},
        id='legacy',
    ),
    pytest.param(
        {
            '_mcp/__init__.py': SERVER.format(name='private_root'),
        },
        {'name': 'private_root', 'tools': ['fixture_read_status']},
        id='private_root',
    ),
    pytest.param(
        {
            'mcp/__init__.py': SERVER.format(name='public_root'),
        },
        {'name': 'public_root', 'tools': ['fixture_read_status']},
        id='public_root',
    ),
    pytest.param(
        {
            '_server.py': SERVER.format(name='lazy_root'),
            '_mcp/__init__.py': LAZY_EXPORT,
        },
        {'name': 'lazy_root', 'tools': ['fixture_read_status']},
        id='lazy_root',
    ),
    pytest.param(
        {
            '_mcp_server.py': SERVER.format(name='legacy'),
            '_mcp/__init__.py': SERVER.format(name='private_root'),
        },
        {'name': 'legacy', 'tools': ['fixture_read_status']},
        id='legacy_before_roots',
    ),
    pytest.param(
        {
            '_mcp/__init__.py': 'mcp = object()\n',
        },
        {'name': None, 'tools': []},
        id='invalid_root',
    ),
    pytest.param(
        {
            '_mcp/__init__.py': OPTIONAL_EXPORT,
            'mcp/__init__.py': SERVER.format(name='public_fallback'),
        },
        {'name': 'public_fallback', 'tools': ['fixture_read_status']},
        id='lazy_import_error',
    ),
    pytest.param(
        {
            '_mcp/__init__.py': EXIT_EXPORT,
        },
        {'name': None, 'tools': []},
        id='lazy_system_exit',
    ),
]


@pytest.mark.parametrize(("modules", "expected"), CASES)
def test_mcp_module_export_discovery(tmp_path, modules, expected):
    # Arrange
    package = tmp_path / "scitex_discovery_fixture"
    package.mkdir()
    (package / "__init__.py").write_text("")
    for relative, content in modules.items():
        path = package / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    # Act
    result = subprocess.run(
        [sys.executable, "-c", PROBE],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    observed = json.loads(result.stdout)

    # Assert
    assert observed == expected
