#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dist-info-count install-integrity check — REAL tmp-dir fixtures, NO mocks.

STX-NM002 forbids monkeypatch, so every case seeds a real temp directory with
real ``*.dist-info`` directories on disk and passes it through the
``site_packages`` seam. Three shapes, matching the three conditions the guard
must distinguish:

* DOUBLE  — two ``foo-*.dist-info`` in one dir, BOTH carrying METADATA →
  count == 2 → dirty-install ERROR carrying the repair text. This is the
  defect the guard exists for and it must keep firing loudly.
* CLEAN   — exactly one → count == 1 → no finding.
* ZERO    — none → count == 0 → the "not installed" branch, distinct from the
  double error.
* RESIDUE — a dist-info NAME that is not an install: an emptied directory
  (no METADATA), or a non-directory entry standing in for an overlayfs
  whiteout. Must NOT count. The whiteout stand-ins are labelled as such —
  a real character-special node cannot be created unprivileged here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scitex_dev._release.dist_info_integrity import (
    AMBIGUOUS_METADATA_REMEDY,
    DIST_INFO_NOTE,
    DOUBLE_INSTALL_REMEDY,
    _REMEDY_CASE_DOUBLE,
    _REMEDY_CASE_RESIDUE,
    _REMEDY_READONLY_LAYER,
    annotate_dist_info_integrity,
    count_dist_infos,
    dist_info_integrity,
    dist_info_status,
)


def _flat(text: str) -> str:
    """Whitespace-collapsed, lowercased text.

    The claims under test span hard-wrapped lines, so an exact-sentence
    assertion breaks on any re-wrap. These tests target the SUBSTANCE — that
    resolution is stated to be unspecified, that both directions are named —
    so the next honest rewording does not have to fight the suite.
    """
    return " ".join(text.split()).lower()


def _make_empty_dist_info(site: Path, dist: str, version: str) -> Path:
    """A dist-info directory with NO METADATA — overlay residue, not an install.

    `pip uninstall` removes a dist-info's FILES; on an overlay filesystem the
    emptied DIRECTORY entry can survive, showing through from the lower layer.
    """
    site.mkdir(parents=True, exist_ok=True)
    info = site / f"{dist.replace('-', '_')}-{version}.dist-info"
    info.mkdir()
    return info


def _make_whiteout_standin_file(site: Path, dist: str, version: str) -> Path:
    """A NON-DIRECTORY entry carrying a ``*.dist-info`` name.

    STAND-IN, LABELLED AS SUCH: the real case is an overlayfs WHITEOUT — a
    character-special device node (major 0, minor 0). This container cannot
    create one (measured: `mknod` fails, CapEff is 0000000000000000, and
    `mount -t overlay` refuses with "must be superuser"), and STX-NM002
    forbids faking it with a mock. A plain FILE exercises the same code path
    — the ``Path.is_dir()`` type test — because a whiteout, like a file, is
    not a directory. It stands in for the whiteout; it is not one.
    """
    site.mkdir(parents=True, exist_ok=True)
    entry = site / f"{dist.replace('-', '_')}-{version}.dist-info"
    entry.write_text("not a directory\n")
    return entry


def _make_whiteout_standin_symlink(site: Path, dist: str, version: str) -> Path:
    """A DANGLING SYMLINK carrying a ``*.dist-info`` name.

    The second labelled stand-in for the un-creatable whiteout node (see
    :func:`_make_whiteout_standin_file`). ``is_dir()`` follows the link,
    finds nothing, and returns False — same rejection path.
    """
    site.mkdir(parents=True, exist_ok=True)
    entry = site / f"{dist.replace('-', '_')}-{version}.dist-info"
    entry.symlink_to(site / "nonexistent-target")
    return entry


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


# --- A NAME MATCH IS NOT AN INSTALL ------------------------------------------


@pytest.fixture
def residue_site(tmp_path: Path) -> Path:
    """One REAL install plus an EMPTY same-package dist-info directory.

    Overlay residue: pip removed the dist-info's files, and on an overlay
    the emptied DIRECTORY can survive as an entry from the lower layer.
    """
    _make_dist_info(tmp_path, "foo", "2.0")
    _make_empty_dist_info(tmp_path, "foo", "1.0")
    return tmp_path


