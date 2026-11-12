"""Read-only scoped verification, source identity and visible failures."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scitex_dev import verify_docs_and_skills


def _project(root, *, source="def public():\n    pass\n", readme=None):
    (root / "src/owned").mkdir(parents=True)
    (root / "src/owned/__init__.py").write_text(source)
    (root / "pyproject.toml").write_text('[project]\nname="owned"\nversion="1.2.3"\n')
    (root / "README.md").write_text(
        readme if readme is not None else "```python\nfrom owned import public\n```\n"
    )
    return root


def test_public_export_checks_selected_source_without_importing_it(tmp_path):
    # Arrange
    root = _project(
        tmp_path, source="raise RuntimeError('never import')\ndef public():\n    pass\n"
    )
    # Act
    report = verify_docs_and_skills(root)
    # Assert
    assert (
        report["status"] == "ok"
        and report["checked_scope"]["python_blocks"] == 1
        and len(report["checked_scope"]["imports"]) == 1
        and report["readme_version_match"] is None
        and report["readme_version_check"] == "not_present"
        and report["export_staleness"] == "not_checked"
    )


def test_verification_cannot_export_execute_or_write_even_to_user_home(tmp_path):
    # Arrange
    root = _project(tmp_path / "project")
    home = tmp_path / "home"
    home.mkdir()
    source_root = Path(__file__).resolve().parents[4] / "src"
    script = """
import os,sys,json
from scitex_dev import verify_docs_and_skills
import scitex_dev._ecosystem._skills.skills as skills
attempts = []

def forbidden_export(*args, **kwargs):
    attempts.append("export")
    raise AssertionError("verification must not export")
skills.export_skills = forbidden_export

def readonly(event, args):
    if event == "open":
        mode, flags = args[1], args[2]
        if (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
            isinstance(flags, int)
            and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)
        ):
            attempts.append(event)
            raise AssertionError("verification attempted a write")
    if event in {"subprocess.Popen", "os.system", "os.mkdir", "os.remove", "os.rename"}:
        attempts.append(event)
        raise AssertionError("verification attempted a mutation or process")
