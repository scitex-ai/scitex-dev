"""Unit tests for scitex_dev.hosts._registry.

Covers: resolve()/list_hosts() against a real temp hosts.yaml (never the
real ~/.scitex), unknown-host actionable error, malformed-YAML/invalid-
kind/missing-field errors, and first-use auto-seeding.

No mocks (NM001-003) — real temp files via `hosts_path=`; env-var tests
use a yield-based fixture that sets/restores the real `os.environ`
(never `monkeypatch`). One assert per test (02_package/13_test-quality.md).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from scitex_dev.hosts import (
    HOST_KINDS,
    HostRecord,
    HostRegistryError,
    UnknownHostError,
    create_default_hosts_yaml,
    list_hosts,
    resolve,
)

_ONE_HOST_YAML = """\
hosts:
  spartan:
    kind: hpc-login
    ssh_alias: spartan
    scitex_root: "/data/gpfs/projects/punim0264/ywatanabe/.scitex"
"""

_TWO_HOST_YAML = """\
hosts:
  mba:
    kind: workstation
    ssh_alias: mba
    scitex_root: "~/.scitex"
  nas:
    kind: storage
    ssh_alias: nas
    scitex_root: "~/.scitex"
"""

_ENV_VAR = "SCITEX_DEV_HOSTS_YAML"


def _write(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "hosts.yaml"
    p.write_text(content)
    return p


@pytest.fixture
def hosts_yaml_env():
    """Yield a setter for `$SCITEX_DEV_HOSTS_YAML`; restores it on exit."""
    saved = os.environ.get(_ENV_VAR)

    def _set(path) -> None:
        os.environ[_ENV_VAR] = str(path)

    try:
        yield _set
    finally:
        if saved is None:
            os.environ.pop(_ENV_VAR, None)
        else:
            os.environ[_ENV_VAR] = saved


# -------- resolve() -------------------------------------------------------


def test_resolve_known_host_returns_host_record(tmp_path):
    # Arrange
    p = _write(tmp_path, _ONE_HOST_YAML)
    # Act
    record = resolve("spartan", hosts_path=p)
    # Assert
    assert isinstance(record, HostRecord)


def test_resolve_known_host_name_matches(tmp_path):
    # Arrange
    p = _write(tmp_path, _ONE_HOST_YAML)
    # Act
    record = resolve("spartan", hosts_path=p)
    # Assert
    assert record.name == "spartan"


def test_resolve_known_host_kind_matches(tmp_path):
    # Arrange
    p = _write(tmp_path, _ONE_HOST_YAML)
    # Act
    record = resolve("spartan", hosts_path=p)
    # Assert
    assert record.kind == "hpc-login"


def test_resolve_known_host_ssh_alias_matches(tmp_path):
    # Arrange
    p = _write(tmp_path, _ONE_HOST_YAML)
    # Act
    record = resolve("spartan", hosts_path=p)
    # Assert
    assert record.ssh_alias == "spartan"


def test_resolve_known_host_scitex_root_matches(tmp_path):
    # Arrange
    p = _write(tmp_path, _ONE_HOST_YAML)
    # Act
    record = resolve("spartan", hosts_path=p)
    # Assert
    assert record.scitex_root == "/data/gpfs/projects/punim0264/ywatanabe/.scitex"


def test_resolve_local_host_ssh_alias_is_none(tmp_path):
    # Arrange
    yaml_text = (
        "hosts:\n"
        "  ywata-note-win:\n"
        "    kind: workstation\n"
        "    ssh_alias: null\n"
        '    scitex_root: "~/.scitex"\n'
    )
    p = _write(tmp_path, yaml_text)
    # Act
    record = resolve("ywata-note-win", hosts_path=p)
    # Assert
    assert record.ssh_alias is None


def test_resolve_unknown_host_raises_unknown_host_error(tmp_path):
    # Arrange
    p = _write(tmp_path, _ONE_HOST_YAML)
    # Act
    # Assert
    with pytest.raises(UnknownHostError):
        resolve("nonexistent-host", hosts_path=p)


def _resolve_and_capture_unknown_host_error(name: str, hosts_path: Path) -> UnknownHostError:
    """Resolve ``name`` and return the raised UnknownHostError.

    Deliberately NOT `pytest.raises` — that context manager itself
    counts as one assertion (STX-TQ007), so a test that both wraps a
    call in `pytest.raises` AND asserts on `excinfo.value` trips the
    one-assert-per-test rule. Capturing manually here keeps each
    caller test down to exactly one `assert`.
    """
    try:
        resolve(name, hosts_path=hosts_path)
    except UnknownHostError as exc:
        return exc
    raise AssertionError("expected UnknownHostError, none was raised")  # pragma: no cover


def test_resolve_unknown_host_error_lists_known_hosts(tmp_path):
    # Arrange
    p = _write(tmp_path, _TWO_HOST_YAML)
    # Act
    exc = _resolve_and_capture_unknown_host_error("nonexistent-host", p)
    # Assert
    assert "mba" in str(exc)


def test_resolve_unknown_host_error_lists_second_known_host(tmp_path):
    # Arrange
    p = _write(tmp_path, _TWO_HOST_YAML)
    # Act
    exc = _resolve_and_capture_unknown_host_error("nonexistent-host", p)
    # Assert
    assert "nas" in str(exc)


def test_resolve_unknown_host_error_has_remediation(tmp_path):
    # Arrange
    p = _write(tmp_path, _ONE_HOST_YAML)
    # Act
    exc = _resolve_and_capture_unknown_host_error("nonexistent-host", p)
    # Assert
    assert exc.remediation


def test_resolve_unknown_host_error_carries_hosts_path(tmp_path):
    # Arrange
    p = _write(tmp_path, _ONE_HOST_YAML)
    # Act
    exc = _resolve_and_capture_unknown_host_error("nonexistent-host", p)
    # Assert
    assert exc.hosts_path == p


# -------- list_hosts() -----------------------------------------------------


def test_list_hosts_returns_all_entries(tmp_path):
    # Arrange
    p = _write(tmp_path, _TWO_HOST_YAML)
    # Act
    records = list_hosts(hosts_path=p)
    # Assert
    assert len(records) == 2


def test_list_hosts_sorted_by_name(tmp_path):
    # Arrange
    p = _write(tmp_path, _TWO_HOST_YAML)
    # Act
    records = list_hosts(hosts_path=p)
    # Assert
    assert [r.name for r in records] == ["mba", "nas"]


def test_list_hosts_empty_registry_returns_empty_list(tmp_path):
    # Arrange
    p = _write(tmp_path, "hosts: {}\n")
    # Act
    records = list_hosts(hosts_path=p)
    # Assert
    assert records == []


# -------- malformed YAML / validation --------------------------------------


def test_load_invalid_yaml_raises_host_registry_error(tmp_path):
    # Arrange
    p = _write(tmp_path, "hosts: [this is not, a mapping\n")
    # Act
    # Assert
    with pytest.raises(HostRegistryError):
        list_hosts(hosts_path=p)


def test_invalid_kind_raises_host_registry_error(tmp_path):
    # Arrange
    yaml_text = (
        "hosts:\n"
        "  bad-host:\n"
        "    kind: not-a-real-kind\n"
        "    ssh_alias: null\n"
        '    scitex_root: "~/.scitex"\n'
    )
    p = _write(tmp_path, yaml_text)
    # Act
    # Assert
    with pytest.raises(HostRegistryError):
        resolve("bad-host", hosts_path=p)


def test_missing_kind_field_raises_host_registry_error(tmp_path):
    # Arrange
    yaml_text = (
        "hosts:\n  bad-host:\n    ssh_alias: null\n    scitex_root: \"~/.scitex\"\n"
    )
    p = _write(tmp_path, yaml_text)
    # Act
    # Assert
    with pytest.raises(HostRegistryError):
        resolve("bad-host", hosts_path=p)


def test_missing_scitex_root_field_raises_host_registry_error(tmp_path):
    # Arrange
    yaml_text = "hosts:\n  bad-host:\n    kind: workstation\n    ssh_alias: null\n"
    p = _write(tmp_path, yaml_text)
    # Act
    # Assert
    with pytest.raises(HostRegistryError):
        resolve("bad-host", hosts_path=p)


def test_host_entry_not_a_mapping_raises_host_registry_error(tmp_path):
    # Arrange
    yaml_text = "hosts:\n  bad-host: just-a-string\n"
    p = _write(tmp_path, yaml_text)
    # Act
    # Assert
    with pytest.raises(HostRegistryError):
        resolve("bad-host", hosts_path=p)


def test_hosts_key_not_a_mapping_raises_host_registry_error(tmp_path):
    # Arrange
    p = _write(tmp_path, "hosts: not-a-mapping\n")
    # Act
    # Assert
    with pytest.raises(HostRegistryError):
        list_hosts(hosts_path=p)


def test_host_record_direct_construction_validates_kind():
    # Arrange
    # Act
    # Assert
    with pytest.raises(HostRegistryError):
        HostRecord(name="x", kind="not-a-kind", ssh_alias=None, scitex_root="~/.scitex")


# -------- HOST_KINDS closed set ---------------------------------------------


def test_host_kinds_is_exactly_the_three_documented_values():
    # Arrange
    # Act
    # Assert
    assert HOST_KINDS == frozenset({"workstation", "hpc-login", "storage"})


# -------- scitex_root_path expansion ----------------------------------------


def test_scitex_root_path_expands_tilde():
    # Arrange
    record = HostRecord(name="x", kind="workstation", ssh_alias=None, scitex_root="~/.scitex")
    # Act
    expanded = record.scitex_root_path
    # Assert
    assert expanded == Path.home() / ".scitex"


def test_scitex_root_path_leaves_absolute_path_unchanged():
    # Arrange
    record = HostRecord(
        name="spartan",
        kind="hpc-login",
        ssh_alias="spartan",
        scitex_root="/data/gpfs/projects/punim0264/ywatanabe/.scitex",
    )
    # Act
    expanded = record.scitex_root_path
    # Assert
    assert str(expanded) == "/data/gpfs/projects/punim0264/ywatanabe/.scitex"


# -------- to_dict() ----------------------------------------------------------


def test_to_dict_round_trips_all_fields():
    # Arrange
    record = HostRecord(name="mba", kind="workstation", ssh_alias="mba", scitex_root="~/.scitex")
    # Act
    payload = record.to_dict()
    # Assert
    assert payload == {
        "name": "mba",
        "kind": "workstation",
        "ssh_alias": "mba",
        "scitex_root": "~/.scitex",
    }


# -------- create_default_hosts_yaml() / first-use seeding -------------------


def test_create_default_hosts_yaml_creates_file(tmp_path):
    # Arrange
    target = tmp_path / "nested" / "hosts.yaml"
    # Act
    create_default_hosts_yaml(target)
    # Assert
    assert target.is_file()


def test_create_default_hosts_yaml_is_idempotent(tmp_path):
    # Arrange
    target = tmp_path / "hosts.yaml"
    create_default_hosts_yaml(target)
    target.write_text("hosts: {}\n")  # simulate a user edit
    # Act
    create_default_hosts_yaml(target)  # must NOT overwrite
    # Assert
    assert target.read_text() == "hosts: {}\n"


def test_resolve_auto_seeds_on_first_use(tmp_path):
    # Arrange
    target = tmp_path / "hosts.yaml"
    # Act
    record = resolve("spartan", hosts_path=target)
    # Assert
    assert record.name == "spartan"


def test_resolve_auto_seeds_writes_file_to_disk(tmp_path):
    # Arrange
    target = tmp_path / "hosts.yaml"
    # Act
    resolve("spartan", hosts_path=target)
    # Assert
    assert target.is_file()


def test_list_hosts_auto_seeds_default_six_hosts(tmp_path):
    # Arrange
    target = tmp_path / "hosts.yaml"
    # Act
    records = list_hosts(hosts_path=target)
    # Assert
    assert len(records) == 6


def test_default_seed_includes_operator_known_hosts(tmp_path):
    # Arrange
    target = tmp_path / "hosts.yaml"
    # Act
    records = list_hosts(hosts_path=target)
    # Assert
    assert {r.name for r in records} == {
        "ywata-note-win",
        "spartan",
        "nas",
        "nas1",
        "nas2",
        "mba",
    }


# -------- path precedence: explicit arg wins ---------------------------------


def test_explicit_hosts_path_overrides_env_var(tmp_path, hosts_yaml_env):
    # Arrange
    explicit_dir = tmp_path / "explicit"
    explicit_dir.mkdir()
    explicit = _write(explicit_dir, _ONE_HOST_YAML)
    env_dir = tmp_path / "envvar"
    env_dir.mkdir()
    env_path = _write(env_dir, _TWO_HOST_YAML)
    hosts_yaml_env(env_path)
    # Act
    record = resolve("spartan", hosts_path=explicit)
    # Assert
    assert record.name == "spartan"


def test_env_var_used_when_no_explicit_path(tmp_path, hosts_yaml_env):
    # Arrange
    env_path = _write(tmp_path, _ONE_HOST_YAML)
    hosts_yaml_env(env_path)
    # Act
    record = resolve("spartan")
    # Assert
    assert record.name == "spartan"


# EOF
