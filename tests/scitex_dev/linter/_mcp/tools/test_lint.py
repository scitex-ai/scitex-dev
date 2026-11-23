#!/usr/bin/env python3
"""Tests for the linter MCP tools registration.

The module exports `register_lint_tools(mcp)` which the host MCP
server calls to attach lint-related tools. We exercise that
registration against a real in-process tool registry so that an
accidental rename or missing decoration trips the test.
"""

from __future__ import annotations

import pytest


class _RecordingMCP:
    """Tiny stand-in for a fastmcp server: records every tool registered.

    Real fastmcp's `@mcp.tool()` decorator returns a decorator; we
    mirror that shape so production code that uses `@mcp.tool()` lands
    its callables in our `tools` list.
    """

    def __init__(self) -> None:
        self.tools: list[str] = []

    def tool(self, *_args, **_kwargs):
        def _decorator(fn):
            self.tools.append(fn.__name__)
            return fn

        return _decorator


def test_register_lint_tools_attaches_at_least_one_tool():
    """Calling `register_lint_tools(mcp)` must register one or more
    tools on the passed MCP-like object. Catches the regression where
    the registration body becomes empty after a refactor."""
    # Arrange
    # Act
    # Assert
    from scitex_dev.linter._mcp.tools.lint import register_lint_tools

    mcp = _RecordingMCP()
    register_lint_tools(mcp)
    assert len(mcp.tools) > 0


@pytest.fixture
def _registered_lint_tool_names():
    from scitex_dev.linter._mcp.tools.lint import register_lint_tools

    mcp = _RecordingMCP()
    register_lint_tools(mcp)
    return list(mcp.tools)


def test_register_lint_tools_tool_names_are_lowercase(_registered_lint_tool_names):
    # Arrange
    names = _registered_lint_tool_names
    # Act
    lowered = [n == n.lower() for n in names]
    # Assert
    assert all(lowered)


def test_register_lint_tools_tool_names_contain_no_spaces(_registered_lint_tool_names):
    # Arrange
    names = _registered_lint_tool_names
    # Act
    has_space = [" " in n for n in names]
    # Assert
    assert not any(has_space)


def test_register_lint_tools_tool_names_are_python_identifiers(
    _registered_lint_tool_names,
):
    # Arrange
    names = _registered_lint_tool_names
    # Act
    valid = [n.isidentifier() for n in names]
    # Assert
    assert all(valid)


@pytest.fixture
def _owned_installed_skill_profile(tmp_path):
    import os

    values = {
        "SCITEX_DIR": str(tmp_path / "state"),
        "SCITEX_DEV_CONFIG": str(tmp_path / "absent.yaml"),
        "SCITEX_DEV_KNOB_STATE": str(tmp_path / "knobs.json"),
    }
    previous = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _call_registered_skill_tool(name, arguments):
    import asyncio
    import json

    from fastmcp import Client, FastMCP
    from scitex_dev.linter._mcp.tools import register_all_tools

    server = FastMCP("owned-linter-skill-regression")
    register_all_tools(server)

    async def invoke():
        async with Client(server) as client:
            return await client.call_tool(name, arguments)

    result = asyncio.run(invoke())
    structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict):
        return structured
    return json.loads("".join(block.text for block in result.content if block.type == "text"))


def test_mcp_skill_list_reads_actual_installed_linter_namespace(
    _owned_installed_skill_profile,
):
    # Arrange
    from scitex_dev._ecosystem._skills.skills import list_skills

    expected = list_skills(package="scitex-dev-linter")["scitex-dev-linter"]
    # Act
    result = _call_registered_skill_tool("linter_skills_list", {})
    # Assert
    assert (result["success"], result.get("skills")) == (True, expected)


def test_mcp_skill_get_matches_actual_installed_owner_content(
    _owned_installed_skill_profile,
):
    # Arrange
    from scitex_dev._ecosystem._skills.skills import get_skill

    expected = get_skill("scitex-dev-linter", "03_python-api", owner="scitex-dev")
    # Act
    result = _call_registered_skill_tool("linter_skills_get", {"name": "03_python-api"})
    # Assert
    assert (result["success"], result.get("content")) == (True, expected)


