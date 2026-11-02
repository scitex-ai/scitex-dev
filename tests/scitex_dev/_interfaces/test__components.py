"""Real component namespaces must count; sample/vendor servers must not."""

from scitex_dev._interfaces._project import inspect_interfaces


def _nested(package, folder, *, guarded=True):
    old = package / "src/branded_demo/_mcp_server.py"
    contents = old.read_text()
    old.unlink()
    root = package / "src/branded_demo" / folder
    root.mkdir(parents=True)
    (root / "__init__.py").write_text('"""Owned component."""\n')
    mcp = root / "_mcp"
    mcp.mkdir()
    (mcp / "__init__.py").write_text('"""Owned protocol."""\n')
    if guarded:
        contents = contents.replace(
            "from fastmcp import FastMCP",
            'try:\n    from fastmcp import FastMCP\nexcept ImportError as exc:\n    raise ImportError("Install the declared extra") from exc',
        )
    path = mcp / "server.py"
    path.write_text(contents)
    return path


def test_owned_nested_component_server_satisfies_mcp_presence(package):
    """A real component-owned server must not be falsely reported as absent."""
    # Arrange
    _nested(package, "component")
    # Act
    findings = inspect_interfaces(package)
    # Assert
    assert not [f for f in findings if f.rule == "PS-IF-003"]


def test_staged_nested_component_uses_identical_source_boundary(package):
    """Complete source overlays discover the same owned nested server."""
    # Arrange
    _nested(package, "component")
    overlays = {
        path.relative_to(package).as_posix(): path.read_text()
        for path in package.rglob("*")
        if path.is_file()
    }
    # Act
    findings = inspect_interfaces(package, overlays=overlays)
    # Assert
    assert not [f for f in findings if f.rule == "PS-IF-003"]


def test_importerror_fallback_factory_cannot_fabricate_mcp(package):
    """A stand-in factory is not accepted as the actual optional server."""
    # Arrange
    path = _nested(package, "component")
    path.write_text(
        path.read_text().replace(
            'raise ImportError("Install the declared extra") from exc',
            "FastMCP = lambda *args: object()",
        )
    )
    # Act
    findings = inspect_interfaces(package)
    # Assert
    assert any(f.rule == "PS-IF-003" for f in findings)


def test_unreachable_tool_definition_cannot_fabricate_presence(package):
    """A tool in a dead branch is not a module-level registration."""
    # Arrange
    path = package / "src/branded_demo/_mcp_server.py"
    path.write_text(
        'from fastmcp import FastMCP\nmcp = FastMCP("demo")\nif False:\n    @mcp.tool()\n    def invisible(value):\n        return str(value)\n'
    )
    # Act
    findings = inspect_interfaces(package)
    # Assert
    assert any(f.rule == "PS-IF-003" for f in findings)


def test_example_server_is_not_an_owned_runtime_component(package):
    """The actual source scanner excludes demonstration/template content."""
    # Arrange
    _nested(package, "examples")
    # Act
    findings = inspect_interfaces(package)
    # Assert
    assert any(f.rule == "PS-IF-003" for f in findings)


def test_symlink_component_never_counts_as_owned_source(package, tmp_path):
    """A real foreign namespace link cannot bypass the normal source jail."""
    # Arrange
    path = _nested(package, "component")
    component = path.parents[1]
    foreign = tmp_path / "foreign"
    component.rename(foreign)
    component.symlink_to(foreign, target_is_directory=True)
    # Act
    findings = inspect_interfaces(package)
    # Assert
    assert any(f.rule == "PS-IF-003" for f in findings)
