#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for systemd unit-file builders."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from scitex_dev.jobs import JobSpec
from scitex_dev.jobs import _systemd as sd


def _empty_bindir(tmp_path: Path):
    """Return an interpreter_bindir factory that points at an empty dir,
    forcing tests through the PATH / fallback branches.
    """
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    return lambda: empty


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
    # Arrange — pick a command name that is GUARANTEED not in
    # sys.executable's sibling bin/ NOR on PATH so the fallback path
    # runs. The warning assertion is split into a separate test below
    # (catch_warnings is more robust against ambient PYTHONWARNINGS).
    job = JobSpec(
        name="x.y",
        kind="timer",
        schedule="0 * * * *",
        command="this-binary-does-not-exist-on-PATH-zzzzz argA argB",
        description="d",
    )
    # Act
    import warnings as _w

    with _w.catch_warnings():
        _w.simplefilter("ignore")
        text = sd.build_service_unit(job)
    # Assert
    assert (
        "ExecStart=/usr/bin/env this-binary-does-not-exist-on-PATH-zzzzz argA argB"
        in text
    )


def test_resolve_execstart_fallback_emits_loud_user_warning(tmp_path):
    """The /usr/bin/env fallback must emit a LOUD UserWarning so the
    bring-up log makes the miss obvious — this is what the ywata-note-win
    crash loop needed to be visible (it was silent for ~12 h).
    """
    # Arrange — empty interpreter bin/, which() returns None so we
    # deterministically hit the fallback.
    import warnings as _w

    # Act
    with _w.catch_warnings(record=True) as recorded:
        _w.simplefilter("always")
        resolved = sd.resolve_execstart(
            "scitex-todo board",
            which=lambda _n: None,
            interpreter_bindir=_empty_bindir(tmp_path),
        )

    # Assert — fallback string, plus a UserWarning naming the binary.
    assert resolved == "/usr/bin/env scitex-todo board"
    matches = [
        w
        for w in recorded
        if issubclass(w.category, UserWarning) and "scitex-todo" in str(w.message)
    ]
    assert matches, (
        f"expected a UserWarning mentioning 'scitex-todo'; recorded={recorded!r}"
    )
    assert "could not resolve" in str(matches[0].message)


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


def test_resolve_execstart_resolves_first_token_via_which(tmp_path):
    # Arrange — empty interpreter bin/ so the PATH lookup branch runs
    # (we explicitly want to verify the second resolution rule here).
    # Act
    resolved = sd.resolve_execstart(
        "scitex-todo board --port 8051",
        which=lambda n: "/home/op/.env/bin/scitex-todo"
        if n == "scitex-todo"
        else None,
        interpreter_bindir=_empty_bindir(tmp_path),
    )
    # Assert
    assert resolved == "/home/op/.env/bin/scitex-todo board --port 8051"


def test_resolve_execstart_preserves_args_after_first_token(tmp_path):
    # Arrange
    # Act
    resolved = sd.resolve_execstart(
        "scitex-dev ecosystem up --yes",
        which=lambda n: "/usr/local/bin/scitex-dev" if n == "scitex-dev" else None,
        interpreter_bindir=_empty_bindir(tmp_path),
    )
    # Assert
    assert resolved.endswith(" ecosystem up --yes")


def test_resolve_execstart_falls_back_when_which_returns_none(tmp_path):
    # Arrange
    # Act
    with pytest.warns(UserWarning, match="could not resolve"):
        resolved = sd.resolve_execstart(
            "nonexistent-binary --arg",
            which=lambda _n: None,
            interpreter_bindir=_empty_bindir(tmp_path),
        )
    # Assert
    assert resolved == "/usr/bin/env nonexistent-binary --arg"


def test_resolve_execstart_passes_through_when_first_token_is_absolute(tmp_path):
    # Arrange
    # Act
    resolved = sd.resolve_execstart(
        "/opt/scitex/sac sweep",
        which=lambda _n: "/wrong/path",  # must NOT be used
        interpreter_bindir=_empty_bindir(tmp_path),
    )
    # Assert
    assert resolved == "/opt/scitex/sac sweep"


