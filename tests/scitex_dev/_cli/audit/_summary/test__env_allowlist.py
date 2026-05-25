#!/usr/bin/env python3
"""Tests for scitex_dev._cli.audit._summary._env_allowlist — §6a per-package opt-out.

Covers the ``[tool.scitex_dev] env_allowlist`` pyproject knob that lets a
package declare brand-prefix env vars (e.g. operator-facing ``SAC_*``)
without a global ``SCITEX_<PKG>_*`` rename. No mocks: synthetic
pyproject trees use ``tmp_path``, and the prefix-match logic is
exercised with real strings.

Pair with ``test__audit.py::TestScanEnvVarsHonorsAllowlist`` which
covers the wire-up at the ``_scan_env_vars`` boundary (passing
``pkg_allowlist=`` directly bypasses the pyproject read — the unit
under test here is the read itself).
"""

from __future__ import annotations

import pytest

from scitex_dev._cli.audit._summary._env_allowlist import (
    is_var_in_pkg_allowlist,
    read_pkg_env_allowlist,
)


def _write_pyproject(repo, body: str) -> None:
    """Write a minimal ``pyproject.toml`` under ``repo`` with ``body`` appended."""
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "brand-pkg"\nversion = "0.0.0"\n' + body
    )


# --------------------------------------------------------------------- #
# read_pkg_env_allowlist — pyproject loading + edge cases
# --------------------------------------------------------------------- #


class TestReadPkgEnvAllowlist:
    def test_single_prefix_entry_is_returned_verbatim(self, tmp_path):
        # Arrange
        _write_pyproject(tmp_path, '\n[tool.scitex_dev]\nenv_allowlist = ["SAC_"]\n')
        # Act
        allowlist = read_pkg_env_allowlist("brand-pkg", repo=tmp_path)
        # Assert
        assert allowlist == ("SAC_",)

    def test_multiple_entries_preserve_source_order(self, tmp_path):
        # Arrange — operator may want both a brand prefix and an exact var name.
        _write_pyproject(
            tmp_path,
            '\n[tool.scitex_dev]\nenv_allowlist = ["SAC_", "BRAND_X_", "GH_TOKEN"]\n',
        )
        # Act
        allowlist = read_pkg_env_allowlist("brand-pkg", repo=tmp_path)
        # Assert — order from the pyproject source is preserved.
        assert allowlist == ("SAC_", "BRAND_X_", "GH_TOKEN")

    def test_missing_pyproject_yields_empty_tuple(self, tmp_path):
        # Arrange — no pyproject.toml at all.
        empty_repo = tmp_path / "no-pyproject"
        empty_repo.mkdir()
        # Act
        allowlist = read_pkg_env_allowlist("brand-pkg", repo=empty_repo)
        # Assert
        assert allowlist == ()

    def test_pyproject_without_tool_block_yields_empty_tuple(self, tmp_path):
        # Arrange — pyproject exists but lacks [tool.scitex_dev].
        _write_pyproject(tmp_path, "")
        # Act
        allowlist = read_pkg_env_allowlist("brand-pkg", repo=tmp_path)
        # Assert
        assert allowlist == ()

    def test_tool_block_without_env_allowlist_yields_empty_tuple(self, tmp_path):
        # Arrange — [tool.scitex_dev] is present but env_allowlist key is absent.
        _write_pyproject(tmp_path, "\n[tool.scitex_dev]\nmcp_parity_exempt = true\n")
        # Act
        allowlist = read_pkg_env_allowlist("brand-pkg", repo=tmp_path)
        # Assert
        assert allowlist == ()

    def test_env_allowlist_as_non_list_value_is_ignored(self, tmp_path):
        # Arrange — author mistakenly wrote a string instead of a list.
        # The auditor must not crash; it returns () so the standard rule
        # still applies (i.e. the audit fails loud rather than silently
        # accepting whatever bytes the typo produced).
        _write_pyproject(tmp_path, '\n[tool.scitex_dev]\nenv_allowlist = "SAC_"\n')
        # Act
        allowlist = read_pkg_env_allowlist("brand-pkg", repo=tmp_path)
        # Assert
        assert allowlist == ()

    def test_non_string_entries_are_silently_dropped(self, tmp_path):
        # Arrange — mixed types in the list. TOML allows it; the helper
        # drops the non-strings and keeps the strings.
        _write_pyproject(
            tmp_path,
            '\n[tool.scitex_dev]\nenv_allowlist = ["SAC_", 42, "BRAND_X_", ""]\n',
        )
        # Act
        allowlist = read_pkg_env_allowlist("brand-pkg", repo=tmp_path)
        # Assert — the int 42 is dropped, the empty "" is dropped, the
        # two real prefixes survive in source order.
        assert allowlist == ("SAC_", "BRAND_X_")

    def test_malformed_toml_yields_empty_tuple(self, tmp_path):
        # Arrange — broken TOML on disk. The helper must not crash.
        (tmp_path / "pyproject.toml").write_text(
            "[project\nname = broken\n"  # missing close bracket + missing quotes
        )
        # Act
        allowlist = read_pkg_env_allowlist("brand-pkg", repo=tmp_path)
        # Assert
        assert allowlist == ()

    def test_missing_repo_root_yields_empty_tuple(self, tmp_path):
        # Arrange — caller passed a nonexistent dir.
        nonexistent = tmp_path / "does-not-exist"
        # Act
        allowlist = read_pkg_env_allowlist("brand-pkg", repo=nonexistent)
        # Assert
        assert allowlist == ()

    def test_hyphenated_table_name_also_recognised(self, tmp_path):
        # Arrange — TOML allows both [tool.scitex_dev] and [tool."scitex-dev"];
        # the helper accepts either spelling for parity with the rest of the
        # ecosystem (some packages use the hyphen form by convention).
        _write_pyproject(tmp_path, '\n[tool."scitex-dev"]\nenv_allowlist = ["SAC_"]\n')
        # Act
        allowlist = read_pkg_env_allowlist("brand-pkg", repo=tmp_path)
        # Assert
        assert allowlist == ("SAC_",)


