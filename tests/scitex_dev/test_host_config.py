"""Tests for scitex_dev.host_config (federated HOST-level configuration).

Uses the real ``extra_providers`` injection seam (no mocks) to supply fake
providers, mirroring how discover_jobs / discover_system_deps are tested,
and the real ``root=`` prefix seam so the applier writes into ``tmp_path``
instead of the host's ``/etc``.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from click.testing import CliRunner

from scitex_dev._cli import main
from scitex_dev._ecosystem_jobs._provider import JOB_SHELL_BODIES, provide_jobs
from scitex_dev._host_config import AUDITD_PROCESS_KILL, JOURNALD_PERSISTENT
from scitex_dev._host_config import provide as provide_declarations
from scitex_dev._host_config_apply import (
    apply_specs,
    backup_path_for,
    needs_root,
    observe_specs,
    write_audit,
)
from scitex_dev.host_config import (
    STATE_ABSENT,
    STATE_DRIFT,
    STATE_NOT_APPLICABLE,
    STATE_OK,
    STATE_PRECONDITION_UNMET,
    HostConfigSpec,
    directives_of,
    discover_host_config,
    evaluate,
)


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


def _by_name(name: str) -> HostConfigSpec:
    """One of scitex-dev's own declarations, by name rather than index."""
    return next(s for s in provide_declarations() if s.name == name)


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
# observe_specs -- what the host SAYS, never a compliance verdict        #
# --------------------------------------------------------------------- #
def test_observation_records_the_command_output(tmp_path):
    # Arrange
    spec = _converged(tmp_path, verify_command="echo 192.168.11.187")
    # Act
    records = observe_specs([spec], root=str(tmp_path))
    # Assert
    assert records[0]["output"] == "192.168.11.187"


def test_observation_is_labelled_as_an_observation_not_a_verdict(tmp_path):
    # Arrange
    spec = _converged(tmp_path, verify_command="echo hi")
    # Act
    records = observe_specs([spec], root=str(tmp_path))
    # Assert
    assert records[0]["action"] == "observed"


def test_a_disagreeing_observation_leaves_the_verdict_ok(tmp_path):
    """A requested DHCP address that was not granted is `ok` + a difference.

    Reporting it as drift would accuse a correct config file of a fault
    it does not have, and would train everyone to ignore drift.
    """
    # Arrange
    spec = _converged(tmp_path, verify_command="echo 192.168.11.187")
    # Act
    verdicts = apply_specs([spec], root=str(tmp_path), run_apply_commands=False)
    # Assert
    assert verdicts[0]["action"] == "unchanged"


def test_observation_reports_a_nonzero_exit_without_failing(tmp_path):
    # Arrange
    spec = _converged(tmp_path, verify_command="exit 3")
    # Act
    records = observe_specs([spec], root=str(tmp_path))
    # Assert
    assert records[0]["exit_code"] == 3


def test_no_verify_command_yields_no_observation(tmp_path):
    # Arrange
    spec = _converged(tmp_path)
    # Act
    records = observe_specs([spec], root=str(tmp_path))
    # Assert
    assert records == []


def test_a_root_only_verifier_is_reported_as_not_observed(tmp_path):
    """A permission error in an observation column reads like a finding."""
    # Arrange
    spec = _converged(
        tmp_path, verify_command="echo should-not-run", verify_requires_root=True
    )
    # Act
    records = observe_specs([spec], root=str(tmp_path))
    # Assert
    assert records[0]["action"] == "not-observed"


def test_a_root_only_verifier_does_not_run_unprivileged(tmp_path):
    # Arrange
    spec = _converged(
        tmp_path, verify_command="echo should-not-run", verify_requires_root=True
    )
    # Act
    records = observe_specs([spec], root=str(tmp_path))
    # Assert
    assert records[0]["output"] == ""


def test_auditd_verifier_declares_that_it_needs_root():
    """auditctl -l needs CAP_AUDIT_CONTROL; there is no unprivileged form."""
    # Arrange
    # Act
    spec = _by_name("auditd.process-kill")
    # Assert
    assert spec.verify_requires_root is True


def test_journald_verifier_works_unprivileged():
    """journalctl --list-boots is readable by the adm group; keep it that way."""
    # Arrange
    # Act
    spec = _by_name("journald.persistent")
    # Assert
    assert spec.verify_requires_root is False


