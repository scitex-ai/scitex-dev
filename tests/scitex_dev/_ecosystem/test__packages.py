#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the unified `ecosystem packages` audit command.

Synthetic fixtures: monkeypatched SHA readers, no real SSH calls.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from click.testing import CliRunner

from scitex_dev.config import DevConfig, HostConfig, PackageConfig
from scitex_dev._ecosystem._packages import (
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


def _patch_shas(origin, local, remote_map):
    """Stack mock patches for SHA readers."""
    return [
        patch(
            "scitex_dev._ecosystem._packages._origin_sha",
            side_effect=lambda path, branch="develop": origin,
        ),
        patch(
            "scitex_dev._ecosystem._packages._local_sha",
            side_effect=lambda path: local,
        ),
        patch(
            "scitex_dev._ecosystem._packages._remote_sha",
            side_effect=lambda host, dir_name: remote_map.get((host.name, dir_name)),
        ),
    ]


def _stack(patches):
    """Enter a list of patch context managers; return a closer."""
    objs = [p.__enter__() for p in patches]

    def close():
        for p in reversed(patches):
            p.__exit__(None, None, None)

    return objs, close


# ── observation ─────────────────────────────────────────────────────────────


def test_observation_renders_nonempty_table(fake_config):
    remote = {
        ("nas", "scitex-io"): "abc1234aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        ("nas", "figrecipe"): None,
        ("mba", "scitex-io"): "abc1234aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        ("mba", "figrecipe"): "deadbeef" + "f" * 32,
    }
    patches = _patch_shas(
        "abc1234aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "abc1234aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        remote,
    )
    _, close = _stack(patches)
    try:
        result = packages_audit(mode="observe", config=fake_config)
    finally:
        close()

    assert result["mode"] == "observe"
    assert "scitex-io" in result["table"]
    assert "figrecipe" in result["table"]
    assert "nas" in result["table"]
    assert "mba" in result["table"]
    # MISSING for nas/figrecipe (no remote sha)
    assert "MISSING" in result["table"]
    # mismatched cell suffixed with *
    assert "*" in result["table"]


def test_summary_counts_match_origin_correctly(fake_config):
    o = "a" * 40
    other = "b" * 40
    remote = {
        ("nas", "scitex-io"): o,  # match
        ("nas", "figrecipe"): other,  # mismatch
        ("mba", "scitex-io"): o,
        ("mba", "figrecipe"): o,
    }
    patches = _patch_shas(o, o, remote)
    _, close = _stack(patches)
    try:
        result = packages_audit(mode="observe", config=fake_config)
    finally:
        close()
    s = result["summary"]
    assert s["total"] == 4
    assert s["matching"] == 3
    assert len(s["needing_sync"]) == 1
    assert s["needing_sync"][0] == {"host": "nas", "pkg": "figrecipe"}


def test_observation_exit_codes_via_cli(fake_config):
    """Mode 1: exit 0 when all match, 1 when mismatched."""
    from scitex_dev._cli import main as root_cli

    o = "c" * 40
    runner = CliRunner()

    # All match -> exit 0
    remote_ok = {
        ("nas", "scitex-io"): o,
        ("nas", "figrecipe"): o,
        ("mba", "scitex-io"): o,
        ("mba", "figrecipe"): o,
    }
    with patch("scitex_dev._ecosystem._packages.load_config", return_value=fake_config):
        with (
            patch("scitex_dev._ecosystem._packages._origin_sha", return_value=o),
            patch("scitex_dev._ecosystem._packages._local_sha", return_value=o),
            patch(
                "scitex_dev._ecosystem._packages._remote_sha",
                side_effect=lambda h, d: remote_ok.get((h.name, d)),
            ),
        ):
            r = runner.invoke(root_cli, ["ecosystem", "packages"])
    assert r.exit_code == 0, r.output

    # One mismatch -> exit 1
    remote_bad = dict(remote_ok)
    remote_bad[("nas", "scitex-io")] = "f" * 40
    with patch("scitex_dev._ecosystem._packages.load_config", return_value=fake_config):
        with (
            patch("scitex_dev._ecosystem._packages._origin_sha", return_value=o),
            patch("scitex_dev._ecosystem._packages._local_sha", return_value=o),
            patch(
                "scitex_dev._ecosystem._packages._remote_sha",
                side_effect=lambda h, d: remote_bad.get((h.name, d)),
            ),
        ):
            r = runner.invoke(root_cli, ["ecosystem", "packages"])
    assert r.exit_code == 1, r.output


# ── dry-run ─────────────────────────────────────────────────────────────────


def test_dry_run_lists_commands_for_mismatches(fake_config):
    o = "d" * 40
    remote = {
        ("nas", "scitex-io"): "x" * 40,  # mismatch
        ("nas", "figrecipe"): o,
        ("mba", "scitex-io"): o,
        ("mba", "figrecipe"): o,
    }
    patches = _patch_shas(o, o, remote)
    _, close = _stack(patches)
    try:
        result = packages_audit(mode="dry-run", config=fake_config)
    finally:
        close()
    cmds = result["commands"]
    assert "nas" in cmds and "scitex-io" in cmds["nas"]
    assert any("git pull" in c for c in cmds["nas"]["scitex-io"])
    assert any("pip install" in c for c in cmds["nas"]["scitex-io"])
    # mba pkgs all in sync — nothing for mba
    assert "mba" not in cmds


# ── exclude: list ────────────────────────────────────────────────────────────


def test_exclude_filters_packages(fake_config):
    """exclude: ['figrecipe'] should drop figrecipe from that host's table."""
    fake_config.hosts[0].exclude = ["figrecipe"]  # nas excludes figrecipe
    o = "e" * 40
    remote = {
        ("nas", "scitex-io"): o,
        ("mba", "scitex-io"): o,
        ("mba", "figrecipe"): o,
    }
    patches = _patch_shas(o, o, remote)
    _, close = _stack(patches)
    try:
        result = packages_audit(mode="observe", config=fake_config)
    finally:
        close()
    # nas/figrecipe cell should be EXCLUDED -> rendered as "-"
    figrecipe_row = next(r for r in result["state"]["rows"] if r["pkg"] == "figrecipe")
    assert figrecipe_row["cells"]["nas"] == "EXCLUDED"
    # And it should not contribute to summary totals
    s = result["summary"]
    # 3 contributing cells: nas/scitex-io, mba/scitex-io, mba/figrecipe
    assert s["total"] == 3
    assert s["matching"] == 3


# ── deprecated aliases ──────────────────────────────────────────────────────


def test_sync_remote_alias_warns(fake_config):
    from scitex_dev._cli import main as root_cli

    runner = CliRunner()
    with patch("scitex_dev.config.load_config", return_value=fake_config):
        r = runner.invoke(
            root_cli,
            ["ecosystem", "sync-remote", "-h", "nas", "-p", "scitex-io", "--dry-run"],
        )
    assert (
        "deprecated" in r.output.lower()
        or "deprecated" in (r.stderr_bytes or b"").decode().lower()
    )


def test_fix_mismatches_alias_warns():
    """`fix-mismatches` keeps working but prints deprecation warning."""
    from scitex_dev._cli import main as root_cli

    runner = CliRunner()
    # We don't care about the underlying action — just the warning surface.
    with patch(
        "scitex_dev._release.fix.fix_mismatches", return_value={"detected": {}, "summary": {}}
    ):
        r = runner.invoke(root_cli, ["ecosystem", "fix-mismatches"])
    combined = r.output + (r.stderr_bytes or b"").decode()
    assert "deprecated" in combined.lower()


# ── helper sanity ───────────────────────────────────────────────────────────


def test_render_table_has_expected_columns(fake_config):
    o = "1" * 40
    patches = _patch_shas(o, o, {})
    _, close = _stack(patches)
    try:
        from scitex_dev._ecosystem._packages import collect_state

        state = collect_state(config=fake_config)
    finally:
        close()
    table = render_table(state)
    # Header row must contain origin/develop, localhost, plus host names
    first_line = table.splitlines()[0]
    assert "origin/develop" in first_line
    assert "localhost" in first_line
    assert "nas" in first_line
    assert "mba" in first_line


def test_out_of_sync_pairs_skips_unknown_origin(fake_config):
    # origin=None means we can't tell; should not list as mismatch
    patches = _patch_shas(None, None, {})
    _, close = _stack(patches)
    try:
        from scitex_dev._ecosystem._packages import collect_state

        state = collect_state(config=fake_config)
    finally:
        close()
    # all rows have origin=None -> empty
    assert out_of_sync_pairs(state) == []
    s = summarize(state)
    assert s["total"] == 0


# EOF
