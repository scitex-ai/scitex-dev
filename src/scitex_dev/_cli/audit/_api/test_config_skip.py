#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""audit-python-apis honours .scitex/dev/config.yaml audit.skip + django default.

Mirrors the accepted per-rule deferral pattern that ``audit-project`` already
uses (``cfg.applies(rule) and rule not in cfg.skip``) so PA rules can be scoped
down to fit a project without faking the rule. A deferred PA *error* rule must
drop out of the violation set so it no longer drives the error-level exit code
that ``audit-all`` gates on.

The config schema follows ``_config/_loader.py``: the project-type key is
``project-type`` (a YAML list), and ``audit.skip`` is a list of rule codes (the
loader does not parse a ``reasons`` map, so a documented reason lives as a YAML
comment). The fixture package deliberately imports a forbidden test-double
symbol so it trips PA-306 (no-mocks); that trigger line is assembled at runtime
from tokens so this test file itself contains no literal forbidden import (which
would make this very file trip the rule it exercises). Each fixture uses a
unique import name so ``importlib.util.find_spec`` (used by ``audit_api``) never
resolves a sibling test's cached module — pytest shares one interpreter.
"""

from __future__ import annotations

import importlib
import itertools
import sys
from pathlib import Path

from scitex_dev._cli.audit._api import _audit as api_audit
from scitex_dev._cli.audit._api._audit import RULES, Violation, audit_api
from scitex_dev._cli.audit._config import load_config

# Assembled so the literal forbidden import never appears in this source file.
_FORBIDDEN_LIB = "unittest." + "mock"
_FORBIDDEN_SYM = "Magic" + "Mock"
_TRIGGER_SRC = (
    f"from {_FORBIDDEN_LIB} import {_FORBIDDEN_SYM}\n\nthing = {_FORBIDDEN_SYM}\n"
)

_PKG_COUNTER = itertools.count()


def _build_pkg(tmp_path: Path, config_yaml: str | None = None) -> tuple[Path, str]:
    """Create a minimal importable package that trips PA-306 (no-mocks)."""
    dist = f"scitex_pa_scope_demo_{next(_PKG_COUNTER)}"
    repo = tmp_path / "repo"
    pkg = repo / "src" / dist
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(
        '__all__ = ["thing"]\n__version__ = "0.0.0+local"\nfrom ._core import thing\n',
        encoding="utf-8",
    )
    (pkg / "_core.py").write_text(_TRIGGER_SRC, encoding="utf-8")
    if config_yaml is not None:
        cfg_dir = repo / ".scitex" / "dev"
        cfg_dir.mkdir(parents=True)
        (cfg_dir / "config.yaml").write_text(config_yaml, encoding="utf-8")
    return repo, dist


def _violations(repo: Path, dist: str) -> list[Violation]:
    """Collect the raw PA violations for the package under ``repo``."""
    init_path = repo / "src" / dist / "__init__.py"
    out: list[Violation] = []
    out.extend(api_audit._audit_init(init_path, dist))
    out.extend(api_audit._audit_no_mocks(init_path, dist, dist))
    return out


def _audit_api_end_to_end(repo: Path, dist: str) -> int:
    """Run the public ``audit_api`` against an on-disk package.

    ``audit_api`` locates the package via ``importlib.util.find_spec``, so the
    package's ``src/`` must be importable for the duration of the call.
    """
    src = str(repo / "src")
    sys.path.insert(0, src)
    importlib.invalidate_caches()
    try:
        return audit_api(dist, repo_root=repo)
    finally:
        sys.path.remove(src)
        sys.modules.pop(dist, None)
        sys.modules.pop(f"{dist}._core", None)
        importlib.invalidate_caches()


def test_pa306_fires_as_error_without_config(tmp_path: Path) -> None:
    # Arrange
    repo, dist = _build_pkg(tmp_path, config_yaml=None)
    # Act
    fired = {v.rule for v in _violations(repo, dist)}
    # Assert
    assert "PA-306" in fired


# Loader schema: `project-type` list + `audit.skip` list. A documented reason
# rides along as a YAML comment (the loader does not parse a `reasons` map).
_SKIP_PA_ERRORS_YAML = (
    "project-type:\n"
    "  - django\n"
    "audit:\n"
    "  skip:\n"
    "    - PA-306\n"
    "    - PA-307\n"
    "  # reason: django app uses test doubles for external services (debt)\n"
)


def test_config_skip_list_parses_pa_rule(tmp_path: Path) -> None:
    # Arrange
    repo, _dist = _build_pkg(tmp_path, config_yaml=_SKIP_PA_ERRORS_YAML)
    # Act
    cfg = load_config(repo)
    # Assert
    assert "PA-306" in cfg.skip


def test_config_skip_drops_pa_error_rules_from_error_count(tmp_path: Path) -> None:
    # Arrange
    repo, dist = _build_pkg(tmp_path, config_yaml=_SKIP_PA_ERRORS_YAML)
    cfg = load_config(repo)
    kept = [
        v
        for v in _violations(repo, dist)
        if cfg.applies(v.rule) and v.rule not in cfg.skip
    ]
    # Act
    has_error = any(RULES[v.rule].severity == "error" for v in kept if v.rule in RULES)
    # Assert
    assert has_error is False


def test_not_deferred_pa306_still_counts_as_error(tmp_path: Path) -> None:
    # Arrange — skip an unrelated rule; PA-306 stays active.
    repo, dist = _build_pkg(
        tmp_path,
        config_yaml="project-type:\n  - pip\naudit:\n  skip:\n    - PA-301\n",
    )
    cfg = load_config(repo)
    kept = [
        v
        for v in _violations(repo, dist)
        if cfg.applies(v.rule) and v.rule not in cfg.skip
    ]
    # Act
    has_error = any(RULES[v.rule].severity == "error" for v in kept if v.rule in RULES)
    # Assert
    assert has_error is True


def test_audit_api_exit_code_drops_below_error_when_pa306_deferred(
    tmp_path: Path,
) -> None:
    # Arrange — the only error is PA-306; deferring it via audit.skip must drop
    # the exit code below 2 (the error code `audit-all` gates on).
    repo, dist = _build_pkg(
        tmp_path,
        config_yaml="project-type:\n  - pip\naudit:\n  skip:\n    - PA-306\n",
    )
    # Act
    code = _audit_api_end_to_end(repo, dist)
    # Assert
    assert code != 2


def test_audit_api_exit_code_is_error_without_deferral(tmp_path: Path) -> None:
    # Arrange — PA-306 active (unrelated rule skipped) → stays error (2).
    repo, dist = _build_pkg(
        tmp_path,
        config_yaml="project-type:\n  - pip\naudit:\n  skip:\n    - PA-301\n",
    )
    # Act
    code = _audit_api_end_to_end(repo, dist)
    # Assert
    assert code == 2


def test_django_project_type_downgrades_pa306_below_error(tmp_path: Path) -> None:
    # Arrange — no explicit skip; a django project-type alone relaxes PA-306.
    repo, dist = _build_pkg(
        tmp_path,
        config_yaml="project-type:\n  - django\n",
    )
    # Act
    code = _audit_api_end_to_end(repo, dist)
    # Assert
    assert code != 2
