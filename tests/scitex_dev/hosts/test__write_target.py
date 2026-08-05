# -*- coding: utf-8 -*-
"""A write to `hosts.yaml` must REFUSE when it cannot tell which registry
the fleet reads.

The failure being pinned is silent: `get_hosts_yaml_path()` resolves through
`Path.home()`, which inside an agent container is `/home/agent`, so a write
lands in a private copy no host-side reader opens while every layer reports
success. Measured 2026-08-05 with `sac host add` — `validate` then said "ok,
2 peer(s)" about the shadow.

No mocks (STX-NM002): every case builds REAL home directories with REAL
registry files under `tmp_path` and passes that root in as a PARAMETER.
Nothing patches module internals — the first draft of this suite did, and the
linter was right to reject it: a test that only passes because it rewrote
production internals is not testing production. The env var is set and popped
by a `yield` fixture on the real `os.environ`.

One assert per test (STX-TQ007), Arrange/Act/Assert markers (STX-TQ002).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from scitex_dev.hosts import HostRegistryError
from scitex_dev.hosts._write_target import (
    _ENV_HOSTS_YAML,
    candidate_hosts_yamls,
    resolve_hosts_yaml_for_write,
)

_REGISTRY = "hosts:\n  spartan:\n    kind: hpc-login\n    ssh_alias: spartan\n"


def _make_home(root: Path, user: str, body: str = _REGISTRY) -> Path:
    """A real home dir carrying a real `.scitex/dev/hosts.yaml`."""
    path = root / user / ".scitex" / "dev" / "hosts.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


@pytest.fixture
def no_env_override():
    """Guarantee the deployment has NOT stated a target, and restore after.

    Real `os.environ`, saved and put back — the ambiguity tests are only
    meaningful when nothing has already settled the question.
    """
    saved = os.environ.pop(_ENV_HOSTS_YAML, None)
    yield
    if saved is not None:
        os.environ[_ENV_HOSTS_YAML] = saved


@pytest.fixture
def env_override():
    """Set `$SCITEX_DEV_HOSTS_YAML` to a caller-supplied path, then restore."""
    saved = os.environ.pop(_ENV_HOSTS_YAML, None)
    applied: list[str] = []

    def _apply(path: Path) -> Path:
        os.environ[_ENV_HOSTS_YAML] = str(path)
        applied.append(str(path))
        return path

    yield _apply
    os.environ.pop(_ENV_HOSTS_YAML, None)
    if saved is not None:
        os.environ[_ENV_HOSTS_YAML] = saved


@pytest.fixture
def two_homes(tmp_path) -> Path:
    """An agent container: the operator's home AND the container's own."""
    root = tmp_path / "home"
    root.mkdir()
    _make_home(root, "ywatanabe")
    _make_home(root, "agent")
    return root


@pytest.fixture
def refusal_message(two_homes, no_env_override) -> str:
    """The text of the refusal raised on an ambiguous root."""
    with pytest.raises(HostRegistryError) as excinfo:
        resolve_hosts_yaml_for_write(homes_root=two_homes)
    return str(excinfo.value)


# -------- one registry, or none: unambiguous, the write proceeds -----------


def test_single_registry_is_not_refused(tmp_path, env_override):
    # Arrange — the operator's own machine: one home, one registry.
    root = tmp_path / "home"
    root.mkdir()
    target = _make_home(root, "ywatanabe")
    env_override(target)
    # Act
    resolved = resolve_hosts_yaml_for_write(homes_root=root)
    # Assert
    assert resolved == target


def test_no_registry_anywhere_yields_no_candidates(tmp_path):
    # Arrange — nothing exists yet; first-run seeding must not be blocked.
    root = tmp_path / "home"
    root.mkdir()
    # Act
    candidates = candidate_hosts_yamls(homes_root=root)
    # Assert
    assert candidates == []


def test_home_without_a_registry_is_not_a_candidate(tmp_path):
    # Arrange — somewhere a registry COULD go is not somewhere the fleet
    # reads. Counting empty homes would refuse writes on ordinary machines.
    root = tmp_path / "home"
    root.mkdir()
    _make_home(root, "ywatanabe")
    (root / "someone-else").mkdir()
    # Act
    candidates = candidate_hosts_yamls(homes_root=root)
    # Assert
    assert len(candidates) == 1


# -------- two registries: the container shadow, and it REFUSES -------------


def test_two_visible_registries_refuse_the_write(two_homes, no_env_override):
    # Arrange — both mounted, nothing says which is canonical.
    root = two_homes
    # Act / Assert — `pytest.raises` IS the assertion (STX-TQ007).
    # Assert
    with pytest.raises(HostRegistryError):
        resolve_hosts_yaml_for_write(homes_root=root)


def test_identical_fixture_really_is_byte_identical(two_homes):
    """THE CONTROL for the test below.

    The two live files were md5-identical, which is why this survived eleven
    days: every CONTENT check agreed. Without this control the refusal test
    could pass because the fixture differed, proving nothing about the case
    that actually occurred.
    """
    # Arrange
    left, right = candidate_hosts_yamls(homes_root=two_homes)
    # Act
    identical = left.read_bytes() == right.read_bytes()
    # Assert
    assert identical


def test_byte_identical_registries_still_refuse(two_homes, no_env_override):
    # Arrange — content agrees (pinned by the control above); only IDENTITY
    # distinguishes these. A detector comparing content would pass here and
    # license the exact write that was reported as success.
    root = two_homes
    # Act
    # Assert
    with pytest.raises(HostRegistryError):
        resolve_hosts_yaml_for_write(homes_root=root)


def test_refusal_names_the_shadow_candidate(refusal_message):
    # Arrange — an error that only says "ambiguous" leaves the reader where
    # they started; the paths are the actionable part.
    message = refusal_message
    # Act
    names_shadow = "agent" in message
    # Assert
    assert names_shadow


def test_refusal_names_the_canonical_candidate(refusal_message):
    # Arrange
    message = refusal_message
    # Act
    names_canonical = "ywatanabe" in message
    # Assert
    assert names_canonical


def test_refusal_names_the_variable_that_settles_it(refusal_message):
    # Arrange
    message = refusal_message
    # Act
    names_var = _ENV_HOSTS_YAML in message
    # Assert
    assert names_var


def test_refusal_says_where_a_containerized_agent_should_write_instead(
    refusal_message,
):
    """The refusal blocks EVERY containerized agent from the default path.

    That is intended, but it means the work must MOVE rather than stop. An
    error that only refuses sends the reader to the operator's shell, which
    is the thing this whole effort exists to avoid — so the remedy has to
    name the bare host, where only one registry is visible and the same rule
    permits the write.
    """
    # Arrange — assert on "bare host", NOT on "host". The refusal already
    # contains the word "host" in "host registry", so the looser check would
    # pass against the message that lacks the remedy entirely — a control
    # that cannot distinguish the fixed text from the broken one.
    message = refusal_message
    # Act
    names_host_route = "bare host" in message.lower()
    # Assert
    assert names_host_route


# -------- an explicit answer always wins over the guessing -----------------


def test_env_override_wins_over_ambiguity(two_homes, env_override):
    # Arrange — a deployment that has been TOLD where the registry lives is
    # not ambiguous, however many files happen to be visible.
    chosen = env_override(two_homes / "ywatanabe" / ".scitex" / "dev" / "hosts.yaml")
    # Act
    resolved = resolve_hosts_yaml_for_write(homes_root=two_homes)
    # Assert
    assert resolved == chosen


def test_explicit_argument_wins_over_ambiguity(two_homes, tmp_path, no_env_override):
    # Arrange — the caller has stated the target; scripted callers must not
    # be blocked by what else happens to be mounted.
    chosen = tmp_path / "explicit.yaml"
    # Act
    resolved = resolve_hosts_yaml_for_write(chosen, homes_root=two_homes)
    # Assert
    assert resolved == chosen

# EOF
