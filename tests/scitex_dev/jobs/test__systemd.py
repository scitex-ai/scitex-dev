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
from tests._child_env import with_loader_path


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


def _capture_fallback_warning(tmp_path):
    """Drive resolve_execstart through the fallback branch and return
    (resolved_command, list_of_recorded_warnings). Tests below each
    assert ONE thing on this captured state — TQ007 compliance.
    """
    import warnings as _w

    with _w.catch_warnings(record=True) as recorded:
        _w.simplefilter("always")
        resolved = sd.resolve_execstart(
            "scitex-todo board",
            which=lambda _n: None,
            interpreter_bindir=_empty_bindir(tmp_path),
        )
    return resolved, recorded


def test_resolve_execstart_fallback_returns_usr_bin_env_command(tmp_path):
    # Arrange
    # Act
    resolved, _recorded = _capture_fallback_warning(tmp_path)
    # Assert
    assert resolved == "/usr/bin/env scitex-todo board"


def test_resolve_execstart_fallback_emits_a_user_warning(tmp_path):
    """The /usr/bin/env fallback must emit a UserWarning so the bring-up
    log makes the miss obvious — silent for ~12 h on ywata-note-win was
    the regression we're guarding against.
    """
    # Arrange
    # Act
    _resolved, recorded = _capture_fallback_warning(tmp_path)
    # Assert
    user_warnings = [w for w in recorded if issubclass(w.category, UserWarning)]
    assert user_warnings, f"expected a UserWarning; recorded={recorded!r}"


