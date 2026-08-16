"""Refusing to declare a file onto storage a reboot erases.

The motivating measurement, taken 2026-08-12 on `scitex-nas-01` and
`scitex-nas-02` (both QNAP QTS):

    none / tmpfs rw,relatime,size=409600k,mode=755

`/` is a 400 MB ramdisk, so `/etc/dhcp`, `/etc/audit` and `/etc/systemd`
all live in RAM and QTS restores the tree from firmware at every boot. A
spec applied there converges, `check` says `ok`, and the setting is gone
after the next reboot — and an apply-then-check job in one run reports
`ok` forever on a host that has never once held the configuration.

Two properties are pinned here, and the second matters as much as the
first:

1. tmpfs/ramfs IS caught, and by longest PATH-COMPONENT prefix. Raw string
   prefixing would be subtly wrong: this project's own agent containers
   mount a tmpfs at `/etc/passwd`, which string-prefixes
   `/etc/passwd_backup` on the durable root.
2. Everything else is "not detected", NOT "durable". `scitex-nas-03` has a
   persistent overlay root and still loses its dhclient.conf every boot to
   a vendor script. A filesystem check cannot see that, and this module
   must not be read as certifying persistence.

No mocks (NM001-003): the mount table is a real file written to tmp_path
in `/proc/mounts` format, not a patched reader — the parser is most of
what is under test, so faking it would test nothing.
One assert per test (STX-TQ007), Arrange/Act/Assert markers (STX-TQ002).
"""

from __future__ import annotations

from scitex_dev.host_config._volatility import (
    VOLATILE_FSTYPES,
    filesystem_of,
    volatile_reason,
)

#: Trimmed from the real table on scitex-nas-01 (QNAP), plus the
#: /etc/passwd tmpfs this project's agent containers really do mount.
_QNAP_MOUNTS = """\
none / tmpfs rw,relatime,size=409600k,mode=755
/dev/md9 /mnt/HDA_ROOT ext4 rw,data=ordered
tmpfs /tmp tmpfs rw,size=64M
"""

#: scitex-compute-03: an ordinary durable root.
_UBUNTU_MOUNTS = """\
/dev/mapper/ubuntu--vg-ubuntu--lv / ext4 rw,relatime
tmpfs /run tmpfs rw,nosuid,nodev
"""

#: The container shape: durable-ish overlay root with a tmpfs mounted at a
#: FILE inside /etc — the string-prefix trap.
_CONTAINER_MOUNTS = """\
fuse-overlayfs / fuse.fuse-overlayfs rw,nosuid,nodev
tmpfs /etc/passwd tmpfs rw,nosuid,size=65536k
"""

#: A mount point containing a space, which /proc/mounts octal-escapes.
_ESCAPED_MOUNTS = """\
/dev/sdb1 /mnt/my\\040disk ext4 rw
/dev/sda1 / ext4 rw
"""


def _mounts(tmp_path, text):
    path = tmp_path / "mounts"
    path.write_text(text)
    return str(path)


def test_a_tmpfs_root_makes_an_etc_path_volatile(tmp_path):
    # Arrange — the QNAP case this module exists for.
    mounts = _mounts(tmp_path, _QNAP_MOUNTS)
    # Act
    reason = volatile_reason("/etc/dhcp/dhclient.conf", mounts_path=mounts)
    # Assert
    assert reason is not None


def test_the_reason_names_the_filesystem_type(tmp_path):
    # Arrange — "it will not persist" is not actionable; "it is tmpfs" is.
    mounts = _mounts(tmp_path, _QNAP_MOUNTS)
    # Act
    reason = volatile_reason("/etc/dhcp/dhclient.conf", mounts_path=mounts)
    # Assert
    assert "tmpfs" in reason


def test_the_reason_says_the_check_would_report_ok_forever(tmp_path):
    # Arrange — the point is not that it reverts, but that the guard keeps
    # claiming success while it does.
    mounts = _mounts(tmp_path, _QNAP_MOUNTS)
    # Act
    reason = volatile_reason("/etc/dhcp/dhclient.conf", mounts_path=mounts)
    # Assert
    assert "ok forever" in reason