@pytest.fixture(params=["missing", "directory", "empty"])
def _unavailable_mcp_target(request, tmp_path):
    values = {"missing": str(tmp_path / "absent.py"), "directory": str(tmp_path), "empty": ""}
    return values[request.param]


def test_mcp_file_check_rejects_unavailable_target(_owned_installed_skill_profile, _unavailable_mcp_target):
    # Arrange
    from fastmcp.exceptions import ToolError

    # Act
    # Assert
    with pytest.raises(ToolError, match="Lint target"):
        _call_registered_skill_tool("linter_check", {"path": _unavailable_mcp_target})


@pytest.fixture(params=["python", "notebook", "markdown", "rst", "text"])
def _valid_mcp_file_case(request, tmp_path):
    import json
    from scitex_dev.linter.checker import lint_file
    from scitex_dev.linter.config import load_config
    from scitex_dev.linter.formatter import to_json

    code = 'import requests\nrequests.get("https://owned.invalid")\n'
    formats = {
        "python": (".py", code),
        "notebook": (".ipynb", json.dumps({"cells": [{"cell_type": "code", "source": code.splitlines(keepends=True)}], "metadata": {}, "nbformat": 4, "nbformat_minor": 5})),
        "markdown": (".md", "```python\n" + code + "```\n"),
        "rst": (".rst", ".. code-block:: python\n\n    import requests\n    requests.get(\"https://owned.invalid\")\n"),
        "text": (".txt", code),
    }
    suffix, content = formats[request.param]
    file = tmp_path / ("owned" + suffix)
    file.write_text(content)
    (tmp_path / "pyproject.toml").write_text('[tool.scitex-dev.linter]\nlibrary_dirs = ["."]\n')
    expected = to_json(lint_file(str(file), config=load_config(str(file))), str(file))
    info = file.stat()
    return file, expected, (file.read_bytes(), info.st_ino, info.st_mtime_ns)


def test_mcp_file_check_preserves_valid_dispatch_payload(_owned_installed_skill_profile, _valid_mcp_file_case):
    # Arrange
    file, expected, _ = _valid_mcp_file_case
    # Act
    result = _call_registered_skill_tool("linter_check", {"path": str(file)})
    # Assert
    assert (result, "STX-NET001" in [issue["rule_id"] for issue in result["issues"]]) == (expected, True)


def test_mcp_file_check_preserves_valid_file_bytes(_owned_installed_skill_profile, _valid_mcp_file_case):
    # Arrange
    file, _, before = _valid_mcp_file_case
    # Act
    _call_registered_skill_tool("linter_check", {"path": str(file)})
    info = file.stat()
    # Assert
    assert (file.read_bytes(), info.st_ino, info.st_mtime_ns) == before


@pytest.fixture(params=[(source, stdin) for source in ["def broken(\n", "if True print('bad')\n", "value = )\n", "pass\x00\n"] for stdin in [False, True]])
def _unparseable_mcp_source(request, tmp_path):
    source, stdin = request.param
    return source, "<stdin>" if stdin else str(tmp_path / "label.py")


def test_mcp_source_check_rejects_ast_parser_error(_owned_installed_skill_profile, _unparseable_mcp_source):
    # Arrange
    from fastmcp.exceptions import ToolError

    source, filepath = _unparseable_mcp_source
    # Act
    # Assert
    with pytest.raises(ToolError, match="Python source could not be parsed"):
        _call_registered_skill_tool("linter_check_source", {"source": source, "filepath": filepath})


def _source_label_state(files):
    result = []
    for file in files:
        if file.exists():
            info = file.stat()
            result.append((file.read_bytes(), info.st_ino, info.st_mtime_ns))
        else:
            result.append(None)
    return result


