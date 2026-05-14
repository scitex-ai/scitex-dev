"""Tests for `_check_license.py` (PS-138 / PS-138b).

PS-138  — file presence (existing rule).
PS-138b — file content matches SPDX declaration.

These tests cover the regression that motivated PS-138b: a 20-line
copyright stub passed PS-138 (file exists) but didn't actually contain
the AGPL terms. PS-138b checks for unmistakable signature lines
including Section 13 ("Remote Network Interaction") that distinguishes
AGPL from GPL.
"""

from __future__ import annotations

from pathlib import Path


from scitex_dev._cli.audit._project._check_license import (
    check_license_content,
    find_license,
)


# ===== fixtures =====

_AGPL_FULL_HEAD = """\
                    GNU AFFERO GENERAL PUBLIC LICENSE
                       Version 3, 19 November 2007

 Copyright (C) 2007 Free Software Foundation, Inc. <http://fsf.org/>
 Everyone is permitted to copy and distribute verbatim copies
 of this license document, but changing it is not allowed.

[... lots of text ...]

  13. Remote Network Interaction; Use with the GNU General Public License.

  Notwithstanding any other provision of this License, if you modify the
Program, your modification ...
"""

_STUB_LICENSE = """\
GNU AFFERO GENERAL PUBLIC LICENSE
Version 3, 19 November 2007

Copyright (c) 2024-2026 Yusuke Watanabe

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU AGPL.
"""


# ===== find_license =====


class TestFindLicense:
    def test_finds_plain_LICENSE_file(self, tmp_path: Path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "LICENSE").write_text("x")
        assert find_license(tmp_path).name == "LICENSE"

    def test_finds_LICENSE_md(self, tmp_path: Path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "LICENSE.md").write_text("x")
        assert find_license(tmp_path).name == "LICENSE.md"

    def test_finds_LICENSE_txt(self, tmp_path: Path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "LICENSE.txt").write_text("x")
        assert find_license(tmp_path).name == "LICENSE.txt"

    def test_returns_None_when_missing(self, tmp_path: Path):
        # Arrange
        # Act
        # Assert
        assert find_license(tmp_path) is None

    def test_LICENSE_wins_over_md(self, tmp_path: Path):
        # Order-of-preference test: LICENSE > LICENSE.md > LICENSE.txt
        # Arrange
        # Act
        # Assert
        (tmp_path / "LICENSE").write_text("a")
        (tmp_path / "LICENSE.md").write_text("b")
        assert find_license(tmp_path).name == "LICENSE"


# ===== check_license_content =====