def test_resolve_execstart_empty_command_passes_through(tmp_path):
    # Arrange
    # Act
    resolved = sd.resolve_execstart(
        "",
        which=lambda _n: "/whatever",
        interpreter_bindir=_empty_bindir(tmp_path),
    )
    # Assert
    assert resolved == ""


# ---------------------------------------------------------------------------
# resolve_execstart — sys.executable sibling-bin probe (BUG B fix)
#
# The ywata-note-win regression: `ecosystem up` was invoked via the venv's
# absolute interpreter (~/.env-3.11/bin/scitex-dev) WITHOUT activation, so
# the ambient PATH didn't include ~/.env-3.11/bin. shutil.which("scitex-todo")
# returned None → unit was written with `ExecStart=/usr/bin/env scitex-todo`
# → systemd user PATH (a minimal /usr/local/bin:/usr/bin:/bin) had no
# scitex-todo → status=127 crash loop for ~12 h (restart counter 2159).
#
# Fix: probe Path(sys.executable).parent / cmd FIRST — the interpreter that
# runs `ecosystem up` is the same interpreter the console scripts are
# installed against, so its sibling bin/ ALWAYS holds them.
# ---------------------------------------------------------------------------


def test_resolve_execstart_prefers_interpreter_sibling_bin_over_path(tmp_path):
    # Arrange — fake interpreter bin/ contains the binary; PATH lookup
    # returns a DIFFERENT path that must NOT be used.
    fake_bin = tmp_path / "fake-venv-bin"
    fake_bin.mkdir()
    binary = fake_bin / "scitex-todo"
    binary.write_text("#!/bin/sh\nexit 0\n")
    binary.chmod(0o755)

    # Act
    resolved = sd.resolve_execstart(
        "scitex-todo board --port 8051",
        which=lambda _n: "/should/not/be/used/scitex-todo",
        interpreter_bindir=lambda: fake_bin,
    )

    # Assert — sibling-bin probe wins.
    assert resolved == f"{binary} board --port 8051"


def test_resolve_execstart_skips_sibling_bin_when_not_executable(tmp_path):
    # Arrange — file exists in the bin/ but is NOT executable; the probe
    # must skip it and fall through to PATH lookup.
    fake_bin = tmp_path / "fake-venv-bin"
    fake_bin.mkdir()
    binary = fake_bin / "scitex-todo"
    binary.write_text("not actually executable")
    binary.chmod(0o644)  # readable but not +x

    # Act
    resolved = sd.resolve_execstart(
        "scitex-todo board",
        which=lambda n: "/path/from/which/scitex-todo" if n == "scitex-todo" else None,
        interpreter_bindir=lambda: fake_bin,
    )

    # Assert — fell through to which().
    assert resolved == "/path/from/which/scitex-todo board"


def test_resolve_execstart_skips_sibling_bin_when_missing(tmp_path):
    # Arrange — bin/ is empty; probe should fall through to which().
    fake_bin = tmp_path / "fake-venv-bin"
    fake_bin.mkdir()

    # Act
    resolved = sd.resolve_execstart(
        "scitex-todo board",
        which=lambda _n: "/usr/local/bin/scitex-todo",
        interpreter_bindir=lambda: fake_bin,
    )

    # Assert
    assert resolved == "/usr/local/bin/scitex-todo board"


def test_default_interpreter_bindir_is_sys_executable_parent():
    # Arrange / Act
    bindir = sd._interpreter_bindir()
    # Assert — the production default reads sys.executable's parent.
    assert bindir == Path(sys.executable).resolve().parent


# ---------------------------------------------------------------------------
# No-mocks integration: spawn a fresh interpreter with PATH stripped of the
# venv's bin/, have it write a service unit, and assert ExecStart is absolute
# (not "/usr/bin/env <cmd>").
#
# This is the regression guard the ywata-note-win incident demands: the bug
# only surfaces when PATH does NOT contain the venv bin/ — which is exactly
# the env `ecosystem up` saw when invoked via absolute interpreter path. Any
# future regression that re-introduces PATH-only resolution will fail this
# test with a `/usr/bin/env` prefix in the ExecStart.
# ---------------------------------------------------------------------------


