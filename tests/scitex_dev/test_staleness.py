#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CURRENCY gate (`scitex_dev.staleness.ensure_current`) against REAL fixtures.

No mocks (PA-306): real dist-info directories with RECORD + payload files in
a temp site dir (injected via the `_search_paths` seam — no
importlib/sys.path patching), real git repos for the editable-freshness leg,
real cache/knob files, and log capture by attaching a handler to the exact
`scitex_dev` logger (the xdist-deterministic idiom from #395 — NOT
redirect_stderr, which scitex-logging's import-time stream binding defeats).

Motivating incident (2026-07-21): a venv carried 0.16.0 + 0.17.4 dist-infos
with 0.17.4 metadata over a 0.16-era file set; a RECORD-listed module was
absent on disk and every version probe lied. The integrity half must catch
exactly that (ambiguous metadata / partial install); the freshness half is
fail-safe (no cache / offline / any error → PASS).
"""

from __future__ import annotations

import contextlib
import io
import json
import logging
import os
import subprocess
from pathlib import Path

import pytest

from scitex_dev.staleness import StalenessError, ensure_current


# --- Real fixtures -----------------------------------------------------------


def _make_dist(site: Path, name: str = "demo-pkg", version: str = "1.0.0") -> Path:
    """A REAL wheel-style install: payload package + dist-info with RECORD."""
    mod = name.replace("-", "_")
    pkg_dir = site / mod
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "__init__.py").write_text(f'__version__ = "{version}"\n')
    (pkg_dir / "_core.py").write_text("VALUE = 1\n")
    info = site / f"{mod}-{version}.dist-info"
    info.mkdir()
    (info / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"
    )
    record_lines = [
        f"{mod}/__init__.py,,",
        f"{mod}/_core.py,,",
        f"{mod}-{version}.dist-info/METADATA,,",
        f"{mod}-{version}.dist-info/RECORD,,",
    ]
    (info / "RECORD").write_text("\n".join(record_lines) + "\n")
    return info


def _make_editable_dist(
    site: Path, src_dir: Path, name: str = "demo-pkg", version: str = "1.0.0"
) -> Path:
    """An editable-style install: direct_url.json editable flag, no RECORD."""
    mod = name.replace("-", "_")
    info = site / f"{mod}-{version}.dist-info"
    info.mkdir(parents=True)
    (info / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"
    )
    (info / "direct_url.json").write_text(
        json.dumps({"url": src_dir.as_uri(), "dir_info": {"editable": True}})
    )
    return info


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _head(repo: Path) -> str:
    out = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return out.stdout.strip()


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "f.txt").write_text("v1")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "c1")
    _git(repo, "branch", "-M", "develop")
    return repo


def _set_upstream(repo: Path, sha: str) -> None:
    """Point develop's upstream at origin/develop pinned to `sha` (offline)."""
    _git(repo, "remote", "add", "origin", str(repo))
    _git(repo, "update-ref", "refs/remotes/origin/develop", sha)
    _git(repo, "branch", "--set-upstream-to=origin/develop", "develop")


def _make_behind_editable(tmp_path: Path) -> tuple[Path, Path]:
    """(site, repo): editable dist whose repo is 2 commits BEHIND upstream."""
    repo = _init_repo(tmp_path)
    (repo / "f.txt").write_text("v2")
    _git(repo, "commit", "-aqm", "c2")
    (repo / "f.txt").write_text("v3")
    _git(repo, "commit", "-aqm", "c3")
    ahead_sha = _head(repo)
    _git(repo, "checkout", "-q", "-B", "develop", "HEAD~2")
    _set_upstream(repo, ahead_sha)
    site = tmp_path / "site"
    _make_editable_dist(site, repo)
    return site, repo


def _make_broken_dist(tmp_path: Path) -> Path:
    """Site dir with the incident shape: a RECORD-listed file gone from disk."""
    site = tmp_path / "site"
    _make_dist(site)
    (site / "demo_pkg" / "_core.py").unlink()
    return site


@contextlib.contextmanager
def _environ(**overrides: str | None):
    saved = {k: os.environ.get(k) for k in overrides}
    try:
        for key, value in overrides.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _gate_env(tmp_path: Path, **extra: str | None):
    """Isolate every gate input from the host machine: absent config/knob
    files, an empty per-dist cache dir, gate + severity envs unset."""
    cache_dir = tmp_path / "version-cache"
    cache_dir.mkdir(exist_ok=True)
    base: dict[str, str | None] = {
        "SCITEX_DEV_CONFIG": str(tmp_path / "absent-config.yaml"),
        "SCITEX_DEV_KNOB_STATE": str(tmp_path / "absent-knob.json"),
        "SCITEX_DEV_VERSION_CACHE": str(tmp_path / "absent-legacy.json"),
        "SCITEX_DEV_VERSION_CACHE_DIR": str(cache_dir),
        "SCITEX_DEV_NO_CURRENCY_GATE": None,
        "SCITEX_DEV_CURRENCY_SEVERITY": None,
    }
    base.update(extra)
    return _environ(**base)


@contextlib.contextmanager
def _capture_gate_log(buf: io.StringIO):
    """Attach our OWN handler to the exact ``scitex_dev`` logger (the
    de-flaked #395 idiom) so the emitted line lands in ``buf`` regardless of
    global handler state or xdist import order."""
    handler = logging.StreamHandler(buf)
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    handler.setLevel(logging.DEBUG)
    logger = logging.getLogger("scitex_dev")
    prev_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    try:
        yield
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prev_level)