def test_a_durable_root_is_not_flagged(tmp_path):
    # Arrange — the compute boxes must keep working.
    mounts = _mounts(tmp_path, _UBUNTU_MOUNTS)
    # Act
    reason = volatile_reason(
        "/etc/systemd/network/10-netplan-enp3s0f0.network.d/50-x.conf",
        mounts_path=mounts,
    )
    # Assert
    assert reason is None


def test_a_path_under_a_tmpfs_submount_is_flagged(tmp_path):
    # Arrange — /run is tmpfs on an otherwise durable host.
    mounts = _mounts(tmp_path, _UBUNTU_MOUNTS)
    # Act
    reason = volatile_reason("/run/systemd/network/x.network", mounts_path=mounts)
    # Assert
    assert reason is not None


def test_longest_prefix_wins_over_the_root_mount(tmp_path):
    # Arrange — / is durable but /run is not; the deeper mount decides.
    mounts = _mounts(tmp_path, _UBUNTU_MOUNTS)
    # Act
    found = filesystem_of("/run/foo", mounts_path=mounts)
    # Assert
    assert found == ("/run", "tmpfs")


def test_a_sibling_of_a_tmpfs_FILE_mount_is_not_captured(tmp_path):
    # Arrange — the string-prefix trap: a tmpfs at /etc/passwd must not
    # claim /etc/passwd_backup, which lives on the durable root.
    mounts = _mounts(tmp_path, _CONTAINER_MOUNTS)
    # Act
    reason = volatile_reason("/etc/passwd_backup", mounts_path=mounts)
    # Assert
    assert reason is None


def test_the_tmpfs_file_mount_itself_is_still_captured(tmp_path):
    # Arrange — the exact path IS the mount point, which must match.
    mounts = _mounts(tmp_path, _CONTAINER_MOUNTS)
    # Act
    reason = volatile_reason("/etc/passwd", mounts_path=mounts)
    # Assert
    assert reason is not None


def test_an_octal_escaped_mount_point_is_decoded(tmp_path):
    # Arrange — /proc/mounts writes a space as \\040; leaving it encoded
    # means that mount never matches a real path.
    mounts = _mounts(tmp_path, _ESCAPED_MOUNTS)
    # Act
    found = filesystem_of("/mnt/my disk/thing", mounts_path=mounts)
    # Assert
    assert found == ("/mnt/my disk", "ext4")


def test_an_unreadable_mount_table_makes_no_claim(tmp_path):
    # Arrange — must degrade to "unknown", never to an exception inside an
    # unprivileged status command.
    missing = str(tmp_path / "does-not-exist")
    # Act
    reason = volatile_reason("/etc/anything", mounts_path=missing)
    # Assert
    assert reason is None


def test_an_unreadable_mount_table_is_not_reported_as_durable(tmp_path):
    # Arrange — the companion to the above: "no mount found" must be
    # distinguishable from "found a durable one".
    missing = str(tmp_path / "does-not-exist")
    # Act
    found = filesystem_of("/etc/anything", mounts_path=missing)
    # Assert
    assert found is None


def test_malformed_rows_are_skipped_not_fatal(tmp_path):
    # Arrange — a truncated line must not take out the whole table.
    mounts = _mounts(tmp_path, "garbage\n/dev/sda1 / ext4 rw\n")
    # Act
    found = filesystem_of("/etc/x", mounts_path=mounts)
    # Assert
    assert found == ("/", "ext4")


def test_overlay_is_deliberately_not_treated_as_volatile():
    # Arrange — an overlay with a disk-backed upperdir persists, and
    # scitex-nas-03 plus every agent container are that shape. Blocking
    # them all would be wrong far more often than right.
    # Act
    volatile = VOLATILE_FSTYPES
    # Assert
    assert "overlay" not in volatile


def test_the_volatile_set_stays_conservative():
    # Arrange — a false positive REFUSES a declaration that would have
    # worked, so membership must be volatile-by-definition, not by local
    # convention.
    # Act
    volatile = VOLATILE_FSTYPES
    # Assert
    assert volatile == frozenset({"tmpfs", "ramfs"})


# EOF