def test_build_service_unit_with_stripped_path_yields_absolute_execstart(tmp_path):
    """No-mocks regression for the ywata-note-win 12 h crash loop.

    Spawns the current interpreter as a subprocess with PATH stripped of
    its own bin/ (mirroring the live bug: `ecosystem up` invoked via
    absolute venv interpreter path, no activation), has it build a
    service unit for a binary that DOES live in the interpreter's bin/
    (we use `python` itself — guaranteed to exist next to sys.executable),
    and asserts the resulting ExecStart is an absolute path, NOT
    "/usr/bin/env ...".
    """
    # Arrange — pick a target binary guaranteed to live alongside the
    # current interpreter: the interpreter itself. (`python3` and `pip`
    # are the other plausible picks but neither is guaranteed.)
    interpreter_dir = Path(sys.executable).resolve().parent
    binary_name = Path(sys.executable).name  # e.g. "python3.12"
    assert (interpreter_dir / binary_name).is_file(), (
        f"sanity: interpreter binary {binary_name!r} must live in "
        f"{interpreter_dir}; this is the precondition the fix relies on."
    )

    # PATH that does NOT contain the interpreter's bin/, mirroring the
    # ywata-note-win bug.
    minimal_path_parts = [
        p for p in ("/usr/local/bin", "/usr/bin", "/bin") if Path(p).is_dir()
    ]
    stripped_path = ":".join(minimal_path_parts)
    # Sanity: the interpreter's bin/ must NOT be in our stripped PATH
    # (otherwise we'd be testing the PATH-lookup branch, not the fix).
    assert str(interpreter_dir) not in stripped_path.split(":"), (
        f"test misconfigured: interpreter bin/ {interpreter_dir} unexpectedly "
        f"appears in stripped PATH {stripped_path!r}"
    )

    program = textwrap.dedent(
        f"""
        import sys
        from scitex_dev.jobs import JobSpec
        from scitex_dev.jobs import _systemd as sd
        job = JobSpec(
            name="repro.crash-loop",
            kind="service",
            schedule="",
            command="{binary_name} --version",
            description="regression repro for ywata-note-win 127 crash loop",
            restart_policy="always",
        )
        text = sd.build_service_unit(job)
        for line in text.splitlines():
            if line.startswith("ExecStart="):
                print(line)
                break
        else:
            sys.exit("ExecStart= line missing from generated unit")
        """
    )

    # Act — subprocess inherits a minimal env: only PATH (without the
    # venv bin/) plus PYTHONPATH so the in-tree package is importable.
    env = {
        "PATH": stripped_path,
        "HOME": os.environ.get("HOME", str(tmp_path)),
        # PYTHONPATH lets the subprocess import our in-tree scitex_dev
        # without relying on PATH or site-packages discovery.
        "PYTHONPATH": os.environ.get("PYTHONPATH", ""),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
    }
    result = subprocess.run(
        [sys.executable, "-W", "ignore", "-c", program],
        check=True,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    line = result.stdout.strip()

    # Assert — ExecStart must be absolute, NOT "/usr/bin/env ...".
    # That is the whole point of the fix: even when PATH lacks the venv
    # bin/, the sibling-bin probe gives systemd an absolute path that
    # works under its minimal user PATH.
    assert line.startswith("ExecStart="), (
        f"subprocess did not emit an ExecStart line; got: {line!r}\n"
        f"stderr: {result.stderr!r}"
    )
    value = line[len("ExecStart=") :]
    assert not value.startswith("/usr/bin/env "), (
        f"REGRESSION (ywata-note-win): unit ExecStart fell back to "
        f"/usr/bin/env under a stripped PATH, which crash-loops at "
        f"status=127 on a real systemd user manager.\n"
        f"  ExecStart={value!r}\n"
        f"  stripped PATH={stripped_path!r}\n"
        f"  interpreter bin/={interpreter_dir}"
    )
    first_token = value.split()[0]
    assert first_token.startswith("/"), (
        f"ExecStart first token must be absolute, got {first_token!r}"
    )
    assert Path(first_token).is_file(), (
        f"ExecStart first token {first_token!r} does not exist as a file"
    )


# EOF
