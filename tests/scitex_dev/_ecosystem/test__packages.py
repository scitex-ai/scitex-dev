#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the unified `ecosystem packages` audit command.

Synthetic fixtures: SHA readers injected via the public sha-fn parameters
on ``packages_audit`` / ``collect_state`` — no real SSH calls, no mocks.
"""

from __future__ import annotations

import pytest

pytest.importorskip("click")

from scitex_dev._core.config import DevConfig, HostConfig, PackageConfig
from scitex_dev._ecosystem._packages import (
    collect_state,
    out_of_sync_pairs,
    packages_audit,
    render_table,
    summarize,
)


@pytest.fixture
def fake_config(tmp_path) -> DevConfig:
    """Two pkgs, two hosts."""
    p1_path = tmp_path / "scitex-io"
    p2_path = tmp_path / "figrecipe"
    for p in (p1_path, p2_path):
        p.mkdir()

    return DevConfig(
        packages=[
            PackageConfig(
                name="scitex-io",
                local_path=str(p1_path),
                pypi_name="scitex-io",
                github_repo="ywatanabe1989/scitex-io",
            ),
            PackageConfig(
                name="figrecipe",
                local_path=str(p2_path),
                pypi_name="figrecipe",
                github_repo="ywatanabe1989/figrecipe",
            ),
        ],
        hosts=[
            HostConfig(name="nas", hostname="nas", user="x", enabled=True),
            HostConfig(name="mba", hostname="mba", user="x", enabled=True),
        ],
    )


def _sha_kwargs(origin, local, remote_map):
    """Build sha-fn kwargs for packages_audit / collect_state."""
    return dict(
        origin_sha_fn=lambda _path, branch="develop": origin,
        local_sha_fn=lambda _path: local,
        remote_sha_fn=lambda host, dir_name: remote_map.get((host.name, dir_name)),
    )


# ── observation ─────────────────────────────────────────────────────────────


def test_observation_renders_nonempty_table_result_mode_observe(fake_config):
    # Arrange
    # Act
    # Assert
    remote = {
        ("nas", "scitex-io"): "abc1234aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        ("nas", "figrecipe"): None,
        ("mba", "scitex-io"): "abc1234aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        ("mba", "figrecipe"): "deadbeef" + "f" * 32,
    }
    result = packages_audit(
        mode="observe",
        config=fake_config,
        **_sha_kwargs(
            "abc1234aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "abc1234aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            remote,
        ),
    )

    assert result["mode"] == "observe"
    # MISSING for nas/figrecipe (no remote sha)
    # mismatched cell suffixed with *


def test_observation_renders_nonempty_table_scitex_io_in_result_table(fake_config):
    # Arrange
    # Act
    # Assert
    remote = {
        ("nas", "scitex-io"): "abc1234aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        ("nas", "figrecipe"): None,
        ("mba", "scitex-io"): "abc1234aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        ("mba", "figrecipe"): "deadbeef" + "f" * 32,
    }
    result = packages_audit(
        mode="observe",
        config=fake_config,
        **_sha_kwargs(
            "abc1234aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "abc1234aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            remote,
        ),
    )

    assert "scitex-io" in result["table"]
    # MISSING for nas/figrecipe (no remote sha)
    # mismatched cell suffixed with *


def test_observation_renders_nonempty_table_figrecipe_in_result_table(fake_config):
    # Arrange
    # Act
    # Assert
    remote = {
        ("nas", "scitex-io"): "abc1234aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        ("nas", "figrecipe"): None,
        ("mba", "scitex-io"): "abc1234aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        ("mba", "figrecipe"): "deadbeef" + "f" * 32,
    }
    result = packages_audit(
        mode="observe",
        config=fake_config,
        **_sha_kwargs(
            "abc1234aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "abc1234aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            remote,
        ),
    )

    assert "figrecipe" in result["table"]
    # MISSING for nas/figrecipe (no remote sha)
    # mismatched cell suffixed with *


def test_observation_renders_nonempty_table_nas_in_result_table(fake_config):
    # Arrange
    # Act
    # Assert
    remote = {
        ("nas", "scitex-io"): "abc1234aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        ("nas", "figrecipe"): None,
        ("mba", "scitex-io"): "abc1234aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        ("mba", "figrecipe"): "deadbeef" + "f" * 32,
    }
    result = packages_audit(
        mode="observe",
        config=fake_config,
        **_sha_kwargs(
            "abc1234aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "abc1234aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            remote,
        ),
    )

    assert "nas" in result["table"]
    # MISSING for nas/figrecipe (no remote sha)
    # mismatched cell suffixed with *


def test_observation_renders_nonempty_table_mba_in_result_table(fake_config):
    # Arrange
    # Act
    # Assert
    remote = {
        ("nas", "scitex-io"): "abc1234aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        ("nas", "figrecipe"): None,
        ("mba", "scitex-io"): "abc1234aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        ("mba", "figrecipe"): "deadbeef" + "f" * 32,
    }
    result = packages_audit(
        mode="observe",
        config=fake_config,
        **_sha_kwargs(
            "abc1234aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "abc1234aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            remote,
        ),
    )

    assert "mba" in result["table"]
    # MISSING for nas/figrecipe (no remote sha)
    # mismatched cell suffixed with *


def test_observation_renders_nonempty_table_missing_in_result_table(fake_config):
    # Arrange
    # Act
    # Assert
    remote = {
        ("nas", "scitex-io"): "abc1234aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        ("nas", "figrecipe"): None,
        ("mba", "scitex-io"): "abc1234aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        ("mba", "figrecipe"): "deadbeef" + "f" * 32,
    }
    result = packages_audit(
        mode="observe",
        config=fake_config,
        **_sha_kwargs(
            "abc1234aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "abc1234aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            remote,
        ),
    )

    # MISSING for nas/figrecipe (no remote sha)
    assert "MISSING" in result["table"]
    # mismatched cell suffixed with *


def test_observation_renders_nonempty_table_in_result_table(fake_config):
    # Arrange
    # Act
    # Assert
    remote = {
        ("nas", "scitex-io"): "abc1234aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        ("nas", "figrecipe"): None,
        ("mba", "scitex-io"): "abc1234aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        ("mba", "figrecipe"): "deadbeef" + "f" * 32,
    }
    result = packages_audit(
        mode="observe",
        config=fake_config,
        **_sha_kwargs(
            "abc1234aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "abc1234aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            remote,
        ),
    )

    # MISSING for nas/figrecipe (no remote sha)
    # mismatched cell suffixed with *
    assert "*" in result["table"]


def test_summary_counts_match_origin_correctly_s_total_4(fake_config):
    # Arrange
    # Act
    # Assert
    o = "a" * 40
    other = "b" * 40
    remote = {
        ("nas", "scitex-io"): o,  # match
        ("nas", "figrecipe"): other,  # mismatch
        ("mba", "scitex-io"): o,
        ("mba", "figrecipe"): o,
    }
    result = packages_audit(
        mode="observe",
        config=fake_config,
        **_sha_kwargs(o, o, remote),
    )
    s = result["summary"]
    assert s["total"] == 4


def test_summary_counts_match_origin_correctly_s_matching_3(fake_config):
    # Arrange
    # Act
    # Assert
    o = "a" * 40
    other = "b" * 40
    remote = {
        ("nas", "scitex-io"): o,  # match
        ("nas", "figrecipe"): other,  # mismatch
        ("mba", "scitex-io"): o,
        ("mba", "figrecipe"): o,
    }
    result = packages_audit(
        mode="observe",
        config=fake_config,
        **_sha_kwargs(o, o, remote),
    )
    s = result["summary"]
    assert s["matching"] == 3


def test_summary_counts_match_origin_correctly_len_s_needing_sync_1(fake_config):
    # Arrange
    # Act
    # Assert
    o = "a" * 40
    other = "b" * 40
    remote = {
        ("nas", "scitex-io"): o,  # match
        ("nas", "figrecipe"): other,  # mismatch
        ("mba", "scitex-io"): o,
        ("mba", "figrecipe"): o,
    }
    result = packages_audit(
        mode="observe",
        config=fake_config,
        **_sha_kwargs(o, o, remote),
    )
    s = result["summary"]
    assert len(s["needing_sync"]) == 1


def test_summary_counts_match_origin_correctly_s_needing_sync_0_host_nas_pkg_figrecipe(fake_config):
    # Arrange
    # Act
    # Assert
    o = "a" * 40
    other = "b" * 40
    remote = {
        ("nas", "scitex-io"): o,  # match
        ("nas", "figrecipe"): other,  # mismatch
        ("mba", "scitex-io"): o,
        ("mba", "figrecipe"): o,
    }
    result = packages_audit(
        mode="observe",
        config=fake_config,
        **_sha_kwargs(o, o, remote),
    )
    s = result["summary"]
    assert s["needing_sync"][0] == {"host": "nas", "pkg": "figrecipe"}


def test_packages_audit_returns_nonzero_summary_on_mismatch(fake_config):
    """Exit-code semantics ride on the summary; verify directly to skip CLI."""
    # Arrange
    # Act
    # Assert
    o = "c" * 40
    remote_bad = {
        ("nas", "scitex-io"): "f" * 40,
        ("nas", "figrecipe"): o,
        ("mba", "scitex-io"): o,
        ("mba", "figrecipe"): o,
    }
    result = packages_audit(
        mode="observe",
        config=fake_config,
        **_sha_kwargs(o, o, remote_bad),
    )
    assert len(result["summary"]["needing_sync"]) == 1


def test_packages_audit_summary_zero_when_all_match(fake_config):
    # Arrange
    # Act
    # Assert
    o = "c" * 40
    remote_ok = {
        ("nas", "scitex-io"): o,
        ("nas", "figrecipe"): o,
        ("mba", "scitex-io"): o,
        ("mba", "figrecipe"): o,
    }
    result = packages_audit(
        mode="observe",
        config=fake_config,
        **_sha_kwargs(o, o, remote_ok),
    )
    assert result["summary"]["needing_sync"] == []


# ── dry-run ─────────────────────────────────────────────────────────────────


def test_dry_run_lists_commands_for_mismatches_nas_in_cmds_and_scitex_io_in_cmds_nas(fake_config):
    # Arrange
    # Act
    # Assert
    o = "d" * 40
    remote = {
        ("nas", "scitex-io"): "x" * 40,  # mismatch
        ("nas", "figrecipe"): o,
        ("mba", "scitex-io"): o,
        ("mba", "figrecipe"): o,
    }
    result = packages_audit(
        mode="dry-run",
        config=fake_config,
        **_sha_kwargs(o, o, remote),
    )
    cmds = result["commands"]
    assert "nas" in cmds and "scitex-io" in cmds["nas"]
    # mba pkgs all in sync — nothing for mba


def test_dry_run_lists_commands_for_mismatches_any_git_pull_in_c_for_c_in_cmds_nas_scit(fake_config):
    # Arrange
    # Act
    # Assert
    o = "d" * 40
    remote = {
        ("nas", "scitex-io"): "x" * 40,  # mismatch
        ("nas", "figrecipe"): o,
        ("mba", "scitex-io"): o,
        ("mba", "figrecipe"): o,
    }
    result = packages_audit(
        mode="dry-run",
        config=fake_config,
        **_sha_kwargs(o, o, remote),
    )
    cmds = result["commands"]
    assert any("git pull" in c for c in cmds["nas"]["scitex-io"])
    # mba pkgs all in sync — nothing for mba


def test_dry_run_lists_commands_for_mismatches_any_pip_install_in_c_for_c_in_cmds_nas_s(fake_config):
    # Arrange
    # Act
    # Assert
    o = "d" * 40
    remote = {
        ("nas", "scitex-io"): "x" * 40,  # mismatch
        ("nas", "figrecipe"): o,
        ("mba", "scitex-io"): o,
        ("mba", "figrecipe"): o,
    }
    result = packages_audit(
        mode="dry-run",
        config=fake_config,
        **_sha_kwargs(o, o, remote),
    )
    cmds = result["commands"]
    assert any("pip install" in c for c in cmds["nas"]["scitex-io"])
    # mba pkgs all in sync — nothing for mba


def test_dry_run_lists_commands_for_mismatches_mba_not_in_cmds(fake_config):
    # Arrange
    # Act
    # Assert
    o = "d" * 40
    remote = {
        ("nas", "scitex-io"): "x" * 40,  # mismatch
        ("nas", "figrecipe"): o,
        ("mba", "scitex-io"): o,
        ("mba", "figrecipe"): o,
    }
    result = packages_audit(
        mode="dry-run",
        config=fake_config,
        **_sha_kwargs(o, o, remote),
    )
    cmds = result["commands"]
    # mba pkgs all in sync — nothing for mba
    assert "mba" not in cmds


# ── exclude: list ────────────────────────────────────────────────────────────


def test_exclude_filters_packages_figrecipe_row_cells_nas_excluded(fake_config):
    """exclude: ['figrecipe'] should drop figrecipe from that host's table."""
    # Arrange
    # Act
    # Assert
    fake_config.hosts[0].exclude = ["figrecipe"]  # nas excludes figrecipe
    o = "e" * 40
    remote = {
        ("nas", "scitex-io"): o,
        ("mba", "scitex-io"): o,
        ("mba", "figrecipe"): o,
    }
    result = packages_audit(
        mode="observe",
        config=fake_config,
        **_sha_kwargs(o, o, remote),
    )
    # nas/figrecipe cell should be EXCLUDED -> rendered as "-"
    figrecipe_row = next(r for r in result["state"]["rows"] if r["pkg"] == "figrecipe")
    assert figrecipe_row["cells"]["nas"] == "EXCLUDED"
    # And it should not contribute to summary totals
    s = result["summary"]
    # 3 contributing cells: nas/scitex-io, mba/scitex-io, mba/figrecipe


