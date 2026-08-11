# -*- coding: utf-8 -*-
"""A registry serving a RETIRED ssh alias must say so at runtime.

`create_default_hosts_yaml` no-ops once the file exists, so a container that
seeded a bad registry keeps it forever — the only code that would fix it is
the code that never runs again. Correcting the packaged seed (#551) helps
new installs and nothing already deployed. Measured 2026-08-11: this
container's own `/home/agent/.scitex/dev/hosts.yaml` was a month old, served
three aliases retired four days earlier, and was missing four compute hosts.

So the check has to run on the READ path, which is the only code that
touches a frozen file. Reported by dotfiles, who found it by live-firing a
fix rather than trusting it.

WARN phase: nothing raises. `list_hosts` / `resolve` are a published
contract, and a registry that suddenly throws would break every caller in
every already-seeded container at once — precisely the population this
helps.

No mocks (NM001-003): every test writes a REAL hosts.yaml.
One assert per test (STX-TQ007), AAA markers (STX-TQ002).
"""

from __future__ import annotations

from pathlib import Path

from scitex_dev.hosts import list_hosts, resolve
from scitex_dev.hosts._retired import (
    RETIRED_SSH_ALIASES,
    successor_for,
    warn_if_retired,
)


def _registry(tmp_path: Path, ssh_alias: str, name: str = "nas") -> Path:
    p = tmp_path / "hosts.yaml"
    p.write_text(
        "hosts:\n"
        f"  {name}:\n"
        "    kind: storage\n"
        f"    ssh_alias: {ssh_alias}\n"
        '    scitex_root: "~/.scitex"\n',
        encoding="utf-8",
    )
    return p


def test_successor_is_the_one_the_retirement_log_recorded():
    # Arrange — `nas` is the case a naming pattern gets WRONG: it maps to
    # -03, not -01. The pairs come from ~/.ssh/retired-alias-hits.log.
    alias = "nas"
    # Act
    found = successor_for(alias)
    # Assert
    assert found == "scitex-nas-03"


def test_a_live_alias_has_no_recorded_retirement():
    # Arrange — POSITIVE CONTROL for the lookup: it must not claim every
    # name is retired, or the warning would fire on healthy registries.
    alias = "scitex-nas-03"
    # Act
    found = successor_for(alias)
    # Assert
    assert found is None


def test_resolving_a_host_with_a_retired_route_warns(tmp_path, caplog):
    # Arrange — the frozen-container case, byte for byte.
    path = _registry(tmp_path, "nas")
    # Act
    with caplog.at_level("WARNING"):
        resolve("nas", hosts_path=path)
    # Assert
    assert "RETIRED" in caplog.text


def test_the_warning_names_the_successor(tmp_path, caplog):
    # Arrange — a warning that does not say what to use instead costs the
    # reader the same lookup that produced this bug.
    path = _registry(tmp_path, "nas2", name="nas2")
    # Act
    with caplog.at_level("WARNING"):
        resolve("nas2", hosts_path=path)
    # Assert
    assert "scitex-nas-02" in caplog.text


def test_a_healthy_registry_warns_about_nothing(tmp_path, caplog):
    # Arrange — SECOND POSITIVE CONTROL. Every test above passes if the
    # code warned unconditionally, which would be noise indistinguishable
    # from signal.
    path = _registry(tmp_path, "scitex-nas-03", name="scitex-nas-03")
    # Act
    with caplog.at_level("WARNING"):
        resolve("scitex-nas-03", hosts_path=path)
    # Assert
    assert caplog.text == ""


def test_resolve_still_returns_the_record(tmp_path):
    # Arrange — WARN phase: reporting must not become refusing. A caller on
    # a stale registry keeps working; it just learns the route is dead.
    path = _registry(tmp_path, "nas")
    # Act
    record = resolve("nas", hosts_path=path)
    # Assert
    assert record.ssh_alias == "nas"


def test_list_hosts_reports_every_retired_row(tmp_path, caplog):
    # Arrange — a real frozen registry had THREE dead routes, so one row
    # warning is not enough.
    p = tmp_path / "hosts.yaml"
    p.write_text(
        "hosts:\n"
        "  nas:\n    kind: storage\n    ssh_alias: nas\n"
        '    scitex_root: "~/.scitex"\n'
        "  nas1:\n    kind: storage\n    ssh_alias: nas1\n"
        '    scitex_root: "~/.scitex"\n'
        "  nas2:\n    kind: storage\n    ssh_alias: nas2\n"
        '    scitex_root: "~/.scitex"\n',
        encoding="utf-8",
    )
    # Act
    with caplog.at_level("WARNING"):
        list_hosts(hosts_path=p)
    # Assert
    assert len([r for r in caplog.records if "RETIRED" in r.message]) == 3


def test_warning_does_not_depend_on_what_ran_before_it(tmp_path, caplog):
    # Arrange — the first implementation kept a module-level set of
    # already-warned (host, alias) pairs so repeated calls stayed quiet.
    # That made the answer depend on interpreter history: three tests here
    # failed on ORDERING alone. A registry still broken on the second call
    # has not become less broken, and suppressing repeats is a consumer's
    # decision the logging system already implements.
    path = _registry(tmp_path, "nas")
    # Act
    with caplog.at_level("WARNING"):
        resolve("nas", hosts_path=path)
        resolve("nas", hosts_path=path)
    # Assert
    assert len([r for r in caplog.records if "RETIRED" in r.message]) == 2


def test_the_message_is_returned_so_it_can_be_asserted_without_logs():
    # Arrange — callers (and a CLI wanting stderr) need the decision, not
    # just a side effect on the logging system.
    alias = next(iter(RETIRED_SSH_ALIASES))
    # Act
    message = warn_if_retired("some-host", alias)
    # Assert
    assert message is not None and "RETIRED" in message


# EOF
