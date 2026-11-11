#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Engine tests: rotation, tmp sweep, caps, apply, exit codes.

Every test runs the real engine against a real fixture tree. The only
fakes are the process boundary (``run``/``read_procs`` seams) and the
pinned clock — no test touches the real /tmp, the real containers tree,
or the real docker daemon.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from scitex_dev.hygiene import disk_exit_code_for, sweep_host
from scitex_dev.hygiene._disk_guard_model import DiskGuardOutcome

#: Pinned "now": everything fixture-old reads as stale.
FUTURE_NOW = float(1_000_000_000 + 400 * 86_400)


def fake_fuser_clean(*args, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=args, returncode=1, stdout=b"", stderr=b"")


def fake_fuser_factory(held: set[str]):
    def _run(cmd, **kwargs) -> subprocess.CompletedProcess:
        code = 0 if str(cmd[-1]) in held else 1
        return subprocess.CompletedProcess(
            args=cmd, returncode=code, stdout=b"", stderr=b""
        )

    return _run


def fake_no_build() -> list[str]:
    return ["1 /sbin/init", "42 /usr/bin/python -m something"]


def test_unarmed_host_reports_nothing(unarmed_home, tmp_path, monkeypatch):
    result = sweep_host(
        home=unarmed_home,
        containers_dir=tmp_path / "nope",
        tmp_dir=tmp_path / "nope",
        run=fake_fuser_clean,
        read_procs=fake_no_build,
    )
    assert result.enabled is False
    assert result.candidates == ()
    assert disk_exit_code_for(DiskGuardOutcome(results=(result,))) == 0


def test_rotation_keeps_newest_two_plus_live(containers, home, tmp_path, monkeypatch):
    monkeypatch.setattr("scitex_dev.hygiene._disk_guard.docker_present", lambda: False)
    result = sweep_host(
        home=home,
        containers_dir=containers,
        tmp_dir=tmp_path / "nope",
        now=FUTURE_NOW,
        run=fake_fuser_clean,
        read_procs=fake_no_build,
    )
    assert result.enabled is True
    by_name = {Path(v.path).name: v for v in result.candidates}
    assert by_name["sac-base-2026-1022-230924.sif"].action == "delete"
    assert by_name["sac-base-2026-1023-002022.sif"].action == "delete"
    assert by_name["sac-base-2026-1025-093116.sif"].action == "keep"
    assert by_name["sac-base-2026-1027-045501.sif"].action == "keep"
    assert by_name["sac-base-2026-1027-045501.sif"].reason == "live-symlink-target"


def test_held_open_sif_is_kept(containers, home, tmp_path):
    held = {str(containers / "sac-base" / "sac-base-2026-1022-230924.sif")}
    result = sweep_host(
        home=home,
        containers_dir=containers,
        tmp_dir=tmp_path / "nope",
        now=FUTURE_NOW,
        run=fake_fuser_factory(held),
        read_procs=fake_no_build,
    )
    by_name = {Path(v.path).name: v for v in result.candidates}
    assert by_name["sac-base-2026-1022-230924.sif"].reason == "held-open"


def test_fuser_missing_keeps_everything(containers, home, tmp_path):
    def no_fuser(*args, **kwargs):
        raise FileNotFoundError("no fuser here")

    result = sweep_host(
        home=home,
        containers_dir=containers,
        tmp_dir=tmp_path / "nope",
        now=FUTURE_NOW,
        run=no_fuser,
        read_procs=fake_no_build,
    )
    assert all(v.action == "keep" for v in result.candidates)
    assert set(v.reason for v in result.candidates) <= {
        "within-keep-newest",
        "live-symlink-target",
        "fuser-unavailable",
    }


def test_tmp_sweep_ages_and_escapes(home, tmp_with_leftovers):
    result = sweep_host(
        home=home,
        containers_dir=home / "no-containers",
        tmp_dir=tmp_with_leftovers,
        now=FUTURE_NOW,
        run=fake_fuser_clean,
        read_procs=fake_no_build,
    )
    by_name = {Path(v.path).name: v for v in result.candidates}
    assert by_name["ci-scitex_scholar-40045228307-1-3.13"].action == "delete"
    assert by_name["ci-scitex_scholar-40119538064-1-3.11"].reason == "too-young"
    assert "not-a-runner" not in by_name


def test_symlink_escape_is_kept(home, tmp_with_leftovers):
    link = tmp_with_leftovers / "ci-evil"
    link.symlink_to("/etc")
    result = sweep_host(
        home=home,
        containers_dir=home / "no-containers",
        tmp_dir=tmp_with_leftovers,
        now=FUTURE_NOW,
        run=fake_fuser_clean,
        read_procs=fake_no_build,
    )
    by_name = {Path(v.path).name: v for v in result.candidates}
    assert by_name["ci-evil"].action == "keep"


def test_apply_deletes_and_remeasures(containers, home, tmp_with_leftovers):
    result = sweep_host(
        home=home,
        containers_dir=containers,
        tmp_dir=tmp_with_leftovers,
        now=FUTURE_NOW,
        apply=True,
        run=fake_fuser_clean,
        read_procs=fake_no_build,
    )
    deleted = {Path(v.path).name for v in result.deleted}
    assert "sac-base-2026-1022-230924.sif" in deleted
    assert "ci-scitex_scholar-40045228307-1-3.13" in deleted
    assert not (containers / "sac-base" / "sac-base-2026-1022-230924.sif").exists()
    assert (
        containers / "sac-base" / "sac-base.sif"
    ).is_symlink()  # live link untouched
    assert result.use_after_pct is not None
    assert result.freed_bytes > 0


def test_dry_run_deletes_nothing(containers, home, tmp_with_leftovers):
    result = sweep_host(
        home=home,
        containers_dir=containers,
        tmp_dir=tmp_with_leftovers,
        now=FUTURE_NOW,
        apply=False,
        run=fake_fuser_clean,
        read_procs=fake_no_build,
    )
    assert result.deleted == ()
    assert (containers / "sac-base" / "sac-base-2026-1022-230924.sif").exists()


def test_max_delete_caps_and_reports(containers, home, tmp_path):
    result = sweep_host(
        home=home,
        containers_dir=containers,
        tmp_dir=tmp_path / "nope",
        now=FUTURE_NOW,
        max_delete=1,
        run=fake_fuser_clean,
        read_procs=fake_no_build,
    )
    assert sum(1 for v in result.candidates if v.action == "delete") == 1
    assert any(v.reason == "over-cap" for v in result.candidates)


def test_cache_leg_reports_only_when_armed_and_hot(home, tmp_path, monkeypatch):
    from scitex_dev.hygiene import _disk_guard

    monkeypatch.setattr(_disk_guard, "docker_present", lambda: True)
    monkeypatch.setattr(_disk_guard, "_use_pct_of", lambda p: 95.0)
    hot = sweep_host(
        home=home,
        containers_dir=tmp_path / "nope",
        tmp_dir=tmp_path / "nope",
        run=fake_fuser_clean,
        read_procs=fake_no_build,
    )
    kinds = [v.kind.value for v in hot.candidates]
    assert "build-cache" in kinds

    monkeypatch.setattr(_disk_guard, "_use_pct_of", lambda p: 40.0)
    cold = sweep_host(
        home=home,
        containers_dir=tmp_path / "nope",
        tmp_dir=tmp_path / "nope",
        run=fake_fuser_clean,
        read_procs=fake_no_build,
    )
    assert all(v.kind.value != "build-cache" for v in cold.candidates)


def test_exit_codes(home):
    ok = DiskGuardOutcome(results=())
    assert disk_exit_code_for(ok) == 0


# EOF