# --- Integrity half ----------------------------------------------------------


def test_intact_dist_passes_at_error_severity(tmp_path):
    # Arrange — a complete install: every RECORD-listed file on disk.
    site = tmp_path / "site"
    _make_dist(site)
    # Act — freshness also passes: empty cache dir, no network.
    with _gate_env(tmp_path):
        result = ensure_current(
            "demo-pkg", severity="error", _search_paths=[str(site)]
        )
    # Assert — returning None (not raising) IS the pass contract.
    assert result is None


def test_missing_record_file_raises_partial_install(tmp_path):
    # Arrange — delete a RECORD-listed payload file (the incident shape:
    # metadata claims a file set the disk does not have).
    site = _make_broken_dist(tmp_path)
    # Act — error severity gates hard.
    with _gate_env(tmp_path):
        # Assert — StalenessError names the violation, the missing file,
        # and the exact remedy command.
        with pytest.raises(
            StalenessError, match=r"partial install.*_core\.py.*pip install -U"
        ):
            ensure_current("demo-pkg", severity="error", _search_paths=[str(site)])


def test_missing_record_file_warns_at_warn_severity(tmp_path):
    # Arrange — same broken dist, severity=warn.
    site = _make_broken_dist(tmp_path)
    buf = io.StringIO()
    # Act — warn must LOG and return, never raise.
    with _gate_env(tmp_path), _capture_gate_log(buf):
        ensure_current("demo-pkg", severity="warn", _search_paths=[str(site)])
    # Assert — the WARN record carries the violation.
    out = buf.getvalue()
    assert "WARN" in out and "partial install" in out


def test_two_dist_infos_same_name_is_ambiguous(tmp_path):
    # Arrange — the incident's other face: 0.16.0 + 0.17.4 dist-infos both
    # claiming the same distribution in ONE site dir. THE PRIMARY CASE: two
    # COMPLETE installs must keep firing, loudly.
    site = tmp_path / "site"
    _make_dist(site, version="0.16.0")
    _make_dist(site, version="0.17.4")
    # Act
    with _gate_env(tmp_path):
        # Assert — both claimants are named in the message.
        with pytest.raises(
            StalenessError, match=r"ambiguous metadata.*0\.16\.0.*0\.17\.4"
        ):
            ensure_current("demo-pkg", severity="error", _search_paths=[str(site)])


# --- A dist-info NAME is not an install --------------------------------------


def _make_residue_dist_info(site: Path, version: str, name: str = "demo-pkg") -> Path:
    """An EMPTY dist-info directory — overlay residue, not an install.

    `pip uninstall` removes a dist-info's FILES; on an overlay filesystem the
    emptied DIRECTORY can survive as an entry showing through from the lower
    layer, so a name-only count sees a duplicate that does not exist.
    """
    info = site / f"{name.replace('-', '_')}-{version}.dist-info"
    info.mkdir(parents=True)
    return info


