"""Invoke real installed-style factories only in isolated child interpreters."""

import base64
import hashlib
import json
import os
import subprocess
import sys

import pytest

CHILD = """import json,sys
from pathlib import Path
from scitex_dev._ecosystem._capability_providers import read_capability_providers
from scitex_dev._ecosystem._capability_loading import load_capability_declaration
root=Path(sys.argv[1]); marker=Path(sys.argv[2])
try:
    provider=read_capability_providers(path=[root])[0]
    values=load_capability_declaration(provider,path=[root])
    result={'names':[item.name for item in values], 'bindings':[item.python for item in values]}
except Exception as exc:
    result={'error':type(exc).__name__,'message':str(exc),'cause':type(exc.__cause__).__name__ if exc.__cause__ else None}
result['calls']=marker.read_text() if marker.exists() else ''
print(json.dumps(result))
"""


def declaration(module):
    return {"schema_version": 1, "distribution": "loading-owner", "provider": "default",
            "capabilities": [{"name": "operation", "purpose": "A Python-only fixture operation.",
                              "python": [module + ".operation"], "test_references": ["fixture"],
                              "mcp_not_applicable_reason": "Python library fixture."}]}


def installed(tmp_path, *, module="loading_owned", package=False, factory=None,
              prefix="", payload=None, shadow=False):
    root = tmp_path / "installed"
    info = root / "loading_owner-1.0.dist-info"
    info.mkdir(parents=True)
    marker = tmp_path / "factory-calls"
    (info / "METADATA").write_text("Metadata-Version: 2.1\nName: loading-owner\nVersion: 1.0\n")
    (info / "entry_points.txt").write_text(f"[scitex_dev.capabilities]\ndefault = {module}:inventory\n")
    parts = module.split(".")
    files = [root.joinpath(*parts[:i], "__init__.py") for i in range(1, len(parts))]
    for parent in files:
        parent.parent.mkdir(parents=True, exist_ok=True)
        parent.write_text("")
    target = root.joinpath(*parts, "__init__.py") if package else root.joinpath(*parts).with_suffix(".py")
    target.parent.mkdir(parents=True, exist_ok=True)
    value = declaration(module) if payload is None else payload
    default = ("def inventory():\n"
               "    MARKER.write_text((MARKER.read_text() if MARKER.exists() else '') + 'x')\n"
               f"    return {value!r}\n")
    content = (f"from pathlib import Path\nMARKER=Path({str(marker)!r})\n" + prefix + "\n"
               "def operation():\n    raise RuntimeError('capability behavior must not execute')\n" +
               (default if factory is None else factory))
    target.write_text(content)
    files.append(target)
    rows = []
    for path in files:
        data = path.read_bytes()
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip("=")
        rows.append(f"{path.relative_to(root).as_posix()},sha256={digest},{len(data)}\n")
    (info / "RECORD").write_text("".join(rows))
    locations = [root]
    if shadow:
        foreign = tmp_path / "shadow"
        path = foreign / "loading_owned" / "__init__.py" if "." in module else foreign / "loading_owned.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"from pathlib import Path\nPath({str(marker)!r}).write_text('foreign')\n")
        locations.insert(0, foreign)
    return root, marker, locations


def run_factory(tmp_path, fixture):
    root, marker, locations = fixture
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([*(str(item) for item in locations), env.get("PYTHONPATH", "")])
    result = subprocess.run([sys.executable, "-c", CHILD, str(root), str(marker)],
                            cwd=tmp_path, env=env, capture_output=True, text=True, timeout=15)
    return json.loads(result.stdout), result.stderr


@pytest.mark.parametrize("module,package", [
    ("loading_owned", False), ("loading_owned", True),
    ("loading_owned.plugin", False), ("loading_owned.plugin", True),
])
def test_explicit_factory_returns_declarations_without_invoking_operations(tmp_path, module, package):
    # Arrange
    fixture = installed(tmp_path, module=module, package=package)
    # Act
    result, _ = run_factory(tmp_path, fixture)
    # Assert
    assert result == {"names": ["operation"], "bindings": [[module + ".operation"]], "calls": "x"}


def bad_factory(scenario):
    return {
        "object": "class Factory:\n    def __call__(self):\n        MARKER.write_text('x')\n        return {}\ninventory = Factory()\n",
        "noncallable": "inventory = {}\n",
        "missing": "answer = 1\n",
        "async": "async def inventory():\n    MARKER.write_text('x')\n    return {}\n",
        "required": "def inventory(required):\n    MARKER.write_text('x')\n    return {}\n",
        "raises": "def inventory():\n    MARKER.write_text('x')\n    raise RuntimeError('fixture failure')\n",
        "awaitable": "async def pending():\n    return {}\ndef inventory():\n    MARKER.write_text('x')\n    return pending()\n",
    }[scenario]


