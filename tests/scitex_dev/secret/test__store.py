# -*- coding: utf-8 -*-
"""Round-trip and failure-representation tests for the GPG secret store.

Every test runs against a THROWAWAY keypair in a temporary GNUPGHOME, created
by really invoking gpg. The operator's key is never touched or required.

Negative assertions are paired with a separate positive-control test, because
"X is absent" passes for free when X exists nowhere.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tarfile

import pytest

from scitex_dev.secret import (
    ALREADY_EXISTS,
    GPG_FAILED,
    INVALID_NAME,
    NOT_FOUND,
    NO_RECIPIENT,
    OK,
    SecretResult,
    SecretStore,
    generate_value,
)

pytestmark = pytest.mark.skipif(shutil.which("gpg") is None, reason="gpg not installed")

_UID = "SciTeX Throwaway Test Key <throwaway@example.invalid>"
_MARKER = "SENTINEL-PLAINTEXT-a7f3d9"


@pytest.fixture()
def gpg_home(tmp_path):
    """A disposable GNUPGHOME holding one real, unprotected throwaway key."""
    home = tmp_path / "gnupg"
    home.mkdir(mode=0o700)
    previous = os.environ.get("GNUPGHOME")
    os.environ["GNUPGHOME"] = str(home)
    proc = subprocess.run(
        [
            "gpg", "--batch", "--quiet", "--passphrase", "", "--pinentry-mode",
            "loopback", "--quick-generate-key", _UID, "default", "default", "never",
        ],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        if previous is None:
            os.environ.pop("GNUPGHOME", None)
        else:
            os.environ["GNUPGHOME"] = previous
        pytest.skip(f"throwaway key creation failed: {proc.stderr.decode(errors='replace')[:200]}")
    yield home
    # gpg leaves a gpg-agent DAEMON per GNUPGHOME; removing the tmp dir does not
    # reap it. Measured 2026-08-03: agents from a finished run were still alive
    # 18 minutes later, one per test. Kill it or a full suite leaks one each.
    subprocess.run(
        ["gpgconf", "--homedir", str(home), "--kill", "gpg-agent"],
        capture_output=True, check=False,
    )
    if previous is None:
        os.environ.pop("GNUPGHOME", None)
    else:
        os.environ["GNUPGHOME"] = previous


@pytest.fixture()
def store(tmp_path, gpg_home):
    made = SecretStore(tmp_path / "secretstore")
    made.init(_UID)
    return made


@pytest.fixture()
def store_with_secret(store):
    store.generate("svc/api-key", length=40)
    return store


# ------------------------------------------------------------- round trip

def test_show_returns_a_value_for_a_generated_secret(store_with_secret):
    # Arrange
    name = "svc/api-key"
    # Act
    result = store_with_secret.show(name)
    # Assert
    assert result.value is not None


def test_show_returns_the_requested_length(store_with_secret):
    # Arrange
    name = "svc/api-key"
    # Act
    result = store_with_secret.show(name)
    # Assert
    assert len(result.value) == 40


def test_generate_does_not_leak_the_value_into_its_result(store):
    # Arrange
    name = "svc/quiet"
    # Act
    result = store.generate(name)
    # Assert
    assert result.value is None


def test_plaintext_is_absent_from_the_encrypted_file(store):
    # Arrange
    store.store("svc/marker", _MARKER)
    # Act
    blob = (store.root / "svc" / "marker.gpg").read_bytes()
    # Assert
    assert _MARKER.encode() not in blob


def test_the_plaintext_search_can_find_the_marker_when_present(store):
    """POSITIVE CONTROL for the test above: the search is discriminating."""
    # Arrange
    store.store("svc/marker", _MARKER)
    blob = (store.root / "svc" / "marker.gpg").read_bytes()
    # Act
    haystack = _MARKER.encode() + blob
    # Assert
    assert _MARKER.encode() in haystack


def test_stored_file_has_no_group_or_other_permissions(store):
    # Arrange
    store.generate("svc/perms")
    # Act
    mode = (store.root / "svc" / "perms.gpg").stat().st_mode & 0o077
    # Assert
    assert mode == 0


def test_list_names_reports_every_stored_secret(store):
    # Arrange
    for name in ("a/one", "a/two", "b/three"):
        store.generate(name)
    # Act
    listed = store.list_names()
    # Assert
    assert set(listed.names) == {"a/one", "a/two", "b/three"}


# --------------------------------------------------- failure has a shape

def test_missing_secret_reports_not_found(store):
    # Arrange
    name = "does/not/exist"
    # Act
    result = store.show(name)
    # Assert
    assert result.code == NOT_FOUND


def test_missing_secret_carries_no_value(store):
    # Arrange
    name = "does/not/exist"
    # Act
    result = store.show(name)
    # Assert
    assert result.value is None


def test_an_existing_secret_is_not_reported_not_found(store):
    """POSITIVE CONTROL: NOT_FOUND distinguishes, rather than always firing."""
    # Arrange
    store.generate("does/exist")
    # Act
    result = store.show("does/exist")
    # Assert
    assert result.code == OK


def test_parent_traversal_name_is_refused(store):
    # Arrange
    name = "../escape"
    # Act
    result = store.show(name)
    # Assert
    assert result.code == INVALID_NAME


def test_absolute_path_name_is_refused(store):
    # Arrange
    name = "/etc/passwd"
    # Act
    result = store.show(name)
    # Assert
    assert result.code == INVALID_NAME


def test_embedded_traversal_name_is_refused(store):
    # Arrange
    name = "a/../../escape"
    # Act
    result = store.show(name)
    # Assert
    assert result.code == INVALID_NAME


def test_a_benign_nested_name_is_accepted(store):
    """POSITIVE CONTROL: the traversal guard is not refusing everything."""
    # Arrange
    name = "a/nested/ok"
    # Act
    result = store.generate(name)
    # Assert
    assert result.code == OK


def test_second_write_to_the_same_name_is_refused(store):
    # Arrange
    store.generate("svc/dup")
    # Act
    result = store.generate("svc/dup")
    # Assert
    assert result.code == ALREADY_EXISTS


def test_overwrite_flag_permits_replacing_a_secret(store):
    # Arrange
    store.generate("svc/dup")
    # Act
    result = store.generate("svc/dup", overwrite=True)
    # Assert
    assert result.code == OK


def test_store_without_a_recipient_is_refused(tmp_path, gpg_home):
    # Arrange
    bare = SecretStore(tmp_path / "norecipient")
    bare.root.mkdir(parents=True)
    # Act
    result = bare.store("x", "y")
    # Assert
    assert result.code == NO_RECIPIENT


def test_a_failing_result_cannot_carry_a_value():
    """The decrypt.sh defect, made structurally impossible to express."""
    # Arrange
    message = "gpg: decryption failed"
    # Act / Assert
    # Assert
    with pytest.raises(ValueError):
        SecretResult(GPG_FAILED, message, value=message)


def test_a_result_without_detail_is_rejected():
    # Arrange
    empty_detail = ""
    # Act
    # Assert
    with pytest.raises(ValueError):
        SecretResult(OK, empty_detail)


# ----------------------------------------------------------------- backup

def test_backup_writes_a_file(store_with_secret, tmp_path):
    # Arrange
    dest = tmp_path / "backup.gpg"
    # Act
    store_with_secret.backup(dest, passphrase="throwaway-passphrase")
    # Assert
    assert dest.is_file()


def test_backup_reports_success(store_with_secret, tmp_path):
    # Arrange
    dest = tmp_path / "backup2.gpg"
    # Act
    result = store_with_secret.backup(dest, passphrase="throwaway-passphrase")
    # Assert
    assert result.code == OK


def test_backup_without_a_passphrase_is_refused(store, tmp_path):
    # Arrange
    dest = tmp_path / "unsafe.gpg"
    # Act
    result = store.backup(dest, passphrase="")
    # Assert
    assert result.code == NO_RECIPIENT


def test_refused_backup_writes_nothing(store, tmp_path):
    # Arrange
    dest = tmp_path / "unsafe2.gpg"
    # Act
    store.backup(dest, passphrase="")
    # Assert
    assert not dest.exists()


def test_backup_with_a_passphrase_succeeds_at_the_same_path(store, tmp_path):
    """POSITIVE CONTROL: the refusal above is about the passphrase, not the path."""
    # Arrange
    dest = tmp_path / "unsafe2.gpg"
    # Act
    result = store.backup(dest, passphrase="pw")
    # Assert
    assert result.code == OK


# -------------------------------------------------------------- generator

def test_generated_values_do_not_collide():
    # Arrange
    draws = 200
    # Act
    values = {generate_value(24) for _ in range(draws)}
    # Assert
    assert len(values) == draws


def test_generated_value_has_the_requested_length():
    # Arrange
    length = 24
    # Act
    value = generate_value(length)
    # Assert
    assert len(value) == length


def test_generator_refuses_a_weak_length():
    # Arrange
    weak = 4
    # Act
    # Assert
    with pytest.raises(ValueError):
        generate_value(weak)


# ---------------------------------------------------------------- restore

@pytest.fixture()
def backed_up(store, tmp_path):
    """A store with three secrets and a backup archive beside it."""
    for name in ("r/one", "r/two", "r/three"):
        store.generate(name)
    archive = tmp_path / "roundtrip.gpg"
    store.backup(archive, passphrase="drill-passphrase")
    return store, archive


def test_restore_reports_success(backed_up, tmp_path):
    # Arrange
    store, archive = backed_up
    # Act
    result = store.restore(archive, passphrase="drill-passphrase", dest=tmp_path / "recovered")
    # Assert
    assert result.code == OK


def test_restore_recovers_every_secret_name(backed_up, tmp_path):
    """The whole point: what went in must come back out."""
    # Arrange
    store, archive = backed_up
    # Act
    result = store.restore(archive, passphrase="drill-passphrase", dest=tmp_path / "recovered2")
    # Assert
    assert set(result.names) == {"r/one", "r/two", "r/three"}


def test_restore_writes_the_store_directory(backed_up, tmp_path):
    # Arrange
    store, archive = backed_up
    dest = tmp_path / "recovered3"
    # Act
    store.restore(archive, passphrase="drill-passphrase", dest=dest)
    # Assert
    assert (dest / "store" / "r" / "one.gpg").is_file()


def test_restore_with_a_wrong_passphrase_fails(backed_up, tmp_path):
    # Arrange
    store, archive = backed_up
    # Act
    result = store.restore(archive, passphrase="not-the-passphrase", dest=tmp_path / "nope")
    # Assert
    assert result.code == GPG_FAILED


def test_restore_without_a_passphrase_is_refused(backed_up, tmp_path):
    # Arrange
    store, archive = backed_up
    # Act
    result = store.restore(archive, passphrase="", dest=tmp_path / "nope2")
    # Assert
    assert result.code == NO_RECIPIENT


def test_restore_refuses_to_overwrite_a_populated_destination(backed_up, tmp_path):
    """A restore drill must never be able to destroy the live store."""
    # Arrange
    store, archive = backed_up
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "already-here.txt").write_text("do not clobber me")
    # Act
    result = store.restore(archive, passphrase="drill-passphrase", dest=occupied)
    # Assert
    assert result.code == ALREADY_EXISTS


def test_restore_leaves_a_populated_destination_untouched(backed_up, tmp_path):
    # Arrange
    store, archive = backed_up
    occupied = tmp_path / "occupied2"
    occupied.mkdir()
    (occupied / "already-here.txt").write_text("do not clobber me")
    # Act
    store.restore(archive, passphrase="drill-passphrase", dest=occupied)
    # Assert
    assert (occupied / "already-here.txt").read_text() == "do not clobber me"


def test_restore_of_a_missing_archive_reports_not_found(store, tmp_path):
    # Arrange
    absent = tmp_path / "never-written.gpg"
    # Act
    result = store.restore(absent, passphrase="x", dest=tmp_path / "nope3")
    # Assert
    assert result.code == NOT_FOUND


# ------------------------------------------------------------------- sync

@pytest.fixture()
def hermetic_git(tmp_path):
    """A git that HAS an identity and reads no configuration from this box.

    ``sync()`` makes a real commit, and git refuses to commit without an
    author. Until 2026-08-12 these tests took whatever identity the machine
    offered — ``~/.gitconfig``, or ``$GIT_AUTHOR_EMAIL`` exported by the
    shell — and there are three ways for that to end. Green on the author's
    box and on the Spartan runners. ``Author identity unknown`` the moment
    CI moved to the scitex-compute nodes, where nothing sets one and the
    hostname carries no domain, so git cannot even guess. And, worst,
    green for the WRONG REASON on a host that merely happens to guess
    successfully — which is why the failure reached CI unseen.

    Who signs a commit in a throwaway ``tmp_path`` repository is not what
    any of these tests assert, so the test STATES an identity instead of
    borrowing one. Supplied the same way as the GNUPGHOME above: real
    environment variables that git really reads, restored on teardown.

    ``GIT_CONFIG_GLOBAL``/``GIT_CONFIG_SYSTEM`` are pointed at a file that
    does not exist — git's documented way to spell "no config file" — so
    the reverse leak is closed too: an ambient ``commit.gpgsign`` wanting
    the operator's real key cannot reach into a throwaway store either.
    """
    absent = tmp_path / "no-such.gitconfig"
    supplied = {
        "GIT_CONFIG_GLOBAL": str(absent),
        "GIT_CONFIG_SYSTEM": str(absent),
        "GIT_AUTHOR_NAME": "SciTeX Test",
        "GIT_AUTHOR_EMAIL": "test@example.invalid",
        "GIT_COMMITTER_NAME": "SciTeX Test",
        "GIT_COMMITTER_EMAIL": "test@example.invalid",
    }
    saved = {key: os.environ.get(key) for key in supplied}
    os.environ.update(supplied)
    try:
        yield
    finally:
        for key, previous in saved.items():
            if previous is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = previous


def test_sync_commits_a_new_store(store, hermetic_git):
    # Arrange
    store.generate("s/one")
    # Act
    result = store.sync()
    # Assert
    assert result.code == OK


def test_sync_creates_a_git_repository(store, hermetic_git):
    # Arrange
    store.generate("s/two")
    # Act
    store.sync()
    # Assert
    assert (store.root / ".git").is_dir()


def test_second_sync_reports_nothing_to_do(store, hermetic_git):
    """POSITIVE CONTROL pairing: the first sync did commit something."""
    # Arrange
    store.generate("s/three")
    store.sync()
    # Act
    result = store.sync()
    # Assert
    assert "nothing to sync" in result.detail


def test_sync_without_a_store_reports_not_found(tmp_path, gpg_home):
    # Arrange
    absent = SecretStore(tmp_path / "no-such-store")
    # Act
    result = absent.sync()
    # Assert
    assert result.code == NOT_FOUND


# ------------------------------------------- malicious archive (tar slip)

@pytest.fixture()
def hostile_archive(tmp_path):
    """A real encrypted archive whose member escapes the destination.

    Built for real — an actual tar with an actual `../` member, actually
    gpg-encrypted — because a hand-waved 'malicious input' fixture proves
    nothing about what the extractor does with one.
    """
    payload = tmp_path / "payload.txt"
    payload.write_text("escaped content")
    raw = tmp_path / "hostile.tar"
    with tarfile.open(raw, "w") as archive:
        archive.add(payload, arcname="../escaped.txt")
    encrypted = tmp_path / "hostile.gpg"
    subprocess.run(
        ["gpg", "--batch", "--yes", "--quiet", "--symmetric", "--cipher-algo",
         "AES256", "--passphrase-fd", "0", "--output", str(encrypted), str(raw)],
        input=b"hostile-pass", capture_output=True, check=False,
    )
    yield encrypted
    # The intermediate tar is removed so a later test cannot accidentally read a
    # hostile archive this fixture left lying in tmp_path.
    raw.unlink(missing_ok=True)


def test_archive_escaping_the_destination_is_rejected(store, hostile_archive, tmp_path):
    # Arrange
    dest = tmp_path / "victim"
    # Act
    result = store.restore(hostile_archive, passphrase="hostile-pass", dest=dest)
    # Assert
    assert result.code == GPG_FAILED


def test_archive_escaping_the_destination_writes_nothing_outside(store, hostile_archive, tmp_path):
    """The consequence that actually matters: no file lands outside dest."""
    # Arrange
    dest = tmp_path / "victim2"
    # Act
    store.restore(hostile_archive, passphrase="hostile-pass", dest=dest)
    # Assert
    assert not (tmp_path / "escaped.txt").exists()


def test_a_benign_archive_still_restores(backed_up, tmp_path):
    """POSITIVE CONTROL: the extraction filter rejects hostile input only."""
    # Arrange
    store, archive = backed_up
    # Act
    result = store.restore(archive, passphrase="drill-passphrase", dest=tmp_path / "benign")
    # Assert
    assert result.code == OK
