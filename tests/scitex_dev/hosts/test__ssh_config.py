"""Unit tests for scitex_dev.hosts._ssh_config.

Covers: the naming rule in the rendered output, idempotence, the managed
block never touching lines outside itself, the refusal on a half-present
block, and the operator rule that an unreachable host is never deleted.

No mocks — real temp files, real reads and writes. One assert per test.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scitex_dev.hosts import (
    BEGIN_MARKER,
    END_MARKER,
    HostConnectivity,
    HostRecord,
    HostRegistryError,
    NetRoute,
    render_ssh_config,
    write_managed,
)

_NAS = HostRecord(
    name="scitex-nas-03",
    kind="storage",
    ssh_alias="scitex-nas-03",
    scitex_root="~/.scitex",
    connectivity=HostConnectivity(
        lan="192.168.11.133",
        mac="6c:1f:f7:40:50:11",
        reported_hostname="DXP480TPLUS-994",
        identity_file="~/.ssh/id_mesh",
        ssh_user="ywatanabe",
        last_seen="2026-08-13",
        net=NetRoute(transport="cloudflared", hostname="bastion.scitex.ai"),
    ),
)

_COMPUTE = HostRecord(
    name="scitex-compute-01",
    kind="compute",
    ssh_alias="scitex-compute-01",
    scitex_root="~/.scitex",
    connectivity=HostConnectivity(
        lan="192.168.11.94", reserved="192.168.11.171", last_seen="2026-08-13"
    ),
)

_NO_ADDRESS = HostRecord(
    name="mba", kind="workstation", ssh_alias="mba", scitex_root="~/.scitex"
)


def _stanza_body(text: str, alias: str) -> str:
    """The lines of one `Host <alias>` stanza, up to the next Host/marker."""
    lines = text.splitlines()
    start = lines.index(f"Host {alias}")
    body = []
    for line in lines[start + 1 :]:
        if line.startswith("Host ") or line.startswith("# <<<"):
            break
        body.append(line)
    return "\n".join(body)


# -------- the naming rule in the output --------------------------------------


def test_the_bare_name_gets_the_lan_address():
    # Arrange
    # Act
    text = render_ssh_config([_NAS])
    # Assert
    assert "HostName 192.168.11.133" in _stanza_body(text, "scitex-nas-03")


def test_the_bare_name_never_gets_a_proxy():
    """The 2026-08-13 misconfiguration, asserted as impossible output."""
    # Arrange
    # Act
    body = _stanza_body(render_ssh_config([_NAS]), "scitex-nas-03")
    # Assert
    assert "Proxy" not in body


def test_the_net_name_carries_the_off_lan_route():
    # Arrange
    # Act
    body = _stanza_body(render_ssh_config([_NAS]), "scitex-nas-03-net")
    # Assert
    assert "HostName bastion.scitex.ai" in body


def test_cloudflared_renders_its_proxy_command():
    # Arrange
    # Act
    body = _stanza_body(render_ssh_config([_NAS]), "scitex-nas-03-net")
    # Assert
    assert "ProxyCommand cloudflared access ssh --hostname %h" in body


def test_a_lan_only_host_gets_no_net_stanza():
    # Arrange
    # Act
    text = render_ssh_config([_COMPUTE])
    # Assert
    assert "scitex-compute-01-net" not in text


def test_a_host_with_no_address_renders_no_stanza():
    """A `Host` block with no HostName silently resolves to the alias itself."""
    # Arrange
    # Act
    text = render_ssh_config([_NO_ADDRESS])
    # Assert
    assert "Host mba" not in text


def test_an_empty_registry_says_so_rather_than_rendering_blank():
    # Arrange
    # Act
    text = render_ssh_config([_NO_ADDRESS])
    # Assert
    assert "no host in the registry records" in text


# -------- identity file ------------------------------------------------------


def test_identity_file_is_rendered():
    # Arrange
    # Act
    body = _stanza_body(render_ssh_config([_NAS]), "scitex-nas-03")
    # Assert
    assert "IdentityFile ~/.ssh/id_mesh" in body


def test_identity_file_is_paired_with_identities_only():
    """Otherwise an agent's key order can exhaust MaxAuthTries first."""
    # Arrange
    # Act
    body = _stanza_body(render_ssh_config([_NAS]), "scitex-nas-03")
    # Assert
    assert "IdentitiesOnly yes" in body


# -------- reserved vs observed is visible where the route is read ------------


def test_an_unrenewed_lease_is_annotated_in_the_stanza():
    # Arrange
    # Act
    body = _stanza_body(render_ssh_config([_COMPUTE]), "scitex-compute-01")
    # Assert
    assert "DHCP reservation is 192.168.11.171" in body


def test_last_seen_is_rendered_as_the_age_of_the_claim():
    # Arrange
    # Act
    body = _stanza_body(render_ssh_config([_COMPUTE]), "scitex-compute-01")
    # Assert
    assert "last_seen: 2026-08-13" in body


# -------- idempotence and the managed block ----------------------------------


def test_rendering_twice_produces_identical_text():
    """No timestamp in the header — otherwise every run looks like a change."""
    # Arrange
    first = render_ssh_config([_NAS, _COMPUTE])
    # Act
    second = render_ssh_config([_NAS, _COMPUTE])
    # Assert
    assert first == second


