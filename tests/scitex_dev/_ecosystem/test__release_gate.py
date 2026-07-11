#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the `ecosystem validate-versions --gate` release-gate mechanism.

Synthetic fixtures: pip-version readers injected via the public
``remote_version_fn`` seam on ``check_release_gate`` / ``collect_gate_state``
— no real SSH calls, no mocks. Mirrors the existing
``tests/scitex_dev/_ecosystem/test__packages.py`` seam-injection pattern.
"""

from __future__ import annotations

import pytest

pytest.importorskip("click")

from scitex_dev._core.config import DevConfig, HostConfig, PackageConfig
from scitex_dev._ecosystem._release_gate import (
    _version_gte,
    _version_tuple,
    check_release_gate,
    collect_gate_state,
    gate_summary,
)


@pytest.fixture
def fake_config(tmp_path) -> DevConfig:
    """One tracked package (scitex-todo), three hosts."""
    pkg_path = tmp_path / "scitex-todo"
    pkg_path.mkdir()

    return DevConfig(
        packages=[
            PackageConfig(
                name="scitex-todo",
                local_path=str(pkg_path),
                pypi_name="scitex-todo",
                github_repo="scitex-ai/scitex-todo",
            ),
        ],
        hosts=[
            HostConfig(name="nas", hostname="nas", user="x", enabled=True),
            HostConfig(name="spartan", hostname="spartan", user="x", enabled=True),
            HostConfig(name="mba", hostname="mba", user="x", enabled=True),
        ],
    )


def _version_fn(version_map):
    """Build a remote_version_fn from a {host_name: version|None} map."""
    return lambda host, pypi_name: version_map.get(host.name)


# ── pure version-compare helpers ────────────────────────────────────────────


def test_version_tuple_parses_dotted_numeric():
    # Arrange
    text = "0.7.51"
    # Act
    result = _version_tuple(text)
    # Assert
    assert result == (0, 7, 51)


def test_version_tuple_stops_at_nonnumeric_trailer():
    # Arrange
    text = "1.2.0rc1"
    # Act
    result = _version_tuple(text)
    # Assert
    assert result == (1, 2, 0)


def test_version_tuple_empty_on_none():
    # Arrange
    text = None
    # Act
    result = _version_tuple(text)
    # Assert
    assert result == ()


def test_version_gte_true_when_equal():
    # Arrange
    installed, minimum = "0.7.51", "0.7.51"
    # Act
    result = _version_gte(installed, minimum)
    # Assert
    assert result is True


def test_version_gte_true_when_greater():
    # Arrange
    installed, minimum = "0.8.0", "0.7.51"
    # Act
    result = _version_gte(installed, minimum)
    # Assert
    assert result is True


def test_version_gte_false_when_lesser():
    # Arrange
    installed, minimum = "0.7.40", "0.7.51"
    # Act
    result = _version_gte(installed, minimum)
    # Assert
    assert result is False


def test_version_gte_false_when_installed_is_none():
    # Arrange
    installed, minimum = None, "0.7.51"
    # Act
    result = _version_gte(installed, minimum)
    # Assert
    assert result is False


# ── collect_gate_state: scoping ─────────────────────────────────────────────


def test_collect_gate_state_includes_all_hosts_when_no_allowlist(fake_config):
    """No host.packages allow-list -> every enabled host is in scope."""
    # Arrange
    versions = {"nas": "0.7.51", "spartan": "0.7.51", "mba": "0.7.51"}
    # Act
    state = collect_gate_state(
        "scitex-todo",
        "0.7.51",
        config=fake_config,
        remote_version_fn=_version_fn(versions),
    )
    # Assert
    assert {r["host"] for r in state["rows"]} == {"nas", "spartan", "mba"}


def test_collect_gate_state_excludes_host_missing_package_from_allowlist(
    fake_config,
):
    """A host whose allow-list omits the package is NOT in scope (not FAIL)."""
    # Arrange
    fake_config.hosts[1].packages = ["some-other-package"]  # spartan excludes it
    versions = {"nas": "0.7.51", "mba": "0.7.51"}
    # Act
    state = collect_gate_state(
        "scitex-todo",
        "0.7.51",
        config=fake_config,
        remote_version_fn=_version_fn(versions),
    )
    # Assert
    assert "spartan" not in {r["host"] for r in state["rows"]}


def test_collect_gate_state_resolves_pypi_name_from_package_config(fake_config):
    # Arrange
    # (fake_config already declares scitex-todo's pypi_name == "scitex-todo")
    # Act
    state = collect_gate_state(
        "scitex-todo",
        "0.7.51",
        config=fake_config,
        remote_version_fn=_version_fn({}),
    )
    # Assert
    assert state["pypi_name"] == "scitex-todo"


# ── gate_summary / check_release_gate: pass case ────────────────────────────


def test_gate_passes_when_every_host_meets_version(fake_config):
    # Arrange
    versions = {"nas": "0.7.51", "spartan": "0.7.52", "mba": "0.8.0"}
    # Act
    result = check_release_gate(
        "scitex-todo",
        "0.7.51",
        config=fake_config,
        remote_version_fn=_version_fn(versions),
    )
    # Assert
    assert result["passed"] is True


def test_gate_pass_case_summary_coverage_is_100(fake_config):
    # Arrange
    versions = {"nas": "0.7.51", "spartan": "0.7.52", "mba": "0.8.0"}
    # Act
    result = check_release_gate(
        "scitex-todo",
        "0.7.51",
        config=fake_config,
        remote_version_fn=_version_fn(versions),
    )
    # Assert
    assert result["summary"]["coverage_pct"] == 100.0


def test_gate_pass_case_not_covered_is_empty(fake_config):
    # Arrange
    versions = {"nas": "0.7.51", "spartan": "0.7.52", "mba": "0.8.0"}
    # Act
    result = check_release_gate(
        "scitex-todo",
        "0.7.51",
        config=fake_config,
        remote_version_fn=_version_fn(versions),
    )
    # Assert
    assert result["summary"]["not_covered"] == []


# ── gate_summary / check_release_gate: fail case ────────────────────────────


def test_gate_fails_when_one_host_is_behind(fake_config):
    # Arrange — mba is on the old build, pre-tolerant-reader.
    versions = {"nas": "0.7.51", "spartan": "0.7.51", "mba": "0.7.40"}
    # Act
    result = check_release_gate(
        "scitex-todo",
        "0.7.51",
        config=fake_config,
        remote_version_fn=_version_fn(versions),
    )
    # Assert
    assert result["passed"] is False


def test_gate_fail_case_not_covered_lists_the_lagging_host(fake_config):
    # Arrange
    versions = {"nas": "0.7.51", "spartan": "0.7.51", "mba": "0.7.40"}
    # Act
    result = check_release_gate(
        "scitex-todo",
        "0.7.51",
        config=fake_config,
        remote_version_fn=_version_fn(versions),
    )
    # Assert
    assert result["summary"]["not_covered"] == ["mba"]


def test_gate_fail_case_coverage_pct_below_100(fake_config):
    # Arrange
    versions = {"nas": "0.7.51", "spartan": "0.7.51", "mba": "0.7.40"}
    # Act
    result = check_release_gate(
        "scitex-todo",
        "0.7.51",
        config=fake_config,
        remote_version_fn=_version_fn(versions),
    )
    # Assert
    assert result["summary"]["coverage_pct"] < 100.0


def test_gate_fails_when_host_unreachable_installed_is_none(fake_config):
    """Unreachable / not-installed hosts (None) fail the gate — fail-safe."""
    # Arrange
    versions = {"nas": "0.7.51", "spartan": "0.7.51", "mba": None}
    # Act
    result = check_release_gate(
        "scitex-todo",
        "0.7.51",
        config=fake_config,
        remote_version_fn=_version_fn(versions),
    )
    # Assert
    assert result["passed"] is False


# ── empty in-scope set: fail-safe, never silently green-light ──────────────


def test_gate_fails_when_no_host_tracks_the_package(fake_config):
    """No host's allow-list includes the package -> passed must be False."""
    # Arrange — every host explicitly excludes scitex-todo.
    for h in fake_config.hosts:
        h.packages = ["some-other-package"]
    # Act
    result = check_release_gate(
        "scitex-todo",
        "0.7.51",
        config=fake_config,
        remote_version_fn=_version_fn({}),
    )
    # Assert
    assert result["passed"] is False