class TestCheckLicenseContent:
    def test_full_AGPL_passes(self, tmp_path: Path):
        # Arrange
        # Act
        # Assert
        path = tmp_path / "LICENSE"
        path.write_text(_AGPL_FULL_HEAD)
        assert check_license_content(path, "AGPL-3.0-only") is None

    def test_stub_fails_AGPL_msg_is_not_none(self, tmp_path: Path):
        # Arrange
        # Act
        # Assert
        path = tmp_path / "LICENSE"
        path.write_text(_STUB_LICENSE)
        msg = check_license_content(path, "AGPL-3.0-only")
        assert msg is not None


    def test_stub_fails_AGPL_remote_network_interaction_in_msg(self, tmp_path: Path):
        # Arrange
        # Act
        # Assert
        path = tmp_path / "LICENSE"
        path.write_text(_STUB_LICENSE)
        msg = check_license_content(path, "AGPL-3.0-only")
        assert "Remote Network Interaction" in msg


    def test_stub_fails_AGPL_stub_in_msg_lower_or_does_not_match_in_m(self, tmp_path: Path):
        # Arrange
        # Act
        # Assert
        path = tmp_path / "LICENSE"
        path.write_text(_STUB_LICENSE)
        msg = check_license_content(path, "AGPL-3.0-only")
        assert "stub" in msg.lower() or "does not match" in msg

    def test_non_AGPL_skips_check_license_content_path_mit_is_none(self, tmp_path: Path):
        # PS-138b only enforces AGPL-3.0-only today. Other SPDX values
        # short-circuit (presence-only check via PS-138 still applies).
        # Arrange
        # Act
        # Assert
        path = tmp_path / "LICENSE"
        path.write_text(_STUB_LICENSE)
        assert check_license_content(path, "MIT") is None


    def test_non_AGPL_skips_check_license_content_path_apache_2_0_is(self, tmp_path: Path):
        # PS-138b only enforces AGPL-3.0-only today. Other SPDX values
        # short-circuit (presence-only check via PS-138 still applies).
        # Arrange
        # Act
        # Assert
        path = tmp_path / "LICENSE"
        path.write_text(_STUB_LICENSE)
        assert check_license_content(path, "Apache-2.0") is None

    def test_None_spdx_skips(self, tmp_path: Path):
        # Arrange
        # Act
        # Assert
        path = tmp_path / "LICENSE"
        path.write_text(_STUB_LICENSE)
        assert check_license_content(path, None) is None

    def test_empty_file_fails(self, tmp_path: Path):
        # Arrange
        # Act
        # Assert
        path = tmp_path / "LICENSE"
        path.write_text("")
        msg = check_license_content(path, "AGPL-3.0-only")
        assert msg is not None

    def test_unreadable_file_fails(self, tmp_path: Path):
        # Path that doesn't exist — read_text raises, helper treats as
        # empty content → all signatures missing → violation.
        # Arrange
        # Act
        # Assert
        path = tmp_path / "MISSING"
        msg = check_license_content(path, "AGPL-3.0-only")
        assert msg is not None

    def test_partial_match_still_fails_msg_is_not_none(self, tmp_path: Path):
        # Has the title but not Section 13 — common stub shape.
        # Arrange
        # Act
        # Assert
        partial = (
            "GNU AFFERO GENERAL PUBLIC LICENSE\n"
            "Version 3, 19 November 2007\n"
            "\nCopyright (c) ...\n"
        )
        path = tmp_path / "LICENSE"
        path.write_text(partial)
        msg = check_license_content(path, "AGPL-3.0-only")
        assert msg is not None


    def test_partial_match_still_fails_remote_network_interaction_in_msg(self, tmp_path: Path):
        # Has the title but not Section 13 — common stub shape.
        # Arrange
        # Act
        # Assert
        partial = (
            "GNU AFFERO GENERAL PUBLIC LICENSE\n"
            "Version 3, 19 November 2007\n"
            "\nCopyright (c) ...\n"
        )
        path = tmp_path / "LICENSE"
        path.write_text(partial)
        msg = check_license_content(path, "AGPL-3.0-only")
        assert "Remote Network Interaction" in msg


# ===== regression marker =====


def test_regression_PS138_alone_misses_stubs_find_license_tmp_path_is_not_none(tmp_path: Path):
    """PS-138 (presence-only) passes a stub; PS-138b catches it.

    This documents the gap that motivated adding PS-138b — written so a
    future regression that reverts to presence-only checking will fail
    here loudly.
    """
    # Arrange
    # Act
    # Assert
    path = tmp_path / "LICENSE"
    path.write_text(_STUB_LICENSE)

    # PS-138 (presence) — passes.
    assert find_license(tmp_path) is not None

    # PS-138b (content) — fails.


def test_regression_PS138_alone_misses_stubs_check_license_content_path_agpl_3_0_only(tmp_path: Path):
    """PS-138 (presence-only) passes a stub; PS-138b catches it.

    This documents the gap that motivated adding PS-138b — written so a
    future regression that reverts to presence-only checking will fail
    here loudly.
    """
    # Arrange
    # Act
    # Assert
    path = tmp_path / "LICENSE"
    path.write_text(_STUB_LICENSE)

    # PS-138 (presence) — passes.

    # PS-138b (content) — fails.
    assert check_license_content(path, "AGPL-3.0-only") is not None
