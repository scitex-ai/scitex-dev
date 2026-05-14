"""Test the pyproject linter — codifies the 2026-04-28 lessons.

Each rule has at least one positive (rule fires) and one negative (clean
fixture passes) test. The fixtures live as inline strings so the tests
are self-contained — run with `pytest tests/test_pyproject_lint.py`.
"""

from __future__ import annotations

from pathlib import Path


from scitex_dev._ecosystem._release.pyproject_lint import (
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
# REL-5 — implicit transitive dep
# ----------------------------------------------------------------------


def test_e5c5_fires_on_undeclared_scitex_config_rel_5_implicit_deps_in_rules(tmp_path):
    """The 2026-04-28 class-action: src imports scitex_config but pyproject doesn't list it."""
    # Arrange
    # Act
    # Assert
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
    assert "REL-5_implicit_deps" in rules
    crit = [f for f in rep.findings if f.rule == "REL-5_implicit_deps"]


def test_e5c5_fires_on_undeclared_scitex_config_crit_0_severity_critical(tmp_path):
    """The 2026-04-28 class-action: src imports scitex_config but pyproject doesn't list it."""
    # Arrange
    # Act
    # Assert
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
    crit = [f for f in rep.findings if f.rule == "REL-5_implicit_deps"]
    assert crit[0].severity == "CRITICAL"


def test_e5c5_fires_on_undeclared_scitex_config_scitex_config_in_crit_0_message(
    tmp_path,
):
    """The 2026-04-28 class-action: src imports scitex_config but pyproject doesn't list it."""
    # Arrange
    # Act
    # Assert
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
    crit = [f for f in rep.findings if f.rule == "REL-5_implicit_deps"]
    assert "scitex-config" in crit[0].message


def test_e5c5_silent_when_dep_declared(tmp_path):
    # Arrange
    # Act
    # Assert
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
    assert "REL-5_implicit_deps" not in [f.rule for f in rep.findings]


def test_e5c5_silent_when_inside_main_guard(tmp_path):
    """`if __name__ == "__main__": import X` is a script-only import."""
    # Arrange
    # Act
    # Assert
    repo = _write_repo(
        tmp_path,
        pyproject="""[project]
name = "demo"
version = "0.1.0"
dependencies = []
""",
        src_files={
            "foo.py": (
                "import numpy as np\n\n"
                "def f(x):\n"
                "    return x * 2\n\n"
                'if __name__ == "__main__":\n'
                "    import scitex_config\n"
                "    print(scitex_config.__version__)\n"
            )
        },
    )
    rep = lint_pyproject(repo, package_name="demo")
    assert "REL-5_implicit_deps" not in [f.rule for f in rep.findings]


def test_e5c5_silent_when_inside_type_checking(tmp_path):
    """`if TYPE_CHECKING: from x import Y` is not a runtime dep."""
    # Arrange
    # Act
    # Assert
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
    assert "REL-5_implicit_deps" not in [f.rule for f in rep.findings]


def test_e5c5_silent_when_function_body_try_except(tmp_path):
    """A try/except ImportError inside a function body is still guarded."""
    # Arrange
    # Act
    # Assert
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
    assert "REL-5_implicit_deps" not in [f.rule for f in rep.findings]


def test_e5c5_silent_when_import_is_guarded(tmp_path):
    """Optional imports wrapped in try/except ImportError don't need a dep.

    scitex-bridge's `try: import figrecipe except ImportError: ...` pattern
    must not trip the linter — it has a fallback path.
    """
    # Arrange
    # Act
    # Assert
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
    assert "REL-5_implicit_deps" not in [f.rule for f in rep.findings]


def test_e5c5_silent_for_self_imports(tmp_path):
    """A package importing its own internals must not flag itself."""
    # Arrange
    # Act
    # Assert
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
    assert "REL-5_implicit_deps" not in [f.rule for f in rep.findings]


# ----------------------------------------------------------------------
# REL-9 — skill bundling
# ----------------------------------------------------------------------


def test_e5c9_fires_when_skills_dir_unbundled_setuptools(tmp_path):
    """setuptools requires explicit package-data — missing both glob and
    entry-point yields two findings."""
    # Arrange
    # Act
    # Assert
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
    rules = [f.rule for f in rep.findings if f.rule == "REL-9_skill_bundling"]
    assert len(rules) == 2  # package-data + entry-point


def test_e5c9_silent_when_hatchling_default(tmp_path):
    """hatchling ships everything in the package dir by default; only the
    entry-point is required."""
    # Arrange
    # Act
    # Assert
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
    assert not [f for f in rep.findings if f.rule == "REL-9_skill_bundling"]


def test_e5c9_fires_when_hatchling_excludes_skills(tmp_path):
    """If hatchling has an explicit exclude that drops _skills, flag it."""
    # Arrange
    # Act
    # Assert
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
    assert [f for f in rep.findings if f.rule == "REL-9_skill_bundling"]


def test_e5c9_silent_when_fully_wired(tmp_path):
    # Arrange
    # Act
    # Assert
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
    assert not [f for f in rep.findings if f.rule == "REL-9_skill_bundling"]


# ----------------------------------------------------------------------
# REL-10 — duplicate TOML table
# ----------------------------------------------------------------------


def test_e5c10_fires_on_duplicate_package_data(tmp_path):
    """Both scitex-resource and scitex-capture hit this on 2026-04-28."""
    # Arrange
    # Act
    # Assert
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
    assert any(f.rule == "REL-10_duplicate_table" for f in findings)


def test_e5c10_silent_on_clean_pyproject(tmp_path):
    # Arrange
    # Act
    # Assert
    fp = tmp_path / "pyproject.toml"
    fp.write_text(
        '[project]\nname = "x"\n[tool.setuptools]\nbuild-backend = "setuptools.build_meta"\n'
    )
    assert check_duplicate_tables(fp) == []


# ----------------------------------------------------------------------
# REL-11 — license
# ----------------------------------------------------------------------


def test_e5c11_fires_on_table_form(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _write_repo(
        tmp_path,
        pyproject="""[project]
name = "demo"
version = "0.1.0"
license = {text = "AGPL-3.0-only"}
""",
    )
    rep = lint_pyproject(repo)
    licenses = [f for f in rep.findings if f.rule == "REL-11_invalid_pep639_license"]
    assert licenses and "deprecated table form" in licenses[0].message


def test_e5c13_fires_on_orphan_legacy_classifier(tmp_path):
    """SPDX license + legacy classifier breaks setuptools 80+."""
    # Arrange
    # Act
    # Assert
    repo = _write_repo(
        tmp_path,
        pyproject="""[project]
name = "demo"
version = "0.1.0"
license = "AGPL-3.0-only"
classifiers = [
    "Operating System :: OS Independent",
    "License :: OSI Approved :: GNU Affero General Public License v3",
]
""",
    )
    rep = lint_pyproject(repo)
    assert any(f.rule == "E5C13_orphan_license_classifier" for f in rep.findings)


def test_e5c13_silent_when_classifiers_have_no_license(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _write_repo(
        tmp_path,
        pyproject="""[project]
name = "demo"
version = "0.1.0"
license = "AGPL-3.0-only"
classifiers = [
    "Operating System :: OS Independent",
]
""",
    )
    rep = lint_pyproject(repo)
    assert not [f for f in rep.findings if f.rule == "E5C13_orphan_license_classifier"]


def test_e5f2_fires_on_umbrella_private_import(tmp_path):
    """Cross-package private imports break when only the standalone is installed."""
    # Arrange
    # Act
    # Assert
    repo = _write_repo(
        tmp_path,
        pyproject="""[project]
name = "demo"
version = "0.1.0"
dependencies = ["scitex-stats>=0.2.0"]
""",
        src_files={
            "foo.py": (
                "from scitex.stats._utils import p2stars\n"
                "def x(): return p2stars(0.05)\n"
            )
        },
    )
    rep = lint_pyproject(repo, package_name="demo")
    assert any(f.rule == "E5F2_internal_api_leak" for f in rep.findings)


def test_e5f2_silent_on_standalone_private_import(tmp_path):
    """Direct standalone import is the canonical fix and must not flag."""
    # Arrange
    # Act
    # Assert
    repo = _write_repo(
        tmp_path,
        pyproject="""[project]
name = "demo"
version = "0.1.0"
dependencies = ["scitex-stats>=0.2.0"]
""",
        src_files={
            "foo.py": (
                "from scitex_stats._utils import p2stars\n"
                "def x(): return p2stars(0.05)\n"
            )
        },
    )
    rep = lint_pyproject(repo, package_name="demo")
    assert not [f for f in rep.findings if f.rule == "E5F2_internal_api_leak"]


def test_e5f2_silent_when_guarded_by_try_except(tmp_path):
    """Optional fallback imports are explicitly handled — don't flag them."""
    # Arrange
    # Act
    # Assert
    repo = _write_repo(
        tmp_path,
        pyproject="""[project]
name = "demo"
version = "0.1.0"
dependencies = ["scitex"]
""",
        src_files={
            "foo.py": (
                "try:\n"
                "    from scitex.io.bundle.kinds._plot._models import FigureModel\n"
                "    HAS = True\n"
                "except ImportError:\n"
                "    HAS = False\n"
            )
        },
    )
    rep = lint_pyproject(repo, package_name="demo")
    assert not [f for f in rep.findings if f.rule == "E5F2_internal_api_leak"]


def test_e5f2_silent_on_public_umbrella_import(tmp_path):
    """`from scitex.stats import ttest_ind` is the public path; not flagged."""
    # Arrange
    # Act
    # Assert
    repo = _write_repo(
        tmp_path,
        pyproject="""[project]
name = "demo"
version = "0.1.0"
dependencies = ["scitex"]
""",
        src_files={"foo.py": "from scitex.stats import ttest_ind\n"},
    )
    rep = lint_pyproject(repo, package_name="demo")
    assert not [f for f in rep.findings if f.rule == "E5F2_internal_api_leak"]


def test_e5l1_release_trigger_hint_for_release_workflow(tmp_path):
    """When pyproject ≠ PyPI and workflow uses release:published, the
    fix-hint must include `gh release create` — operators routinely
    forget this and tag-push alone never publishes."""
    # Arrange
    # Act
    # Assert
    repo = _write_repo(
        tmp_path,
        pyproject="""[project]
name = "demo"
version = "1.0.0"
""",
    )
    wf = repo / ".github" / "workflows" / "publish-pypi.yml"
    wf.parent.mkdir(parents=True)
    wf.write_text("name: Publish\non:\n  release:\n    types: [published]\n")
    rep = lint_pyproject(repo, package_name="demo")
    e5l1 = [f for f in rep.findings if f.rule == "REL-21_dirty_release_state"]
    # Either the tag-mismatch or pypi-mismatch path: at least one finding
    # should mention `gh release create` since the workflow uses
    # release:published trigger.
    assert any("gh release create" in (f.fix_hint or f.detail) for f in e5l1)


def test_e5l1_tag_trigger_fix_hint_omits_gh_release_create(tmp_path):
    """tag-trigger workflows publish on push --tags; no gh release needed."""
    # Arrange
    repo = _write_repo(
        tmp_path,
        pyproject="""[project]
name = "demo"
version = "1.0.0"
""",
    )
    wf = repo / ".github" / "workflows" / "publish-pypi.yml"
    wf.parent.mkdir(parents=True)
    wf.write_text("name: Publish\non:\n  push:\n    tags:\n      - 'v*'\n")
    # Act
    rep = lint_pyproject(repo, package_name="demo")
    e5l1 = [f for f in rep.findings if f.rule == "REL-21_dirty_release_state"]
    fix_hints = [(f.fix_hint or "") for f in e5l1]
    # Assert
    assert all("gh release create" not in h for h in fix_hints)


def test_e5l1_tag_trigger_detail_omits_gh_release_create(tmp_path):
    """tag-trigger workflows publish on push --tags; no gh release needed."""
    # Arrange
    repo = _write_repo(
        tmp_path,
        pyproject="""[project]
name = "demo"
version = "1.0.0"
""",
    )
    wf = repo / ".github" / "workflows" / "publish-pypi.yml"
    wf.parent.mkdir(parents=True)
    wf.write_text("name: Publish\non:\n  push:\n    tags:\n      - 'v*'\n")
    # Act
    rep = lint_pyproject(repo, package_name="demo")
    e5l1 = [f for f in rep.findings if f.rule == "REL-21_dirty_release_state"]
    details = [(f.detail or "") for f in e5l1]
    # Assert
    assert all("gh release create" not in d for d in details)


def test_e5c11_silent_on_spdx(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _write_repo(
        tmp_path,
        pyproject="""[project]
name = "demo"
version = "0.1.0"
license = "AGPL-3.0-only"
""",
    )
    rep = lint_pyproject(repo)
    assert not [f for f in rep.findings if f.rule == "REL-11_invalid_pep639_license"]


# ----------------------------------------------------------------------
# Aggregation
# ----------------------------------------------------------------------


def test_lint_pyproject_aggregates_severity_rep_has_critical(tmp_path):
    # Arrange
    # Act
    # Assert
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
    assert rep.has_critical  # REL-5 fires
    rules = {f.rule for f in rep.findings}


def test_lint_pyproject_aggregates_severity_rep_has_high(tmp_path):
    # Arrange
    # Act
    # Assert
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
    assert rep.has_high  # REL-9 fires too
    rules = {f.rule for f in rep.findings}


def test_lint_pyproject_aggregates_severity_rel_5_implicit_deps_in_rules(tmp_path):
    # Arrange
    # Act
    # Assert
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
    rules = {f.rule for f in rep.findings}
    assert "REL-5_implicit_deps" in rules


def test_lint_pyproject_aggregates_severity_rel_9_skill_bundling_in_rules(tmp_path):
    # Arrange
    # Act
    # Assert
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
    rules = {f.rule for f in rep.findings}
    assert "REL-9_skill_bundling" in rules


def test_lint_pyproject_aggregates_severity_rel_11_invalid_pep639_license_in_rules(
    tmp_path,
):
    # Arrange
    # Act
    # Assert
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
    rules = {f.rule for f in rep.findings}
    assert "REL-11_invalid_pep639_license" in rules


def test_missing_pyproject_emits_e5c1_finding(tmp_path):
    # Arrange
    # Act
    # Assert
    rep = lint_pyproject(tmp_path)
    assert any(f.rule == "E5C1_missing_pyproject" for f in rep.findings)


# ----------------------------------------------------------------------
# REL-31 — __version__ drift
# ----------------------------------------------------------------------


def test_e5f1_fires_when_version_literal_drifts_drift(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _write_repo(
        tmp_path,
        pyproject="""[project]
name = "demo"
version = "0.2.0"
""",
        src_files={"__init__.py": '__version__ = "0.1.0"\n'},
    )
    rep = lint_pyproject(repo, package_name="demo")
    drift = [f for f in rep.findings if f.rule == "REL-31_version_drift"]
    assert drift


def test_e5f1_fires_when_version_literal_drifts_0_1_0_in_drift_0_message_and_0_2_0_in_dr(
    tmp_path,
):
    # Arrange
    # Act
    # Assert
    repo = _write_repo(
        tmp_path,
        pyproject="""[project]
name = "demo"
version = "0.2.0"
""",
        src_files={"__init__.py": '__version__ = "0.1.0"\n'},
    )
    rep = lint_pyproject(repo, package_name="demo")
    drift = [f for f in rep.findings if f.rule == "REL-31_version_drift"]
    assert "0.1.0" in drift[0].message and "0.2.0" in drift[0].message


def test_e5f1_silent_when_version_matches(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _write_repo(
        tmp_path,
        pyproject="""[project]
name = "demo"
version = "0.1.0"
""",
        src_files={"__init__.py": '__version__ = "0.1.0"\n'},
    )
    rep = lint_pyproject(repo, package_name="demo")
    assert not [f for f in rep.findings if f.rule == "REL-31_version_drift"]


def test_e5f1_silent_when_version_dynamic(tmp_path):
    """importlib.metadata-based version can't drift; no finding expected."""
    # Arrange
    # Act
    # Assert
    repo = _write_repo(
        tmp_path,
        pyproject="""[project]
name = "demo"
version = "0.2.0"
""",
        src_files={
            "__init__.py": (
                "from importlib.metadata import version as _v\n"
                "__version__ = _v('demo')\n"
            )
        },
    )
    rep = lint_pyproject(repo, package_name="demo")
    assert not [f for f in rep.findings if f.rule == "REL-31_version_drift"]


# ----------------------------------------------------------------------
# REL-41 — README interfaces callout
# ----------------------------------------------------------------------


def test_e5j1_fires_when_readme_missing_callout(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _write_repo(
        tmp_path,
        pyproject="""[project]
name = "demo"
version = "0.1.0"
""",
    )
    # Long enough to bypass the placeholder filter, but no Interfaces callout.
    (repo / "README.md").write_text("# demo\n\n" + ("This is a real package. " * 30))
    rep = lint_pyproject(repo, package_name="demo")
    assert [f for f in rep.findings if f.rule == "REL-41_readme_interfaces_callout"]


def test_e5j1_silent_when_callout_present(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _write_repo(
        tmp_path,
        pyproject="""[project]
name = "demo"
version = "0.1.0"
""",
    )
    (repo / "README.md").write_text(
        "# demo\n\n"
        "> **Interfaces:** Python ⭐⭐⭐ (primary) · CLI — · MCP — · Skills ⭐⭐ · Hook — · HTTP —\n\n"
        + ("Body. " * 60)
    )
    rep = lint_pyproject(repo, package_name="demo")
    assert not [f for f in rep.findings if f.rule == "REL-41_readme_interfaces_callout"]


def test_e5j1_silent_when_readme_is_placeholder(tmp_path):
    """Don't nag short/stub READMEs (< 500 chars)."""
    # Arrange
    # Act
    # Assert
    repo = _write_repo(
        tmp_path,
        pyproject="""[project]
name = "demo"
version = "0.1.0"
""",
    )
    (repo / "README.md").write_text("# demo\n\nWIP.\n")
    rep = lint_pyproject(repo, package_name="demo")
    assert not [f for f in rep.findings if f.rule == "REL-41_readme_interfaces_callout"]


# ----------------------------------------------------------------------
# REL-12 — missing CLA workflow
# ----------------------------------------------------------------------


def test_e5c12_fires_when_cla_workflow_missing(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _write_repo(
        tmp_path,
        pyproject='[project]\nname = "demo"\nversion = "0.1.0"\n',
    )
    rep = lint_pyproject(repo, package_name="demo")
    assert any(f.rule == "REL-12_missing_cla_workflow" for f in rep.findings)


def test_e5c12_silent_when_cla_workflow_exists(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _write_repo(
        tmp_path,
        pyproject='[project]\nname = "demo"\nversion = "0.1.0"\n',
    )
    wf = repo / ".github" / "workflows" / "cla.yml"
    wf.parent.mkdir(parents=True)
    wf.write_text("name: CLA Assistant\non:\n  pull_request_target:\n")
    rep = lint_pyproject(repo, package_name="demo")
    assert not any(f.rule == "REL-12_missing_cla_workflow" for f in rep.findings)


# ----------------------------------------------------------------------
# E5C14 — malformed cla-signatures/signatures/cla.json
# ----------------------------------------------------------------------


def _init_git_repo_with_cla_signatures(repo: Path, content: str) -> None:
    """Set up a tmp git repo with a `cla-signatures` branch holding given content."""
    import subprocess

    def run(*args: str) -> None:
        subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True,
            capture_output=True,
        )

    run("init", "--quiet", "-b", "main")
    run("config", "user.email", "test@example.com")
    run("config", "user.name", "test")
    run("commit", "--allow-empty", "-m", "init", "--quiet")
    run("checkout", "--quiet", "-b", "cla-signatures")
    sigs = repo / "signatures"
    sigs.mkdir()
    (sigs / "cla.json").write_text(content)
    run("add", "signatures/cla.json")
    run("commit", "-m", "init signatures", "--quiet")
    run("checkout", "--quiet", "main")


def test_e5c14_fires_on_bare_array_signatures(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _write_repo(
        tmp_path,
        pyproject='[project]\nname = "demo"\nversion = "0.1.0"\n',
    )
    _init_git_repo_with_cla_signatures(repo, "[]\n")
    rep = lint_pyproject(repo, package_name="demo")
    assert any(f.rule == "E5C14_malformed_cla_signatures" for f in rep.findings)


def test_e5c14_silent_on_proper_object_signatures(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _write_repo(
        tmp_path,
        pyproject='[project]\nname = "demo"\nversion = "0.1.0"\n',
    )
    _init_git_repo_with_cla_signatures(repo, '{"signedContributors": []}\n')
    rep = lint_pyproject(repo, package_name="demo")
    assert not any(f.rule == "E5C14_malformed_cla_signatures" for f in rep.findings)


def test_e5c14_silent_when_branch_absent(tmp_path):
    """No cla-signatures branch is a healthy fresh-repo state — no finding."""
    # Arrange
    # Act
    # Assert
    repo = _write_repo(
        tmp_path,
        pyproject='[project]\nname = "demo"\nversion = "0.1.0"\n',
    )
    rep = lint_pyproject(repo, package_name="demo")
    assert not any(f.rule == "E5C14_malformed_cla_signatures" for f in rep.findings)