sys.addaudithook(readonly)
report = verify_docs_and_skills(sys.argv[1])
sys.stdout.write(json.dumps({"report": report, "attempts": attempts}))
"""
    env = dict(
        os.environ,
        HOME=str(home),
        PYTHONPATH=str(source_root),
        PYTHONDONTWRITEBYTECODE="1",
    )
    # Act
    result = subprocess.run(
        [sys.executable, "-B", "-c", script, str(root)],
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    # Assert
    assert (
        result.returncode == 0
        and json.loads(result.stdout)["report"]["status"] == "ok"
        and json.loads(result.stdout)["attempts"] == []
        and list(home.iterdir()) == []
    ), result.stderr


@pytest.mark.parametrize(
    "snippet",
    ["from owned.missing import value", "from owned import absent", "def broken(:"],
)
def test_definite_source_or_example_failures_are_visible(tmp_path, snippet):
    # Arrange
    root = _project(tmp_path, readme=f"```python\n{snippet}\n```\n")
    # Act
    report = verify_docs_and_skills(root)
    # Assert
    assert (
        report["status"] == "needs_update"
        and report["issues"]
        and report["stale_files"] == [str(root / "README.md")]
    )


@pytest.mark.parametrize(
    "source,expected",
    [
        ("from .backend import public\n", "needs_update"),
        ("def __getattr__(name):\n    raise AttributeError(name)\n", "incomplete"),
        ("if True:\n    def public():\n        pass\n", "incomplete"),
    ],
)
def test_missing_reexports_and_dynamic_bindings_have_distinct_outcomes(
    tmp_path, source, expected
):
    # Arrange
    root = _project(tmp_path, source=source)
    # Act
    report = verify_docs_and_skills(root)
    # Assert
    assert (report["status"], bool(report["unverified"]), bool(report["issues"])) == (
        expected,
        expected == "incomplete",
        expected == "needs_update",
    )


def test_only_python_fences_are_parsed_and_explicit_docs_scope_is_reported(tmp_path):
    # Arrange
    root = _project(tmp_path)
    guide = root / "guide.md"
    guide.write_text(
        "Prose: from owned import absent\n```bash\nfrom owned import absent\n```\n"
        "~~~py\nfrom owned import public\n~~~\n"
    )
    # Act
    report = verify_docs_and_skills(root, documents=[Path("guide.md")])
    # Assert
    assert (
        report["status"] == "ok"
        and report["checked_scope"]["documents"] == [str(guide)]
        and report["readme_version_check"] == "not_checked"
    )


@pytest.mark.parametrize("document", ["missing.md", "invalid.md", "unclosed.md"])
def test_document_read_and_parse_failures_are_never_suppressed(tmp_path, document):
    # Arrange
    root = _project(tmp_path)
    (root / "invalid.md").write_bytes(b"\xff")
    (root / "unclosed.md").write_text("```python\nfrom owned import public\n")
    # Act
    report = verify_docs_and_skills(root, documents=[Path(document)])
    # Assert
    assert report["status"] == "needs_update" and report["issues"]


def test_external_import_and_no_python_blocks_cannot_claim_complete_success(tmp_path):
    # Arrange
    root = _project(tmp_path, readme="```python\nimport external_dependency\n```\n")
    prose = root / "prose.md"
    prose.write_text("A guide without Python examples.\n")
    # Act
    external = verify_docs_and_skills(root)
    empty = verify_docs_and_skills(root, documents=[prose])
    # Assert
    assert (
        external["status"] == empty["status"] == "incomplete"
        and external["unverified"]
        and empty["unverified"]
    )


@pytest.mark.parametrize(
    ("claim", "expected", "status"),
    [("1.2.3", True, "ok"), ("9.9.9", False, "needs_update")],
)
def test_explicit_readme_version_claim_is_compared(tmp_path, claim, expected, status):
    # Arrange
    root = _project(
        tmp_path, readme=f"Version: {claim}\n```python\nfrom owned import public\n```\n"
    )
    # Act
    report = verify_docs_and_skills(root)
    # Assert
    assert report["readme_version_match"] is expected and report["status"] == status


def test_failed_metadata_check_is_visible(tmp_path):
    # Arrange
    root = _project(tmp_path, readme="Version: 1.2.3\n")
    (root / "pyproject.toml").write_text("[broken")
    # Act
    report = verify_docs_and_skills(root)
    # Assert
    assert (
        report["readme_version_check"] == "failed"
        and report["status"] == "needs_update"
        and report["issues"]
    )


def test_default_packaged_skill_failures_are_reported(tmp_path):
    # Arrange
    root = _project(tmp_path)
    skill = root / "src/owned/_skills/owned/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("```python\nfrom owned import absent\n```\n")
    # Act
    report = verify_docs_and_skills(root)
    # Assert
    assert (
        report["skills_stale"] is True
        and report["stale_files"] == [str(skill)]
        and report["status"] == "needs_update"
    )


def test_symlink_document_cannot_read_outside_selected_package(tmp_path):
    # Arrange
    root = _project(tmp_path / "project")
    outside = tmp_path / "outside.md"
    outside.write_text("```python\nfrom owned import public\n```\n")
    (root / "link.md").symlink_to(outside)
    # Act
    report = verify_docs_and_skills(root, documents=[Path("link.md")])
    # Assert
    assert report["status"] == "needs_update" and any(
        "outside package root" in issue for issue in report["issues"]
    )


@pytest.mark.parametrize(
    "source", [b"def broken(:", b"\xff"], ids=["syntax", "encoding"]
)
def test_referenced_source_parse_and_read_errors_are_visible(tmp_path, source):
    # Arrange
    root = _project(tmp_path)
    (root / "src/owned/__init__.py").write_bytes(source)
    # Act
    report = verify_docs_and_skills(root)
    # Assert
    assert report["status"] == "needs_update" and report["issues"]


def test_empty_explicit_selection_cannot_pass(tmp_path):
    # Arrange
    root = _project(tmp_path)
    # Act
    report = verify_docs_and_skills(root, documents=[])
    # Assert
    assert (
        report["status"] == "needs_update"
        and "No documents selected" in report["issues"]
    )


@pytest.mark.parametrize("indent", [0, 1, 2, 3])
@pytest.mark.parametrize("marker", ["```", "~~~"])
def test_fence_indentation_does_not_become_python_indentation(tmp_path, indent, marker):
    # Arrange
    prefix = " " * indent
    content = (
        f"{prefix}{marker}python\n"
        f"{prefix}from owned import public\n"
        f"{prefix}def example():\n"
        f"{prefix}    return public()\n"
        f"{prefix}{marker}\n"
    )
    root = _project(tmp_path, readme=content)
    # Act
    report = verify_docs_and_skills(root)
    # Assert
    # Parsing still succeeds; the nested call now has explicit limited coverage.
    assert (
        report["status"],
        report["issues"],
        len(report["checked_scope"]["imports"]),
        report["checked_scope"]["calls"],
        len(report["unverified"]),
        any("nested Python scope" in item for item in report["unverified"]),
    ) == ("incomplete", [], 1, [], 1, True)


def test_fence_removes_at_most_its_own_indent_from_each_line(tmp_path):
    # Arrange
    root = _project(
        tmp_path,
        readme="   ```python\n  from owned import public\nvalue = 3\n   ```\n",
    )
    # Act
    report = verify_docs_and_skills(root)
    # Assert
    assert (report["status"], report["issues"]) == ("ok", [])


def test_unindented_fence_does_not_hide_invalid_python_indentation(tmp_path):
    # Arrange
    root = _project(tmp_path, readme="```python\n    from owned import public\n```\n")
    # Act
    report = verify_docs_and_skills(root)
    # Assert
    assert report["status"] == "needs_update" and any(
        "IndentationError" in issue for issue in report["issues"]
    )
