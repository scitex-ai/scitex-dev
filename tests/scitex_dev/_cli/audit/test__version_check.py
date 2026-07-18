#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The auditor-staleness self-check, now dogfooding scitex_dev.versioning.

Driven through real ``StaticSources`` (a genuine ``Sources`` implementation
fed recorded evidence — no mocks, no network) and real env vars. The whole
point of the migration is the editable-no-clobber case: an editable checkout
whose working tree is current must NOT warn and must NEVER suggest
``pip install -U``. That danger is asserted directly here.
"""

from __future__ import annotations

import io
import os

import pytest

from scitex_dev._cli.audit._version_check import config, warn_if_stale
from scitex_dev.versioning import StaticSources


@pytest.fixture
def env():
    """Set/unset real env vars for one test; restore exactly on teardown."""
    saved: dict[str, str | None] = {}

    def _set(name: str, value: str | None) -> None:
        if name not in saved:
            saved[name] = os.environ.get(name)
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value

    yield _set

    for name, old in saved.items():
        if old is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = old


@pytest.fixture(autouse=True)
def _clear_skip_knobs(env):
    """Every test starts with the skip/silent knobs OFF unless it sets them."""
    env("SCITEX_DEV_SKIP_VERSION_CHECK", None)
    env("SCITEX_DEV_VERSION_CHECK_SILENT", None)


def _editable(*, ahead_behind, metadata="0.29.0", latest="0.31.0"):
    """An editable checkout: judged by CONTENT, never the fossil metadata."""
    return StaticSources(
        install_kind="editable",
        metadata_version=metadata,
        module_origin="/home/ywatanabe/proj/scitex-dev/src/scitex_dev/__init__.py",
        executable="/home/ywatanabe/proj/scitex-dev/.venv/bin/python",
        pypi_latest=latest,
        editable_ahead_behind=ahead_behind,
    )


def _wheel(*, effective, latest):
    return StaticSources(
        install_kind="wheel",
        effective_version=effective,
        metadata_version=effective,
        module_origin="/opt/venv/lib/python3.12/site-packages/scitex_dev/__init__.py",
        executable="/opt/venv/bin/python",
        pypi_latest=latest,
    )


# --------------------------------------------------------------------------
# (a) editable + current tree -> no warn, no pip-install-U (the no-clobber
#     case: the exact danger the primitive removes from this self-check)
# --------------------------------------------------------------------------
def test_editable_current_tree_returns_false(env):
    # Arrange — working tree carries every released commit (behind==0), even
    # though the frozen metadata (0.29.0) trails PyPI (0.31.0).
    out = io.StringIO()
    # Act
    warned = warn_if_stale(stream=out, sources=_editable(ahead_behind=(3, 0)))
    # Assert
    assert warned is False


def test_editable_current_tree_prints_nothing(env):
    # Arrange
    out = io.StringIO()
    # Act
    warn_if_stale(stream=out, sources=_editable(ahead_behind=(3, 0)))
    # Assert
    assert out.getvalue() == ""


def test_editable_current_tree_never_suggests_pip_install_u(env):
    # Arrange
    out = io.StringIO()
    # Act
    warn_if_stale(stream=out, sources=_editable(ahead_behind=(0, 0)))
    # Assert — the clobber remedy must never appear for a current editable.
    assert "pip install -U" not in out.getvalue()


def test_editable_behind_returns_true(env):
    # Arrange — editable tree BEHIND its latest tag: genuinely stale.
    out = io.StringIO()
    # Act
    warned = warn_if_stale(stream=out, sources=_editable(ahead_behind=(0, 4)))
    # Assert
    assert warned is True


def test_editable_behind_remedy_is_git_pull(env):
    # Arrange
    out = io.StringIO()
    # Act
    warn_if_stale(stream=out, sources=_editable(ahead_behind=(0, 4)))
    # Assert
    assert "git pull" in out.getvalue()


def test_editable_behind_never_suggests_pip_install_u(env):
    # Arrange — even when genuinely behind, an editable fix is a pull, never
    # a wheel clobber.
    out = io.StringIO()
    # Act
    warn_if_stale(stream=out, sources=_editable(ahead_behind=(0, 4)))
    # Assert
    assert "pip install -U" not in out.getvalue()


# --------------------------------------------------------------------------
# (b) wheel genuinely behind -> warns with pip-install-U + names the binary
# --------------------------------------------------------------------------
def test_wheel_behind_returns_true(env):
    # Arrange
    out = io.StringIO()
    # Act
    warned = warn_if_stale(
        stream=out, sources=_wheel(effective="0.29.0", latest="0.31.0")
    )
    # Assert
    assert warned is True


def test_wheel_behind_remedy_is_pip_install_u(env):
    # Arrange
    out = io.StringIO()
    # Act
    warn_if_stale(stream=out, sources=_wheel(effective="0.29.0", latest="0.31.0"))
    # Assert
    assert "pip install -U" in out.getvalue()


def test_wheel_behind_names_the_origin(env):
    # Arrange
    out = io.StringIO()
    # Act
    warn_if_stale(stream=out, sources=_wheel(effective="0.29.0", latest="0.31.0"))
    # Assert — the warning must say WHICH scitex-dev is stale (package origin).
    assert "/opt/venv" in out.getvalue()


def test_wheel_behind_names_the_interpreter(env):
    # Arrange
    out = io.StringIO()
    # Act
    warn_if_stale(stream=out, sources=_wheel(effective="0.29.0", latest="0.31.0"))
    # Assert
    assert "/opt/venv/bin/python" in out.getvalue()


def test_wheel_current_returns_false(env):
    # Arrange
    out = io.StringIO()
    # Act
    warned = warn_if_stale(
        stream=out, sources=_wheel(effective="0.31.0", latest="0.31.0")
    )
    # Assert
    assert warned is False


def test_wheel_current_prints_nothing(env):
    # Arrange
    out = io.StringIO()
    # Act
    warn_if_stale(stream=out, sources=_wheel(effective="0.31.0", latest="0.31.0"))
    # Assert
    assert out.getvalue() == ""


# --------------------------------------------------------------------------
# (c) UNKNOWN (PyPI unreachable) -> no false stale-warn
# --------------------------------------------------------------------------
def test_pypi_unreachable_returns_false(env):
    # Arrange — a wheel whose PyPI latest is unknown (offline). The old fossil
    # compare could still fire; the tri-state must stay silent.
    out = io.StringIO()
    # Act
    warned = warn_if_stale(stream=out, sources=_wheel(effective="0.29.0", latest=None))
    # Assert
    assert warned is False


def test_pypi_unreachable_prints_nothing(env):
    # Arrange
    out = io.StringIO()
    # Act
    warn_if_stale(stream=out, sources=_wheel(effective="0.29.0", latest=None))
    # Assert
    assert out.getvalue() == ""


def test_editable_no_checkout_is_not_stale(env):
    # Arrange — editable install but no git checkout/tag to compare against.
    out = io.StringIO()
    # Act
    warned = warn_if_stale(stream=out, sources=_editable(ahead_behind=None))
    # Assert
    assert warned is False


# --------------------------------------------------------------------------
# (d) env skip / silent knobs still work
# --------------------------------------------------------------------------
def test_skip_env_returns_false(env):
    # Arrange — a genuinely stale wheel, but the skip knob is set.
    env("SCITEX_DEV_SKIP_VERSION_CHECK", "1")
    out = io.StringIO()
    # Act
    warned = warn_if_stale(
        stream=out, sources=_wheel(effective="0.29.0", latest="0.31.0")
    )
    # Assert
    assert warned is False


def test_skip_env_prints_nothing(env):
    # Arrange
    env("SCITEX_DEV_SKIP_VERSION_CHECK", "1")
    out = io.StringIO()
    # Act
    warn_if_stale(stream=out, sources=_wheel(effective="0.29.0", latest="0.31.0"))
    # Assert
    assert out.getvalue() == ""


def test_silent_env_still_signals_true(env):
    # Arrange — stale wheel, silent knob set: no print, but caller still learns.
    env("SCITEX_DEV_VERSION_CHECK_SILENT", "1")
    out = io.StringIO()
    # Act
    warned = warn_if_stale(
        stream=out, sources=_wheel(effective="0.29.0", latest="0.31.0")
    )
    # Assert
    assert warned is True


def test_silent_env_suppresses_the_print(env):
    # Arrange
    env("SCITEX_DEV_VERSION_CHECK_SILENT", "1")
    out = io.StringIO()
    # Act
    warn_if_stale(stream=out, sources=_wheel(effective="0.29.0", latest="0.31.0"))
    # Assert
    assert out.getvalue() == ""


# --------------------------------------------------------------------------
# resilience: a broken probe must never break the audit
# --------------------------------------------------------------------------
def _boom_sources():
    class _Boom:
        def __getattr__(self, name):
            def _raise(*a, **k):
                raise RuntimeError("boom")

            return _raise

    return _Boom()


def test_broken_sources_returns_false(env):
    # Arrange — a Sources whose every method raises.
    out = io.StringIO()
    # Act
    warned = warn_if_stale(stream=out, sources=_boom_sources())
    # Assert
    assert warned is False


def test_broken_sources_prints_nothing(env):
    # Arrange
    out = io.StringIO()
    # Act
    warn_if_stale(stream=out, sources=_boom_sources())
    # Assert
    assert out.getvalue() == ""


# --------------------------------------------------------------------------
# config: targets scitex-dev, shipping-pipeline checks deliberately disabled
# --------------------------------------------------------------------------
def test_config_dist_is_scitex_dev():
    # Arrange
    cfg = config()
    # Act
    dist = cfg.dist
    # Assert
    assert dist == "scitex-dev"


def test_config_module_is_scitex_dev():
    # Arrange
    cfg = config()
    # Act
    module = cfg.module
    # Assert
    assert module == "scitex_dev"


def test_config_release_workflow_disabled():
    # Arrange
    cfg = config()
    # Act
    workflow = cfg.release_workflow
    # Assert
    assert workflow is None


def test_config_systemd_unit_disabled():
    # Arrange
    cfg = config()
    # Act
    unit = cfg.systemd_unit
    # Assert
    assert unit is None


# EOF
