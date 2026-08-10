# -*- coding: utf-8 -*-
"""`HostRecord.aliases` — a former spelling must keep resolving.

The field exists so a host can be RE-KEYED without orphaning whatever already
referenced the old name. Host names are on-disk keys (cron, JobSpecs, sync
configs, other packages' rows), and a rewritten key orphans them silently —
"nothing to do" rather than an error.

No mocks (STX-NM002): every case writes a REAL `hosts.yaml` under `tmp_path`
and passes it through the existing `hosts_path=` file-path seam. Nothing is
patched.

One assert per test (STX-TQ007), Arrange/Act/Assert markers (STX-TQ002).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scitex_dev.hosts import HostRegistryError, UnknownHostError, resolve


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "hosts.yaml"
    path.write_text(body, encoding="utf-8")
    return path


_RENAMED = """\
hosts:
  scitex-nas-03:
    kind: storage
    ssh_alias: nas-03
    scitex_root: "~/.scitex"
    aliases: [nas, nas3]
"""


@pytest.fixture
def renamed_host(tmp_path) -> Path:
    """A host re-keyed to its canonical name, keeping the old spellings."""
    return _write(tmp_path, _RENAMED)


# -------- the old spelling still reaches the host --------------------------


def test_alias_resolves_to_the_canonical_record(renamed_host):
    # Arrange — `nas` is the moving alias the fleet used before the re-key.
    registry = renamed_host
    # Act
    record = resolve("nas", hosts_path=registry)
    # Assert
    assert record.name == "scitex-nas-03"


def test_second_alias_also_resolves(renamed_host):
    # Arrange — a host may carry several former spellings.
    registry = renamed_host
    # Act
    record = resolve("nas3", hosts_path=registry)
    # Assert
    assert record.name == "scitex-nas-03"


def test_canonical_name_still_resolves(renamed_host):
    # Arrange — adding aliases must not disturb the primary lookup.
    registry = renamed_host
    # Act
    record = resolve("scitex-nas-03", hosts_path=registry)
    # Assert
    assert record.name == "scitex-nas-03"


def test_aliases_are_exposed_on_the_record(renamed_host):
    # Arrange
    registry = renamed_host
    # Act
    record = resolve("scitex-nas-03", hosts_path=registry)
    # Assert
    assert record.aliases == ("nas", "nas3")


def test_unknown_name_still_fails_loud(renamed_host):
    # Arrange — the fallback must not turn a typo into a silent match.
    registry = renamed_host
    # Act
    # Assert
    with pytest.raises(UnknownHostError):
        resolve("nas-99", hosts_path=registry)


# -------- a canonical key OUTRANKS another host's alias --------------------


def test_canonical_key_wins_over_another_hosts_alias(tmp_path):
    """A name that is somebody's canonical key must never be captured.

    Canonical keys are tried first and exhaustively for exactly this case: if
    alias matching ran first, `mba` would resolve to `spartan` here and every
    command aimed at one machine would silently reach another.
    """
    # Arrange
    registry = _write(
        tmp_path,
        "hosts:\n"
        "  mba:\n    kind: workstation\n    scitex_root: '~/.scitex'\n"
        "  spartan:\n    kind: hpc-login\n    scitex_root: '~/.scitex'\n"
        "    aliases: [mba]\n",
    )
    # Act
    record = resolve("mba", hosts_path=registry)
    # Assert
    assert record.name == "mba"


def test_alias_claimed_by_two_hosts_raises(tmp_path):
    """Resolving would be a GUESS, and the guess reaches the wrong machine."""
    # Arrange
    registry = _write(
        tmp_path,
        "hosts:\n"
        "  host-a:\n    kind: storage\n    scitex_root: '~/.scitex'\n"
        "    aliases: [shared]\n"
        "  host-b:\n    kind: storage\n    scitex_root: '~/.scitex'\n"
        "    aliases: [shared]\n",
    )
    # Act
    # Assert
    with pytest.raises(HostRegistryError):
        resolve("shared", hosts_path=registry)


# -------- malformed input FAILS rather than degrading to empty -------------


def test_bare_string_aliases_is_rejected(tmp_path):
    """`aliases: nas` reads as one alias to a human but iterates to letters.

    Wrapping it helpfully would make the literal reading and the intended one
    disagree, so it is refused instead.
    """
    # Arrange
    registry = _write(
        tmp_path,
        "hosts:\n  h:\n    kind: storage\n    scitex_root: '~/.scitex'\n"
        "    aliases: nas\n",
    )
    # Act
    # Assert
    with pytest.raises(HostRegistryError):
        resolve("h", hosts_path=registry)


def test_empty_string_alias_is_rejected(tmp_path):
    # Arrange — an empty alias would match nothing while looking configured.
    registry = _write(
        tmp_path,
        "hosts:\n  h:\n    kind: storage\n    scitex_root: '~/.scitex'\n"
        "    aliases: ['']\n",
    )
    # Act
    # Assert
    with pytest.raises(HostRegistryError):
        resolve("h", hosts_path=registry)


def test_self_alias_is_rejected(tmp_path):
    # Arrange — listing the canonical name is meaningless, and it hides
    # whether the author meant a DIFFERENT spelling.
    registry = _write(
        tmp_path,
        "hosts:\n  h:\n    kind: storage\n    scitex_root: '~/.scitex'\n"
        "    aliases: [h]\n",
    )
    # Act
    # Assert
    with pytest.raises(HostRegistryError):
        resolve("h", hosts_path=registry)


# -------- absence is the norm and must stay silent ------------------------


def test_host_without_aliases_defaults_to_empty(tmp_path):
    # Arrange — the overwhelming majority of rows carry no aliases.
    registry = _write(
        tmp_path,
        "hosts:\n  h:\n    kind: storage\n    scitex_root: '~/.scitex'\n",
    )
    # Act
    record = resolve("h", hosts_path=registry)
    # Assert
    assert record.aliases == ()

# EOF