def test_exclude_filters_packages_s_total_3(fake_config):
    """exclude: ['figrecipe'] should drop figrecipe from that host's table."""
    # Arrange
    # Act
    # Assert
    fake_config.hosts[0].exclude = ["figrecipe"]  # nas excludes figrecipe
    o = "e" * 40
    remote = {
        ("nas", "scitex-io"): o,
        ("mba", "scitex-io"): o,
        ("mba", "figrecipe"): o,
    }
    result = packages_audit(
        mode="observe",
        config=fake_config,
        **_sha_kwargs(o, o, remote),
    )
    # nas/figrecipe cell should be EXCLUDED -> rendered as "-"
    figrecipe_row = next(r for r in result["state"]["rows"] if r["pkg"] == "figrecipe")
    # And it should not contribute to summary totals
    s = result["summary"]
    # 3 contributing cells: nas/scitex-io, mba/scitex-io, mba/figrecipe
    assert s["total"] == 3


def test_exclude_filters_packages_s_matching_3(fake_config):
    """exclude: ['figrecipe'] should drop figrecipe from that host's table."""
    # Arrange
    # Act
    # Assert
    fake_config.hosts[0].exclude = ["figrecipe"]  # nas excludes figrecipe
    o = "e" * 40
    remote = {
        ("nas", "scitex-io"): o,
        ("mba", "scitex-io"): o,
        ("mba", "figrecipe"): o,
    }
    result = packages_audit(
        mode="observe",
        config=fake_config,
        **_sha_kwargs(o, o, remote),
    )
    # nas/figrecipe cell should be EXCLUDED -> rendered as "-"
    figrecipe_row = next(r for r in result["state"]["rows"] if r["pkg"] == "figrecipe")
    # And it should not contribute to summary totals
    s = result["summary"]
    # 3 contributing cells: nas/scitex-io, mba/scitex-io, mba/figrecipe
    assert s["matching"] == 3