@pytest.fixture
def corrupt_metadata_site(tmp_path: Path) -> Path:
    """One real install plus a second whose METADATA is present but garbage."""
    _make_dist_info(tmp_path, "foo", "2.0")
    broken = _make_empty_dist_info(tmp_path, "foo", "1.0")
    (broken / "METADATA").write_bytes(b"\x00\xff\x00 not parseable metadata")
    return tmp_path


def test_empty_dist_info_directory_does_not_count(residue_site):
    # Arrange
    dist = "foo"
    # Act
    count = count_dist_infos(dist, site_packages=residue_site)
    # Assert — residue is not a distribution; the install is clean.
    assert count == 1


def test_empty_residue_status_is_ok(residue_site):
    # Arrange
    dist = "foo"
    # Act
    result = dist_info_integrity(dist, site_packages=residue_site)
    # Assert
    assert result["status"] == "ok"


def test_empty_residue_carries_no_message(residue_site):
    # Arrange
    dist = "foo"
    # Act
    result = dist_info_integrity(dist, site_packages=residue_site)
    # Assert — a non-problem must not produce a remediation.
    assert result["message"] is None


def test_two_dist_infos_both_with_metadata_still_count_two(double_site):
    # Arrange — MUTATION PROOF: requiring METADATA must not neuter the check.
    dist = "foo"
    # Act
    count = count_dist_infos(dist, site_packages=double_site)
    # Assert
    assert count == 2


def test_two_dist_infos_both_with_metadata_still_dirty(dirty_result):
    # Arrange — the same shape through the classifier. Two COMPLETE
    # dist-infos is the defect the guard exists for (scitex-storage ran
    # 0.30.0 files under a 0.37.1 dist-info for weeks).
    verdict = dirty_result
    # Act
    status = verdict["status"]
    # Assert — still fires, loudly.
    assert status == "dirty_install"


def test_unreadable_metadata_still_counts_as_installed(corrupt_metadata_site):
    # Arrange — PINNED DECISION: METADATA present but not valid metadata
    # COUNTS. "Absent" means residue, a non-problem; "present but
    # unreadable" means a CORRUPT install, a real problem. Collapsing the
    # two would let corruption vanish through the residue door.
    dist = "foo"
    # Act
    count = count_dist_infos(dist, site_packages=corrupt_metadata_site)
    # Assert
    assert count == 2


def test_unreadable_metadata_is_reported_as_dirty(corrupt_metadata_site):
    # Arrange
    dist = "foo"
    # Act
    result = dist_info_integrity(dist, site_packages=corrupt_metadata_site)
    # Assert — the corrupt second install still trips the guard.
    assert result["status"] == "dirty_install"


def test_whiteout_standin_plain_file_does_not_count(tmp_path):
    # Arrange — a NON-DIRECTORY entry named `foo-1.0.dist-info`. LABELLED
    # STAND-IN for an overlayfs whiteout (a character-special node), which
    # this container cannot create unprivileged — see the helper's docstring.
    _make_dist_info(tmp_path, "foo", "2.0")
    _make_whiteout_standin_file(tmp_path, "foo", "1.0")
    # Act
    count = count_dist_infos("foo", site_packages=tmp_path)
    # Assert — the TYPE test, not the name, decides.
    assert count == 1


def test_whiteout_standin_dangling_symlink_does_not_count(tmp_path):
    # Arrange — same LABELLED stand-in, second shape: a dangling symlink.
    _make_dist_info(tmp_path, "foo", "2.0")
    _make_whiteout_standin_symlink(tmp_path, "foo", "1.0")
    # Act
    count = count_dist_infos("foo", site_packages=tmp_path)
    # Assert
    assert count == 1


# --- Remediation text --------------------------------------------------------


def test_remedy_gives_the_ls_a_discriminator_first():
    # Arrange
    text = AMBIGUOUS_METADATA_REMEDY
    # Act
    discriminator = "ls -A"
    # Assert — the reader must be able to tell WHICH case they are in first.
    assert discriminator in text


def test_remedy_names_the_empty_directory_tell():
    # Arrange
    text = AMBIGUOUS_METADATA_REMEDY
    # Act
    tell = "EMPTY DIRECTORY"
    # Assert
    assert tell in text