def test_gate_fails_when_no_host_tracks_the_package_total_hosts_zero(fake_config):
    # Arrange
    for h in fake_config.hosts:
        h.packages = ["some-other-package"]
    # Act
    result = check_release_gate(
        "scitex-todo",
        "0.7.51",
        config=fake_config,
        remote_version_fn=_version_fn({}),
    )
    # Assert
    assert result["summary"]["total_hosts"] == 0


# ── host filter ──────────────────────────────────────────────────────────


def test_gate_respects_explicit_host_filter(fake_config):
    # Arrange
    versions = {"nas": "0.7.51", "spartan": "0.1.0", "mba": "0.7.51"}
    # Act — only ask about nas and mba; spartan's low version must not count.
    result = check_release_gate(
        "scitex-todo",
        "0.7.51",
        hosts=["nas", "mba"],
        config=fake_config,
        remote_version_fn=_version_fn(versions),
    )
    # Assert
    assert result["passed"] is True


# ── gate_summary as a standalone function ──────────────────────────────────


def test_gate_summary_covered_count():
    # Arrange
    state = {
        "rows": [
            {"host": "a", "installed": "1.0.0", "meets": True},
            {"host": "b", "installed": "0.9.0", "meets": False},
        ]
    }
    # Act
    summ = gate_summary(state)
    # Assert
    assert summ["covered"] == 1


def test_gate_summary_not_covered_list():
    # Arrange
    state = {
        "rows": [
            {"host": "a", "installed": "1.0.0", "meets": True},
            {"host": "b", "installed": "0.9.0", "meets": False},
        ]
    }
    # Act
    summ = gate_summary(state)
    # Assert
    assert summ["not_covered"] == ["b"]


# EOF
