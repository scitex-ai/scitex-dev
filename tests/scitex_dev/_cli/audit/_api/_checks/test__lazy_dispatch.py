"""Static lazy-export declarations, with no inspected package execution."""

from pathlib import Path
import textwrap

import pytest

from scitex_dev._cli.audit._api._checks._init_surface import _audit_init


def _module(tmp_path, definition, prefix=""):
    package = tmp_path / "owned_api"
    package.mkdir()
    path = package / "__init__.py"
    path.write_text(
        "from __future__ import annotations\n"
        "__version__ = '0.0.0+local'\n"
        "__all__ = ['__version__', 'lazy']\n" + prefix + textwrap.dedent(definition)
    )
    return path


def _unbound(path):
    return [v.detail for v in _audit_init(path, "owned-api") if v.rule == "PA-102"]


@pytest.mark.parametrize("collection", ["{'lazy'}", "('lazy',)", "['lazy']"])
@pytest.mark.parametrize("parameter", ["name", "attribute"])
def test_literal_guard_declares_the_returned_attribute(tmp_path, collection, parameter):
    # Arrange
    path = _module(tmp_path, f"def __getattr__({parameter}):\n    if {parameter} in {collection}:\n        value = 1\n        return value\n    raise AttributeError({parameter})\n")
    # Act
    violations = _unbound(path)
    # Assert
    assert violations == []


@pytest.mark.parametrize("definition", [
    pytest.param("def __getattr__(name, required):\n    if name in {'lazy'}:\n        return 1\n", id="extra-positional-argument"),
    pytest.param("def __getattr__(name, *, required):\n    if name in {'lazy'}:\n        return 1\n", id="required-keyword-argument"),
    pytest.param("def __getattr__(name):\n    if name in dynamic:\n        return 1\n", id="dynamic-container"),
    pytest.param("def __getattr__(name):\n    if name in {'lazy', dynamic}:\n        return 1\n", id="mixed-container"),
    pytest.param("def __getattr__(name):\n    if name not in {'lazy'}:\n        return 1\n", id="negated-guard"),
    pytest.param("def __getattr__(name):\n    if other in {'lazy'}:\n        return 1\n", id="unrelated-name"),
    pytest.param("def __getattr__(name):\n    if name in {'lazy'}:\n        raise AttributeError(name)\n", id="raises-instead"),
    pytest.param("def __getattr__(name):\n    if name in {'lazy'}:\n        raise AttributeError(name)\n        return 1\n", id="unreachable-return"),
    pytest.param("def __getattr__(name):\n    def nested():\n        if name in {'lazy'}:\n            return 1\n    raise AttributeError(name)\n", id="nested-helper"),
    pytest.param("def __getattr__(name):\n    if name in {'lazy'} is True:\n        return 1\n", id="chained-guard"),
])
def test_unproven_guard_keeps_the_unbound_warning(tmp_path, definition):
    # Arrange
    path = _module(tmp_path, definition)
    # Act
    violations = _unbound(path)
    # Assert
    assert len(violations) == 1


def test_recognition_does_not_execute_module_side_effects(tmp_path):
    # Arrange
    marker = tmp_path / "must-not-be-created"
    prefix = f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n"
    path = _module(tmp_path, "def __getattr__(name):\n    if name in {'lazy'}:\n        return 1\n    raise AttributeError(name)\n", prefix)
    # Act
    violations = _unbound(path)
    # Assert
    assert (violations, marker.exists()) == ([], False)
