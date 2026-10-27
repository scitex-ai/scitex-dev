#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Config + predicate tests: gates fail closed, legs read unevaluable."""

from __future__ import annotations

import subprocess
from pathlib import Path

from scitex_dev.hygiene import load_disk_cleanup_config
from scitex_dev.hygiene._disk_guard_model import (
    clamp_min_age_days,
    clamp_sif_keep_newest,
    clamp_threshold_pct,
)
from scitex_dev.hygiene._disk_guard_predicate import (
    BuildState,
    fuser_holds,
    is_build_in_flight,
    matches_protect,
    should_prune_build_cache,
)


def _write(home: Path, text: str) -> Path:
    path = home / ".scitex" / "dev" / "config.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return home


def test_missing_config_is_off(tmp_path):
    assert load_disk_cleanup_config(tmp_path / "nothing").enabled is False


def test_enabled_requires_literal_true(tmp_path):
    # Quoted impostors stay OFF — only YAML-true arms the gate. (Unquoted
    # `yes` parses as boolean true under YAML 1.1 and arms, exactly like
    # the branch-gc gate: the identity test is on the PARSED value.)
    for raw in ("'yes'", "'1'", "'true'", "'True'", "1", "0"):
        home = _write(
            tmp_path / raw.replace("'", ""), f"cleanup:\n  disk:\n    enabled: {raw}\n"
        )
        assert load_disk_cleanup_config(home).enabled is False, raw
    for raw in ("true", "True", "TRUE", "yes"):
        home = _write(
            tmp_path / f"armed-{raw}", f"cleanup:\n  disk:\n    enabled: {raw}\n"
        )
        assert load_disk_cleanup_config(home).enabled is True, raw


def test_malformed_and_misshapen_are_off_with_reason(tmp_path):
    bad = _write(tmp_path / "bad", "cleanup:\n  disk: [unclosed\n")
    config = load_disk_cleanup_config(bad)
    assert config.enabled is False and config.error
    flat = _write(tmp_path / "flat", "just: a string\n")
    # top-level mapping without cleanup block: off, no error
    assert load_disk_cleanup_config(flat).enabled is False
    wrong = _write(tmp_path / "wrong", "cleanup:\n  disk: true\n")
    config = load_disk_cleanup_config(wrong)
    assert config.enabled is False and config.error


def test_clamps():
    assert clamp_threshold_pct(10) == 50
    assert clamp_threshold_pct(100) == 99
    assert clamp_threshold_pct("junk") == 88
    assert clamp_min_age_days(0.5) == 2.0
    assert clamp_sif_keep_newest(0) == 1


def test_prune_leg_matrix():
    assert should_prune_build_cache(BuildState(None, False, False), 88) == (
        False,
        "docker-unavailable",
    )
    assert should_prune_build_cache(BuildState(99.0, True, True), 88) == (
        False,
        "build-in-flight",
    )
    assert should_prune_build_cache(BuildState(50.0, True, False), 88) == (
        False,
        "below-threshold",
    )
    assert should_prune_build_cache(BuildState(88.0, True, False), 88) == (
        True,
        "at-threshold",
    )
    assert should_prune_build_cache(BuildState(None, True, False), 88) == (
        False,
        "fuser-unavailable",
    )


def test_fuser_legs():
    ok = lambda *a, **k: subprocess.CompletedProcess(a, 0, b"", b"")
    assert fuser_holds(Path("/x"), run=ok) is True
    missing = lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError())
    assert fuser_holds(Path("/x"), run=missing) is None
    weird = lambda *a, **k: subprocess.CompletedProcess(a, 3, b"", b"")
    assert fuser_holds(Path("/x"), run=weird) is None


def test_build_detection_and_protect():
    assert is_build_in_flight(lambda: ["99 [d]ocker build x"]) is False
    assert is_build_in_flight(lambda: ["99 docker build -t x ."]) is True
    assert is_build_in_flight(lambda: (_ for _ in ()).throw(OSError())) is None
    assert matches_protect("/tmp/ci-keep-1", ("/tmp/ci-keep-*",))
    assert not matches_protect("/tmp/ci-drop-1", ("/tmp/ci-keep-*",))


# EOF
