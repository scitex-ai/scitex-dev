#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The every-invocation warning: speak on STALE and ONLY on STALE.

Driven through the real cache file and real env vars — the same seams
production uses. ``warn_if_stale`` writes to an injected stream so output is
captured without touching sys.stderr.
"""

from __future__ import annotations

import io
import time

from scitex_dev.versioning._cache import write_cache
from scitex_dev.versioning._config import VersioningConfig
from scitex_dev.versioning._model import Currency, Finding, Report
from scitex_dev.versioning._warn import EXIT_STALE, emit_once, warn_if_stale

CFG = VersioningConfig(dist="scitex-dev")


def _write(path, state, at=None):
    report = Report(
        findings=(
            Finding(
                check="install-currency",
                state=state,
                summary="installed 0.29.0 is BEHIND PyPI 0.31.0",
                remedy="python -m pip install -U 'scitex-dev==0.31.0'",
            ),
        ),
        generated_at=time.time() if at is None else at,
    )
    write_cache(CFG, report, path)
    return path


def test_stale_cache_warns_on_stream(tmp_path, env):
    # Arrange
    cache = _write(tmp_path / "f.json", Currency.STALE)
    env(CFG.env_cache, str(cache))
    env(CFG.env_quiet, None)
    env(CFG.env_severity, None)
    out = io.StringIO()
    # Act
    warn_if_stale(CFG, stream=out)
    # Assert
    assert "BEHIND PyPI 0.31.0" in out.getvalue()


def test_warning_names_the_fix_command(tmp_path, env):
    # Arrange
    cache = _write(tmp_path / "f.json", Currency.STALE)
    env(CFG.env_cache, str(cache))
    env(CFG.env_quiet, None)
    env(CFG.env_severity, None)
    out = io.StringIO()
    # Act
    warn_if_stale(CFG, stream=out)
    # Assert
    assert "pip install -U 'scitex-dev==0.31.0'" in out.getvalue()


def test_fresh_cache_says_nothing(tmp_path, env):
    # Arrange
    cache = _write(tmp_path / "f.json", Currency.FRESH)
    env(CFG.env_cache, str(cache))
    env(CFG.env_quiet, None)
    env(CFG.env_severity, None)
    out = io.StringIO()
    # Act
    warn_if_stale(CFG, stream=out)
    # Assert
    assert out.getvalue() == ""


def test_unknown_cache_says_nothing(tmp_path, env):
    # Arrange
    cache = _write(tmp_path / "f.json", Currency.UNKNOWN)
    env(CFG.env_cache, str(cache))
    env(CFG.env_quiet, None)
    env(CFG.env_severity, None)
    out = io.StringIO()
    # Act
    warn_if_stale(CFG, stream=out)
    # Assert
    assert out.getvalue() == ""


def test_missing_cache_says_nothing(tmp_path, env):
    # Arrange
    env(CFG.env_cache, str(tmp_path / "absent.json"))
    env(CFG.env_quiet, None)
    env(CFG.env_severity, None)
    out = io.StringIO()
    # Act
    warn_if_stale(CFG, stream=out)
    # Assert
    assert out.getvalue() == ""


def test_corrupt_cache_exits_zero(tmp_path, env):
    # Arrange
    cache = tmp_path / "f.json"
    cache.write_text("}{ not json at all")
    env(CFG.env_cache, str(cache))
    env(CFG.env_quiet, None)
    env(CFG.env_severity, None)
    out = io.StringIO()
    # Act
    code = warn_if_stale(CFG, stream=out)
    # Assert
    assert code == 0


def test_quiet_env_silences_the_warning(tmp_path, env):
    # Arrange
    cache = _write(tmp_path / "f.json", Currency.STALE)
    env(CFG.env_cache, str(cache))
    env(CFG.env_quiet, "1")
    out = io.StringIO()
    # Act
    warn_if_stale(CFG, stream=out)
    # Assert
    assert out.getvalue() == ""


def test_warn_severity_exits_zero(tmp_path, env):
    # Arrange
    cache = _write(tmp_path / "f.json", Currency.STALE)
    env(CFG.env_cache, str(cache))
    env(CFG.env_quiet, None)
    env(CFG.env_severity, None)
    out = io.StringIO()
    # Act
    code = warn_if_stale(CFG, stream=out)
    # Assert
    assert code == 0


def test_error_severity_returns_stale_exit_code(tmp_path, env):
    # Arrange
    cache = _write(tmp_path / "f.json", Currency.STALE)
    env(CFG.env_cache, str(cache))
    env(CFG.env_quiet, None)
    env(CFG.env_severity, "error")
    out = io.StringIO()
    # Act
    code = warn_if_stale(CFG, stream=out)
    # Assert
    assert code == EXIT_STALE


def test_error_severity_still_silent_when_unknown(tmp_path, env):
    # Arrange
    env(CFG.env_cache, str(tmp_path / "absent.json"))
    env(CFG.env_quiet, None)
    env(CFG.env_severity, "error")
    out = io.StringIO()
    # Act
    code = warn_if_stale(CFG, stream=out)
    # Assert
    assert code == 0


def test_bad_severity_falls_back_to_warn(tmp_path, env):
    # Arrange
    cache = _write(tmp_path / "f.json", Currency.STALE)
    env(CFG.env_cache, str(cache))
    env(CFG.env_quiet, None)
    env(CFG.env_severity, "erorr")
    out = io.StringIO()
    # Act
    code = warn_if_stale(CFG, stream=out)
    # Assert
    assert code == 0


def test_expired_cache_says_nothing(tmp_path, env):
    # Arrange — 30 days old, far past any TTL.
    cache = _write(tmp_path / "f.json", Currency.STALE, at=time.time() - 30 * 86_400)
    env(CFG.env_cache, str(cache))
    env(CFG.env_quiet, None)
    env(CFG.env_severity, None)
    out = io.StringIO()
    # Act
    warn_if_stale(CFG, stream=out)
    # Assert
    assert out.getvalue() == ""


def test_emit_once_is_silent_on_second_call(tmp_path, env):
    # Arrange
    cache = _write(tmp_path / "f.json", Currency.STALE)
    env(CFG.env_cache, str(cache))
    env(CFG.env_quiet, None)
    env(CFG.env_severity, None)
    env("_" + CFG.env_prefix + "_EMITTED", None)
    emit_once._seen = set()  # reset the in-process guard for a clean run
    first = io.StringIO()
    second = io.StringIO()
    emit_once(CFG, stream=first)
    # Act
    emit_once(CFG, stream=second)
    # Assert
    assert second.getvalue() == ""


# EOF
