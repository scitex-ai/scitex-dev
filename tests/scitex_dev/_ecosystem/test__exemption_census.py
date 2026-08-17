#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/scitex_dev/_ecosystem/test__exemption_census.py

"""Tests for :mod:`scitex_dev._ecosystem._exemption_census`.

The load-bearing tests are the ones asserting that an UNREADABLE package
lands in `unreadable` rather than in `clean`. A census that silently skips
what it cannot read reports a smaller number than the truth, and reports it
in the reassuring direction — which is the failure this module exists to
avoid, so it is the failure that must be pinned.

Real temp trees and a real `load_config` stand-in; nothing patched.
"""

from __future__ import annotations

from dataclasses import dataclass

from scitex_dev._ecosystem._exemption_census import (
    ExemptionCensus,
    collect_exemptions,
)


@dataclass(frozen=True)
class _Exemption:
    """Shaped like the real `Exemption` (rule / path / line / reason)."""

    rule: str
    path: str
    line: int
    reason: str


@dataclass(frozen=True)
class _Config:
    exemptions: tuple = ()


def _loader_returning(*exemptions):
    def _load(_repo):
        return _Config(exemptions=tuple(exemptions))

    return _load


def _loader_raising(message="boom"):
    def _load(_repo):
        raise RuntimeError(message)

    return _load


def _eco(tmp_path, name="scitex-demo", checked_out=True):
    repo = tmp_path / name
    if checked_out:
        repo.mkdir(parents=True, exist_ok=True)
    return {name: {"local_path": str(repo)}}


EX = _Exemption("PS-231", ".github/workflows/x.yml", 0, "genuinely leaf-specific")


def test_a_declared_exemption_is_returned():
    # Arrange
    eco = {"scitex-demo": {"local_path": "."}}
    # Act
    census = collect_exemptions(eco, load_config=_loader_returning(EX))
    # Assert
    assert census.total_declared == 1


def test_the_exemption_carries_its_package():
    """Fleet-wide output is useless if a row cannot name its repo."""
    # Arrange
    eco = {"scitex-demo": {"local_path": "."}}
    # Act
    census = collect_exemptions(eco, load_config=_loader_returning(EX))
    # Assert
    assert census.exemptions[0].package == "scitex-demo"


def test_the_exemption_carries_its_reason():
    """A reason-less exemption is the thing the audit config forbids."""
    # Arrange
    eco = {"scitex-demo": {"local_path": "."}}
    # Act
    census = collect_exemptions(eco, load_config=_loader_returning(EX))
    # Assert
    assert census.exemptions[0].reason == "genuinely leaf-specific"


def test_a_package_declaring_none_is_clean(tmp_path):
    # Arrange
    eco = _eco(tmp_path)
    # Act
    census = collect_exemptions(eco, load_config=_loader_returning())
    # Assert
    assert census.clean == ("scitex-demo",)


def test_an_absent_checkout_is_unreadable_not_clean(tmp_path):
    """THE test. A missing checkout must not read as 'no exemptions'."""
    # Arrange
    eco = _eco(tmp_path, checked_out=False)
    # Act
    census = collect_exemptions(eco, load_config=_loader_returning(EX))
    # Assert
    assert [p for p, _ in census.unreadable] == ["scitex-demo"]


def test_an_absent_checkout_does_not_land_in_clean(tmp_path):
    # Arrange
    eco = _eco(tmp_path, checked_out=False)
    # Act
    census = collect_exemptions(eco, load_config=_loader_returning(EX))
    # Assert
    assert census.clean == ()


def test_an_absent_checkout_says_why(tmp_path):
    """An unreadable entry nobody can act on is only half a report."""
    # Arrange
    eco = _eco(tmp_path, checked_out=False)
    # Act
    census = collect_exemptions(eco, load_config=_loader_returning(EX))
    # Assert
    assert "not checked out" in census.unreadable[0][1]


def test_a_registry_entry_without_local_path_is_unreadable():
    # Arrange
    eco = {"scitex-demo": {}}
    # Act
    census = collect_exemptions(eco, load_config=_loader_returning(EX))
    # Assert
    assert "no local_path" in census.unreadable[0][1]


def test_an_unknown_package_is_unreadable():
    # Arrange
    eco = {}
    # Act
    census = collect_exemptions(eco, load_config=_loader_returning(EX), packages=["ghost"])
    # Assert
    assert "not in the ECOSYSTEM registry" in census.unreadable[0][1]


def test_a_raising_loader_is_reported_not_swallowed(tmp_path):
    """A config that blows up is unknown, never 'clean'."""
    # Arrange
    eco = _eco(tmp_path)
    # Act
    census = collect_exemptions(eco, load_config=_loader_raising("bad yaml"))
    # Assert
    assert "bad yaml" in census.unreadable[0][1]


def test_a_raising_loader_does_not_land_in_clean(tmp_path):
    # Arrange
    eco = _eco(tmp_path)
    # Act
    census = collect_exemptions(eco, load_config=_loader_raising())
    # Assert
    assert census.clean == ()


def test_is_complete_is_false_when_anything_was_unread(tmp_path):
    """The flag a caller must print beside the total."""
    # Arrange
    eco = _eco(tmp_path, checked_out=False)
    # Act
    census = collect_exemptions(eco, load_config=_loader_returning(EX))
    # Assert
    assert not census.is_complete


def test_is_complete_is_true_when_everything_was_read(tmp_path):
    # Arrange
    eco = _eco(tmp_path)
    # Act
    census = collect_exemptions(eco, load_config=_loader_returning(EX))
    # Assert
    assert census.is_complete


def test_total_declared_counts_only_what_was_found(tmp_path):
    """It must NOT estimate the unread packages — a guess in a number's clothes."""
    # Arrange
    eco = _eco(tmp_path, name="a")
    eco.update(_eco(tmp_path, name="b", checked_out=False))
    # Act
    census = collect_exemptions(eco, load_config=_loader_returning(EX, EX))
    # Assert
    assert census.total_declared == 2


def test_an_empty_census_is_complete():
    # Arrange
    eco = {}
    # Act
    census = ExemptionCensus()
    # Assert
    assert census.is_complete


# EOF