def test_write_creates_the_file(tmp_path):
    # Arrange
    target = tmp_path / "conf.d" / "hosts.conf"
    # Act
    write_managed(target, render_ssh_config([_NAS]))
    # Assert
    assert target.is_file()


def test_write_reports_created(tmp_path):
    # Arrange
    target = tmp_path / "hosts.conf"
    # Act
    outcome = write_managed(target, render_ssh_config([_NAS]))
    # Assert
    assert outcome.created is True


def test_a_second_identical_write_changes_nothing(tmp_path):
    """Idempotence as DATA, not inferred from the absence of an error."""
    # Arrange
    target = tmp_path / "hosts.conf"
    block = render_ssh_config([_NAS])
    write_managed(target, block)
    # Act
    outcome = write_managed(target, block)
    # Assert
    assert outcome.changed is False


def test_write_sets_owner_only_permissions(tmp_path):
    """ssh REFUSES a group/world-readable user config."""
    # Arrange
    target = tmp_path / "hosts.conf"
    # Act
    write_managed(target, render_ssh_config([_NAS]))
    # Assert
    assert oct(target.stat().st_mode & 0o777) == "0o600"


def test_lines_above_the_block_are_preserved(tmp_path):
    # Arrange
    target = tmp_path / "config"
    target.write_text("Host handwritten\n    HostName 10.0.0.1\n")
    # Act
    write_managed(target, render_ssh_config([_NAS]))
    # Assert
    assert "Host handwritten" in target.read_text()


def test_lines_below_the_block_are_preserved(tmp_path):
    # Arrange
    target = tmp_path / "config"
    target.write_text(render_ssh_config([_NAS]) + "Host trailing\n    HostName 10.0.0.2\n")
    # Act
    write_managed(target, render_ssh_config([_COMPUTE]))
    # Assert
    assert "Host trailing" in target.read_text()


def test_rewriting_replaces_only_the_managed_region(tmp_path):
    # Arrange
    target = tmp_path / "config"
    target.write_text(render_ssh_config([_NAS]))
    # Act
    write_managed(target, render_ssh_config([_COMPUTE]))
    # Assert
    assert "scitex-nas-03-net" not in target.read_text()


def test_a_dry_run_writes_nothing(tmp_path):
    # Arrange
    target = tmp_path / "hosts.conf"
    # Act
    write_managed(target, render_ssh_config([_NAS]), dry_run=True)
    # Assert
    assert not target.exists()


def test_a_dry_run_still_reports_what_would_change(tmp_path):
    """A preview that reported nothing would be indistinguishable from a no-op."""
    # Arrange
    target = tmp_path / "hosts.conf"
    # Act
    outcome = write_managed(target, render_ssh_config([_NAS]), dry_run=True)
    # Assert
    assert outcome.state == "created"


def test_a_dry_run_on_a_converged_file_reports_unchanged(tmp_path):
    # Arrange
    target = tmp_path / "hosts.conf"
    block = render_ssh_config([_NAS])
    write_managed(target, block)
    # Act
    outcome = write_managed(target, block, dry_run=True)
    # Assert
    assert outcome.state == "unchanged"


def test_a_dry_run_raises_the_same_refusal_the_real_run_would(tmp_path):
    """A preview that quietly succeeded where the real run fails is worse
    than no preview."""
    # Arrange
    target = tmp_path / "config"
    target.write_text(f"{BEGIN_MARKER}\nHost orphan\n    HostName 10.0.0.3\n")
    # Act
    # Assert
    with pytest.raises(HostRegistryError):
        write_managed(target, render_ssh_config([_NAS]), dry_run=True)


def test_a_half_present_block_is_refused(tmp_path):
    """One marker without its partner: the region's extent is unknown."""
    # Arrange
    target = tmp_path / "config"
    target.write_text(f"{BEGIN_MARKER}\nHost orphan\n    HostName 10.0.0.3\n")
    # Act
    # Assert
    with pytest.raises(HostRegistryError):
        write_managed(target, render_ssh_config([_NAS]))


def test_a_refused_write_leaves_the_file_untouched(tmp_path):
    # Arrange
    target = tmp_path / "config"
    original = f"{END_MARKER}\nHost orphan\n    HostName 10.0.0.3\n"
    target.write_text(original)
    # Act
    try:
        write_managed(target, render_ssh_config([_NAS]))
    except HostRegistryError:
        pass
    # Assert
    assert target.read_text() == original


# -------- unreachable != delete ----------------------------------------------


def test_a_stale_host_is_still_rendered():
    """Operator rule: unreachable != delete. `last_seen` ages; the name stays.

    A generator that dropped an entry on a failed probe would silently
    unregister a laptop closed for a weekend, and the registry would then
    describe the reachability of the moment rather than the fleet.
    """
    # Arrange — last observed a year ago, and nothing has probed it since.
    stale = HostRecord(
        name="scitex-nas-01",
        kind="storage",
        ssh_alias="scitex-nas-01",
        scitex_root="~/.scitex",
        connectivity=HostConnectivity(lan="192.168.11.131", last_seen="2025-08-13"),
    )
    # Act
    text = render_ssh_config([stale])
    # Assert
    assert "Host scitex-nas-01" in text


# EOF