@pytest.fixture(params=[(source, label) for source in ["", "values = (\n 1,\n 2,\n)\n", 'import requests\nrequests.get("https://owned.invalid")\n', 'raise RuntimeError("source must not execute")\n', "await worker()\n"] for label in ["existing", "absent", "stdin"]])
def _parseable_mcp_source_case(request, tmp_path):
    from scitex_dev.linter.checker import lint_source
    from scitex_dev.linter.config import load_config
    from scitex_dev.linter.formatter import to_json

    source, label = request.param
    file = tmp_path / "label.py"
    if label == "existing":
        file.write_text("UNRELATED_LABEL_CONTENT = True\n")
    config = tmp_path / "pyproject.toml"
    config.write_text('[tool.scitex-dev.linter]\nlibrary_dirs = ["."]\n')
    filepath = "<stdin>" if label == "stdin" else str(file)
    expected = to_json(lint_source(source, filepath=filepath, config=load_config(filepath)), filepath)
    files = [config, file]
    return source, filepath, expected, files, _source_label_state(files)


def test_mcp_parseable_source_preserves_issue_payload(_owned_installed_skill_profile, _parseable_mcp_source_case):
    # Arrange
    source, filepath, expected, _, _ = _parseable_mcp_source_case
    # Act
    result = _call_registered_skill_tool("linter_check_source", {"source": source, "filepath": filepath})
    # Assert
    assert result == expected


def test_mcp_parseable_source_does_not_write_label_or_config(_owned_installed_skill_profile, _parseable_mcp_source_case):
    # Arrange
    source, filepath, _, files, before = _parseable_mcp_source_case
    # Act
    _call_registered_skill_tool("linter_check_source", {"source": source, "filepath": filepath})
    after = _source_label_state(files)
    # Assert
    assert after == before


@pytest.fixture(params=["python", "text", "notebook-code", "notebook-json", "notebook-empty", "notebook-no-cells", "notebook-null-cells", "notebook-map-cells", "notebook-cell-type", "notebook-missing-source", "markdown", "rst"])
def _bad_mcp_file_input(request, tmp_path):
    import json

    invalid = "def broken(\n"
    notebook = lambda cells: json.dumps({"cells": cells})
    cases = {
        "python": (".py", invalid),
        "text": (".txt", invalid),
        "notebook-code": (".ipynb", notebook([{"cell_type": "code", "source": [invalid]}])),
        "notebook-json": (".ipynb", "{broken JSON"),
        "notebook-empty": (".ipynb", ""),
        "notebook-no-cells": (".ipynb", "{}"),
        "notebook-null-cells": (".ipynb", notebook(None)),
        "notebook-map-cells": (".ipynb", notebook({})),
        "notebook-cell-type": (".ipynb", notebook([{"cell_type": "cod", "source": [invalid]}])),
        "notebook-missing-source": (".ipynb", notebook([{"cell_type": "code"}])),
        "markdown": (".md", "```python\n" + invalid + "```\n"),
        "rst": (".rst", ".. code-block:: python\n\n    def broken(\n"),
    }
    suffix, content = cases[request.param]
    file = tmp_path / ("bad-input" + suffix)
    file.write_text(content)
    (tmp_path / "pyproject.toml").write_text('[tool.scitex-dev.linter]\nlibrary_dirs = ["."]\n')
    return file


def test_mcp_file_input_errors_are_visible(_owned_installed_skill_profile, _bad_mcp_file_input):
    # Arrange
    from fastmcp.exceptions import ToolError

    # Act
    # Assert
    with pytest.raises(ToolError):
        _call_registered_skill_tool("linter_check", {"path": str(_bad_mcp_file_input)})