# ── helper sanity ───────────────────────────────────────────────────────────


def test_render_table_has_expected_columns_origin_develop_in_first_line(fake_config):
    # Arrange
    # Act
    # Assert
    o = "1" * 40
    state = collect_state(config=fake_config, **_sha_kwargs(o, o, {}))
    table = render_table(state)
    # Header row must contain origin/develop, localhost, plus host names
    first_line = table.splitlines()[0]
    assert "origin/develop" in first_line


def test_render_table_has_expected_columns_localhost_in_first_line(fake_config):
    # Arrange
    # Act
    # Assert
    o = "1" * 40
    state = collect_state(config=fake_config, **_sha_kwargs(o, o, {}))
    table = render_table(state)
    # Header row must contain origin/develop, localhost, plus host names
    first_line = table.splitlines()[0]
    assert "localhost" in first_line


def test_render_table_has_expected_columns_nas_in_first_line(fake_config):
    # Arrange
    # Act
    # Assert
    o = "1" * 40
    state = collect_state(config=fake_config, **_sha_kwargs(o, o, {}))
    table = render_table(state)
    # Header row must contain origin/develop, localhost, plus host names
    first_line = table.splitlines()[0]
    assert "nas" in first_line


def test_render_table_has_expected_columns_mba_in_first_line(fake_config):
    # Arrange
    # Act
    # Assert
    o = "1" * 40
    state = collect_state(config=fake_config, **_sha_kwargs(o, o, {}))
    table = render_table(state)
    # Header row must contain origin/develop, localhost, plus host names
    first_line = table.splitlines()[0]
    assert "mba" in first_line


def test_out_of_sync_pairs_skips_unknown_origin_out_of_sync_pairs_state(fake_config):
    # origin=None means we can't tell; should not list as mismatch
    # Arrange
    # Act
    # Assert
    state = collect_state(config=fake_config, **_sha_kwargs(None, None, {}))
    # all rows have origin=None -> empty
    assert out_of_sync_pairs(state) == []
    s = summarize(state)


def test_out_of_sync_pairs_skips_unknown_origin_s_total_0(fake_config):
    # origin=None means we can't tell; should not list as mismatch
    # Arrange
    # Act
    # Assert
    state = collect_state(config=fake_config, **_sha_kwargs(None, None, {}))
    # all rows have origin=None -> empty
    s = summarize(state)
    assert s["total"] == 0


# EOF