def _make_whiteout_standin(site: Path, version: str, name: str = "demo-pkg") -> Path:
    """A NON-DIRECTORY entry carrying a ``*.dist-info`` name.

    LABELLED STAND-IN: the real case is an overlayfs WHITEOUT — a
    character-special device node (major 0, minor 0). This container cannot
    create one (measured: `mknod` fails with CapEff 0000000000000000, and
    `mount -t overlay` refuses with "must be superuser"), and STX-NM002
    forbids faking it with a mock. A plain FILE exercises the same rejection
    path — `Path.is_dir()` — because a whiteout, like a file, is not a
    directory. It stands in for the whiteout; it is not one.
    """
    site.mkdir(parents=True, exist_ok=True)
    entry = site / f"{name.replace('-', '_')}-{version}.dist-info"
    entry.write_text("not a directory\n")
    return entry


def test_empty_residue_dist_info_is_not_ambiguous(tmp_path):
    # Arrange — one REAL install plus an EMPTY same-package dist-info dir.
    # A directory with no METADATA is filesystem residue, not a second
    # distribution, so it must not manufacture an ambiguity finding.
    site = tmp_path / "site"
    _make_dist(site, version="0.17.4")
    _make_residue_dist_info(site, "0.16.0")
    # Act
    with _gate_env(tmp_path):
        result = ensure_current(
            "demo-pkg", severity="error", _search_paths=[str(site)]
        )
    # Assert — returning None (not raising) IS the pass contract.
    assert result is None


def test_dist_info_with_unreadable_metadata_still_ambiguous(tmp_path):
    # Arrange — PINNED DECISION: METADATA present but unparseable COUNTS.
    # "Absent" means residue (a non-problem); "present but unreadable" means
    # a CORRUPT install (a real problem the operator must see). Collapsing
    # them would let corruption vanish through the residue door.
    site = tmp_path / "site"
    _make_dist(site, version="0.17.4")
    broken = _make_residue_dist_info(site, "0.16.0")
    (broken / "METADATA").write_bytes(b"\x00\xff\x00 not parseable metadata")
    # Act
    with _gate_env(tmp_path):
        # Assert — the corrupt second install still trips the gate.
        with pytest.raises(StalenessError, match=r"ambiguous metadata"):
            ensure_current("demo-pkg", severity="error", _search_paths=[str(site)])


def test_whiteout_standin_entry_is_not_ambiguous(tmp_path):
    # Arrange — a NON-DIRECTORY entry named `demo_pkg-0.16.0.dist-info`,
    # the labelled stand-in for an overlayfs whiteout (see the helper).
    site = tmp_path / "site"
    _make_dist(site, version="0.17.4")
    _make_whiteout_standin(site, "0.16.0")
    # Act
    with _gate_env(tmp_path):
        result = ensure_current(
            "demo-pkg", severity="error", _search_paths=[str(site)]
        )
    # Assert — the TYPE test, not the name, decides.
    assert result is None


def test_dangling_symlink_dist_info_is_not_ambiguous(tmp_path):
    # Arrange — second labelled whiteout stand-in: a dangling symlink whose
    # name matches. `is_dir()` follows the link, finds nothing, returns False.
    site = tmp_path / "site"
    _make_dist(site, version="0.17.4")
    (site / "demo_pkg-0.16.0.dist-info").symlink_to(site / "nonexistent-target")
    # Act
    with _gate_env(tmp_path):
        result = ensure_current(
            "demo-pkg", severity="error", _search_paths=[str(site)]
        )
    # Assert
    assert result is None


# --- The remediation the gate hands the reader -------------------------------


def _ambiguity_message(tmp_path: Path) -> str:
    """The gate's full ambiguous-metadata text for a real two-install site."""
    site = tmp_path / "site"
    _make_dist(site, version="0.16.0")
    _make_dist(site, version="0.17.4")
    with _gate_env(tmp_path):
        with pytest.raises(StalenessError) as excinfo:
            ensure_current("demo-pkg", severity="error", _search_paths=[str(site)])
    return str(excinfo.value)


def test_ambiguity_message_gives_the_ls_a_discriminator(tmp_path):
    # Arrange
    message = _ambiguity_message(tmp_path)
    # Act
    discriminator = "ls -A"
    # Assert — the reader must be able to tell WHICH case they are in.
    assert discriminator in message


def test_ambiguity_message_names_the_empty_directory_tell(tmp_path):
    # Arrange
    message = _ambiguity_message(tmp_path)
    # Act
    tell = "EMPTY DIRECTORY"
    # Assert
    assert tell in message


