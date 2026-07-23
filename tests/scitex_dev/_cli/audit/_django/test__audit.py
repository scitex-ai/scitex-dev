"""Tests for the Django "apps and config" auditor (DJ<n> rules).

Each rule has a positive test (fires on a synthetic broken repo); the
conforming fixture has negative tests (stays silent on a clean repo). The
clean fixture is a minimal-but-conforming mirror of scitex-hub's layout
per ADR 0002.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from scitex_dev._cli.audit._django import RULES, audit_django
from scitex_dev._cli.audit._django._audit import Violation
from scitex_dev._cli.audit._django._checks import (
    check_apps,
    check_config,
    check_deps,
    check_pip_package,
    check_pytest_config,
    check_templates_static,
    is_django_app,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_conforming_repo(tmp_path: Path, name: str = "scitex-demo") -> Path:
    """Build a minimal-but-conforming "apps and config" Django repo."""
    import_name = name.replace("-", "_")

    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nname = "{name}"\nversion = "0.1.0"\n'
        'dependencies = ["click>=8.0"]\n'
        "[project.optional-dependencies]\n"
        'all = ["Django>=5.2", "djangorestframework>=3.16"]\n'
        'dev = ["ruff"]\n'
    )
    (tmp_path / "manage.py").write_text(
        "import os\n"
        'os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")\n'
    )

    config = tmp_path / "config"
    config.mkdir()
    (config / "__init__.py").write_text("")
    (config / "urls.py").write_text("urlpatterns = []\n")
    (config / "asgi.py").write_text("application = None\n")
    (config / "wsgi.py").write_text("application = None\n")

    settings = config / "settings"
    settings.mkdir()
    (settings / "__init__.py").write_text(
        'import os\nenv = os.environ.get("SCITEX_DEMO_ENV", "development")\n'
        "from .settings_dev import *\n"
    )
    (settings / "settings_shared.py").write_text("INSTALLED_APPS = []\n")
    (settings / "settings_dev.py").write_text("from .settings_shared import *\n")
    (settings / "settings_prod.py").write_text("from .settings_shared import *\n")

    apps = tmp_path / "apps"
    (apps / "infra").mkdir(parents=True)
    (apps / "__init__.py").write_text("")
    (apps / "infra" / "__init__.py").write_text("")
    demo_app = apps / "infra" / "demo_app"
    demo_app.mkdir()
    (demo_app / "__init__.py").write_text("")
    (demo_app / "apps.py").write_text(
        "from django.apps import AppConfig\n"
        "class DemoConfig(AppConfig):\n"
        '    name = "apps.infra.demo_app"\n'
    )

    (tmp_path / "templates").mkdir()
    (tmp_path / "static").mkdir()

    src = tmp_path / "src" / import_name
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("")

    return tmp_path


def _violations(repo: Path, name: str = "scitex-demo") -> list[str]:
    """Run all rule checks directly; return the rule codes that fired."""
    out: list[Violation] = []
    check_config(repo, Violation, out)
    check_apps(repo, Violation, out)
    check_templates_static(repo, Violation, out)
    check_pip_package(repo, name, Violation, out)
    check_deps(repo, Violation, out)
    return [v.rule for v in out]


# ---------------------------------------------------------------------------
# Negative: conforming repo is clean
# ---------------------------------------------------------------------------


def test_conforming_repo_has_no_violations(tmp_path):
    # Arrange
    repo = _make_conforming_repo(tmp_path)
    # Act
    fired = _violations(repo)
    # Assert
    assert fired == []


def test_conforming_repo_audit_django_exit_zero(tmp_path):
    # Arrange
    repo = _make_conforming_repo(tmp_path)
    # Act
    rc = audit_django("scitex-demo", repo=repo, severity="info")
    # Assert
    assert rc == 0


# ---------------------------------------------------------------------------
# §1 — config/
# ---------------------------------------------------------------------------


def test_dj101_fires_without_config(tmp_path):
    # Arrange
    repo = _make_conforming_repo(tmp_path)
    shutil.rmtree(repo / "config")
    # Act
    fired = _violations(repo)
    # Assert
    assert "DJ-101" in fired


def test_dj102_fires_when_settings_is_single_module(tmp_path):
    # Arrange
    repo = _make_conforming_repo(tmp_path)
    shutil.rmtree(repo / "config" / "settings")
    (repo / "config" / "settings.py").write_text("INSTALLED_APPS = []\n")
    # Act
    fired = _violations(repo)
    # Assert
    assert "DJ-102" in fired


def test_dj103_fires_when_settings_init_has_no_env_dispatch(tmp_path):
    # Arrange — overwrite config/settings/__init__.py so it carries neither
    # the SCITEX_<PKG>_ENV dispatch token nor a `from .settings_<env> import *`.
    repo = _make_conforming_repo(tmp_path)
    (repo / "config" / "settings" / "__init__.py").write_text(
        "INSTALLED_APPS = []\n"
    )
    # Act
    fired = _violations(repo)
    # Assert
    assert "DJ-103" in fired


def test_dj105_fires_without_per_env_settings_modules(tmp_path):
    # Arrange — remove both per-env settings modules
    repo = _make_conforming_repo(tmp_path)
    (repo / "config" / "settings" / "settings_dev.py").unlink()
    (repo / "config" / "settings" / "settings_prod.py").unlink()
    # Act
    fired = _violations(repo)
    # Assert
    assert "DJ-105" in fired


def test_dj104_fires_without_settings_shared(tmp_path):
    # Arrange
    repo = _make_conforming_repo(tmp_path)
    (repo / "config" / "settings" / "settings_shared.py").unlink()
    # Act
    fired = _violations(repo)
    # Assert
    assert "DJ-104" in fired


def test_dj106_fires_without_urls(tmp_path):
    # Arrange
    repo = _make_conforming_repo(tmp_path)
    (repo / "config" / "urls.py").unlink()
    # Act
    fired = _violations(repo)
    # Assert
    assert "DJ-106" in fired


def test_dj108_fires_without_manage_py(tmp_path):
    # Arrange
    repo = _make_conforming_repo(tmp_path)
    (repo / "manage.py").unlink()
    # Act
    fired = _violations(repo)
    # Assert
    assert "DJ-108" in fired


def test_dj109_fires_when_manage_py_omits_config_settings(tmp_path):
    # Arrange — manage.py present but pointing at a non-config settings module
    repo = _make_conforming_repo(tmp_path)
    (repo / "manage.py").write_text(
        "import os\n"
        'os.environ.setdefault("DJANGO_SETTINGS_MODULE", "demo.settings")\n'
    )
    # Act
    fired = _violations(repo)
    # Assert
    assert "DJ-109" in fired


def test_dj110_fires_with_legacy_project_package(tmp_path):
    # Arrange
    repo = _make_conforming_repo(tmp_path)
    legacy = repo / "demo"
    legacy.mkdir()
    (legacy / "settings.py").write_text("X = 1\n")
    (legacy / "wsgi.py").write_text("application = None\n")
    # Act
    fired = _violations(repo)
    # Assert
    assert "DJ-110" in fired


# ---------------------------------------------------------------------------
# §2 — apps/
# ---------------------------------------------------------------------------


def test_dj201_fires_without_apps_dir(tmp_path):
    # Arrange
    repo = _make_conforming_repo(tmp_path)
    shutil.rmtree(repo / "apps")
    # Act
    fired = _violations(repo)
    # Assert
    assert "DJ-201" in fired


def test_dj202_fires_when_apps_dir_missing_init(tmp_path):
    # Arrange — apps/ exists but has no __init__.py
    repo = _make_conforming_repo(tmp_path)
    (repo / "apps" / "__init__.py").unlink()
    # Act
    fired = _violations(repo)
    # Assert
    assert "DJ-202" in fired


def test_dj203_fires_when_no_registered_apps(tmp_path):
    # Arrange — remove the only registered app, leaving apps/ empty of apps.py
    repo = _make_conforming_repo(tmp_path)
    shutil.rmtree(repo / "apps" / "infra" / "demo_app")
    # Act
    fired = _violations(repo)
    # Assert
    assert "DJ-203" in fired


def test_dj204_fires_for_app_without_appconfig(tmp_path):
    # Arrange
    repo = _make_conforming_repo(tmp_path)
    broken = repo / "apps" / "infra" / "broken_app"
    broken.mkdir()
    (broken / "__init__.py").write_text("")
    # Act
    fired = _violations(repo)
    # Assert
    assert "DJ-204" in fired


# ---------------------------------------------------------------------------
# §3 — templates / static
# ---------------------------------------------------------------------------


def test_dj301_fires_without_templates(tmp_path):
    # Arrange
    repo = _make_conforming_repo(tmp_path)
    (repo / "templates").rmdir()
    # Act
    fired = _violations(repo)
    # Assert
    assert "DJ-301" in fired


def test_dj302_fires_without_static(tmp_path):
    # Arrange
    repo = _make_conforming_repo(tmp_path)
    (repo / "static").rmdir()
    # Act
    fired = _violations(repo)
    # Assert
    assert "DJ-302" in fired


# ---------------------------------------------------------------------------
# §4 — pip package relationship
# ---------------------------------------------------------------------------


def test_dj401_fires_without_src_package(tmp_path):
    # Arrange
    repo = _make_conforming_repo(tmp_path)
    shutil.rmtree(repo / "src")
    # Act
    fired = _violations(repo)
    # Assert
    assert "DJ-401" in fired


def test_dj402_fires_when_django_nested_in_pip_package(tmp_path):
    # Arrange
    repo = _make_conforming_repo(tmp_path)
    nested = repo / "src" / "scitex_demo" / "config"
    (nested / "settings").mkdir(parents=True)
    (nested / "__init__.py").write_text("")
    (nested / "settings" / "__init__.py").write_text("")
    # Act
    fired = _violations(repo)
    # Assert
    assert "DJ-402" in fired


# ---------------------------------------------------------------------------
# §5 — deps
# ---------------------------------------------------------------------------


def test_dj501_fires_without_django_dependency(tmp_path):
    # Arrange
    repo = _make_conforming_repo(tmp_path)
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "scitex-demo"\nversion = "0.1.0"\n'
        'dependencies = ["click>=8.0"]\n'
    )
    # Act
    fired = _violations(repo)
    # Assert
    assert "DJ-501" in fired


def test_dj502_fires_with_django_subextra(tmp_path):
    # Arrange
    repo = _make_conforming_repo(tmp_path)
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "scitex-demo"\nversion = "0.1.0"\n'
        'dependencies = ["click>=8.0"]\n'
        "[project.optional-dependencies]\n"
        'django = ["Django>=5.2"]\n'
    )
    # Act
    fired = _violations(repo)
    # Assert
    assert "DJ-502" in fired


def test_dj503_fires_with_e2e_flags_in_addopts(tmp_path):
    # Arrange
    repo = _make_conforming_repo(tmp_path)
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "scitex-demo"\nversion = "0.1.0"\n'
        'dependencies = ["click>=8.0"]\n'
        "[project.optional-dependencies]\n"
        'all = ["Django>=5.2"]\n'
        "[tool.pytest.ini_options]\n"
        'addopts = "-v --headed --browser chromium"\n'
    )
    out: list[Violation] = []
    # Act
    check_pytest_config(repo, Violation, out)
    # Assert
    assert "DJ-503" in [v.rule for v in out]


def test_dj503_fires_with_list_addopts(tmp_path):
    # Arrange
    repo = _make_conforming_repo(tmp_path)
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "scitex-demo"\nversion = "0.1.0"\n'
        "[tool.pytest.ini_options]\n"
        'addopts = ["-v", "--video", "on"]\n'
    )
    out: list[Violation] = []
    # Act
    check_pytest_config(repo, Violation, out)
    # Assert
    assert "DJ-503" in [v.rule for v in out]


def test_dj503_silent_on_clean_addopts(tmp_path):
    # Arrange
    repo = _make_conforming_repo(tmp_path)
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "scitex-demo"\nversion = "0.1.0"\n'
        "[tool.pytest.ini_options]\n"
        'addopts = "-v --tb=short --strict-markers"\n'
    )
    out: list[Violation] = []
    # Act
    check_pytest_config(repo, Violation, out)
    # Assert
    assert "DJ-503" not in [v.rule for v in out]


def test_dj503_silent_without_pytest_config(tmp_path):
    # Arrange — conforming repo has no [tool.pytest.ini_options]
    repo = _make_conforming_repo(tmp_path)
    out: list[Violation] = []
    # Act
    check_pytest_config(repo, Violation, out)
    # Assert
    assert "DJ-503" not in [v.rule for v in out]


# ---------------------------------------------------------------------------
# Skip behavior + metadata
# ---------------------------------------------------------------------------


def test_non_django_repo_is_not_detected_as_django_app(tmp_path):
    # Arrange
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "scitex-lib"\nversion = "0.1.0"\n'
    )
    # Act
    is_django = is_django_app(tmp_path)
    # Assert
    assert is_django is False


def test_non_django_repo_audit_exits_zero(tmp_path):
    # Arrange
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "scitex-lib"\nversion = "0.1.0"\n'
    )
    # Act
    rc = audit_django("scitex-lib", repo=tmp_path)
    # Assert
    assert rc == 0


def test_all_rule_codes_are_dj_namespaced():
    # Arrange
    codes = list(RULES)
    # Act
    bad = [c for c in codes if not c.startswith("DJ-")]
    # Assert
    assert bad == []


def test_all_rules_have_valid_severity():
    # Arrange
    severities = {rule.severity for rule in RULES.values()}
    # Act
    invalid = severities - {"E", "W", "I"}
    # Assert
    assert invalid == set()
