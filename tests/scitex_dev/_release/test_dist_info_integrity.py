#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dist-info-count install-integrity check — REAL tmp-dir fixtures, NO mocks.

STX-NM002 forbids monkeypatch, so every case seeds a real temp directory with
real ``*.dist-info`` directories on disk and passes it through the
``site_packages`` seam. Three shapes, matching the three conditions the guard
must distinguish:

* DOUBLE  — two ``foo-*.dist-info`` in one dir → count == 2 → dirty-install
  ERROR carrying the non-obvious repair text.
* CLEAN   — exactly one → count == 1 → no finding.
* ZERO    — none → count == 0 → the "not installed" branch, distinct from the
  double error.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scitex_dev._release.dist_info_integrity import (
    DOUBLE_INSTALL_REMEDY,
    annotate_dist_info_integrity,
    count_dist_infos,
    dist_info_integrity,
    dist_info_status,
)


def _make_dist_info(site: Path, dist: str, version: str) -> Path:
    """Create a real ``<dist>-<version>.dist-info`` dir with a METADATA file."""
    stem = dist.replace("-", "_")
    info = site / f"{stem}-{version}.dist-info"
    info.mkdir(parents=True)
    (info / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {dist}\nVersion: {version}\n"
    )
    return info


@pytest.fixture
def double_site(tmp_path: Path) -> Path:
    """A site dir with TWO ``foo-*.dist-info`` — the incident shape."""
    _make_dist_info(tmp_path, "foo", "1.0")
    _make_dist_info(tmp_path, "foo", "2.0")
    return tmp_path


@pytest.fixture
def clean_site(tmp_path: Path) -> Path:
    """A site dir with exactly ONE ``foo-*.dist-info``."""
    _make_dist_info(tmp_path, "foo", "1.0")
    return tmp_path


@pytest.fixture
def dirty_result(double_site: Path) -> dict:
    """The classifier verdict for the double-install fixture."""
    return dist_info_integrity("foo", site_packages=double_site)


# --- count_dist_infos --------------------------------------------------------


def test_double_install_counts_two(double_site):
    # Arrange
    dist = "foo"
    # Act
    count = count_dist_infos(dist, site_packages=double_site)
    # Assert
    assert count == 2


def test_clean_install_counts_one(clean_site):
    # Arrange
    dist = "foo"
    # Act
    count = count_dist_infos(dist, site_packages=clean_site)
    # Assert
    assert count == 1


def test_absent_counts_zero(tmp_path):
    # Arrange
    empty_site = tmp_path
    # Act
    count = count_dist_infos("foo", site_packages=empty_site)
    # Assert
    assert count == 0


def test_hyphen_query_matches_underscore_dir(tmp_path):
    # Arrange — pip writes underscores; query with hyphens.
    _make_dist_info(tmp_path, "scitex-cards", "0.17.0")
    # Act
    count = count_dist_infos("scitex-cards", site_packages=tmp_path)
    # Assert
    assert count == 1


def test_underscore_query_matches_underscore_dir(tmp_path):
    # Arrange
    _make_dist_info(tmp_path, "scitex-cards", "0.17.0")
    # Act
    count = count_dist_infos("scitex_cards", site_packages=tmp_path)
    # Assert
    assert count == 1


def test_same_prefix_distribution_not_counted(tmp_path):
    # Arrange — a different distribution that shares a prefix.
    _make_dist_info(tmp_path, "foo", "1.0")
    _make_dist_info(tmp_path, "foobar", "9.9")
    # Act
    count = count_dist_infos("foo", site_packages=tmp_path)
    # Assert
    assert count == 1


# --- dist_info_integrity classifier -----------------------------------------


def test_dirty_result_count_is_two(dirty_result):
    # Arrange
    result = dirty_result
    # Act
    count = result["count"]
    # Assert
    assert count == 2


def test_dirty_result_status_is_dirty_install(dirty_result):
    # Arrange
    result = dirty_result
    # Act
    status = result["status"]
    # Assert
    assert status == "dirty_install"


def test_dirty_message_says_force_reinstall_does_not_fix(dirty_result):
    # Arrange
    result = dirty_result
    # Act
    message = result["message"]
    # Assert
    assert "pip install --force-reinstall` does NOT fix this" in message


def test_dirty_message_says_uninstall_repeatedly(dirty_result):
    # Arrange
    result = dirty_result
    # Act
    message = result["message"]
    # Assert
    assert "pip uninstall foo` REPEATEDLY" in message


def test_dirty_message_matches_repair_template(dirty_result):
    # Arrange
    result = dirty_result
    # Act
    message = result["message"]
    # Assert
    assert DOUBLE_INSTALL_REMEDY.format(dist="foo") in message


def test_clean_status_is_ok(clean_site):
    # Arrange
    result = dist_info_integrity("foo", site_packages=clean_site)
    # Act
    status = result["status"]
    # Assert
    assert status == "ok"


def test_clean_message_is_none(clean_site):
    # Arrange
    result = dist_info_integrity("foo", site_packages=clean_site)
    # Act
    message = result["message"]
    # Assert
    assert message is None


def test_zero_status_is_not_installed(tmp_path):
    # Arrange
    result = dist_info_integrity("foo", site_packages=tmp_path)
    # Act
    status = result["status"]
    # Assert — distinct from the double-install error, never conflated.
    assert status == "not_installed"


def test_zero_message_is_none(tmp_path):
    # Arrange
    result = dist_info_integrity("foo", site_packages=tmp_path)
    # Act
    message = result["message"]
    # Assert
    assert message is None


# --- report wiring (status verdict + annotate) ------------------------------


def _dirty_local(site: Path) -> dict:
    """The ``local`` sub-dict a report entry would carry for a dirty install."""
    return {
        "dist_info_count": count_dist_infos("foo", site_packages=site),
        "dist_info_integrity": dist_info_integrity("foo", site_packages=site)[
            "message"
        ],
    }


def test_verdict_status_is_dirty_install(double_site):
    # Arrange
    local = _dirty_local(double_site)
    # Act
    status, _issues = dist_info_status(local)
    # Assert
    assert status == "dirty_install"


def test_verdict_message_carries_repair(double_site):
    # Arrange
    local = _dirty_local(double_site)
    # Act
    _status, issues = dist_info_status(local)
    # Assert
    assert "REPEATEDLY" in issues[0]


def test_verdict_none_when_count_one():
    # Arrange
    local = {"dist_info_count": 1}
    # Act
    verdict = dist_info_status(local)
    # Assert
    assert verdict is None


def test_verdict_none_when_count_zero():
    # Arrange
    local = {"dist_info_count": 0}
    # Act
    verdict = dist_info_status(local)
    # Assert
    assert verdict is None


def test_verdict_none_when_count_missing():
    # Arrange
    local = {}
    # Act
    verdict = dist_info_status(local)
    # Assert
    assert verdict is None


def test_annotate_records_zero_count_for_absent_dist():
    # Arrange — exercises the interpreter-site-packages resolution path.
    local: dict = {}
    # Act
    annotate_dist_info_integrity(local, "definitely-not-a-real-dist-xyz")
    # Assert
    assert local["dist_info_count"] == 0


def test_annotate_no_dirty_message_for_absent_dist():
    # Arrange
    local: dict = {}
    # Act
    annotate_dist_info_integrity(local, "definitely-not-a-real-dist-xyz")
    # Assert
    assert "dist_info_integrity" not in local


# EOF
