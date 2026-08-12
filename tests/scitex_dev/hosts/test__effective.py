"""Unit tests for scitex_dev.hosts._effective.

NOT MOCKED, and deliberately so: these tests run the REAL ``ssh -G`` against
REAL temporary config files. That matters more here than anywhere else in
this package, because the whole premise is that a config file does not tell
you what ssh will do — a fake `ssh -G` would just re-encode our assumption
and prove nothing.

The centrepiece is `test_an_include_above_the_stanza_silently_wins`, which
reconstructs the 2026-08-13 incident exactly: `Include conf.d/*.conf` on line
1 beating a stanza below it. Measured here with OpenSSH 9.6: the included
`10.9.9.9` wins over the later `10.0.0.1`.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scitex_dev.hosts import (
    HostConnectivity,
    HostRecord,
    check_ssh_config,
    effective_config,
    parse_ssh_g,
)

pytestmark = pytest.mark.skipif(
    shutil.which("ssh") is None, reason="ssh is not installed in this environment"
)

_SSH_G_SAMPLE = """\
user ywatanabe
hostname 10.9.9.9
port 22
identitiesonly no
identityfile ~/.ssh/id_rsa
identityfile ~/.ssh/id_ed25519
"""


def _record(name: str, lan: str, identity_file: str | None = None) -> HostRecord:
    return HostRecord(
        name=name,
        kind="compute",
        ssh_alias=name,
        scitex_root="~/.scitex",
        connectivity=HostConnectivity(lan=lan, identity_file=identity_file),
    )


def _config(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "config"
    path.write_text(body)
    path.chmod(0o600)
    return path


def _home_with_keys(tmp_path: Path, *names: str) -> Path:
    home = tmp_path / "home"
    (home / ".ssh").mkdir(parents=True)
    for name in names:
        (home / ".ssh" / name).write_text("not a real key, just a present file\n")
    return home


# -------- parse_ssh_g --------------------------------------------------------


def test_parse_keeps_every_repeated_identityfile():
    """A scalar would silently keep ssh's LOWEST-priority candidate."""
    # Arrange
    # Act
    parsed = parse_ssh_g(_SSH_G_SAMPLE)
    # Assert
    assert parsed["identityfile"] == ["~/.ssh/id_rsa", "~/.ssh/id_ed25519"]


def test_parse_lowercases_keys():
    # Arrange
    # Act
    parsed = parse_ssh_g("HostName 10.0.0.1\n")
    # Assert
    assert parsed["hostname"] == ["10.0.0.1"]


# -------- the 2026-08-13 incident, reproduced --------------------------------


def test_an_include_above_the_stanza_silently_wins(tmp_path):
    """The fault nobody could see by reading the file they believed was live.

    ssh takes the FIRST value it obtains for each keyword and expands an
    Include in place, so the included 10.9.9.9 beats the 10.0.0.1 written
    plainly below it. This is measured, not assumed.
    """
    # Arrange
    included = tmp_path / "conf.d"
    included.mkdir()
    (included / "wrong.conf").write_text("Host myhost\n    HostName 10.9.9.9\n")
    config = _config(
        tmp_path,
        f"Include {included}/*.conf\n\nHost myhost\n    HostName 10.0.0.1\n",
    )
    # Act
    resolved = effective_config("myhost", config_file=config)
    # Assert
    assert resolved["hostname"] == ["10.9.9.9"]


def test_that_drift_is_reported_against_the_registry(tmp_path):
    # Arrange — the registry says .1; the file ssh obeys says .9.9.
    included = tmp_path / "conf.d"
    included.mkdir()
    (included / "wrong.conf").write_text("Host myhost\n    HostName 10.9.9.9\n")
    config = _config(
        tmp_path,
        f"Include {included}/*.conf\n\nHost myhost\n    HostName 10.0.0.1\n",
    )
    home = _home_with_keys(tmp_path, "id_rsa")
    # Act
    report = check_ssh_config(
        [_record("myhost", "10.0.0.1")], config_file=config, home=home
    )
    codes = {f.code for f in report.findings}
    # Assert
    assert "hostname-drift" in codes


def test_a_matching_stanza_reports_no_drift(tmp_path):
    # Arrange
    config = _config(tmp_path, "Host myhost\n    HostName 10.0.0.1\n")
    home = _home_with_keys(tmp_path, "id_rsa")
    # Act
    report = check_ssh_config(
        [_record("myhost", "10.0.0.1")], config_file=config, home=home
    )
    codes = {f.code for f in report.findings}
    # Assert
    assert "hostname-drift" not in codes


# -------- the compute-01 fault: a stanza naming a key that is not there ------


def test_a_stanza_naming_a_missing_key_is_an_error(tmp_path):
    """scitex-compute-01, 2026-08-13. The stanza named ~/.ssh/id_rsa, which
    did not exist, so ssh offered no key and the far end said Permission
    denied — while id_mesh was already authorised there."""
    # Arrange — id_mesh exists; the stanza names id_rsa, which does not.
    config = _config(
        tmp_path,
        "Host myhost\n    HostName 10.0.0.1\n    IdentityFile ~/.ssh/id_rsa\n",
    )
    home = _home_with_keys(tmp_path, "id_mesh")
    # Act
    report = check_ssh_config(
        [_record("myhost", "10.0.0.1")], config_file=config, home=home
    )
    codes = {f.code for f in report.findings}
    # Assert
    assert "missing-identity-file" in codes


