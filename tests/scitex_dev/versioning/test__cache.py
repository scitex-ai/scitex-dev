#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cache round-trip + TTL. All four of missing/corrupt/undated/expired => None.

Driven through the real cache file and the real env vars — the same seams
production uses. ``None`` is how UNKNOWN (=> silence) reaches the reader; a
stale-but-plausible value is exactly the fossil this subsystem exists to kill.
"""

from __future__ import annotations

import json
import time

from scitex_dev.versioning._cache import (
    DEFAULT_TTL_S,
    cache_path,
    read_cache,
    scitex_dir,
    write_cache,
)
from scitex_dev.versioning._config import VersioningConfig
from scitex_dev.versioning._model import Currency, Finding, Report

CFG = VersioningConfig(dist="scitex-dev")


def _report(state=Currency.STALE, at=None):
    return Report(
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


def test_cache_round_trips_the_verdict(tmp_path):
    # Arrange
    path = tmp_path / "currency.json"
    write_cache(CFG, _report(), path)
    # Act
    loaded = read_cache(CFG, path)
    # Assert
    assert loaded.state is Currency.STALE


def test_cache_round_trips_the_remedy(tmp_path):
    # Arrange
    path = tmp_path / "currency.json"
    write_cache(CFG, _report(), path)
    # Act
    loaded = read_cache(CFG, path)
    # Assert
    assert loaded.findings[0].remedy == "python -m pip install -U 'scitex-dev==0.31.0'"


def test_missing_cache_reads_as_none(tmp_path):
    # Arrange
    path = tmp_path / "nope.json"
    # Act
    loaded = read_cache(CFG, path)
    # Assert
    assert loaded is None


def test_corrupt_cache_reads_as_none(tmp_path):
    # Arrange
    path = tmp_path / "currency.json"
    path.write_text("{ this is not json")
    # Act
    loaded = read_cache(CFG, path)
    # Assert
    assert loaded is None


def test_expired_cache_reads_as_none(tmp_path):
    # Arrange
    path = tmp_path / "currency.json"
    write_cache(CFG, _report(at=time.time() - DEFAULT_TTL_S - 60), path)
    # Act
    loaded = read_cache(CFG, path)
    # Assert
    assert loaded is None


def test_undated_cache_reads_as_none(tmp_path):
    # Arrange
    path = tmp_path / "currency.json"
    path.write_text(json.dumps({"state": "stale", "findings": []}))
    # Act
    loaded = read_cache(CFG, path)
    # Assert
    assert loaded is None


def test_fresh_cache_within_ttl_is_served(tmp_path):
    # Arrange
    path = tmp_path / "currency.json"
    write_cache(CFG, _report(at=time.time() - 60), path)
    # Act
    loaded = read_cache(CFG, path)
    # Assert
    assert loaded is not None


def test_cache_write_is_atomic(tmp_path):
    # Arrange
    path = tmp_path / "currency.json"
    write_cache(CFG, _report(), path)
    # Act
    leftovers = list(tmp_path.glob("*.tmp"))
    # Assert
    assert leftovers == []


def test_env_override_redirects_the_cache(tmp_path, env):
    # Arrange
    target = tmp_path / "elsewhere.json"
    env(CFG.env_cache, str(target))
    # Act
    resolved = cache_path(CFG)
    # Assert
    assert resolved == target


def test_cache_path_follows_scitex_dir(tmp_path, env):
    # Arrange
    env(CFG.env_cache, None)
    env("SCITEX_DIR", str(tmp_path))
    # Act
    resolved = cache_path(CFG)
    # Assert
    assert resolved.is_relative_to(tmp_path)


def test_scitex_dir_follows_env(tmp_path, env):
    # Arrange
    env("SCITEX_DIR", str(tmp_path))
    # Act
    resolved = scitex_dir()
    # Assert
    assert resolved == tmp_path


# EOF
