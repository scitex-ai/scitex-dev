"""Test the pyproject linter — codifies the 2026-04-28 lessons.

Each rule has at least one positive (rule fires) and one negative (clean
fixture passes) test. The fixtures live as inline strings so the tests
are self-contained — run with `pytest tests/test_pyproject_lint.py`.
"""

from __future__ import annotations

from pathlib import Path


from scitex_dev._pyproject_lint import (
    check_duplicate_tables,
    lint_pyproject,
)


def _write_repo(
    tmp_path: Path,
    pyproject: str,
    src_files: dict[str, str] | None = None,
    skills: bool = False,
) -> Path:
    """Build a fake repo on disk and return its root."""
    (tmp_path / "pyproject.toml").write_text(pyproject)
    name = (tmp_path / "pyproject.toml").read_text()
    # crude: pull import_name from the project name field for src layout
    import re

    m = re.search(r'^name\s*=\s*"([^"]+)"', name, re.MULTILINE)
    pkg = m.group(1) if m else "pkg"
    imp = pkg.replace("-", "_")
    src = tmp_path / "src" / imp
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("")
    for rel, body in (src_files or {}).items():
        target = src / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body)
    if skills:
        skill_md = src / "_skills" / pkg / "SKILL.md"
        skill_md.parent.mkdir(parents=True, exist_ok=True)
        skill_md.write_text("---\nname: x\n---\n# x\n")
    return tmp_path


# ----------------------------------------------------------------------
# E5C5 — implicit transitive dep
# ----------------------------------------------------------------------


def test_e5c5_fires_on_undeclared_scitex_config(tmp_path):
    """The 2026-04-28 class-action: src imports scitex_config but pyproject doesn't list it."""
    repo = _write_repo(
        tmp_path,
        pyproject="""[project]
name = "demo"
version = "0.1.0"
dependencies = ["numpy"]
""",
        src_files={"foo.py": "from scitex_config._ecosystem import local_state\n"},
    )
    rep = lint_pyproject(repo, package_name="demo")
    rules = [f.rule for f in rep.findings]
    assert "E5C5_implicit_deps" in rules
    crit = [f for f in rep.findings if f.rule == "E5C5_implicit_deps"]
    assert crit[0].severity == "CRITICAL"
    assert "scitex-config" in crit[0].message


def test_e5c5_silent_when_dep_declared(tmp_path):
    repo = _write_repo(
        tmp_path,
        pyproject="""[project]
name = "demo"
version = "0.1.0"
dependencies = ["numpy", "scitex-config>=0.3.0"]
""",
        src_files={"foo.py": "from scitex_config._ecosystem import local_state\n"},
    )
    rep = lint_pyproject(repo, package_name="demo")
    assert "E5C5_implicit_deps" not in [f.rule for f in rep.findings]


def test_e5c5_silent_when_inside_type_checking(tmp_path):
    """`if TYPE_CHECKING: from x import Y` is not a runtime dep."""
    repo = _write_repo(
        tmp_path,
        pyproject="""[project]
name = "demo"
version = "0.1.0"
dependencies = []
""",
        src_files={
            "foo.py": (
                "from typing import TYPE_CHECKING\n"
                "if TYPE_CHECKING:\n"
                "    from scitex_config._ecosystem import local_state\n"
            )
        },
    )
    rep = lint_pyproject(repo, package_name="demo")
    assert "E5C5_implicit_deps" not in [f.rule for f in rep.findings]


def test_e5c5_silent_when_function_body_try_except(tmp_path):
    """A try/except ImportError inside a function body is still guarded."""
    repo = _write_repo(
        tmp_path,
        pyproject="""[project]
name = "demo"
version = "0.1.0"
dependencies = []
""",
        src_files={
            "foo.py": (
                "def maybe():\n"
                "    try:\n"
                "        from scitex_hpc import Reservation\n"
                "    except ImportError:\n"
                "        return None\n"
                "    return Reservation\n"
            )
        },
    )
    rep = lint_pyproject(repo, package_name="demo")
    assert "E5C5_implicit_deps" not in [f.rule for f in rep.findings]


def test_e5c5_silent_when_import_is_guarded(tmp_path):
    """Optional imports wrapped in try/except ImportError don't need a dep.

    scitex-bridge's `try: import figrecipe except ImportError: ...` pattern
    must not trip the linter — it has a fallback path.
    """
    repo = _write_repo(
        tmp_path,
        pyproject="""[project]
name = "demo"
version = "0.1.0"
dependencies = ["matplotlib"]
""",
        src_files={
            "foo.py": (
                "try:\n"
                "    from scitex_config._ecosystem import local_state\n"
                "    HAS = True\n"
                "except ImportError:\n"
                "    HAS = False\n"
            )
        },
    )
    rep = lint_pyproject(repo, package_name="demo")
    assert "E5C5_implicit_deps" not in [f.rule for f in rep.findings]


def test_e5c5_silent_for_self_imports(tmp_path):
    """A package importing its own internals must not flag itself."""
    repo = _write_repo(
        tmp_path,
        pyproject="""[project]
name = "scitex-config"
version = "0.3.1"
dependencies = ["PyYAML"]
""",
        src_files={"_paths.py": "from scitex_config._ecosystem import local_state\n"},
    )
    rep = lint_pyproject(repo, package_name="scitex-config")
    assert "E5C5_implicit_deps" not in [f.rule for f in rep.findings]


