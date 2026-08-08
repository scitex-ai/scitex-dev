"""Unit tests for scitex_dev.hosts._aliases — the logical-label surface.

Covers the `aliases:` schema that lets a registry KEY be a fleet label
(`scitex-laptop-01`) while the name the machine actually answers to
(`ywata-note-win`) keeps resolving: parsing, resolution precedence, and
the loud refusals on an ambiguous index.

No mocks (NM001-003) — every case writes a real hosts.yaml under tmp_path
and passes it via the `hosts_path=` seam, so the canonical
`~/.scitex/dev/hosts.yaml` is never read or written. One assert per test
(STX-TQ007 / 02_package/13_test-quality.md), Arrange/Act/Assert.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scitex_dev.hosts import HostRegistryError, UnknownHostError, list_hosts, resolve

_LAPTOP_WITH_ALIASES = """\
hosts:
  scitex-laptop-01:
    kind: workstation
    ssh_alias: null
    scitex_root: "~/.scitex"
    hostname_reported: ywata-note-win
    aliases:
      - ywata-note-win
      - ywata
  nas:
    kind: storage
    ssh_alias: nas
    scitex_root: "~/.scitex"
"""

_NO_ALIASES = """\
hosts:
  nas:
    kind: storage
    ssh_alias: nas
    scitex_root: "~/.scitex"
"""

_TWO_HOSTS_ONE_ALIAS = """\
hosts:
  host-a:
    kind: workstation
    ssh_alias: a
    scitex_root: "~/.scitex"
    aliases: [shared]
  host-b:
    kind: workstation
    ssh_alias: b
    scitex_root: "~/.scitex"
    aliases: [shared]
"""


def _write(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "hosts.yaml"
    p.write_text(content)
    return p


# -------- parsing ----------------------------------------------------------


def test_aliases_are_parsed_into_a_tuple(tmp_path: Path) -> None:
    # Arrange
    path = _write(tmp_path, _LAPTOP_WITH_ALIASES)
    # Act
    record = resolve("scitex-laptop-01", hosts_path=path)
    # Assert
    assert record.aliases == ("ywata-note-win", "ywata")


def test_absent_aliases_block_is_not_an_error(tmp_path: Path) -> None:
    # Arrange
    path = _write(tmp_path, _NO_ALIASES)
    # Act
    record = resolve("nas", hosts_path=path)
    # Assert
    assert record.aliases == ()


def test_duplicate_aliases_within_one_host_are_collapsed(tmp_path: Path) -> None:
    # Arrange
    path = _write(
        tmp_path,
        """\
hosts:
  mba:
    kind: workstation
    ssh_alias: mba
    scitex_root: "~/.scitex"
    aliases: [macbook-air, macbook-air]
""",
    )
    # Act
    record = resolve("mba", hosts_path=path)
    # Assert
    assert record.aliases == ("macbook-air",)


def test_bare_string_aliases_block_is_rejected(tmp_path: Path) -> None:
    # Arrange: a bare string is a YAML typo whose "obvious" wrapped
    # reading is wrong -- `aliases: a, b` becomes ONE alias named "a, b".
    path = _write(
        tmp_path,
        """\
hosts:
  mba:
    kind: workstation
    ssh_alias: mba
    scitex_root: "~/.scitex"
    aliases: macbook-air
""",
    )
    # Act
    # Assert
    with pytest.raises(HostRegistryError, match="must be a LIST"):
        list_hosts(hosts_path=path)


def test_non_string_alias_entry_is_rejected(tmp_path: Path) -> None:
    # Arrange
    path = _write(
        tmp_path,
        """\
hosts:
  mba:
    kind: workstation
    ssh_alias: mba
    scitex_root: "~/.scitex"
    aliases: [42]
""",
    )
    # Act
    # Assert
    with pytest.raises(HostRegistryError, match="must be a string"):
        list_hosts(hosts_path=path)


def test_empty_alias_entry_is_rejected(tmp_path: Path) -> None:
    # Arrange
    path = _write(
        tmp_path,
        """\
hosts:
  mba:
    kind: workstation
    ssh_alias: mba
    scitex_root: "~/.scitex"
    aliases: ["  "]
