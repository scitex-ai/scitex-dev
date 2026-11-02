"""Real owned-source fixtures prove missing, unsafe and implemented interfaces."""

from __future__ import annotations

import sys
from dataclasses import dataclass

import pytest

from scitex_dev._interfaces._project import inspect_interfaces


def _errors(root):
    return [f for f in inspect_interfaces(root) if f.severity == "E"]


def test_real_bindings_need_no_package_import(package):
    """An import sentinel remains untouched while all five source checks pass."""
    # Arrange
    # Act
    observed = (_errors(package), "branded_demo" in sys.modules)
    # Assert
    assert observed == ([], False)


@pytest.mark.parametrize(
    "relative,code",
    [
        ("src/branded_demo/api.py", "PS-IF-001"),
        ("src/branded_demo/cli.py", "PS-IF-002"),
        ("src/branded_demo/_mcp_server.py", "PS-IF-003"),
        ("src/branded_demo/web.py", "PS-IF-004"),
        ("src/branded_demo/_skills/branded-demo/SKILL.md", "PS-IF-005"),
    ],
)
def test_each_missing_binding_is_an_error(package, relative, code):
    """Removing a real interface can never become an informational skip."""
    # Arrange
    (package / relative).unlink()
    # Act
    # Assert
    assert code in {f.rule for f in _errors(package)}


@pytest.mark.parametrize(
    "body", ["pass", "...", "return None", "raise NotImplementedError()"]
)
def test_empty_operation_is_not_python_or_mcp_implementation(package, body):
    """Placeholder handlers cannot satisfy the default contract."""
    # Arrange
    (package / "src/branded_demo/api.py").write_text(
        f'def echo(value):\n    """Not implemented."""\n    {body}\n'
    )
    server = package / "src/branded_demo/_mcp_server.py"
    server.write_text(
        f'from fastmcp import FastMCP\nmcp = FastMCP("demo")\n@mcp.tool()\ndef echo_tool(value):\n    {body}\n'
    )
    # Act
    codes = {f.rule for f in _errors(package)}
    # Assert
    assert {"PS-IF-001", "PS-IF-003"} <= codes


def test_lazy_literal_facade_is_resolved_without_import(package):
    """The real PEP-562 export shape preserves source-backed lazy APIs."""
    # Arrange
    (
        package / "src/branded_demo/__init__.py"
    ).write_text("""_LAZY_ATTRS = {"echo": "api"}
__all__ = ["echo"]
def __getattr__(name):
    from importlib import import_module
    module = _LAZY_ATTRS[name]
    return getattr(import_module(f".{module}", __name__), name)
""")
    # Act
    # Assert
    assert _errors(package) == []


def test_unreferenced_lazy_map_is_not_evidence(package):
    """A decorative dictionary must not fabricate an exported operation."""
    # Arrange
    (package / "src/branded_demo/__init__.py").write_text(
        '_LAZY_ATTRS = {"echo": "api"}\n__all__ = ["echo"]\n'
    )
    # Act
    # Assert
    assert "PS-IF-001" in {f.rule for f in _errors(package)}


def test_dynamic_facade_is_an_explicit_unproven_finding(package):
    """Unsupported dynamic exports require evidence, not a guessed pass."""
    # Arrange
    (package / "src/branded_demo/__init__.py").write_text(
        "__all__ = compute_exports()\n"
    )
    # Act
    findings = _errors(package)
    # Assert
    assert any(
        f.rule == "PS-IF-001" and "dynamic __all__" in f.detail for f in findings
    )


@pytest.mark.parametrize(
    "binding",
    [
        "os:system",
        "branded_demo.cli:missing",
        "../escape:main",
        "branded_demo.cli:main.extra",
    ],
)
def test_dangling_or_external_console_binding_is_refused(package, binding):
    """A console-script spelling cannot stand in for owned implementation."""
    # Arrange
    metadata = package / "pyproject.toml"
    metadata.write_text(metadata.read_text().replace("branded_demo.cli:main", binding))
    # Act
    # Assert
    assert "PS-IF-002" in {f.rule for f in _errors(package)}


@pytest.mark.parametrize(
    "suffix", ["_mcp_server", "mcp_server", "_mcp.server", "mcp.server", "_mcp._server"]
)
def test_existing_mcp_conventions_are_shared(package, suffix):
    """Every admitted source convention binds the same actual tool."""
    # Arrange
    old = package / "src/branded_demo/_mcp_server.py"
    destination = package / "src/branded_demo" / (suffix.replace(".", "/") + ".py")
    contents = old.read_text()
    old.unlink()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(contents)
    # Act
    # Assert
    assert _errors(package) == []


def test_mcp_registration_of_owned_imported_handler(package):
    """FastMCP's direct registration form resolves the actual leaf callable."""
    # Arrange
    (package / "src/branded_demo/_mcp_server.py").write_text(
        'from fastmcp import FastMCP\nfrom .api import echo\nmcp = FastMCP("demo")\nmcp.tool()(echo)\n'
    )
    # Act
    # Assert
    assert _errors(package) == []


@pytest.mark.parametrize(
    "relative", ["api.py", "web.py", "_skills/branded-demo/SKILL.md"]
)
def test_source_links_outside_repo_never_count(package, tmp_path, relative):
    """Real symlink escapes are refused before reading foreign source."""
    # Arrange
    target = package / "src/branded_demo" / relative
    foreign = tmp_path / "foreign"
    foreign.write_bytes(target.read_bytes())
    target.unlink()
    target.symlink_to(foreign)
    # Act
    # Assert
    assert _errors(package)