# ----------------------------------------------------------------------
# E5C9 — skill bundling
# ----------------------------------------------------------------------


def test_e5c9_fires_when_skills_dir_unbundled_setuptools(tmp_path):
    """setuptools requires explicit package-data — missing both glob and
    entry-point yields two findings."""
    repo = _write_repo(
        tmp_path,
        pyproject="""[build-system]
requires = ["setuptools"]
build-backend = "setuptools.build_meta"
[project]
name = "demo"
version = "0.1.0"
[tool.setuptools.packages.find]
where = ["src"]
""",
        skills=True,
    )
    rep = lint_pyproject(repo, package_name="demo")
    rules = [f.rule for f in rep.findings if f.rule == "E5C9_skill_bundling"]
    assert len(rules) == 2  # package-data + entry-point


def test_e5c9_silent_when_hatchling_default(tmp_path):
    """hatchling ships everything in the package dir by default; only the
    entry-point is required."""
    repo = _write_repo(
        tmp_path,
        pyproject="""[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
[project]
name = "demo"
version = "0.1.0"
[project.entry-points."scitex_dev.skills"]
demo = "demo"
[tool.hatch.build.targets.wheel]
packages = ["src/demo"]
""",
        skills=True,
    )
    rep = lint_pyproject(repo, package_name="demo")
    assert not [f for f in rep.findings if f.rule == "E5C9_skill_bundling"]


def test_e5c9_fires_when_hatchling_excludes_skills(tmp_path):
    """If hatchling has an explicit exclude that drops _skills, flag it."""
    repo = _write_repo(
        tmp_path,
        pyproject="""[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
[project]
name = "demo"
version = "0.1.0"
[project.entry-points."scitex_dev.skills"]
demo = "demo"
[tool.hatch.build.targets.wheel]
packages = ["src/demo"]
exclude = ["**/_skills/**"]
""",
        skills=True,
    )
    rep = lint_pyproject(repo, package_name="demo")
    assert [f for f in rep.findings if f.rule == "E5C9_skill_bundling"]


def test_e5c9_silent_when_fully_wired(tmp_path):
    repo = _write_repo(
        tmp_path,
        pyproject="""[project]
name = "demo"
version = "0.1.0"

[project.entry-points."scitex_dev.skills"]
demo = "demo"

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-data]
demo = ["_skills/**/*.md"]
""",
        skills=True,
    )
    rep = lint_pyproject(repo, package_name="demo")
    assert not [f for f in rep.findings if f.rule == "E5C9_skill_bundling"]


# ----------------------------------------------------------------------
# E5C10 — duplicate TOML table
# ----------------------------------------------------------------------


def test_e5c10_fires_on_duplicate_package_data(tmp_path):
    """Both scitex-resource and scitex-capture hit this on 2026-04-28."""
    pyproject = """[project]
name = "demo"
version = "0.1.0"

[tool.setuptools.package-data]
demo = ["_skills/**/*.md"]

[tool.setuptools.package-data]
demo = ["data/*.yaml"]
"""
    fp = tmp_path / "pyproject.toml"
    fp.write_text(pyproject)
    findings = check_duplicate_tables(fp)
    assert any(f.rule == "E5C10_duplicate_table" for f in findings)


def test_e5c10_silent_on_clean_pyproject(tmp_path):
    fp = tmp_path / "pyproject.toml"
    fp.write_text(
        '[project]\nname = "x"\n[tool.setuptools]\nbuild-backend = "setuptools.build_meta"\n'
    )
    assert check_duplicate_tables(fp) == []


# ----------------------------------------------------------------------
# E5C11 — license
# ----------------------------------------------------------------------


def test_e5c11_fires_on_table_form(tmp_path):
    repo = _write_repo(
        tmp_path,
        pyproject="""[project]
name = "demo"
version = "0.1.0"
license = {text = "AGPL-3.0-only"}
""",
    )
    rep = lint_pyproject(repo)
    licenses = [f for f in rep.findings if f.rule == "E5C11_invalid_pep639_license"]
    assert licenses and "deprecated table form" in licenses[0].message


def test_e5c11_silent_on_spdx(tmp_path):
    repo = _write_repo(
        tmp_path,
        pyproject="""[project]
name = "demo"
version = "0.1.0"
license = "AGPL-3.0-only"
""",
    )
    rep = lint_pyproject(repo)
    assert not [f for f in rep.findings if f.rule == "E5C11_invalid_pep639_license"]


# ----------------------------------------------------------------------
# Aggregation
# ----------------------------------------------------------------------


def test_lint_pyproject_aggregates_severity(tmp_path):
    repo = _write_repo(
        tmp_path,
        pyproject="""[project]
name = "demo"
version = "0.1.0"
license = {text = "AGPL-3.0-only"}
dependencies = []

[tool.setuptools.packages.find]
where = ["src"]
""",
        src_files={"foo.py": "from scitex_config._ecosystem import local_state\n"},
        skills=True,
    )
    rep = lint_pyproject(repo, package_name="demo")
    assert rep.has_critical  # E5C5 fires
    assert rep.has_high  # E5C9 fires too
    rules = {f.rule for f in rep.findings}
    assert "E5C5_implicit_deps" in rules
    assert "E5C9_skill_bundling" in rules
    assert "E5C11_invalid_pep639_license" in rules


def test_missing_pyproject(tmp_path):
    rep = lint_pyproject(tmp_path)
    assert any(f.rule == "E5C1_missing_pyproject" for f in rep.findings)
