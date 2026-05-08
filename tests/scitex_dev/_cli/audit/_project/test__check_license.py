"""Tests for `_check_license.py` (PS138 / PS138b).

PS138  — file presence (existing rule).
PS138b — file content matches SPDX declaration.

These tests cover the regression that motivated PS138b: a 20-line
copyright stub passed PS138 (file exists) but didn't actually contain
the AGPL terms. PS138b checks for unmistakable signature lines
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
    def test_finds_LICENSE(self, tmp_path: Path):
        (tmp_path / "LICENSE").write_text("x")
        assert find_license(tmp_path).name == "LICENSE"

    def test_finds_LICENSE_md(self, tmp_path: Path):
        (tmp_path / "LICENSE.md").write_text("x")
        assert find_license(tmp_path).name == "LICENSE.md"

    def test_finds_LICENSE_txt(self, tmp_path: Path):
        (tmp_path / "LICENSE.txt").write_text("x")
        assert find_license(tmp_path).name == "LICENSE.txt"

    def test_returns_None_when_missing(self, tmp_path: Path):
        assert find_license(tmp_path) is None

    def test_LICENSE_wins_over_md(self, tmp_path: Path):
        # Order-of-preference test: LICENSE > LICENSE.md > LICENSE.txt
        (tmp_path / "LICENSE").write_text("a")
        (tmp_path / "LICENSE.md").write_text("b")
        assert find_license(tmp_path).name == "LICENSE"


# ===== check_license_content =====


class TestCheckLicenseContent:
    def test_full_AGPL_passes(self, tmp_path: Path):
        path = tmp_path / "LICENSE"
        path.write_text(_AGPL_FULL_HEAD)
        assert check_license_content(path, "AGPL-3.0-only") is None

    def test_stub_fails_AGPL(self, tmp_path: Path):
        path = tmp_path / "LICENSE"
        path.write_text(_STUB_LICENSE)
        msg = check_license_content(path, "AGPL-3.0-only")
        assert msg is not None
        assert "Remote Network Interaction" in msg
        assert "stub" in msg.lower() or "does not match" in msg

    def test_non_AGPL_skips(self, tmp_path: Path):
        # PS138b only enforces AGPL-3.0-only today. Other SPDX values
        # short-circuit (presence-only check via PS138 still applies).
        path = tmp_path / "LICENSE"
        path.write_text(_STUB_LICENSE)
        assert check_license_content(path, "MIT") is None
        assert check_license_content(path, "Apache-2.0") is None

    def test_None_spdx_skips(self, tmp_path: Path):
        path = tmp_path / "LICENSE"
        path.write_text(_STUB_LICENSE)
        assert check_license_content(path, None) is None

    def test_empty_file_fails(self, tmp_path: Path):
        path = tmp_path / "LICENSE"
        path.write_text("")
        msg = check_license_content(path, "AGPL-3.0-only")
        assert msg is not None

    def test_unreadable_file_fails(self, tmp_path: Path):
        # Path that doesn't exist — read_text raises, helper treats as
        # empty content → all signatures missing → violation.
        path = tmp_path / "MISSING"
        msg = check_license_content(path, "AGPL-3.0-only")
        assert msg is not None

    def test_partial_match_still_fails(self, tmp_path: Path):
        # Has the title but not Section 13 — common stub shape.
        partial = (
            "GNU AFFERO GENERAL PUBLIC LICENSE\n"
            "Version 3, 19 November 2007\n"
            "\nCopyright (c) ...\n"
        )
        path = tmp_path / "LICENSE"
        path.write_text(partial)
        msg = check_license_content(path, "AGPL-3.0-only")
        assert msg is not None
        assert "Remote Network Interaction" in msg


# ===== regression marker =====


def test_regression_PS138_alone_misses_stubs(tmp_path: Path):
    """PS138 (presence-only) passes a stub; PS138b catches it.

    This documents the gap that motivated adding PS138b — written so a
    future regression that reverts to presence-only checking will fail
    here loudly.
    """
    path = tmp_path / "LICENSE"
    path.write_text(_STUB_LICENSE)

    # PS138 (presence) — passes.
    assert find_license(tmp_path) is not None

    # PS138b (content) — fails.
    assert check_license_content(path, "AGPL-3.0-only") is not None