def test_remedy_forbids_judging_by_directory_size():
    # Arrange
    text = AMBIGUOUS_METADATA_REMEDY
    # Act
    warning = "never by directory SIZE"
    # Assert — directory size is the overlay trap that misled this incident.
    assert warning in text


def test_remedy_names_the_overlay_size_zero_trap():
    # Arrange
    text = AMBIGUOUS_METADATA_REMEDY
    # Act
    trap = "size 0"
    # Assert
    assert trap in text


def test_residue_branch_recommends_rmdir():
    # Arrange
    residue = _REMEDY_CASE_RESIDUE
    # Act
    remedy = "rmdir"
    # Assert — `rmdir` removes zero files and refuses on a non-empty dir.
    assert remedy in residue


def test_residue_branch_never_recommends_force_reinstall():
    # Arrange
    residue = _REMEDY_CASE_RESIDUE
    # Act
    destructive = "force-reinstall"
    # Assert — prescribing the same action for a non-problem and a real
    # problem is what pushed an agent to disarm the gate entirely.
    assert destructive not in residue


def test_residue_branch_never_recommends_pip_uninstall():
    # Arrange
    residue = _REMEDY_CASE_RESIDUE
    # Act
    destructive = "pip uninstall"
    # Assert — an empty directory contains nothing to uninstall.
    assert destructive not in residue


def test_remedy_labels_both_cases_distinctly():
    # Arrange
    text = AMBIGUOUS_METADATA_REMEDY
    # Act
    labelled = "CASE 1" in text and "CASE 2" in text
    # Assert
    assert labelled


def test_remedy_gives_the_two_cases_different_commands():
    # Arrange
    text = AMBIGUOUS_METADATA_REMEDY
    # Act
    distinct = "rmdir" in text and "rm -rf" in text
    # Assert
    assert distinct


# --- Resolution among duplicates is UNSPECIFIED ------------------------------
# CORRECTED 2026-07-29 (second correction). The shipped text said
# importlib.metadata "locks onto whichever dist-info it enumerates first —
# measured: it picked the OLDER one". That was ONE measurement on ONE setup
# generalised into a rule. Three hosts, both outcomes: scitex-dev 0.38.0 over
# 0.38.1 (OLDER won) and scitex-cards two-in-one-dir (OLDER won), against
# scitex-cards 0.17.10 over a base-layer 0.17.9 (NEWER won). Resolution is
# UNSPECIFIED — sys.path order, no version preference — so "the older" is a
# prediction nobody may build a repair on.


def test_remedy_says_resolution_among_duplicates_is_unspecified():
    # Arrange
    text = _flat(AMBIGUOUS_METADATA_REMEDY)
    # Act
    stated = "unspecified" in text
    # Assert
    assert stated


def test_remedy_explains_why_resolution_is_unspecified():
    # Arrange — a bare "unspecified" invites the reader to go find the rule
    # anyway. The mechanism has to be named: sys.path iteration order, with
    # no version preference of any kind.
    text = _flat(AMBIGUOUS_METADATA_REMEDY)
    # Act
    names_mechanism = "sys.path" in text and (
        "no version comparison" in text or "no version preference" in text
    )
    # Assert
    assert names_mechanism


def test_remedy_names_both_directions():
    # Arrange — it must be visible that it goes BOTH ways; naming only one
    # outcome is what produced the wrong rule in the first place.
    text = _flat(AMBIGUOUS_METADATA_REMEDY)
    # Act
    both = "older" in text and "newer" in text
    # Assert
    assert both


def test_remedy_never_predicts_which_duplicate_wins():
    # Arrange — regression guard on the retired sentence, in either spelling.
    text = _flat(AMBIGUOUS_METADATA_REMEDY)
    # Act
    predicts = "picked the older" in text or "enumerates first" in text
    # Assert
    assert not predicts


def test_remedy_keeps_the_concrete_consequence():
    # Arrange — the correction must not soften the point: the consequence is
    # unchanged and is why the check exists.
    text = _flat(AMBIGUOUS_METADATA_REMEDY)
    # Act
    consequence = "may not describe the files that actually run" in text
    # Assert
    assert consequence


def test_note_says_resolution_is_unspecified_in_either_direction():
    # Arrange — the report-level note carried the same wrong shape ("a stale
    # dist-info shadow the newer one").
    text = _flat(DIST_INFO_NOTE)
    # Act
    honest = "unspecified" in text and "newer" in text and "older" in text
    # Assert
    assert honest


