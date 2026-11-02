"""Owned source fixtures shared by interface and hook contract tests."""

import pytest


@pytest.fixture
def package(tmp_path):
    """Write an import-hostile package with real thin interface bindings."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "pyproject.toml").write_text("""[project]
name = "branded-demo"
version = "1.0.0"
[project.scripts]
demo = "branded_demo.cli:main"
[project.entry-points."scitex.apis"]
demo = "branded_demo.web:plugin"
[project.entry-points."scitex_dev.skills"]
branded-demo = "branded_demo"
""")
    source = root / "src" / "branded_demo"
    source.mkdir(parents=True)
    (source / "__init__.py").write_text(
        'raise RuntimeError("AUDIT MUST NOT IMPORT THIS PACKAGE")\nfrom .api import echo\n__all__ = ["echo"]\n'
    )
    (source / "api.py").write_text("def echo(value):\n    return value\n")
    (source / "cli.py").write_text(
        "from .api import echo\ndef main():\n    return echo(1)\n"
    )
    (source / "_mcp_server.py").write_text(
        'from fastmcp import FastMCP\nfrom .api import echo\nmcp = FastMCP("demo")\n@mcp.tool()\ndef echo_tool(value):\n    return echo(value)\n'
    )
    (source / "web.py").write_text(
        'from scitex_sdk.app.api_plugin import ApiPlugin\nplugin = ApiPlugin(name="demo")\n'
    )
    skills = source / "_skills" / "branded-demo"
    skills.mkdir(parents=True)
    (skills / "SKILL.md").write_text(
        "# Branded Demo\n\nCall echo(value) to return the supplied value. Use demo --help for CLI discovery.\n"
    )
    return root