def test_that_finding_is_an_error_not_a_warning(tmp_path):
    # Arrange
    config = _config(
        tmp_path,
        "Host myhost\n    HostName 10.0.0.1\n    IdentityFile ~/.ssh/id_rsa\n",
    )
    home = _home_with_keys(tmp_path, "id_mesh")
    # Act
    report = check_ssh_config(
        [_record("myhost", "10.0.0.1")], config_file=config, home=home
    )
    missing = [f for f in report.findings if f.code == "missing-identity-file"]
    # Assert
    assert missing[0].severity == "error"


def test_a_stanza_naming_a_present_key_is_clean(tmp_path):
    # Arrange
    config = _config(
        tmp_path,
        "Host myhost\n    HostName 10.0.0.1\n    IdentityFile ~/.ssh/id_mesh\n",
    )
    home = _home_with_keys(tmp_path, "id_mesh")
    # Act
    report = check_ssh_config(
        [_record("myhost", "10.0.0.1", "~/.ssh/id_mesh")],
        config_file=config,
        home=home,
    )
    # Assert
    assert report.verdict == "pass"


def test_a_declared_key_that_shares_a_default_name_is_still_caught(tmp_path):
    """The trap that broke the first implementation, pinned.

    compute-01's stanza named `~/.ssh/id_rsa` — which is ALSO one of ssh's
    seven built-in candidates. Classifying declared keys by SUBTRACTING the
    default set erases exactly this case and reports nothing wrong. The
    working discriminator is REPLACEMENT: a stanza that declares any
    IdentityFile makes `ssh -G` report only the declared ones (1 line here,
    7 when nothing is declared), so the list simply differs from the
    built-in set.
    """
    # Arrange
    config = _config(
        tmp_path,
        "Host myhost\n    HostName 10.0.0.1\n    IdentityFile ~/.ssh/id_rsa\n",
    )
    home = _home_with_keys(tmp_path, "id_mesh")
    # Act
    report = check_ssh_config(
        [_record("myhost", "10.0.0.1")], config_file=config, home=home
    )
    # Assert
    assert report.checks[0].declared_identity_files == ("~/.ssh/id_rsa",)


def test_ssh_builtin_default_keys_are_not_reported_as_declared(tmp_path):
    """ssh -G always lists ~/.ssh/id_rsa, id_ecdsa, id_ed25519 ... whether or
    not any config mentioned them, and most legitimately do not exist.
    Flagging all seven would bury the one that matters, so the baseline is
    MEASURED from a sentinel name rather than hardcoded."""
    # Arrange — a stanza that declares NO IdentityFile at all.
    config = _config(tmp_path, "Host myhost\n    HostName 10.0.0.1\n")
    home = _home_with_keys(tmp_path, "id_rsa")
    # Act
    report = check_ssh_config(
        [_record("myhost", "10.0.0.1")], config_file=config, home=home
    )
    # Assert
    assert report.checks[0].declared_identity_files == ()


def test_a_declared_key_is_separated_from_the_defaults(tmp_path):
    # Arrange
    config = _config(
        tmp_path,
        "Host myhost\n    HostName 10.0.0.1\n    IdentityFile ~/.ssh/id_mesh\n",
    )
    home = _home_with_keys(tmp_path, "id_mesh")
    # Act
    report = check_ssh_config(
        [_record("myhost", "10.0.0.1")], config_file=config, home=home
    )
    # Assert
    assert report.checks[0].declared_identity_files == ("~/.ssh/id_mesh",)


def test_no_usable_key_at_all_is_its_own_finding(tmp_path):
    # Arrange — an empty home: not one of ssh's candidates exists.
    config = _config(tmp_path, "Host myhost\n    HostName 10.0.0.1\n")
    home = _home_with_keys(tmp_path)
    # Act
    report = check_ssh_config(
        [_record("myhost", "10.0.0.1")], config_file=config, home=home
    )
    codes = {f.code for f in report.findings}
    # Assert
    assert "no-key-offered" in codes


# -------- an unanswered check is never a pass --------------------------------


def test_an_unresolvable_alias_is_not_counted_as_checked(tmp_path):
    # Arrange — a config file ssh cannot read at all.
    home = _home_with_keys(tmp_path, "id_rsa")
    # Act
    report = check_ssh_config(
        [_record("myhost", "10.0.0.1")],
        config_file=tmp_path / "does-not-exist",
        home=home,
    )
    # Assert
    assert report.checked == 0


def test_an_unresolvable_alias_makes_the_verdict_incomplete(tmp_path):
    """'No finding' from a check that did not run is not a pass."""
    # Arrange
    home = _home_with_keys(tmp_path, "id_rsa")
    # Act
    report = check_ssh_config(
        [_record("myhost", "10.0.0.1")],
        config_file=tmp_path / "does-not-exist",
        home=home,
    )
    # Assert
    assert report.verdict == "incomplete"


def test_the_summary_names_how_many_of_how_many_resolved(tmp_path):
    # Arrange
    config = _config(tmp_path, "Host myhost\n    HostName 10.0.0.1\n")
    home = _home_with_keys(tmp_path, "id_rsa")
    # Act
    report = check_ssh_config(
        [_record("myhost", "10.0.0.1")], config_file=config, home=home
    )
    # Assert
    assert "1/1 aliases resolved" in report.summary_line()


# EOF