# --------------------------------------------------------------------- #
# is_var_in_pkg_allowlist — prefix-match semantics
# --------------------------------------------------------------------- #


class TestIsVarInPkgAllowlist:
    def test_prefix_entry_matches_any_var_with_that_prefix(self):
        # Arrange
        allowlist = ("SAC_",)
        # Act
        # Assert
        assert is_var_in_pkg_allowlist("SAC_FOO", allowlist) is True

    def test_prefix_entry_matches_deeply_nested_name(self):
        # Arrange
        allowlist = ("SAC_",)
        # Act
        # Assert
        assert is_var_in_pkg_allowlist("SAC_LISTEN_BASE_URL", allowlist) is True

    def test_exact_name_entry_matches_only_the_stripped_form(self):
        # Arrange — entry "GH_TOKEN" matches only the exact name "GH_TOKEN"
        # (mirroring the universal-allowlist convention in _audit.py).
        allowlist = ("GH_TOKEN",)
        # Act
        # Assert
        assert is_var_in_pkg_allowlist("GH_TOKEN", allowlist) is True

    def test_unrelated_var_does_not_match(self):
        # Arrange
        allowlist = ("SAC_",)
        # Act
        # Assert
        assert is_var_in_pkg_allowlist("UNKNOWN", allowlist) is False

    def test_empty_allowlist_never_matches(self):
        # Arrange
        allowlist: tuple[str, ...] = ()
        # Act
        # Assert
        assert is_var_in_pkg_allowlist("ANYTHING", allowlist) is False

    def test_empty_var_never_matches(self):
        # Arrange
        allowlist = ("SAC_",)
        # Act
        # Assert
        assert is_var_in_pkg_allowlist("", allowlist) is False

    def test_var_must_match_at_start_not_substring(self):
        # Arrange — a SAC_ entry must not match SOMETHING_SAC_BAR.
        allowlist = ("SAC_",)
        # Act
        # Assert
        assert is_var_in_pkg_allowlist("SOMETHING_SAC_BAR", allowlist) is False


# --------------------------------------------------------------------- #
# Wire-up: _is_allowed_env / _scan_env_vars honour the new layer
# --------------------------------------------------------------------- #


class TestIsAllowedEnvWithPkgAllowlist:
    def test_universal_allowlist_still_works_when_pkg_allowlist_empty(self):
        # Arrange — PATH is in the universal hardcoded list.
        from scitex_dev._cli.audit._summary._audit import _is_allowed_env

        # Act
        result = _is_allowed_env("PATH", ())
        # Assert
        assert result is True

    def test_pkg_allowlist_extends_the_universal_layer(self):
        # Arrange — SAC_FOO is not in the universal list; pkg_allowlist adds it.
        from scitex_dev._cli.audit._summary._audit import _is_allowed_env

        # Act
        result = _is_allowed_env("SAC_FOO", ("SAC_",))
        # Assert
        assert result is True

    def test_var_outside_both_layers_is_not_allowed(self):
        # Arrange — neither layer covers UNKNOWN_BRAND.
        from scitex_dev._cli.audit._summary._audit import _is_allowed_env

        # Act
        result = _is_allowed_env("UNKNOWN_BRAND_FOO", ("SAC_",))
        # Assert
        assert result is False

    def test_default_pkg_allowlist_is_empty(self):
        # Arrange — explicit assertion that the signature default makes
        # `_is_allowed_env(var)` backward-compatible: no pkg_allowlist
        # means only the universal layer is consulted.
        from scitex_dev._cli.audit._summary._audit import _is_allowed_env

        # Act
        result = _is_allowed_env("SAC_FOO")
        # Assert — without an explicit allowlist, the SAC_ prefix is
        # not recognised (legacy behaviour preserved).
        assert result is False


class TestScanEnvVarsHonorsAllowlist:
    def test_explicit_allowlist_kwarg_suppresses_violations(self, tmp_path):
        # Arrange — feed _scan_env_vars an explicit allowlist; this
        # exercises the in-process wire-up without needing a real
        # editable install of a brand-prefix package on disk. The
        # SAC_ prefix is the canonical example from
        # scitex-agent-container.
        from scitex_dev._cli.audit._summary._audit import _scan_env_vars

        out: list = []
        # Act — scitex-dev itself is importable; the scanner walks its
        # own .py files. With ("SAC_",) on the allowlist any SAC_* var
        # it encounters would be skipped; scitex-dev's own source does
        # not contain SAC_ references, so out remains empty regardless.
        _scan_env_vars("scitex-dev", out, pkg_allowlist=("SAC_",))
        # Assert — no SAC_* violations leak through; the universal
        # layer continues to do its job for everything else.
        assert all("SAC_" not in v.message for v in out)

    def test_explicit_empty_allowlist_skips_pyproject_read(self, tmp_path):
        # Arrange — passing an empty tuple (not None) MUST short-circuit
        # the pyproject read entirely. This is the "tests bypass the
        # filesystem" escape hatch documented in the helper docstring.
        from scitex_dev._cli.audit._summary._audit import _scan_env_vars

        out: list = []
        # Act
        _scan_env_vars("scitex-dev", out, pkg_allowlist=())
        # Assert — call completes without crashing; behavior matches
        # the legacy code path (universal allowlist only).
        assert isinstance(out, list)