def test_no_observation_when_the_precondition_is_unmet(tmp_path):
    """`auditctl -l` on a host with no auditd is a shell error, not a finding."""
    # Arrange
    spec = _spec(
        requires_command="a-binary-that-does-not-exist", verify_command="echo x"
    )
    # Act
    records = observe_specs([spec], root=str(tmp_path))
    # Assert
    assert records == []


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
def test_scitex_dev_declares_persistent_journald():
    # Arrange
    # Act
    specs = provide_declarations()
    # Assert
    assert "journald.persistent" in [s.name for s in specs]


def test_journald_declaration_targets_a_drop_in_not_the_distro_file():
    # Arrange
    # Act
    spec = _by_name("journald.persistent")
    # Assert
    assert spec.path == "/etc/systemd/journald.conf.d/99-scitex-persistent.conf"


def test_journald_declaration_requires_root():
    # Arrange
    # Act
    spec = _by_name("journald.persistent")
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
    spec = _by_name("journald.persistent")
    # Assert
    assert spec.verify_command == "journalctl --list-boots"


def test_journald_declaration_reloads_the_daemon():
    # Arrange
    # Act
    spec = _by_name("journald.persistent")
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
# requires_command -- a file no daemon reads must not report `ok`        #
# --------------------------------------------------------------------- #
def test_precondition_unmet_when_the_required_command_is_missing(tmp_path):
    # Arrange
    spec = _spec(requires_command="a-binary-that-does-not-exist")
    # Act
    status = evaluate(spec, root=str(tmp_path))
    # Assert
    assert status.state == STATE_PRECONDITION_UNMET


def test_precondition_detail_names_the_missing_command(tmp_path):
    # Arrange
    spec = _spec(requires_command="a-binary-that-does-not-exist")
    # Act
    status = evaluate(spec, root=str(tmp_path))
    # Assert
    assert "a-binary-that-does-not-exist" in status.detail


def test_precondition_satisfied_by_a_command_that_exists(tmp_path):
    # Arrange
    spec = _spec(requires_command="sh")
    # Act
    status = evaluate(spec, root=str(tmp_path))
    # Assert
    assert status.state == STATE_ABSENT


def test_apply_refuses_to_write_when_the_precondition_is_unmet(tmp_path):
    """A correct-looking file nothing reads would answer `ok` forever."""
    # Arrange
    spec = _spec(requires_command="a-binary-that-does-not-exist")
    # Act
    apply_specs([spec], root=str(tmp_path))
    # Assert
    assert not _target(tmp_path, spec).exists()


def test_apply_reports_an_unmet_precondition_as_blocked(tmp_path):
    # Arrange
    spec = _spec(requires_command="a-binary-that-does-not-exist")
    # Act
    records = apply_specs([spec], root=str(tmp_path))
    # Assert
    assert records[0]["action"] == "blocked"


def test_force_does_not_override_an_unmet_precondition(tmp_path):
    """--force repairs drift; it cannot conjure the daemon that reads the file."""
    # Arrange
    spec = _spec(requires_command="a-binary-that-does-not-exist")
    # Act
    apply_specs([spec], root=str(tmp_path), force=True)
    # Assert
    assert not _target(tmp_path, spec).exists()


# --------------------------------------------------------------------- #
# scitex-dev's own declaration: auditd process-kill attribution          #
# --------------------------------------------------------------------- #
def test_scitex_dev_declares_the_auditd_ruleset():
    # Arrange
    # Act
    names = [s.name for s in provide_declarations()]
    # Assert
    assert "auditd.process-kill" in names


def test_auditd_declaration_is_gated_on_auditd_being_installed():
    """Without auditctl the file is inert; that must be reportable, not hidden."""
    # Arrange
    # Act
    spec = _by_name("auditd.process-kill")
    # Assert
    assert spec.requires_command == "auditctl"


def test_auditd_rules_audit_the_kill_syscall():
    """`kill` is a shell BUILTIN, so `kill -9` emits no execve at all."""
    # Arrange
    # Act
    body = AUDITD_PROCESS_KILL
    # Assert
    assert "-S kill,tkill,tgkill" in body


def test_auditd_rules_cover_sigkill():
    # Arrange
    # Act
    body = AUDITD_PROCESS_KILL
    # Assert
    assert "-F a1=9" in body


