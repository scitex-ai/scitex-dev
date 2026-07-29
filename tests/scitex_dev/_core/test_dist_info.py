#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex_dev._core.dist_info`` must DETECT duplicates, never delete them.

REAL tmp-dir fixtures, NO mocks (STX-NM002 forbids monkeypatch): every case
builds actual ``*.dist-info`` directories on disk and passes them through the
``site_packages`` seam.

WHAT THIS FILE PINS, stated precisely because the severity was measured and
came back LOWER than assumed. Until 2026-07-29 ``clean_stale_dist_info()``
sorted a package's dist-infos by MTIME and ``shutil.rmtree``'d all but the
newest, and ran unconditionally inside the skills-export path. Mtime is not
version ordering (``cp -p`` preserves it, image builds stamp it, an overlay
lower-layer directory carries the base image's), so with mtime order REVERSED
relative to version order that code would delete the NEWER distribution's
metadata, leaving a package that imports fine while reporting the wrong
version.

IT NEVER FIRED. Measured on a real venv: the grouping key was
``d.name.rsplit("-", 1)[0]`` with ``.dist-info`` still on the name, so the
split hit the hyphen in "dist-info" and every distribution grouped under a
key containing its own version — groups of size 1, ``continue``, nothing
deleted, return ``[]``. So these tests are NOT a red-to-green regression
against origin/develop's behaviour, and must not be described as one: on
develop nothing is deleted because nothing is ever grouped.

They are a GUARD. The removal is gone, and the grouping is now correct — the
combination a one-line "fix the obvious typo" commit would otherwise turn
into an armed, mtime-ordered ``rmtree`` inside an unrelated export path.
``test_duplicates_are_reported`` pins the half that must work; the
``*_deletes_nothing`` tests pin the half that must not come back.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from scitex_dev._core.dist_info import (
    clean_stale_dist_info,
    find_duplicate_dist_infos,
    report_duplicate_dist_infos,
)


def _make_dist_info(
    site: Path, dist: str, version: str, mtime: float | None = None
) -> Path:
    """A real ``<dist>-<version>.dist-info`` directory with a METADATA file."""
    site.mkdir(parents=True, exist_ok=True)
    info = site / f"{dist.replace('-', '_')}-{version}.dist-info"
    info.mkdir()
    (info / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {dist}\nVersion: {version}\n"
    )
    if mtime is not None:
        os.utime(info, (mtime, mtime))
    return info


@pytest.fixture
def reverse_mtime_site(tmp_path: Path) -> Path:
    """Two real dist-infos whose MTIME ORDER REVERSES their VERSION ORDER.

    The NEWER version (2.0) carries the OLDER mtime — the exact shape ``cp -p``
    or an image build produces. Had the pre-2026-07-29 grouping worked, its
    mtime sort would have deleted 2.0 and kept 1.0. (It did not work; see the
    module docstring. These fixtures pin the behaviour that must hold once
    grouping DOES work, which it now does.)
    """
    _make_dist_info(tmp_path, "foo", "2.0", mtime=1_000_000.0)
    _make_dist_info(tmp_path, "foo", "1.0", mtime=2_000_000.0)
    return tmp_path


@pytest.fixture
def whiteout_standin_site(tmp_path: Path) -> Path:
    """One real dist-info plus NON-DIRECTORY entries carrying dist-info names.

    LABELLED STAND-INS: the real case is an overlayfs WHITEOUT, a
    character-special device node (major 0, minor 0). This container cannot
    create one — measured: ``mknod`` fails with ``CapEff 0000000000000000``
    and ``mount -t overlay`` refuses with "must be superuser" — and
    STX-NM002 forbids faking it with a mock. A plain FILE and a DANGLING
    SYMLINK exercise the same rejection path (``Path.is_dir()``), because a
    whiteout, like a file, is not a directory. They stand in for the
    whiteout; they are not one.
    """
    _make_dist_info(tmp_path, "foo", "2.0")
    (tmp_path / "foo-1.0.dist-info").write_text("not a directory\n")
    (tmp_path / "foo-0.9.dist-info").symlink_to(tmp_path / "nonexistent-target")
    return tmp_path


# --- Reverse mtime: nothing may be deleted -----------------------------------


def test_newer_version_metadata_survives_reverse_mtime(reverse_mtime_site):
    # Arrange — 2.0 carries the OLDER mtime, so an mtime sort would pick it
    # as the victim.
    newer = reverse_mtime_site / "foo-2.0.dist-info"
    # Act
    find_duplicate_dist_infos(site_packages=reverse_mtime_site)
    # Assert — THE regression: the newer distribution's metadata is intact.
    assert newer.is_dir()


def test_older_version_metadata_also_survives_reverse_mtime(reverse_mtime_site):
    # Arrange — detection must not delete the other one either.
    older = reverse_mtime_site / "foo-1.0.dist-info"
    # Act
    find_duplicate_dist_infos(site_packages=reverse_mtime_site)
    # Assert
    assert older.is_dir()


def test_reporting_deletes_nothing(reverse_mtime_site):
    # Arrange
    before = sorted(p.name for p in reverse_mtime_site.iterdir())
    # Act
    report_duplicate_dist_infos(site_packages=reverse_mtime_site)
    # Assert — the directory listing is byte-for-byte unchanged.
    assert sorted(p.name for p in reverse_mtime_site.iterdir()) == before


def test_deprecated_clean_entry_point_deletes_nothing(reverse_mtime_site):
    # Arrange — the old destructive name must be inert now.
    before = sorted(p.name for p in reverse_mtime_site.iterdir())
    # Act
    clean_stale_dist_info(site_packages=reverse_mtime_site)
    # Assert
    assert sorted(p.name for p in reverse_mtime_site.iterdir()) == before


# --- Detection still detects -------------------------------------------------


def test_duplicates_are_reported(reverse_mtime_site):
    # Arrange — the predecessor could not report this: its grouping key kept
    # the version (it split on the hyphen inside ".dist-info"), so no two
    # distributions ever landed in the same group.
    package = "foo"
    # Act
    duplicates = find_duplicate_dist_infos(site_packages=reverse_mtime_site)
    # Assert — silence would be the other failure mode.
    assert package in duplicates


def test_both_duplicates_are_listed(reverse_mtime_site):
    # Arrange
    package = "foo"
    # Act
    duplicates = find_duplicate_dist_infos(site_packages=reverse_mtime_site)
    # Assert
    assert len(duplicates[package]) == 2


def test_report_returns_the_duplicated_package_names(reverse_mtime_site):
    # Arrange
    expected = ["foo"]
    # Act
    reported = report_duplicate_dist_infos(site_packages=reverse_mtime_site)
    # Assert
    assert reported == expected


def test_single_install_is_not_a_duplicate(tmp_path):
    # Arrange — one clean install.
    _make_dist_info(tmp_path, "foo", "1.0")
    # Act
    duplicates = find_duplicate_dist_infos(site_packages=tmp_path)
    # Assert
    assert duplicates == {}


def test_empty_residue_directory_is_not_a_duplicate(tmp_path):
    # Arrange — a real install plus an EMPTY same-package dist-info dir
    # (overlay residue: pip removed the files, the directory survived).
    _make_dist_info(tmp_path, "foo", "2.0")
    (tmp_path / "foo-1.0.dist-info").mkdir()
    # Act
    duplicates = find_duplicate_dist_infos(site_packages=tmp_path)
    # Assert
    assert duplicates == {}


# --- Non-directory entries never reach a removal path ------------------------


def test_whiteout_standin_file_is_not_counted(whiteout_standin_site):
    # Arrange
    site = whiteout_standin_site
    # Act
    duplicates = find_duplicate_dist_infos(site_packages=site)
    # Assert — the TYPE test, not the name, decides.
    assert duplicates == {}


def test_whiteout_standin_file_survives(whiteout_standin_site):
    # Arrange
    standin = whiteout_standin_site / "foo-1.0.dist-info"
    # Act
    report_duplicate_dist_infos(site_packages=whiteout_standin_site)
    # Assert — it was not passed to any removal path.
    assert standin.is_file()


def test_whiteout_standin_symlink_survives(whiteout_standin_site):
    # Arrange
    standin = whiteout_standin_site / "foo-0.9.dist-info"
    # Act
    report_duplicate_dist_infos(site_packages=whiteout_standin_site)
    # Assert
    assert standin.is_symlink()


# EOF
