#!/usr/bin/env python3
"""Does the reader read the ref its label names?

Both defects these readers replace produced PLAUSIBLE numbers, which is why
they survived: the working tree usually equals develop, and the newest
reachable tag usually IS the newest tag. So every test here constructs the
case where the two DISAGREE, and asserts the reader follows the label rather
than the thing closest to hand.

Two controls that would have caught the originals:

  * a working tree edited away from the committed value -- the SSoT defect
  * a newer tag cut on an unmerged branch -- the github defect, which was
    reachability and not staleness (the real clone was fetched that day and
    held 143 tags)

No mocks (STX-NM002): every case builds a REAL git repository under
``tmp_path`` with real commits, branches and tags. A fake git would have
agreed with whatever I believed `git describe` does -- and believing that
incorrectly is precisely what produced a published wrong refutation.
"""

import subprocess

import pytest

from scitex_dev._ecosystem._drift_report._refs import (
    PROV_NO_REF,
    PROV_NO_REPO,
    PROV_REF,
    latest_tag_at_ref,
    newest_tag_in_clone,
    unreachable_tag_note,
    version_at_ref,
)


def _git(repo, *args):
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )


def _write_version(repo, version):
    (repo / "pyproject.toml").write_text(
        f'[project]\nname = "demo"\nversion = "{version}"\n'
    )


@pytest.fixture
def repo(tmp_path):
    """A real repo on `develop` at 1.0.0, tagged v1.0.0."""
    root = tmp_path / "demo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "develop")
    _git(root, "config", "user.email", "test@scitex.ai")
    _git(root, "config", "user.name", "test")
    _write_version(root, "1.0.0")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "v1.0.0")
    _git(root, "tag", "v1.0.0")
    return root


@pytest.fixture
def repo_with_dirty_tree(repo):
    """develop committed at 1.0.0; the WORKING TREE says 9.9.9."""
    _write_version(repo, "9.9.9")
    return repo


@pytest.fixture
def repo_with_unreachable_tag(repo):
    """v2.0.0 cut on a branch never merged back into develop."""
    _git(repo, "checkout", "-q", "-b", "main")
    _write_version(repo, "2.0.0")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "v2.0.0")
    _git(repo, "tag", "v2.0.0")
    _git(repo, "checkout", "-q", "develop")
    return repo


def test_the_dirty_tree_really_differs_from_the_commit(repo_with_dirty_tree):
    """CONTROL FOR THE FIXTURE -- otherwise the next test proves nothing."""
    # Arrange
    target = repo_with_dirty_tree / "pyproject.toml"
    # Act
    on_disk = target.read_text()
    # Assert
    assert "9.9.9" in on_disk


def test_the_reference_comes_from_the_ref_not_the_working_tree(repo_with_dirty_tree):
    """THE SSoT DEFECT, 2026-08-16.

    An uncommitted edit must not move the reference every other column is
    compared against.
    """
    # Arrange
    candidates = ("develop",)
    # Act
    reading = version_at_ref(repo_with_dirty_tree, candidates)
    # Assert
    assert reading.value == "1.0.0"


def test_the_reference_records_which_ref_it_read(repo_with_dirty_tree):
    """A value without its provenance is how the original defect hid."""
    # Arrange
    candidates = ("develop",)
    # Act
    reading = version_at_ref(repo_with_dirty_tree, candidates)
    # Assert
    assert reading.provenance == PROV_REF


def test_a_missing_ref_refuses_rather_than_substituting(repo):
    """NEGATIVE CONTROL -- refusal is the whole point.

    Falling back to something closer to hand is the defect, so the absence
    of the named ref must produce UNKNOWN, never a number.
    """
    # Arrange
    candidates = ("no-such-branch",)
    # Act
    reading = version_at_ref(repo, candidates)
    # Assert
    assert reading.value is None


def test_a_missing_ref_says_why(repo):
    """UNKNOWN must be distinguishable from 'not a repo'."""
    # Arrange
    candidates = ("no-such-branch",)
    # Act
    reading = version_at_ref(repo, candidates)
    # Assert
    assert reading.provenance == PROV_NO_REF


def test_a_non_repo_is_reported_as_such(tmp_path):
    """'no git checkout' and 'ref absent' need different fixes, so they are
    different provenances rather than a shared None."""
    # Arrange
    plain = tmp_path / "not-a-repo"
    plain.mkdir()
    # Act
    reading = version_at_ref(plain, ("develop",))
    # Assert
    assert reading.provenance == PROV_NO_REPO


def test_an_unreachable_tag_is_not_reported_as_the_ref_tag(
    repo_with_unreachable_tag,
):
    """THE github DEFECT -- reachability, not staleness.

    v2.0.0 is in the clone and is NEWER, but was cut on a branch never
    merged into develop. Describing develop must yield v1.0.0.
    """
    # Arrange
    candidates = ("develop",)
    # Act
    reading = latest_tag_at_ref(repo_with_unreachable_tag, candidates)
    # Assert
    assert reading.value == "v1.0.0"


def test_the_newer_tag_really_is_present_in_the_clone(repo_with_unreachable_tag):
    """CONTROL FOR THE CONTROL -- the previous test would pass trivially if
    the tag had never been created."""
    # Arrange
    root = repo_with_unreachable_tag
    # Act
    newest = newest_tag_in_clone(root)
    # Assert
    assert newest == "v2.0.0"


def test_the_divergence_is_stated_rather_than_silently_walked_past(
    repo_with_unreachable_tag,
):
    """'nothing newer was released' and 'something newer is unreachable from
    here' are different facts and must not render identically."""
    # Arrange
    reading = latest_tag_at_ref(repo_with_unreachable_tag, ("develop",))
    newest = newest_tag_in_clone(repo_with_unreachable_tag)
    # Act
    note = unreachable_tag_note(reading, newest)
    # Assert
    assert "v2.0.0" in note


def test_no_divergence_note_when_the_ref_can_see_the_newest_tag(repo):
    """POSITIVE CONTROL -- the note must discriminate, not always fire."""
    # Arrange
    reading = latest_tag_at_ref(repo, ("develop",))
    newest = newest_tag_in_clone(repo)
    # Act
    note = unreachable_tag_note(reading, newest)
    # Assert
    assert note == ""


def test_the_tag_reader_follows_the_named_ref(repo_with_unreachable_tag):
    """Describing `main` sees v2.0.0 -- same clone, same call, different ref,
    which is what makes the label meaningful at all."""
    # Arrange
    candidates = ("main",)
    # Act
    reading = latest_tag_at_ref(repo_with_unreachable_tag, candidates)
    # Assert
    assert reading.value == "v2.0.0"
