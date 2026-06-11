#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for systemd unit-file builders."""

from __future__ import annotations

from scitex_dev.jobs import JobSpec
from scitex_dev.jobs import _systemd as sd


def _job():
    return JobSpec(
        name="sac.accounts-refresh",
        schedule="0 */4 * * *",
        command="sac accounts refresh --all",
        description="rotate tokens",
        kind="timer",
        on_boot_sec="15min",
        on_unit_active_sec="4h",
        timeout_sec=120,
    )


def test_service_unit_is_oneshot():
    # Arrange
    job = _job()
    # Act
    text = sd.build_service_unit(job)
    # Assert
    assert "Type=oneshot" in text


def test_service_unit_execstart_falls_back_to_usr_bin_env_when_unresolved():
    # Arrange — pick a command name that is GUARANTEED not on PATH so
    # the fallback path runs. `build_service_unit` resolves
    # `resolve_execstart` against the live shutil.which; in the test
    # env that returns None for this nonce.
    job = JobSpec(
        name="x.y",
        kind="timer",
        schedule="0 * * * *",
        command="this-binary-does-not-exist-on-PATH-zzzzz argA argB",
        description="d",
    )
    # Act
    text = sd.build_service_unit(job)
    # Assert
    assert (
        "ExecStart=/usr/bin/env this-binary-does-not-exist-on-PATH-zzzzz argA argB"
        in text
    )


def test_service_unit_includes_timeout():
    # Arrange
    job = _job()
    # Act
    text = sd.build_service_unit(job)
    # Assert
    assert "TimeoutStartSec=120s" in text


def test_service_unit_logs_to_journal():
    # Arrange
    job = _job()
    # Act
    text = sd.build_service_unit(job)
    # Assert
    assert "StandardOutput=journal" in text


def test_timer_unit_uses_declared_on_boot_sec():
    # Arrange
    job = _job()
    # Act
    text = sd.build_timer_unit(job)
    # Assert
    assert "OnBootSec=15min" in text


def test_timer_unit_uses_declared_on_unit_active_sec():
    # Arrange
    job = _job()
    # Act
    text = sd.build_timer_unit(job)
    # Assert
    assert "OnUnitActiveSec=4h" in text


def test_timer_unit_is_persistent():
    # Arrange
    job = _job()
    # Act
    text = sd.build_timer_unit(job)
    # Assert
    assert "Persistent=true" in text


def test_timer_unit_points_at_service():
    # Arrange
    job = _job()
    # Act
    text = sd.build_timer_unit(job)
    # Assert
    assert "Unit=sac.accounts-refresh.service" in text


def test_timer_default_on_boot_when_unset():
    # Arrange
    job = JobSpec(
        name="x.y", schedule="0 * * * *", command="c", description="d", kind="timer"
    )
    # Act
    text = sd.build_timer_unit(job)
    # Assert
    assert f"OnBootSec={sd.DEFAULT_ON_BOOT_SEC}" in text


def test_derive_on_unit_active_sec_from_minute_step():
    # Arrange
    # Act
    derived = sd.derive_on_unit_active_sec("*/10 * * * *")
    # Assert
    assert derived == "10min"


def test_derive_on_unit_active_sec_from_hour_step():
    # Arrange
    # Act
    derived = sd.derive_on_unit_active_sec("0 */4 * * *")
    # Assert
    assert derived == "4h"


def test_derive_on_unit_active_sec_fallback_for_unknown():
    # Arrange
    # Act
    derived = sd.derive_on_unit_active_sec("garbage")
    # Assert
    assert derived == sd.DEFAULT_ON_UNIT_ACTIVE_SEC


# ---------------------------------------------------------------------------
# resolve_execstart — absolute-path fix (BUG A on the host bring-up)
# ---------------------------------------------------------------------------


def test_resolve_execstart_resolves_first_token_via_which():
    # Arrange
    # Act
    resolved = sd.resolve_execstart(
        "scitex-todo board --port 8051",
        which=lambda n: "/home/op/.env/bin/scitex-todo"
        if n == "scitex-todo"
        else None,
    )
    # Assert
    assert resolved == "/home/op/.env/bin/scitex-todo board --port 8051"


def test_resolve_execstart_preserves_args_after_first_token():
    # Arrange
    # Act
    resolved = sd.resolve_execstart(
        "scitex-dev ecosystem up --yes",
        which=lambda n: "/usr/local/bin/scitex-dev" if n == "scitex-dev" else None,
    )
    # Assert
    assert resolved.endswith(" ecosystem up --yes")


def test_resolve_execstart_falls_back_when_which_returns_none():
    # Arrange
    # Act
    resolved = sd.resolve_execstart(
        "nonexistent-binary --arg",
        which=lambda _n: None,
    )
    # Assert
    assert resolved == "/usr/bin/env nonexistent-binary --arg"


def test_resolve_execstart_passes_through_when_first_token_is_absolute():
    # Arrange
    # Act
    resolved = sd.resolve_execstart(
        "/opt/scitex/sac sweep",
        which=lambda _n: "/wrong/path",  # must NOT be used
    )
    # Assert
    assert resolved == "/opt/scitex/sac sweep"


def test_resolve_execstart_empty_command_passes_through():
    # Arrange
    # Act
    resolved = sd.resolve_execstart("", which=lambda _n: "/whatever")
    # Assert
    assert resolved == ""


# EOF