@pytest.mark.parametrize("scenario,message,calls,cause", [
    ("object", "selected module", "", None),
    ("noncallable", "callable", "", None), ("missing", "attribute", "", "AttributeError"),
    ("async", "synchronous", "", None), ("required", "factory failed", "", "TypeError"),
    ("raises", "factory failed", "x", "RuntimeError"), ("awaitable", "awaitable", "x", None),
])
def test_invalid_factories_fail_explicitly_without_unawaited_coroutines(tmp_path, scenario, message, calls, cause):
    # Arrange
    fixture = installed(tmp_path, factory=bad_factory(scenario))
    # Act
    result, stderr = run_factory(tmp_path, fixture)
    # Assert
    assert (result.get("error"), message in result.get("message", ""), result.get("calls"),
            result.get("cause"), "was never awaited" in stderr) == ("ValueError", True, calls, cause, False)


def bad_payload(scenario):
    data = declaration("loading_owned")
    if scenario == "owner":
        data["distribution"] = "another-owner"
    elif scenario == "version":
        data["schema_version"] = 2
    elif scenario == "flag":
        data["behavior_verified"] = True
    else:
        data = 7
    return data


@pytest.mark.parametrize("scenario,message", [("owner", "distribution"), ("version", "schema_version"),
                                              ("flag", "unexpected"), ("scalar", "plain object")])
def test_factory_payloads_use_the_existing_strict_contract(tmp_path, scenario, message):
    # Arrange
    fixture = installed(tmp_path, payload=bad_payload(scenario))
    # Act
    result, _ = run_factory(tmp_path, fixture)
    # Assert
    assert (result.get("error"), message in result.get("message", ""), result.get("calls")) == ("ValueError", True, "x")


@pytest.mark.parametrize("module", ["loading_owned", "loading_owned.plugin"])
def test_shadowed_target_or_parent_is_refused_before_import(tmp_path, module):
    # Arrange
    fixture = installed(tmp_path, module=module, shadow=True)
    # Act
    result, _ = run_factory(tmp_path, fixture)
    # Assert
    assert (result.get("error"), "origin differs" in result.get("message", ""), result.get("calls")) == ("ValueError", True, "")


@pytest.mark.parametrize("prefix,message", [
    ("__file__ = 'foreign.py'", "module file"),
    ("__package__ = 'foreign'", "package context"),
])
def test_mutated_import_metadata_prevents_factory_invocation(tmp_path, prefix, message):
    # Arrange
    fixture = installed(tmp_path, prefix=prefix)
    # Act
    result, _ = run_factory(tmp_path, fixture)
    # Assert
    assert (result.get("error"), message in result.get("message", ""), result.get("calls")) == ("ValueError", True, "")


def test_changed_source_during_import_prevents_factory_invocation(tmp_path):
    # Arrange
    fixture = installed(tmp_path, prefix="Path(__file__).write_text('changed = True')")
    # Act
    result, _ = run_factory(tmp_path, fixture)
    # Assert
    assert (result.get("error"), "digest mismatch" in result.get("message", ""), result.get("calls")) == ("ValueError", True, "")


def test_changed_source_during_factory_rejects_its_result(tmp_path):
    # Arrange
    code = "def inventory():\n    MARKER.write_text('x')\n    Path(__file__).write_text('changed = True')\n    return {}\n"
    fixture = installed(tmp_path, factory=code)
    # Act
    result, _ = run_factory(tmp_path, fixture)
    # Assert
    assert (result.get("error"), "digest mismatch" in result.get("message", ""), result.get("calls")) == ("ValueError", True, "x")


def test_expanded_package_search_path_prevents_factory_invocation(tmp_path):
    # Arrange
    fixture = installed(tmp_path, package=True, prefix="__path__.append('foreign')")
    # Act
    result, _ = run_factory(tmp_path, fixture)
    # Assert
    assert (result.get("error"), "package search path" in result.get("message", ""), result.get("calls")) == ("ValueError", True, "")


def test_provider_import_failure_preserves_its_cause(tmp_path):
    # Arrange
    fixture = installed(tmp_path, prefix="raise RuntimeError('import fixture failure')")
    # Act
    result, _ = run_factory(tmp_path, fixture)
    # Assert
    assert (result.get("error"), "import failed" in result.get("message", ""),
            result.get("calls"), result.get("cause")) == ("ValueError", True, "", "RuntimeError")


@pytest.mark.parametrize("mutation,message", [
    ("import sys; sys.modules[__package__].__file__='foreign.py'", "module file"),
    ("import sys; sys.modules[__package__].__path__.append('foreign')", "package search path"),
])
def test_target_initializer_cannot_change_parent_before_factory(tmp_path, mutation, message):
    # Arrange
    fixture = installed(tmp_path, module="loading_owned.plugin", prefix=mutation)
    # Act
    result, _ = run_factory(tmp_path, fixture)
    # Assert
    assert (result.get("error"), message in result.get("message", ""), result.get("calls")) == ("ValueError", True, "")


def test_reexported_foreign_factory_is_refused_before_calling_it(tmp_path):
    # Arrange
    fixture = installed(tmp_path, factory="from foreign_factory import inventory\n")
    directory, marker, _ = fixture
    code = (f"from pathlib import Path\ndef inventory():\n"
            f"    Path({str(marker)!r}).write_text('foreign')\n"
            f"    return {declaration('loading_owned')!r}\n")
    (directory / "foreign_factory.py").write_text(code)
    # Act
    result, _ = run_factory(tmp_path, fixture)
    # Assert
    assert (result.get("error"), "selected module" in result.get("message", ""), result.get("calls")) == ("ValueError", True, "")
