"""Tests for scitex_dev.host_config (federated HOST-level configuration).

Uses the real ``extra_providers`` injection seam (no mocks) to supply fake
providers, mirroring how discover_jobs / discover_system_deps are tested,
and the real ``root=`` prefix seam so the applier writes into ``tmp_path``
instead of the host's ``/etc``.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from click.testing import CliRunner

from scitex_dev._cli import main
from scitex_dev._ecosystem_jobs._provider import JOB_SHELL_BODIES, provide_jobs
from scitex_dev.host_config._declarations import JOURNALD_PERSISTENT
from scitex_dev.host_config._declarations import provide as provide_journald
from scitex_dev.host_config._apply import (
    AUDIT_LOG_ENV,
    apply_specs,
    backup_path_for,
    needs_root,
    write_audit,
)
from scitex_dev.host_config import (
    STATE_ABSENT,
    STATE_DRIFT,
    STATE_NOT_APPLICABLE,
    STATE_OK,
    HostConfigSpec,
    directives_of,
    discover_host_config,
    evaluate,
)


def invoke_cli(runner, args):
    """Invoke the CLI and, on an unhandled exception, FAIL WITH THE TRACEBACK.

    `CliRunner` swallows exceptions into `result.exception` and leaves
    `result.stdout` EMPTY. Every assertion downstream then reports the wrong
    thing: `assert "preview" in ""` says the output was wrong when the
    command actually CRASHED, and the frame that would name the cause never
    reaches the log.

    THIS COST FOUR WRONG DIAGNOSES ON 2026-08-15. A `PermissionError(13)`
    surfaced only as an empty string in an assertion message, on one runner
    (scitex-04-org-cpu-01) and nowhere else. I proposed `write_audit`,
    `scitex_logging`'s import-time mkdir, a root-owned `~/.scitex`, and
    xdist contention — each plausible, each refuted by measurement, none
    of them findable from the evidence the test chose to print.

    So this helper exists to make the NEXT failure self-diagnosing rather
    than to make it pass. An empty stdout is a symptom; the traceback is the
    finding.
    """
    result = runner.invoke(main, args)
    exc = result.exception
    if exc is not None and not isinstance(exc, SystemExit):
        import traceback

        frames = "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        )
        raise AssertionError(
            "the CLI RAISED instead of running, so stdout is empty and any "
            "assertion on it is misleading. Traceback:\n" + frames
        )
    return result


@pytest.fixture(autouse=True)
def isolated_audit_log(tmp_path):
    """Keep every test in this module OFF the real, shared audit log.

    HYGIENE, NOT A FIX — and the distinction is recorded because I got it
    wrong. `write_audit` appends to
    ``~/.scitex/dev/runtime/logs/host-config.log``: one real file, outside
    any tmp_path. The CLI tests here invoke `host-config apply` for real, so
    they wrote to a path no test owned, in a suite that runs under xdist. A
    test that touches shared real state is worth isolating on its own
    merits, whatever else is true.

    WHAT IT DOES NOT FIX. I introduced this believing it explained the CI
    failures, on the theory that concurrent workers contended for that file.
    THAT WAS WRONG: on the very next run,
    `test_a_preview_survives_an_unwritable_audit_log` — which redirects the
    log to tmp_path — still failed with the same PermissionError. The
    exception never came from `write_audit`.

    The real discriminator turned out to be the MACHINE, not concurrency:
    every failure lands on runner scitex-04-org-cpu-01 and never on
    scitex-02 or scitex-03. The "different leg each run" pattern was a proxy
    for "whichever leg landed on scitex-04", because the three legs are
    distributed one per machine.

    Kept, because isolating shared state is right regardless. Documented
    this way so nobody reads it as the cause and stops looking — which is
    exactly what a fix that does not fix anything invites.
    """
    saved = os.environ.get(AUDIT_LOG_ENV)
    os.environ[AUDIT_LOG_ENV] = str(tmp_path / "audit" / "host-config.log")
    try:
        yield
    finally:
        if saved is None:
            os.environ.pop(AUDIT_LOG_ENV, None)
        else:
            os.environ[AUDIT_LOG_ENV] = saved


def _spec(**over) -> HostConfigSpec:
    base = dict(
        name="test.thing",
        path="/etc/scitex-test.d/10-thing.conf",
        content="[Thing]\nEnabled=yes\n",
        purpose="a test",
        provider="scitex-test",
    )
    base.update(over)
    return HostConfigSpec(**base)


def _converged(tmp_path, **over) -> HostConfigSpec:
    """A spec already written into ``tmp_path`` -- the post-apply state."""
    spec = _spec(**over)
    apply_specs([spec], root=str(tmp_path))
    return spec


def _target(tmp_path, spec: HostConfigSpec):
    return tmp_path / spec.path.lstrip("/")


# --------------------------------------------------------------------- #
# Declaration validation -- fail EARLY, never at a root-owned write      #
# --------------------------------------------------------------------- #
def test_rejects_relative_path():
    # Arrange
    bad = "etc/relative.conf"
    # Act
    # Assert
    with pytest.raises(ValueError, match="ABSOLUTE"):
        _spec(path=bad)


def test_rejects_content_without_trailing_newline():
    # Arrange
    bad = "[Thing]\nEnabled=yes"
    # Act
    # Assert
    with pytest.raises(ValueError, match="newline"):
        _spec(content=bad)


def test_rejects_empty_content():
    # Arrange
    bad = ""
    # Act
    # Assert
    with pytest.raises(ValueError, match="non-empty"):
        _spec(content=bad)


def test_rejects_non_octal_mode():
    # Arrange
    bad = "rw-r--r--"
    # Act
    # Assert
    with pytest.raises(ValueError, match="octal"):
        _spec(mode=bad)


# --------------------------------------------------------------------- #
# Federation -- same contract as discover_jobs / discover_system_deps    #
# --------------------------------------------------------------------- #
def test_discover_returns_specs_from_an_injected_provider():
    # Arrange
    def provide():
        return [_spec()]

    # Act
    specs = discover_host_config(
        include_entry_points=False, extra_providers=[provide]
    )
    # Assert
    assert [s.name for s in specs] == ["test.thing"]


def test_discover_dedups_by_name_first_provider_wins():
    # Arrange
    def first():
        return [_spec(purpose="from-first")]

    def second():
        return [_spec(purpose="from-second", path="/etc/other.conf")]

    # Act
    specs = discover_host_config(
        include_entry_points=False, extra_providers=[first, second]
    )
    # Assert
    assert [s.purpose for s in specs] == ["from-first"]


def test_an_unstattable_target_is_drift_not_absent(tmp_path):
    """THE CAUSE OF THE scitex-04 CI FAILURE, found 2026-08-15.

    `Path.exists()` does NOT swallow errors: on 3.12 it PROPAGATES
    PermissionError when a parent directory cannot be traversed. That made
    `evaluate` raise, which aborted the whole `host-config apply` CLI before
    it printed anything — on the one host where /etc/audit exists as
    `drwxr-x--- root:root`, and no other.

    ABSENT would be the dangerous answer, not merely a wrong one: absent is
    the state `apply` CREATES, so an unreadable root-owned file would be
    reported missing and then written.
    """
    # Arrange
    locked = tmp_path / "etc" / "locked"
    locked.mkdir(parents=True)
    (locked / "thing.conf").write_text("x = 1\n", encoding="utf-8")
    locked.chmod(0o000)
    spec = _spec(path="/etc/locked/thing.conf")
    try:
        # Act
        status = evaluate(spec, root=str(tmp_path), hostname="anyhost")
    finally:
        locked.chmod(0o700)
    # Assert
    assert status.state == STATE_DRIFT


def test_the_unstattable_detail_names_the_path_and_the_error(tmp_path):
    """A finding nobody can act on is one people learn to skip."""
    # Arrange
    locked = tmp_path / "etc" / "locked2"
    locked.mkdir(parents=True)
    (locked / "thing.conf").write_text("x = 1\n", encoding="utf-8")
    locked.chmod(0o000)
    spec = _spec(path="/etc/locked2/thing.conf")
    try:
        # Act
        status = evaluate(spec, root=str(tmp_path), hostname="anyhost")
    finally:
        locked.chmod(0o700)
    # Assert
    assert "could not be stat'd" in status.detail


def test_a_stattable_absent_target_is_still_absent(tmp_path):
    """POSITIVE CONTROL. A guard that returned DRIFT for everything would
    pass both tests above while destroying the absent/drift split that is
    the whole point of this module — absent is safe to converge, drift
    never is."""
    # Arrange
    spec = _spec(path="/etc/definitely-not-here.conf")
    # Act
    status = evaluate(spec, root=str(tmp_path), hostname="anyhost")
    # Assert
    assert status.state == STATE_ABSENT


def test_dry_run_overrides_yes_rather_than_the_other_way_round():
    """The two conflicting must resolve to the NON-writing side.

    A decorative `--dry-run` that `--yes` silently beat would satisfy the
    CLI convention rule while doing the opposite of what it says — the
    worst of both, since the flag's presence is what invites trust.
    """
    # Arrange
    runner = CliRunner()
    # Act
    result = invoke_cli(
        runner, ["ecosystem", "host-config", "apply", "--yes", "--dry-run"]
    )
    # Assert
    assert "preview" in result.stdout


def test_per_host_declarations_may_share_one_path():
    """A fleet address map is nine specs, one path, disjoint hosts.

    Keying the collision guard on path ALONE dropped eight of the nine
    and logged a warning nothing surfaces -- the silent loss this
    federation exists to prevent, committed by the guard meant to
    prevent it.
    """
    # Arrange
    def provide():
        return [
            _spec(name=f"dhcp.{h}", path="/etc/netplan/99-scitex.yaml",
                  content=f"addr {h}\n", hosts=(h,))
            for h in ("compute-01", "compute-02", "compute-03", "compute-04")
        ]

    # Act
    specs = discover_host_config(
        include_entry_points=False, extra_providers=[provide]
    )
    # Assert
    assert len(specs) == 4


def test_same_path_still_conflicts_when_two_specs_share_a_host():
    # Arrange
    def provide():
        return [
            _spec(name="a", path="/etc/x.conf", hosts=("h1", "h2")),
            _spec(name="b", path="/etc/x.conf", hosts=("h2", "h3")),
        ]

    # Act
    specs = discover_host_config(
        include_entry_points=False, extra_providers=[provide]
    )
    # Assert
    assert [s.name for s in specs] == ["a"]


def test_an_all_hosts_spec_conflicts_with_a_per_host_one_on_the_same_path():
    """Empty `hosts` means everywhere, so it overlaps with everything."""
    # Arrange
    def provide():
        return [
            _spec(name="everywhere", path="/etc/x.conf"),
            _spec(name="just-one", path="/etc/x.conf", hosts=("h1",)),
        ]

    # Act
    specs = discover_host_config(
        include_entry_points=False, extra_providers=[provide]
    )
    # Assert
    assert [s.name for s in specs] == ["everywhere"]


def test_discover_refuses_two_declarations_of_the_same_path():
    """Two providers fighting over one file is the dangerous collision."""

    # Arrange
    def first():
        return [_spec(name="a.thing")]

    def second():
        return [_spec(name="b.thing")]

    # Act
    specs = discover_host_config(
        include_entry_points=False, extra_providers=[first, second]
    )
    # Assert
    assert [s.name for s in specs] == ["a.thing"]


def test_discover_tolerates_a_broken_provider():
    # Arrange
    def boom():
        raise RuntimeError("leaf is broken")

    def healthy():
        return [_spec()]

    # Act
    specs = discover_host_config(
        include_entry_points=False, extra_providers=[boom, healthy]
    )
    # Assert
    assert [s.name for s in specs] == ["test.thing"]


# --------------------------------------------------------------------- #
# evaluate() -- four outcomes, no writes, no root                        #
# --------------------------------------------------------------------- #
def test_absent_when_the_file_does_not_exist(tmp_path):
    # Arrange
    spec = _spec()
    # Act
    status = evaluate(spec, root=str(tmp_path))
    # Assert
    assert status.state == STATE_ABSENT


def test_ok_when_content_and_mode_match(tmp_path):
    # Arrange
    spec = _converged(tmp_path)
    # Act
    status = evaluate(spec, root=str(tmp_path))
    # Assert
    assert status.state == STATE_OK


def test_drift_when_content_differs(tmp_path):
    # Arrange
    spec = _converged(tmp_path)
    _target(tmp_path, spec).write_text("[Thing]\nEnabled=no\n", encoding="utf-8")
    # Act
    status = evaluate(spec, root=str(tmp_path))
    # Assert
    assert status.state == STATE_DRIFT


def test_drift_detail_names_the_content_mismatch(tmp_path):
    # Arrange
    spec = _converged(tmp_path)
    _target(tmp_path, spec).write_text("[Thing]\nEnabled=no\n", encoding="utf-8")
    # Act
    status = evaluate(spec, root=str(tmp_path))
    # Assert
    assert "content differs" in status.detail


def test_drift_when_mode_differs(tmp_path):
    # Arrange
    spec = _converged(tmp_path)
    _target(tmp_path, spec).chmod(0o600)
    # Act
    status = evaluate(spec, root=str(tmp_path))
    # Assert
    assert status.state == STATE_DRIFT


def test_drift_detail_names_the_actual_mode(tmp_path):
    # Arrange
    spec = _converged(tmp_path)
    _target(tmp_path, spec).chmod(0o600)
    # Act
    status = evaluate(spec, root=str(tmp_path))
    # Assert
    assert "mode is 0600" in status.detail


def test_not_applicable_off_target_host(tmp_path):
    # Arrange
    spec = _spec(hosts=("some-other-host",))
    # Act
    status = evaluate(spec, root=str(tmp_path), hostname="scitex-compute-04")
    # Assert
    assert status.state == STATE_NOT_APPLICABLE


def test_applies_to_every_host_when_hosts_is_empty():
    # Arrange
    spec = _spec()
    # Act
    result = spec.applies_to("anything")
    # Assert
    assert result is True


# --------------------------------------------------------------------- #
# apply_specs() -- idempotent, reports, never converges drift silently   #
# --------------------------------------------------------------------- #
def test_apply_creates_an_absent_file(tmp_path):
    # Arrange
    spec = _spec()
    # Act
    records = apply_specs([spec], root=str(tmp_path))
    # Assert
    assert records[0]["action"] == "created"


def test_apply_writes_the_declared_content_verbatim(tmp_path):
    # Arrange
    spec = _spec()
    # Act
    apply_specs([spec], root=str(tmp_path))
    # Assert
    assert _target(tmp_path, spec).read_text(encoding="utf-8") == spec.content


def test_apply_sets_the_declared_mode(tmp_path):
    # Arrange
    spec = _spec(mode="0600")
    # Act
    apply_specs([spec], root=str(tmp_path))
    # Assert
    assert oct(_target(tmp_path, spec).stat().st_mode & 0o777) == "0o600"


def test_second_apply_is_a_no_op_and_says_so(tmp_path):
    """The idempotence contract: converged reports `unchanged`, not silence."""
    # Arrange
    spec = _converged(tmp_path)
    # Act
    records = apply_specs([spec], root=str(tmp_path))
    # Assert
    assert [r["action"] for r in records] == ["unchanged"]


def test_apply_reports_drift_rather_than_converging_it(tmp_path):
    # Arrange
    spec = _converged(tmp_path)
    _target(tmp_path, spec).write_text("hand-edited\n", encoding="utf-8")
    # Act
    records = apply_specs([spec], root=str(tmp_path))
    # Assert
    assert records[0]["action"] == "drift"


def test_apply_leaves_a_drifted_file_untouched(tmp_path):
    """Quietly re-converging drift destroys the evidence of what happened."""
    # Arrange
    spec = _converged(tmp_path)
    _target(tmp_path, spec).write_text("hand-edited\n", encoding="utf-8")
    # Act
    apply_specs([spec], root=str(tmp_path))
    # Assert
    assert _target(tmp_path, spec).read_text(encoding="utf-8") == "hand-edited\n"


def test_force_repairs_drift(tmp_path):
    # Arrange
    spec = _converged(tmp_path)
    _target(tmp_path, spec).write_text("hand-edited\n", encoding="utf-8")
    # Act
    apply_specs([spec], root=str(tmp_path), force=True)
    # Assert
    assert _target(tmp_path, spec).read_text(encoding="utf-8") == spec.content


def test_force_backs_the_old_file_up_before_overwriting(tmp_path):
    # Arrange
    spec = _converged(tmp_path)
    target = _target(tmp_path, spec)
    target.write_text("hand-edited\n", encoding="utf-8")
    # Act
    apply_specs([spec], root=str(tmp_path), force=True)
    # Assert
    assert [
        p.read_text(encoding="utf-8")
        for p in target.parent.glob(f"{target.name}.scitex-bak.*")
    ] == ["hand-edited\n"]


def test_dry_run_reports_a_would_create(tmp_path):
    # Arrange
    spec = _spec()
    # Act
    records = apply_specs([spec], root=str(tmp_path), dry_run=True)
    # Assert
    assert records[0]["action"] == "would-create"


def test_dry_run_writes_nothing(tmp_path):
    # Arrange
    spec = _spec()
    # Act
    apply_specs([spec], root=str(tmp_path), dry_run=True)
    # Assert
    assert not _target(tmp_path, spec).exists()


def test_apply_command_runs_when_the_file_was_created(tmp_path):
    # Arrange
    marker = tmp_path / "reload-marker"
    spec = _spec(apply_command=f"touch {marker}")
    # Act
    apply_specs([spec], root=str(tmp_path))
    # Assert
    assert marker.exists()


def test_apply_command_does_not_run_on_a_converged_pass(tmp_path):
    """A timer must not restart a daemon every pass over a correct file."""
    # Arrange
    marker = tmp_path / "reload-marker"
    spec = _converged(tmp_path, apply_command=f"touch {marker}")
    marker.unlink()
    # Act
    apply_specs([spec], root=str(tmp_path))
    # Assert
    assert not marker.exists()


def test_apply_command_runs_once_for_two_specs_sharing_it(tmp_path):
    # Arrange
    counter = tmp_path / "count"
    command = f"printf x >> {counter}"
    specs = [
        _spec(name="a", path="/etc/a.conf", apply_command=command),
        _spec(name="b", path="/etc/b.conf", apply_command=command),
    ]
    # Act
    apply_specs(specs, root=str(tmp_path))
    # Assert
    assert counter.read_text(encoding="utf-8") == "x"


def test_needs_root_flags_a_pending_privileged_write(tmp_path):
    # Arrange
    spec = _spec()
    preview = apply_specs(
        [spec], root=str(tmp_path), dry_run=True, run_apply_commands=False
    )
    # Act
    result = needs_root(preview, [spec])
    # Assert
    assert result is True


def test_needs_root_is_false_once_converged(tmp_path):
    # Arrange
    spec = _converged(tmp_path)
    preview = apply_specs(
        [spec], root=str(tmp_path), dry_run=True, run_apply_commands=False
    )
    # Act
    result = needs_root(preview, [spec])
    # Assert
    assert result is False


# --------------------------------------------------------------------- #
# Audit trail -- the record has to survive the run                       #
# --------------------------------------------------------------------- #
def test_audit_log_records_a_run_that_changed_nothing(tmp_path):
    """"All correct at T" is what distinguishes converged from never-ran."""
    # Arrange
    spec = _converged(tmp_path)
    records = apply_specs([spec], root=str(tmp_path))
    log = tmp_path / "audit.log"
    # Act
    write_audit(records, mode="check", log_path=log)
    # Assert
    assert "unchanged" in log.read_text(encoding="utf-8")


def test_audit_log_records_the_mode_it_ran_in(tmp_path):
    # Arrange
    log = tmp_path / "audit.log"
    # Act
    write_audit([], mode="check", log_path=log)
    # Assert
    assert "mode=check" in log.read_text(encoding="utf-8")


def test_audit_log_appends_rather_than_truncating(tmp_path):
    # Arrange
    log = tmp_path / "audit.log"
    write_audit([], mode="check", log_path=log)
    # Act
    write_audit([], mode="check", log_path=log)
    # Assert
    assert len(log.read_text(encoding="utf-8").splitlines()) == 2


def test_backup_path_is_timestamped_and_sortable(tmp_path):
    # Arrange
    when = datetime(2026, 8, 12, 7, 55, 0, tzinfo=timezone.utc)
    # Act
    got = backup_path_for(tmp_path / "x.conf", now=when)
    # Assert
    assert got.name == "x.conf.scitex-bak.20260812T075500Z"


# --------------------------------------------------------------------- #
# scitex-dev's own declaration: persistent journald                      #
# --------------------------------------------------------------------- #
def _journald_spec():
    """The journald declaration, SELECTED BY NAME rather than by position.

    `provide()` returns scitex-dev's whole declaration set, and that set grows:
    journald, then auditd, then one `dhcp.requested-address.*` per machine. Any
    test that indexes `[0]` is asserting an ORDERING nobody promised, and it
    breaks on the next correct addition — which is what happened here when the
    DHCP declarations landed beside the existing two.
    """
    matches = [s for s in provide_journald() if s.name == "journald.persistent"]
    assert len(matches) == 1, f"expected exactly one journald spec, got {matches}"
    return matches[0]


def test_scitex_dev_declares_persistent_journald():
    """MEMBERSHIP, not equality — the assertion now matches the test's name.

    This read `== ["journald.persistent"]`, which asserted the ENTIRE
    federation's contents from a test about one declaration. Adding a correct,
    unrelated declaration failed it, so the test punished exactly the change it
    was never about.
    """
    # Arrange
    # Act
    names = [s.name for s in provide_journald()]
    # Assert
    assert "journald.persistent" in names


def test_journald_declaration_targets_a_drop_in_not_the_distro_file():
    # Arrange
    # Act
    spec = _journald_spec()
    # Assert
    assert spec.path == "/etc/systemd/journald.conf.d/99-scitex-persistent.conf"


def test_journald_declaration_requires_root():
    # Arrange
    # Act
    spec = _journald_spec()
    # Assert
    assert spec.requires_root is True


def test_journald_declaration_sets_storage_persistent():
    """`Storage=auto` silently degrades to RAM-only; persistent is the point."""
    # Arrange
    # Act
    body = JOURNALD_PERSISTENT
    # Assert
    assert "Storage=persistent" in body


def test_journald_declaration_does_not_leave_storage_on_auto():
    """Checked against live directives -- the comments EXPLAIN auto, at length."""
    # Arrange
    # Act
    directives = directives_of(JOURNALD_PERSISTENT)
    # Assert
    assert directives["Storage"] == "persistent"


def test_directives_of_ignores_commented_out_settings():
    # Arrange
    body = "[Journal]\n# Storage=auto\nStorage=persistent\n"
    # Act
    directives = directives_of(body)
    # Assert
    assert directives == {"Storage": "persistent"}


def test_builtin_provider_is_found_without_an_installed_entry_point():
    """The declaration must not depend on dist-info being reinstalled."""
    # Arrange
    # Act
    specs = discover_host_config()
    # Assert
    assert "journald.persistent" in [s.name for s in specs]


def test_journald_declaration_verifies_by_observation_not_by_config():
    """Reading back the file you wrote proves nothing; --list-boots does."""
    # Arrange
    # Act
    spec = _journald_spec()
    # Assert
    assert spec.verify_command == "journalctl --list-boots"


def test_journald_declaration_reloads_the_daemon():
    # Arrange
    # Act
    spec = _journald_spec()
    # Assert
    assert spec.apply_command == "systemctl restart systemd-journald"


def test_journald_declaration_names_the_incident_it_exists_for():
    """A future reader must find WHY without archaeology."""
    # Arrange
    # Act
    body = JOURNALD_PERSISTENT
    # Assert
    assert "2026-08-11" in body


def test_journald_declaration_warns_against_hand_editing():
    # Arrange
    # Act
    body = JOURNALD_PERSISTENT
    # Assert
    assert "Managed by scitex-dev" in body


# --------------------------------------------------------------------- #
# The scheduled job that federates it                                    #
# --------------------------------------------------------------------- #
def test_host_config_check_is_a_declared_ecosystem_job():
    # Arrange
    jobs = provide_jobs()
    # Act
    names = [j.name for j in jobs]
    # Assert
    assert "scitex-dev-host-config-check" in names


def test_host_config_check_catches_up_after_a_boot():
    """A reboot is exactly when host config is most likely to have been lost."""
    # Arrange
    jobs = provide_jobs()
    # Act
    job = next(j for j in jobs if j.name == "scitex-dev-host-config-check")
    # Assert
    assert job.on_boot_sec == "5min"


def test_host_config_check_job_runs_the_check_verb():
    # Arrange
    # Act
    body = JOB_SHELL_BODIES["scitex-dev-host-config-check"]
    # Assert
    assert "host-config check" in body


def test_host_config_check_job_never_applies():
    """The timer has no root and wants none -- it reports, never converges."""
    # Arrange
    # Act
    body = JOB_SHELL_BODIES["scitex-dev-host-config-check"]
    # Assert
    assert "apply" not in body


# --------------------------------------------------------------------- #
# CLI surface                                                            #
# --------------------------------------------------------------------- #
def test_cli_list_json_includes_the_journald_spec():
    # Arrange
    runner = CliRunner()
    # Act
    result = invoke_cli(runner, ["ecosystem", "host-config", "list", "--json"])
    # Assert
    assert "journald.persistent" in [r["name"] for r in json.loads(result.stdout)]


def test_cli_check_runs_without_privileges():
    """`check` must work as a normal user -- that is what lets the timer run."""
    # Arrange
    runner = CliRunner()
    # Act
    result = invoke_cli(runner, ["ecosystem", "host-config", "check", "--no-log"])
    # Assert
    assert result.exit_code in (0, 1)


def test_cli_apply_without_yes_is_a_preview():
    # Arrange
    runner = CliRunner()
    # Act
    result = invoke_cli(runner, ["ecosystem", "host-config", "apply"])
    # Assert
    assert "preview" in result.stdout


@pytest.fixture
def unwritable_audit_log(tmp_path):
    """Point the audit log at a REAL read-only directory.

    No patched internals: the directory is chmod 0o500 on disk and the
    write genuinely fails with the same PermissionError a CI runner
    produced. `audit_log_path()` resolves the env var at call time, which
    is the refactor that made this reachable without rewriting production.
    """
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    saved = os.environ.get(AUDIT_LOG_ENV)
    os.environ[AUDIT_LOG_ENV] = str(locked / "host-config.log")
    try:
        yield
    finally:
        locked.chmod(0o700)
        if saved is None:
            os.environ.pop(AUDIT_LOG_ENV, None)
        else:
            os.environ[AUDIT_LOG_ENV] = saved


def test_the_locked_directory_really_is_unwritable(unwritable_audit_log):
    """CONTROL FOR THE FIXTURE ITSELF.

    Every test below is meaningless if the chmod silently did nothing —
    running as root, or on a filesystem that ignores mode bits, would make
    them all pass while testing the ordinary writable path. This asserts
    the precondition rather than assuming it.
    """
    # Arrange
    target = Path(os.environ[AUDIT_LOG_ENV])
    # Act
    def attempt():
        target.open("a").close()

    # Assert
    with pytest.raises(OSError):
        attempt()


def test_a_preview_survives_an_unwritable_audit_log(unwritable_audit_log):
    """THE TRUNK BREAKAGE, 2026-08-15.

    `write_audit` appends under ``~/.scitex/dev/runtime/logs/``. On a CI
    runner where that directory was not writable, the PermissionError
    aborted the command BEFORE it printed anything: stdout was empty and
    the user got a traceback instead of the preview they asked for.

    A preview changed nothing, so its record costs a log line. The result
    is the preview; the telemetry is secondary.
    """
    # Arrange
    runner = CliRunner()
    # Act
    result = invoke_cli(runner, ["ecosystem", "host-config", "apply"])
    # Assert
    assert "preview" in result.stdout


def test_the_unwritable_audit_log_is_announced_not_swallowed(unwritable_audit_log):
    """Surviving it must not mean hiding it — the log path still needs fixing
    before anyone runs --yes, and that is what the message says."""
    # Arrange
    runner = CliRunner()
    # Act
    result = invoke_cli(runner, ["ecosystem", "host-config", "apply"])
    # Assert
    assert "audit log" in result.output


def test_a_real_apply_still_refuses_when_it_cannot_be_recorded(unwritable_audit_log):
    """POSITIVE CONTROL, and the half that must NOT become lenient.

    A dry run that goes unrecorded costs nothing. A REAL apply that goes
    unrecorded is precisely the "converged, or never ran?" ambiguity this
    log exists to remove, so it is still allowed to fail. A fix that made
    both paths tolerant would pass the two tests above and quietly delete
    the guarantee.
    """
    # Arrange
    runner = CliRunner()
    # Act
    result = invoke_cli(runner, ["ecosystem", "host-config", "apply", "--yes"])
    # Assert
    assert result.exit_code != 0