def test_auditd_rules_cover_sigterm():
    # Arrange
    # Act
    body = AUDITD_PROCESS_KILL
    # Assert
    assert "-F a1=15" in body


def test_auditd_rules_audit_tmux_execve():
    """`tmux kill-server` acts from inside the server; only the client's
    execve carries the human's loginuid."""
    # Arrange
    # Act
    body = AUDITD_PROCESS_KILL
    # Assert
    assert "-F exe=/usr/bin/tmux" in body


def test_auditd_rules_audit_pkill_execve():
    # Arrange
    # Act
    body = AUDITD_PROCESS_KILL
    # Assert
    assert "-F exe=/usr/bin/pkill" in body


def test_auditd_rules_scope_to_real_login_sessions():
    # Arrange
    # Act
    body = AUDITD_PROCESS_KILL
    # Assert
    assert body.count("-F auid>=1000") == 6


def test_auditd_rules_use_numeric_unset_for_old_auditctl():
    """The friendlier `auid!=unset` alias is rejected by older auditctl."""
    # Arrange
    # Act
    body = AUDITD_PROCESS_KILL
    # Assert
    assert "-F auid!=unset" not in body


def test_auditd_rules_never_flush_existing_policy():
    """A `-D` in a drop-in would silently wipe every other package's rules."""
    # Arrange
    # Act
    lines = [ln.strip() for ln in AUDITD_PROCESS_KILL.splitlines()]
    # Assert
    assert "-D" not in lines


def test_auditd_declaration_verifies_against_the_kernel_not_the_file():
    """Reading the file back proves it was written, not that it took."""
    # Arrange
    # Act
    spec = _by_name("auditd.process-kill")
    # Assert
    assert spec.verify_command == "auditctl -l"


def test_auditd_declaration_loads_rules_without_restarting_the_daemon():
    # Arrange
    # Act
    spec = _by_name("auditd.process-kill")
    # Assert
    assert spec.apply_command == "augenrules --load"


def test_auditd_rules_stay_readable_so_check_works_unprivileged():
    """0640 would make the honest unprivileged check report false drift."""
    # Arrange
    # Act
    spec = _by_name("auditd.process-kill")
    # Assert
    assert spec.mode == "0644"


def test_auditd_declaration_points_at_the_incident_card_not_a_retelling():
    # Arrange
    # Act
    body = AUDITD_PROCESS_KILL
    # Assert
    assert "hostconfig-federation-journald" in body


# --------------------------------------------------------------------- #
# The scheduled job that federates it                                    #
# --------------------------------------------------------------------- #
def test_host_config_check_is_a_declared_ecosystem_job():
    # Arrange
    jobs = provide_jobs()
    # Act
    names = [j.name for j in jobs]
    # Assert
    assert "host-config-check" in names


def test_host_config_check_catches_up_after_a_boot():
    """A reboot is exactly when host config is most likely to have been lost."""
    # Arrange
    jobs = provide_jobs()
    # Act
    job = next(j for j in jobs if j.name == "host-config-check")
    # Assert
    assert job.on_boot_sec == "5min"


def test_host_config_check_job_runs_the_check_verb():
    # Arrange
    # Act
    body = JOB_SHELL_BODIES["host-config-check"]
    # Assert
    assert "host-config check" in body


def test_host_config_check_job_never_applies():
    """The timer has no root and wants none -- it reports, never converges."""
    # Arrange
    # Act
    body = JOB_SHELL_BODIES["host-config-check"]
    # Assert
    assert "apply" not in body


# --------------------------------------------------------------------- #
# CLI surface                                                            #
# --------------------------------------------------------------------- #
def test_cli_list_json_includes_the_journald_spec():
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(main, ["ecosystem", "host-config", "list", "--json"])
    # Assert
    assert "journald.persistent" in [r["name"] for r in json.loads(result.stdout)]


def test_cli_check_runs_without_privileges():
    """`check` must work as a normal user -- that is what lets the timer run."""
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(main, ["ecosystem", "host-config", "check", "--no-log"])
    # Assert
    assert result.exit_code in (0, 1)


def test_cli_apply_without_yes_is_a_preview():
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(main, ["ecosystem", "host-config", "apply"])
    # Assert
    assert "preview" in result.stdout