def test_source_alias_cycle_is_bounded(package):
    """A cycle produces one finding without imports or unbounded traversal."""
    # Arrange
    (package / "src/branded_demo/api.py").write_text("echo = other\nother = echo\n")
    # Act
    # Assert
    assert "PS-IF-001" in {f.rule for f in _errors(package)}


def test_malformed_package_metadata_fails_all_interfaces(package):
    """Broken metadata cannot make a package disappear from its audit."""
    # Arrange
    (package / "pyproject.toml").write_text("[project\n")
    # Act
    # Assert
    assert {f.rule for f in _errors(package)} == {f"PS-IF-{x:03}" for x in range(1, 6)}


def test_research_tree_without_package_metadata_is_outside_contract(tmp_path):
    """The default concerns packages, not arbitrary research directories."""
    # Arrange
    # Act
    # Assert
    assert inspect_interfaces(tmp_path) == []


def _exception(package, reason, rule="PS-IF-004", path="pyproject.toml", line=1):
    config = package / ".scitex/dev/config.yaml"
    config.parent.mkdir(parents=True)
    config.write_text(
        f'project-type: [pip]\naudit:\n  exemptions:\n    {rule}:\n      - path: "{path}"\n        line: {line}\n        reason: "{reason}"\n'
    )


def test_narrow_reasoned_exception_remains_visible(package):
    """A specific inapplicable interface is recorded, never invented."""
    # Arrange
    (package / "src/branded_demo/web.py").unlink()
    _exception(
        package,
        "This offline cryptographic utility must not expose secret operations over HTTP.",
    )
    # Act
    findings = inspect_interfaces(package)
    observed = [
        (f.rule, f.severity, "Explicit interface exception" in f.detail)
        for f in findings
    ]
    # Assert
    assert observed == [("PS-IF-004", "I", True)]


@pytest.mark.parametrize(
    "reason,path,line",
    [
        ("TODO", "pyproject.toml", 1),
        (" ", "pyproject.toml", 1),
        ("This offline utility intentionally does not serve HTTP.", "*", 1),
        (
            "This offline utility intentionally does not serve HTTP.",
            "pyproject.toml",
            99,
        ),
    ],
)
def test_unreasoned_or_broad_exception_does_not_silence_missing_binding(
    package, reason, path, line
):
    """Only the exact rule/site with a real reason can take effect."""
    # Arrange
    (package / "src/branded_demo/web.py").unlink()
    _exception(package, reason, path=path, line=line)
    # Act
    # Assert
    assert "PS-IF-004" in {f.rule for f in _errors(package)}


def test_existing_project_provider_contains_default_five_rules():
    """The normal project SPI owns the new checks without another registry."""
    # Arrange
    from scitex_dev._interfaces._project import check_interfaces
    from scitex_dev._runtime_gitignore_plugin import get_plugin

    # Act
    plugin = get_plugin()
    observed = ({r[0] for r in plugin["rules"]}, check_interfaces in plugin["checks"])
    # Assert
    assert observed == ({"PS-234", *{f"PS-IF-{x:03}" for x in range(1, 6)}}, True)


def test_project_spi_preserves_error_and_information_severity(package):
    """The actual SPI adapter carries a justified exception as information."""
    # Arrange
    from scitex_dev._interfaces._project import check_interfaces

    @dataclass
    class Violation:
        rule: str
        where: str
        detail: str
        severity_override: str | None = None

    (package / "src/branded_demo/web.py").unlink()
    _exception(
        package, "This offline utility intentionally does not serve HTTP operations."
    )
    out = []
    # Act
    check_interfaces(package, Violation, out)
    # Assert
    assert len(out) == 1 and out[0].severity_override == "I"


def test_decorative_getter_cannot_fabricate_lazy_export(package):
    """Mentioning a lazy map without returning its imported attribute is unproven."""
    # Arrange
    (package / "src/branded_demo/__init__.py").write_text(
        '_LAZY_ATTRS = {"echo": "api"}\n__all__ = ["echo"]\ndef __getattr__(name):\n    value = _LAZY_ATTRS[name]\n    raise NotImplementedError(value)\n'
    )
    # Act
    # Assert
    assert "PS-IF-001" in {f.rule for f in _errors(package)}


def test_malformed_exception_yaml_is_an_error_not_an_audit_crash(package):
    """Invalid exception syntax fails closed and retains missing-interface evidence."""
    # Arrange
    config = package / ".scitex/dev/config.yaml"
    config.parent.mkdir(parents=True)
    config.write_text("audit: [\n")
    (package / "src/branded_demo/web.py").unlink()
    # Act
    findings = _errors(package)
    observed = (
        any("Cannot parse narrow interface exemptions" in f.detail for f in findings),
        "PS-IF-004" in {f.rule for f in findings},
    )
    # Assert
    assert observed == (True, True)


def test_export_overwritten_with_nonoperation_does_not_count(package):
    """A real earlier function cannot conceal a later placeholder rebinding."""
    # Arrange
    (package / "src/branded_demo/api.py").write_text(
        "def echo(value):\n    return value\necho = None\n"
    )
    # Act
    # Assert
    assert "PS-IF-001" in {f.rule for f in _errors(package)}