""",
    )
    # Act
    # Assert
    with pytest.raises(HostRegistryError, match="empty alias"):
        list_hosts(hosts_path=path)


# -------- resolution -------------------------------------------------------


def test_resolve_finds_a_host_by_its_alias(tmp_path: Path) -> None:
    # Arrange: the whole point -- the key is the logical label, and the
    # name the machine answers to still resolves.
    path = _write(tmp_path, _LAPTOP_WITH_ALIASES)
    # Act
    record = resolve("ywata-note-win", hosts_path=path)
    # Assert
    assert record.name == "scitex-laptop-01"


def test_resolve_still_finds_a_host_by_its_key(tmp_path: Path) -> None:
    # Arrange
    path = _write(tmp_path, _LAPTOP_WITH_ALIASES)
    # Act
    record = resolve("scitex-laptop-01", hosts_path=path)
    # Assert
    assert record.name == "scitex-laptop-01"


def test_a_host_may_alias_its_own_key(tmp_path: Path) -> None:
    # Arrange: redundant, not wrong -- it resolves to the same machine
    # either way, and refusing it would punish a verbose config.
    path = _write(
        tmp_path,
        """\
hosts:
  mba:
    kind: workstation
    ssh_alias: mba
    scitex_root: "~/.scitex"
    aliases: [mba]
""",
    )
    # Act
    record = resolve("mba", hosts_path=path)
    # Assert
    assert record.name == "mba"


def _unknown_host_message(name: str, hosts_path: Path) -> str:
    """Return the UnknownHostError text for ``name``, or "" if none was raised.

    A helper rather than a `pytest.raises` block so the assertion budget
    stays on the ONE thing under test -- what the message CONTAINS. That
    the call raises at all is already covered by the registry's own
    suite; re-asserting it here would cost the single assert TQ007
    allows and leave the message content unchecked.
    """
    try:
        resolve(name, hosts_path=hosts_path)
    except UnknownHostError as exc:
        return str(exc)
    return ""


def test_unknown_name_error_lists_aliases_too(tmp_path: Path) -> None:
    # Arrange: a caller who used a legitimate alias must not be told it
    # does not exist by an error that then omits every alias.
    path = _write(tmp_path, _LAPTOP_WITH_ALIASES)
    # Act
    message = _unknown_host_message("nope", path)
    # Assert
    assert "ywata-note-win" in message


# -------- ambiguity is refused, never ranked -------------------------------


def test_alias_claimed_by_two_hosts_is_refused(tmp_path: Path) -> None:
    # Arrange
    path = _write(tmp_path, _TWO_HOSTS_ONE_ALIAS)
    # Act
    # Assert
    with pytest.raises(HostRegistryError, match="claimed by both"):
        list_hosts(hosts_path=path)


def test_alias_shadowing_another_hosts_key_is_refused(tmp_path: Path) -> None:
    # Arrange: the key always resolves to itself, so this alias could
    # never win -- dropping it silently would hide a naming conflict.
    path = _write(
        tmp_path,
        """\
hosts:
  nas:
    kind: storage
    ssh_alias: nas
    scitex_root: "~/.scitex"
  workstation:
    kind: workstation
    ssh_alias: ws
    scitex_root: "~/.scitex"
    aliases: [nas]
""",
    )
    # Act
    # Assert
    with pytest.raises(HostRegistryError, match="another host's registry key"):
        list_hosts(hosts_path=path)


def test_ambiguity_fails_list_hosts_not_only_resolve(tmp_path: Path) -> None:
    # Arrange: an ambiguous alias is a property of the FILE. If only
    # resolve() noticed, the inventory would read clean and one unlucky
    # caller would be the only one to learn the registry is broken.
    path = _write(tmp_path, _TWO_HOSTS_ONE_ALIAS)
    # Act
    # Assert
    with pytest.raises(HostRegistryError):
        list_hosts(hosts_path=path)


# -------- serialisation ----------------------------------------------------


def test_to_dict_carries_aliases(tmp_path: Path) -> None:
    # Arrange
    path = _write(tmp_path, _LAPTOP_WITH_ALIASES)
    # Act
    payload = resolve("scitex-laptop-01", hosts_path=path).to_dict()
    # Assert
    assert payload["aliases"] == ["ywata-note-win", "ywata"]


# EOF