# --- CASE 3: read-only lower overlay layer -----------------------------------
# The measured "delete the stale dist-info directory only — safe" advice is a
# SAME-LAYER fix. It does not transfer to a stale dist-info in a read-only
# lower layer, where rm -rf only masks the entry in the caller's upper layer.


def test_read_only_layer_is_its_own_labelled_case():
    # Arrange
    text = _flat(AMBIGUOUS_METADATA_REMEDY)
    # Act
    labelled = "case 3" in text and "read-only lower overlay layer" in text
    # Assert — a distinct case, not a footnote to CASE 2.
    assert labelled


def test_read_only_layer_says_the_same_layer_fix_does_not_transfer():
    # Arrange
    text = _flat(_REMEDY_READONLY_LAYER)
    # Act
    scoped = "does not transfer" in text
    # Assert
    assert scoped


def test_read_only_layer_states_the_image_still_ships_two():
    # Arrange — the failure mode is that the container looks repaired while
    # every FRESH container starts broken again.
    text = _flat(_REMEDY_READONLY_LAYER)
    # Act
    stated = "fresh container" in text
    # Assert
    assert stated


def test_read_only_layer_is_labelled_inferred_not_measured():
    # Arrange — overlay mechanics could not be reproduced here (`mount -t
    # overlay` needs superuser, `mknod` fails, CapEff 0000000000000000), so
    # the case must not be promoted to a measured result.
    text = _flat(_REMEDY_READONLY_LAYER)
    # Act
    labelled = "inferred, not measured" in text
    # Assert
    assert labelled


def test_same_layer_fix_is_scoped_to_the_same_layer():
    # Arrange — the rm -rf prescription itself must carry its scope, so it
    # cannot be lifted out of context into a CASE 3 situation.
    text = _flat(_REMEDY_CASE_DOUBLE)
    # Act
    scoped = "same-layer" in text and "rm -rf" in text
    # Assert
    assert scoped


def test_rewrite_did_not_drop_the_parts_that_were_right():
    # Arrange — POSITIVE CONTROL for the correction above. The two things the
    # shipped text got RIGHT are the case discriminator and the residue tell;
    # a rewrite must not silently take them with it.
    text = AMBIGUOUS_METADATA_REMEDY
    # Act
    kept = "ls -A" in text and "EMPTY DIRECTORY" in text
    # Assert
    assert kept


def test_double_install_remedy_alias_is_the_same_text():
    # Arrange
    alias = DOUBLE_INSTALL_REMEDY
    # Act
    canonical = AMBIGUOUS_METADATA_REMEDY
    # Assert — back-compat name kept for existing importers.
    assert alias == canonical


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


def test_dirty_message_states_force_reinstall_clears_only_one(dirty_result):
    # Arrange — CORRECTED 2026-07-29. This test used to assert the message
    # said force-reinstall "does NOT fix this". Measured against real venvs,
    # that claim is FALSE: force-reinstall does remove a prior dist-info
    # (3 dist-infos -> one run -> 2 left; 2 -> 1). The true, narrower fact
    # is that it clears only the ONE installation pip resolves per run.
    result = dirty_result
    # Act
    message = result["message"]
    # Assert
    assert "removes only the ONE installation pip currently" in message


def test_dirty_message_says_uninstall_repeatedly(dirty_result):
    # Arrange
    result = dirty_result
    # Act
    message = result["message"]
    # Assert
    assert "pip uninstall foo` REPEATEDLY" in message


def test_dirty_message_says_resolution_is_unspecified(dirty_result):
    # Arrange — the verdict line above the remediation carried its own copy
    # of the "(measured: the OLDER one)" claim.
    result = dirty_result
    # Act
    message = _flat(result["message"])
    # Assert
    assert "unspecified" in message and "sys.path" in message


def test_dirty_message_names_both_directions(dirty_result):
    # Arrange
    result = dirty_result
    # Act
    message = _flat(result["message"])
    # Assert — measured both ways across three hosts.
    assert "older" in message and "newer" in message


def test_dirty_message_keeps_the_concrete_consequence(dirty_result):
    # Arrange
    result = dirty_result
    # Act
    message = _flat(result["message"])
    # Assert — the point survives the correction.
    assert "may not describe the files that actually run" in message


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