def test_ambiguity_message_offers_rmdir_for_residue(tmp_path):
    # Arrange
    message = _ambiguity_message(tmp_path)
    # Act
    safe_remedy = "rmdir"
    # Assert — the residue case's fix removes zero files.
    assert safe_remedy in message


def test_ambiguity_message_says_resolution_is_unspecified(tmp_path):
    # Arrange — CORRECTED 2026-07-29. The gate used to hand the reader
    # "measured: it picked the OLDER one", a one-host result generalised
    # into a rule; a third host measured the NEWER winning. Assert the
    # SUBSTANCE (unspecified, and both directions named), not a sentence.
    message = " ".join(_ambiguity_message(tmp_path).split()).lower()
    # Act
    honest = (
        "unspecified" in message
        and "sys.path" in message
        and "older" in message
        and "newer" in message
    )
    # Assert
    assert honest


def test_ambiguity_message_keeps_the_concrete_consequence(tmp_path):
    # Arrange — the correction must not soften why the gate fires.
    message = " ".join(_ambiguity_message(tmp_path).split()).lower()
    # Act
    consequence = "may not describe the files that actually run" in message
    # Assert
    assert consequence


def test_ambiguity_message_labels_the_read_only_layer_case(tmp_path):
    # Arrange — CASE 2's `rm -rf` does not transfer to a stale dist-info in a
    # read-only lower layer; the gate's text must carry that as its own case.
    message = " ".join(_ambiguity_message(tmp_path).split()).lower()
    # Act
    labelled = "case 3" in message and "does not transfer" in message
    # Assert
    assert labelled


def test_ambiguity_message_no_longer_prescribes_force_reinstall(tmp_path):
    # Arrange
    message = _ambiguity_message(tmp_path)
    # Act
    old_remedy = "run: pip install -U --force-reinstall"
    # Assert — the old one-size-fits-all instruction is gone; force-reinstall
    # now appears only as a measured caveat, never as the prescription.
    assert old_remedy not in message


def test_editable_without_record_skips_integrity(tmp_path):
    # Arrange — editable-style dist: direct_url.json editable flag, no
    # RECORD (files is None). Integrity must skip gracefully; freshness on a
    # non-repo source dir resolves to None (fail-safe).
    site = tmp_path / "site"
    src = tmp_path / "src-checkout"
    src.mkdir()
    _make_editable_dist(site, src)
    # Act
    with _gate_env(tmp_path):
        result = ensure_current(
            "demo-pkg", severity="error", _search_paths=[str(site)]
        )
    # Assert — no crash, no raise.
    assert result is None


def test_absent_dist_gives_no_verdict(tmp_path):
    # Arrange — nothing installed in the site dir (source-tree run shape).
    site = tmp_path / "site"
    site.mkdir()
    # Act — fail-safe: no metadata, no verdict.
    with _gate_env(tmp_path):
        result = ensure_current(
            "demo-pkg", severity="error", _search_paths=[str(site)]
        )
    # Assert
    assert result is None


# --- Freshness half ----------------------------------------------------------


def test_freshness_no_cache_passes(tmp_path):
    # Arrange — intact wheel dist, EMPTY cache dir: no evidence, no network.
    site = tmp_path / "site"
    _make_dist(site, version="0.0.1")
    # Act
    with _gate_env(tmp_path):
        result = ensure_current(
            "demo-pkg", severity="error", _search_paths=[str(site)]
        )
    # Assert — fail-safe PASS.
    assert result is None


def test_freshness_behind_cached_latest_raises(tmp_path):
    # Arrange — the per-dist cache advertises a far-newer latest.
    site = tmp_path / "site"
    _make_dist(site, version="1.0.0")
    cache_dir = tmp_path / "version-cache"
    cache_dir.mkdir()
    (cache_dir / "demo-pkg.json").write_text(
        json.dumps({"latest": "99.0.0", "fetched_at": 0})
    )
    # Act
    with _gate_env(tmp_path):
        # Assert — installed vs latest plus the exact pip remedy.
        with pytest.raises(
            StalenessError,
            match=r"1\.0\.0 is behind latest 99\.0\.0.*pip install -U demo-pkg",
        ):
            ensure_current("demo-pkg", severity="error", _search_paths=[str(site)])