def test_resolve_execstart_fallback_warning_names_the_unresolved_binary(tmp_path):
    # Arrange
    # Act
    _resolved, recorded = _capture_fallback_warning(tmp_path)
    # Assert — the warning text must mention the unresolved binary so
    # an operator scanning the bring-up log can grep for it.
    matching = [
        w
        for w in recorded
        if issubclass(w.category, UserWarning)
        and "scitex-todo" in str(w.message)
        and "could not resolve" in str(w.message)
    ]
    assert matching, (
        f"expected a 'could not resolve' UserWarning mentioning 'scitex-todo'; "
        f"recorded={recorded!r}"
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
# kind="service" long-running unit + WatchdogSec opt-in
# ---------------------------------------------------------------------------


def _service_job(**overrides):
    base = dict(
        name="sac.listen",
        kind="service",
        schedule="",
        command="sac listen --port 7878",
        description="sac long-poll listen daemon",
        restart_policy="always",
    )
    base.update(overrides)
    return JobSpec(**base)


def test_service_unit_kind_service_is_type_simple_by_default():
    # Arrange
    job = _service_job()
    # Act
    text = sd.build_service_unit(job)
    # Assert — no watchdog opt-in ⇒ plain Type=simple.
    assert "Type=simple" in text


def test_service_unit_kind_service_has_restart_policy():
    # Arrange
    job = _service_job(restart_policy="always")
    # Act
    text = sd.build_service_unit(job)
    # Assert
    assert "Restart=always" in text


def test_service_unit_omits_watchdog_when_not_opted_in():
    # Arrange — WatchdogSec absent for a plain Type=simple daemon avoids
    # the "kill+restart every interval" footgun.
    job = _service_job()
    # Act
    text = sd.build_service_unit(job)
    # Assert
    assert "WatchdogSec" not in text


def test_service_unit_not_type_notify_when_not_opted_in():
    # Arrange
    job = _service_job()
    # Act
    text = sd.build_service_unit(job)
    # Assert — Type=notify only when a watchdog is requested.
    assert "Type=notify" not in text


def test_service_unit_emits_watchdog_when_opted_in():
    # Arrange
    job = _service_job(watchdog_sec=30)
    # Act
    text = sd.build_service_unit(job)
    # Assert
    assert "WatchdogSec=30s" in text


def test_service_unit_switches_to_type_notify_when_watchdog_opted_in():
    # Arrange — WatchdogSec requires Type=notify + sd_notify pings.
    job = _service_job(watchdog_sec=30)
    # Act
    text = sd.build_service_unit(job)
    # Assert
    assert "Type=notify" in text


def test_service_unit_watchdog_opted_in_is_not_type_simple():
    # Arrange
    job = _service_job(watchdog_sec=30)
    # Act
    text = sd.build_service_unit(job)
    # Assert
    assert "Type=simple" not in text


# ---------------------------------------------------------------------------
# kind="service" long-running unit — per-job venv pin
#
# "Leaf owns its own venv": scitex-todo's dashboard service must resolve
# ExecStart against scitex-todo's OWN venv, not scitex-dev's (the
# supervisor). See JobSpec.venv.
# ---------------------------------------------------------------------------


def test_service_unit_long_running_execstart_uses_venv_bin(tmp_path):
    # Arrange
    venv_dir = tmp_path / "scitex-todo" / ".venv"
    binary = venv_dir / "bin" / "scitex-todo"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/bin/sh\nexit 0\n")
    binary.chmod(0o755)
    job = _service_job(command="scitex-todo serve --port 8051", venv=str(venv_dir))
    # Act
    text = sd.build_service_unit(job)
    # Assert
    assert f"ExecStart={binary} serve --port 8051" in text


def test_service_unit_long_running_emits_working_directory_when_venv_set():
    # Arrange
    job = _service_job(venv="/home/ywatanabe/proj/scitex-todo/.venv")
    # Act
    text = sd.build_service_unit(job)
    # Assert — cwd is the venv's parent, the package root.
    assert "WorkingDirectory=/home/ywatanabe/proj/scitex-todo" in text


def test_service_unit_long_running_emits_virtual_env_when_venv_set():
    # Arrange
    job = _service_job(venv="/home/ywatanabe/proj/scitex-todo/.venv")
    # Act
    text = sd.build_service_unit(job)
    # Assert
    assert "Environment=VIRTUAL_ENV=/home/ywatanabe/proj/scitex-todo/.venv" in text


def test_service_unit_long_running_omits_working_directory_without_venv():
    # Arrange — regression: a JobSpec with no venv keeps the historical
    # unit shape (no WorkingDirectory= line at all).
    job = _service_job()
    # Act
    text = sd.build_service_unit(job)
    # Assert
    assert "WorkingDirectory" not in text


def test_service_unit_long_running_omits_virtual_env_without_venv():
    # Arrange — regression companion to the WorkingDirectory check above.
    job = _service_job()
    # Act
    text = sd.build_service_unit(job)
    # Assert
    assert "VIRTUAL_ENV" not in text


# ---------------------------------------------------------------------------
# kind="timer" oneshot unit — per-job venv pin (same rationale as above)
# ---------------------------------------------------------------------------


def test_oneshot_unit_execstart_uses_venv_bin(tmp_path):
    # Arrange
    venv_dir = tmp_path / "sac" / ".venv"
    binary = venv_dir / "bin" / "sac"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/bin/sh\nexit 0\n")
    binary.chmod(0o755)
    job = JobSpec(
        name="sac.accounts-refresh",
        schedule="0 */4 * * *",
        command="sac accounts refresh --all",
        description="rotate tokens",
        kind="timer",
        on_unit_active_sec="4h",
        venv=str(venv_dir),
    )
    # Act
    text = sd.build_service_unit(job)
    # Assert
    assert f"ExecStart={binary} accounts refresh --all" in text


def test_oneshot_unit_emits_working_directory_when_venv_set():
    # Arrange
    job = JobSpec(
        name="sac.accounts-refresh",
        schedule="0 */4 * * *",
        command="sac accounts refresh --all",
        description="rotate tokens",
        kind="timer",
        on_unit_active_sec="4h",
        venv="/home/ywatanabe/proj/sac/.venv",
    )
    # Act
    text = sd.build_service_unit(job)
    # Assert
    assert "WorkingDirectory=/home/ywatanabe/proj/sac" in text


def test_oneshot_unit_omits_working_directory_without_venv():
    # Arrange — regression: unchanged shape for a JobSpec without venv.
    job = _job()
    # Act
    text = sd.build_service_unit(job)
    # Assert
    assert "WorkingDirectory" not in text


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
    import warnings as _w

    # Act
    with _w.catch_warnings():
        _w.simplefilter("ignore")
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
    # Arrange
    expected = Path(sys.executable).resolve().parent
    # Act
    bindir = sd._interpreter_bindir()
    # Assert — the production default reads sys.executable's parent.
    assert bindir == expected


# ---------------------------------------------------------------------------
# resolve_execstart — per-job venv pin ("leaf owns its own venv")
#
# A supervised cross-package child (e.g. scitex-todo's dashboard) must NOT
# resolve against the SUPERVISOR's own interpreter (scitex-dev's venv) —
# that venv may lack the package entirely, or hold a stale version. When
# JobSpec.venv is set, resolve_execstart must prefer <venv>/bin/<head>
# over both the interpreter sibling-bin probe and the PATH lookup.
# ---------------------------------------------------------------------------


def _make_venv_bin(tmp_path: Path, name: str) -> Path:
    venv_bin = tmp_path / "leaf-venv" / "bin"
    venv_bin.mkdir(parents=True)
    binary = venv_bin / name
    binary.write_text("#!/bin/sh\nexit 0\n")
    binary.chmod(0o755)
    return binary


def test_resolve_execstart_venv_pin_used_when_binary_present(tmp_path):
    # Arrange — the pinned venv has the binary; sibling-bin/PATH probes
    # would resolve to something ELSE that must NOT be used.
    binary = _make_venv_bin(tmp_path, "scitex-todo")
    other_bin = tmp_path / "supervisor-bin"
    other_bin.mkdir()

    # Act
    resolved = sd.resolve_execstart(
        "scitex-todo board --port 8051",
        venv=str(binary.parent.parent),
        which=lambda _n: "/should/not/be/used/scitex-todo",
        interpreter_bindir=lambda: other_bin,
    )

    # Assert — the venv-pinned binary wins.
    assert resolved == f"{binary} board --port 8051"


def test_resolve_execstart_venv_pin_falls_through_when_binary_missing(tmp_path):
    # Arrange — venv is pinned but doesn't actually hold the binary (stale
    # pin); must degrade to the normal resolution chain, not error out.
    venv_dir = tmp_path / "leaf-venv"
    (venv_dir / "bin").mkdir(parents=True)

    # Act
    resolved = sd.resolve_execstart(
        "scitex-todo board",
        venv=str(venv_dir),
        which=lambda n: "/path/from/which/scitex-todo" if n == "scitex-todo" else None,
        interpreter_bindir=lambda: tmp_path / "empty-supervisor-bin",
    )

    # Assert — fell through to which().
    assert resolved == "/path/from/which/scitex-todo board"


def test_resolve_execstart_without_venv_kwarg_is_unaffected(tmp_path):
    # Arrange — regression: omitting ``venv`` entirely (every pre-existing
    # call site) must behave exactly as before the venv-pin feature.
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

    # Assert — unchanged sibling-bin-probe behavior.
    assert resolved == f"{binary} board --port 8051"


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


# ywata-note-win regression repro: build a service unit from a subprocess
# whose PATH does NOT contain the interpreter's bin/, then assert the
# resulting ExecStart is absolute (not "/usr/bin/env ..."). Split across
# multiple one-assert tests (STX-TQ007) sharing a module-scoped fixture so
# the subprocess only runs once.


@pytest.fixture(scope="module")
def _stripped_path_execstart_line(tmp_path_factory):
    """Spawn the current interpreter as a subprocess with PATH stripped of
    its own bin/, have it build a service unit, and return the resulting
    ExecStart line.

    Mirrors the ywata-note-win env shape: `ecosystem up` was invoked via
    the venv's absolute interpreter path with no activation, so PATH did
    not include ~/.env-3.11/bin. The fix is verified end-to-end here: the
    ExecStart that comes back must be absolute despite PATH lacking the
    venv bin/.
    """
    tmp_path = tmp_path_factory.mktemp("stripped-path-execstart")
    interpreter_dir = Path(sys.executable).resolve().parent
    binary_name = Path(sys.executable).name
    if not (interpreter_dir / binary_name).is_file():
        pytest.skip(
            f"precondition: interpreter binary {binary_name!r} must live in "
            f"{interpreter_dir}; CI runner has it relocated, skipping no-mocks repro."
        )

    minimal_path_parts = [
        p for p in ("/usr/local/bin", "/usr/bin", "/bin") if Path(p).is_dir()
    ]
    stripped_path = ":".join(minimal_path_parts)
    if str(interpreter_dir) in stripped_path.split(":"):
        pytest.skip(
            f"precondition: interpreter bin/ {interpreter_dir} unexpectedly in "
            f"stripped PATH {stripped_path!r}; cannot exercise the fix here."
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

    # `$PATH` is stripped ON PURPOSE — that is the repro. The loader path
    # is not part of it: without it the child cannot start at all and the
    # repro measures nothing. See tests/_child_env.py.
    env = with_loader_path(
        {
            "PATH": stripped_path,
            "HOME": os.environ.get("HOME", str(tmp_path)),
            "PYTHONPATH": os.environ.get("PYTHONPATH", ""),
            "LANG": os.environ.get("LANG", "C.UTF-8"),
        }
    )
    result = subprocess.run(
        [sys.executable, "-W", "ignore", "-c", program],
        check=True,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    return {
        "line": result.stdout.strip(),
        "stderr": result.stderr,
        "stripped_path": stripped_path,
        "interpreter_dir": interpreter_dir,
    }


def test_stripped_path_subprocess_emits_an_execstart_line(
    _stripped_path_execstart_line,
):
    # Arrange
    captured = _stripped_path_execstart_line
    # Act
    line = captured["line"]
    # Assert — the subprocess must have produced an ExecStart line at all.
    assert line.startswith("ExecStart="), (
        f"subprocess did not emit an ExecStart line; got: {line!r}\n"
        f"stderr: {captured['stderr']!r}"
    )


def test_stripped_path_execstart_does_not_fall_back_to_usr_bin_env(
    _stripped_path_execstart_line,
):
    """REGRESSION (ywata-note-win 12 h crash loop): the unit must not be
    written with `/usr/bin/env <cmd>` under a stripped PATH — that form
    crash-loops at status=127 on a real systemd user manager.
    """
    # Arrange
    captured = _stripped_path_execstart_line
    # Act
    value = captured["line"][len("ExecStart=") :]
    # Assert
    assert not value.startswith("/usr/bin/env "), (
        f"REGRESSION (ywata-note-win): unit ExecStart fell back to "
        f"/usr/bin/env under a stripped PATH.\n"
        f"  ExecStart={value!r}\n"
        f"  stripped PATH={captured['stripped_path']!r}\n"
        f"  interpreter bin/={captured['interpreter_dir']}"
    )


def test_stripped_path_execstart_first_token_is_absolute(
    _stripped_path_execstart_line,
):
    # Arrange
    captured = _stripped_path_execstart_line
    # Act
    first_token = captured["line"][len("ExecStart=") :].split()[0]
    # Assert
    assert first_token.startswith("/"), (
        f"ExecStart first token must be absolute, got {first_token!r}"
    )


def test_stripped_path_execstart_first_token_exists_on_disk(
    _stripped_path_execstart_line,
):
    # Arrange
    captured = _stripped_path_execstart_line
    # Act
    first_token = captured["line"][len("ExecStart=") :].split()[0]
    # Assert
    assert Path(first_token).is_file(), (
        f"ExecStart first token {first_token!r} does not exist as a file"
    )


# EOF
