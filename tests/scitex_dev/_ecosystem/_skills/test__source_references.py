"""Documented public imports must follow explicit local source re-exports."""

import json

from click.testing import CliRunner
import pytest

from scitex_dev import verify_docs_and_skills
from scitex_dev._cli import main


def _project(root, files):
    for name, content in files.items():
        path = root / "src/owned" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else content.encode())
    (root / "pyproject.toml").write_text('[project]\nname="owned"\nversion="1.0.0"\n')
    (root / "README.md").write_text("```python\nfrom owned import public\n```\n")
    return root


@pytest.mark.parametrize(
    "files",
    [
        {
            "__init__.py": "from .backend import public\n",
            "backend.py": "def public(): pass\n",
        },
        {
            "__init__.py": "from .backend import original as public\n",
            "backend.py": "class original: pass\n",
        },
        {
            "__init__.py": "from owned.backend import public\n",
            "backend.py": "async def public(): pass\n",
        },
        {
            "__init__.py": "from .api import public\n",
            "api/__init__.py": "from ..backend import value as public\n",
            "backend.py": "def value(): pass\n",
        },
        {
            "__init__.py": "from . import tools as public\n",
            "tools.py": "def run(): pass\n",
        },
        {
            "__init__.py": "from .api.bridge import public\n",
            "api/__init__.py": "",
            "api/bridge.py": "from ..backend import value as public\n",
            "backend.py": "def value(): pass\n",
        },
        {
            "__init__.py": "from .backend import public\n",
            "backend.py": "def another(): pass\n",
            "backend/__init__.py": "def public(): pass\n",
        },
    ],
)
def test_explicit_local_reexports_are_checked_through_the_public_api(tmp_path, files):
    # Arrange
    root = _project(tmp_path, files)
    # Act
    report = verify_docs_and_skills(root)
    # Assert
    assert (
        report["status"],
        len(report["checked_scope"]["imports"]),
        report["issues"],
        report["unverified"],
    ) == ("ok", 1, [], [])


@pytest.mark.parametrize(
    "extra_files",
    [
        {},
        {"backend.py": "def another(): pass\n"},
        {"backend.py": "def invalid(:"},
        {"backend.py": b"\xff"},
    ],
)
def test_broken_local_reexport_targets_are_visible_failures(tmp_path, extra_files):
    # Arrange
    files = {"__init__.py": "from .backend import public\n", **extra_files}
    root = _project(tmp_path, files)
    # Act
    report = verify_docs_and_skills(root)
    # Assert
    assert report["status"] == "needs_update" and report["issues"]


@pytest.mark.parametrize(
    "source,backend",
    [
        ("from .backend import public\n", "from . import public\n"),
        ("if True:\n    from .backend import public\n", "def public(): pass\n"),
        ("from .backend import public\npublic = object()\n", "def public(): pass\n"),
        ("from external_dependency import public\n", "def public(): pass\n"),
        ("from .backend import *\n", "def public(): pass\n"),
        ("def __getattr__(name):\n    return object()\n", "def public(): pass\n"),
        (
            "from .backend import public\nfrom .other import public\n",
            "def public(): pass\n",
        ),
    ],
)
def test_uncertain_reexports_remain_incomplete(tmp_path, source, backend):
    # Arrange
    root = _project(tmp_path, {"__init__.py": source, "backend.py": backend})
    # Act
    report = verify_docs_and_skills(root)
    # Assert
    assert (
        report["status"] == "incomplete"
        and report["unverified"]
        and not report["issues"]
    )


def test_reexported_source_is_read_without_import_or_execution(tmp_path):
    # Arrange
    marker = tmp_path / "must-not-be-written"
    root = _project(
        tmp_path / "project",
        {
            "__init__.py": "from .backend import public\n",
            "backend.py": f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\ndef public(): pass\n",
        },
    )
    # Act
    report = verify_docs_and_skills(root)
    # Assert
    assert (report["status"], marker.exists()) == ("ok", False)


def test_reexport_cannot_read_source_outside_the_selected_root(tmp_path):
    # Arrange
    root = _project(
        tmp_path / "project", {"__init__.py": "from .backend import public\n"}
    )
    outside = tmp_path / "outside.py"
    outside.write_text("def public(): pass\n")
    (root / "src/owned/backend.py").symlink_to(outside)
    # Act
    report = verify_docs_and_skills(root)
    # Assert
    assert report["status"] == "needs_update" and any(
        "outside package root" in issue for issue in report["issues"]
    )


def test_overlong_reexport_chain_is_explicitly_incomplete(tmp_path):
    # Arrange
    files = {"__init__.py": "from .step0 import public\n"}
    files.update(
        {
            f"step{number}.py": f"from .step{number + 1} import public\n"
            for number in range(34)
        }
    )
    files["step34.py"] = "def public(): pass\n"
    root = _project(tmp_path, files)
    # Act
    report = verify_docs_and_skills(root)
    # Assert
    assert report["status"] == "incomplete" and any(
        "depth limit" in item for item in report["unverified"]
    )


def test_relative_reexport_cannot_leave_the_source_package(tmp_path):
    # Arrange
    root = _project(tmp_path, {"__init__.py": "from ..backend import public\n"})
    # Act
    report = verify_docs_and_skills(root)
    # Assert
    assert report["status"] == "needs_update" and any(
        "beyond the source package" in item for item in report["issues"]
    )


@pytest.mark.parametrize(
    "extra_files,expected,status",
    [({"backend.py": "def public(): pass\n"}, 0, "ok"), ({}, 1, "needs_update")],
)
def test_real_cli_preserves_checked_and_broken_reexport_outcomes(
    tmp_path, extra_files, expected, status
):
    # Arrange
    files = {"__init__.py": "from .backend import public\n", **extra_files}
    root = _project(tmp_path, files)
    # Act
    result = CliRunner().invoke(
        main,
        ["docs", "validate", "--path", str(root), "--document", "README.md", "--json"],
    )
    report = json.loads(result.stdout)
    # Assert
    assert (result.exit_code, report["status"]) == (expected, status)


def test_explicit_binding_precedes_an_unrelated_same_named_submodule(tmp_path):
    # Arrange
    root = _project(
        tmp_path, {"__init__.py": "def public(): pass\n", "public.py": "def invalid(:"}
    )
    # Act
    report = verify_docs_and_skills(root)
    # Assert
    assert report["status"] == "ok" and not report["issues"]