@pytest.fixture(params=["empty-notebook", "mixed-notebook", "markdown-nonpython", "rst-nonpython", "AST-only-python"])
def _accepted_mcp_file_input(request, tmp_path):
    import json
    from scitex_dev.linter.checker import lint_file
    from scitex_dev.linter.config import load_config
    from scitex_dev.linter.formatter import to_json

    source = 'import requests\nrequests.get("https://owned.invalid")\n'
    cases = {
        "empty-notebook": (".ipynb", json.dumps({"cells": []})),
        "mixed-notebook": (".ipynb", json.dumps({"cells": [
            {"cell_type": "markdown", "source": ["not Python syntax ("]},
            {"cell_type": "raw", "source": ["not Python syntax ("]},
            {"cell_type": "code", "source": source.splitlines(keepends=True)},
        ], "metadata": {"owned": True}})),
        "markdown-nonpython": (".md", "```bash\nnot Python syntax (\n```\n"),
        "rst-nonpython": (".rst", ".. code-block:: bash\n\n    not Python syntax (\n"),
        "AST-only-python": (".py", "return 1\n"),
    }
    suffix, content = cases[request.param]
    file = tmp_path / ("accepted-input" + suffix)
    file.write_text(content)
    config = tmp_path / "pyproject.toml"
    config.write_text('[tool.scitex-dev.linter]\nlibrary_dirs = ["."]\n')
    expected = to_json(lint_file(str(file), config=load_config(str(file))), str(file))
    files = [file, config]
    return file, expected, files, _source_label_state(files)


def test_mcp_file_input_accepted_payloads_stay_stable(_owned_installed_skill_profile, _accepted_mcp_file_input):
    # Arrange
    file, expected, _, _ = _accepted_mcp_file_input
    # Act
    result = _call_registered_skill_tool("linter_check", {"path": str(file)})
    # Assert
    assert result == expected


def test_mcp_file_input_preserves_accepted_file_bytes(_owned_installed_skill_profile, _accepted_mcp_file_input):
    # Arrange
    file, _, files, before = _accepted_mcp_file_input
    # Act
    _call_registered_skill_tool("linter_check", {"path": str(file)})
    after = _source_label_state(files)
    # Assert
    assert after == before


@pytest.fixture(params=["linter_check", "linter_list_rules"])
def _severity_contract_tool(request, tmp_path):
    from scitex_dev import linter
    from scitex_dev.linter.checker import lint_file
    from scitex_dev.linter.config import load_config
    from scitex_dev.linter.formatter import to_json
    from scitex_dev.linter.rules import SEVERITY_ORDER

    file = tmp_path / "owned.py"
    file.write_text('import requests\nrequests.get("https://owned.invalid")\n')
    (tmp_path / "pyproject.toml").write_text('[tool.scitex-dev.linter]\nlibrary_dirs = ["."]\n')
    issues = lint_file(str(file), config=load_config(str(file)))
    expected = {value: to_json([i for i in issues if SEVERITY_ORDER[i.rule.severity] >= SEVERITY_ORDER[value]], str(file)) for value in ["error", "warning", "info"]}
    catalogs = {value: {"rules": [{"id": r.id, "severity": r.severity, "category": r.category, "message": r.message, "suggestion": r.suggestion} for r in linter.list_rules() if r.severity == value], "count": sum(r.severity == value for r in linter.list_rules())} for value in ["error", "warning", "info"]}
    return request.param, {"path": str(file)} if request.param == "linter_check" else {}, expected if request.param == "linter_check" else catalogs


@pytest.mark.parametrize("severity", ["warn", "fatal", "", "ERROR", " warning", "warning "])
def test_mcp_severity_contract_rejects_unknown_values(_owned_installed_skill_profile, _severity_contract_tool, severity):
    # Arrange
    from fastmcp.exceptions import ToolError

    tool, arguments, _ = _severity_contract_tool
    # Act
    # Assert
    with pytest.raises(ToolError, match="severity"):
        _call_registered_skill_tool(tool, {**arguments, "severity": severity})


@pytest.mark.parametrize("severity", ["error", "warning", "info"])
def test_mcp_severity_contract_preserves_known_filters(_owned_installed_skill_profile, _severity_contract_tool, severity):
    # Arrange
    tool, arguments, expected = _severity_contract_tool
    # Act
    result = _call_registered_skill_tool(tool, {**arguments, "severity": severity})
    # Assert
    assert result == expected[severity]