def test_freshness_current_version_passes(tmp_path):
    # Arrange — cached latest equals the installed version.
    site = tmp_path / "site"
    _make_dist(site, version="1.0.0")
    cache_dir = tmp_path / "version-cache"
    cache_dir.mkdir()
    (cache_dir / "demo-pkg.json").write_text(json.dumps({"latest": "1.0.0"}))
    # Act
    with _gate_env(tmp_path):
        result = ensure_current(
            "demo-pkg", severity="error", _search_paths=[str(site)]
        )
    # Assert — no raise.
    assert result is None


def test_editable_behind_remote_raises_with_ff_only_remedy(tmp_path):
    # Arrange — a REAL git repo whose upstream is 2 commits ahead of HEAD,
    # wired as the editable source of the dist.
    site, _repo = _make_behind_editable(tmp_path)
    # Act
    with _gate_env(tmp_path):
        # Assert — behind-remote editable is STALE; the remedy is the
        # CWD-safe, non-destructive ff-only form (never a bare `git pull`).
        with pytest.raises(
            StalenessError, match=r"editable demo-pkg.*pull --ff-only"
        ):
            ensure_current("demo-pkg", severity="error", _search_paths=[str(site)])


def test_editable_level_with_remote_passes(tmp_path):
    # Arrange — upstream pinned AT HEAD: current, nothing to pull.
    repo = _init_repo(tmp_path)
    _set_upstream(repo, _head(repo))
    site = tmp_path / "site"
    _make_editable_dist(site, repo)
    # Act
    with _gate_env(tmp_path):
        result = ensure_current(
            "demo-pkg", severity="error", _search_paths=[str(site)]
        )
    # Assert — no raise.
    assert result is None


# --- Severity ladder ---------------------------------------------------------


def test_default_severity_is_error(tmp_path):
    # Arrange — broken dist, NO explicit severity, env/config/knob isolated
    # to absent files: the ladder must bottom out at the operator's default
    # ("普通は warning ですが、私たちはエラーを選びます").
    site = _make_broken_dist(tmp_path)
    # Act
    with _gate_env(tmp_path):
        # Assert — default is ERROR.
        with pytest.raises(StalenessError):
            ensure_current("demo-pkg", _search_paths=[str(site)])


def test_env_severity_silent_short_circuits(tmp_path):
    # Arrange — broken dist, but $SCITEX_DEV_CURRENCY_SEVERITY=silent.
    site = _make_broken_dist(tmp_path)
    buf = io.StringIO()
    # Act — silent is a no-op: no raise, nothing emitted.
    with _gate_env(tmp_path, SCITEX_DEV_CURRENCY_SEVERITY="silent"):
        with _capture_gate_log(buf):
            ensure_current("demo-pkg", _search_paths=[str(site)])
    # Assert
    assert buf.getvalue() == ""


def test_explicit_severity_beats_env_knob(tmp_path):
    # Arrange — env says silent, but the explicit arg says error.
    site = _make_broken_dist(tmp_path)
    # Act
    with _gate_env(tmp_path, SCITEX_DEV_CURRENCY_SEVERITY="silent"):
        # Assert — the explicit arg is the top rung of the ladder.
        with pytest.raises(StalenessError):
            ensure_current("demo-pkg", severity="error", _search_paths=[str(site)])


def test_invalid_explicit_severity_raises_value_error(tmp_path):
    # Arrange — a caller typo, not a knob value.
    bad_severity = "fatal"
    # Act
    with _gate_env(tmp_path):
        # Assert — caller bugs surface immediately, not fail-safe-silently.
        with pytest.raises(ValueError):
            ensure_current("demo-pkg", severity=bad_severity)


# --- Bypass env: loud, never silent ------------------------------------------


def test_bypass_env_skips_both_halves_but_logs_loudly(tmp_path):
    # Arrange — a BROKEN dist that would raise, plus the bypass env.
    site = _make_broken_dist(tmp_path)
    buf = io.StringIO()
    # Act — bypass must not raise, even on a broken dist.
    with _gate_env(tmp_path, SCITEX_DEV_NO_CURRENCY_GATE="1"):
        with _capture_gate_log(buf):
            ensure_current("demo-pkg", severity="error", _search_paths=[str(site)])
    # Assert — the exercised bypass is emitted as a loud WARN naming the env.
    out = buf.getvalue()
    assert (
        "WARN" in out
        and "BYPASSED" in out
        and "SCITEX_DEV_NO_CURRENCY_GATE" in out
    )


# EOF
