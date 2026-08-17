#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/scitex_dev/_ecosystem/test__install_kind.py

"""An editable install's version number describes a different moment than its code.

The failure these tests exist for is not a crash. It is a venv that answers
every question politely while `import` raises: scitex-hpc measured a `.pth`
pointing at a deleted worktree that went unnoticed for TWENTY DAYS because
`importlib.metadata.version()` kept returning a tidy number.

So the tests below are weighted toward the states that LOOK fine — an
editable that resolves, and an editable whose target is gone — rather than
toward the missing case, which announces itself.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scitex_dev._ecosystem._install_kind import (
    InstallFacts,
    InstallKind,
    describe_install,
)


def _sp(tmp_path: Path) -> Path:
    site = tmp_path / "site-packages"
    site.mkdir()
    return site


def test_a_plain_install_is_resolved(tmp_path):
    # Arrange
    site = _sp(tmp_path)
    # Act
    facts = describe_install("scitex-dev", site, version_of=lambda d: "0.50.0")
    # Assert
    assert facts.kind is InstallKind.RESOLVED


def test_a_plain_install_version_is_meaningful(tmp_path):
    # Arrange
    site = _sp(tmp_path)
    # Act
    facts = describe_install("scitex-dev", site, version_of=lambda d: "0.50.0")
    # Assert
    assert facts.version_is_meaningful is True


def test_an_absent_distribution_is_missing(tmp_path):
    # Arrange
    site = _sp(tmp_path)

    def absent(_):
        raise LookupError("no such distribution")

    # Act
    facts = describe_install("scitex-dev", site, version_of=absent)
    # Assert
    assert facts.kind is InstallKind.MISSING


def test_a_uv_editable_pth_is_detected(tmp_path):
    """`_editable_impl_<name>.pth` — the spelling uv writes."""
    # Arrange
    site = _sp(tmp_path)
    target = tmp_path / "proj" / "scitex-cards" / "src"
    target.mkdir(parents=True)
    (site / "_editable_impl_scitex_cards.pth").write_text(str(target))
    # Act
    facts = describe_install("scitex-cards", site, version_of=lambda d: "0.32.1")
    # Assert
    assert facts.kind is InstallKind.EDITABLE


def test_a_pip_editable_pth_is_detected(tmp_path):
    """`__editable__.<name>-<ver>.pth` — the spelling pip writes.

    Both are live on this host; a checker that knew only one spelling would
    silently classify half the editables as ordinary installs, which is the
    failure this module exists to prevent.
    """
    # Arrange
    site = _sp(tmp_path)
    target = tmp_path / "proj" / "scitex-cloud" / "src"
    target.mkdir(parents=True)
    (site / "__editable__.scitex_hub-0.19.0.pth").write_text(str(target))
    # Act
    facts = describe_install("scitex-hub", site, version_of=lambda d: "0.19.0")
    # Assert
    assert facts.kind is InstallKind.EDITABLE


def test_an_editable_version_is_NOT_meaningful(tmp_path):
    """The whole point: the number is a fossil from install time."""
    # Arrange
    site = _sp(tmp_path)
    target = tmp_path / "src"
    target.mkdir()
    (site / "_editable_impl_scitex_cards.pth").write_text(str(target))
    # Act
    facts = describe_install("scitex-cards", site, version_of=lambda d: "0.32.1")
    # Assert
    assert facts.version_is_meaningful is False


def test_an_editable_reports_the_path_it_points_at(tmp_path):
    """A caller needs the PATH; the version tells them nothing useful."""
    # Arrange
    site = _sp(tmp_path)
    target = tmp_path / "proj" / "scitex-todo" / "src"
    target.mkdir(parents=True)
    (site / "_editable_impl_scitex_cards.pth").write_text(str(target))
    # Act
    facts = describe_install("scitex-cards", site, version_of=lambda d: "0.32.1")
    # Assert
    assert facts.target == target


def test_an_editable_whose_target_is_GONE_is_reported_broken(tmp_path):
    """The measured failure: `sac-imgbuild-venv` on this host, right now.

    Its .pth points at `.worktrees/agent-a17c9eeb753a07e10/src`, a worktree
    deleted under the three-days rule. `import` fails; the version query does
    not. Nothing raised for as long as nobody imported.
    """
    # Arrange
    site = _sp(tmp_path)
    gone = tmp_path / "proj" / "pkg" / ".worktrees" / "deleted" / "src"
    (site / "_editable_impl_pkg.pth").write_text(str(gone))
    # Act
    facts = describe_install("pkg", site, version_of=lambda d: "0.9.0")
    # Assert
    assert facts.is_broken is True


def test_a_healthy_editable_is_not_reported_broken(tmp_path):
    """The control against flagging every editable as a problem.

    Editable installs are a normal development tool. The defect is reporting
    their version as though it described the code — not their existence.
    """
    # Arrange
    site = _sp(tmp_path)
    target = tmp_path / "src"
    target.mkdir()
    (site / "_editable_impl_pkg.pth").write_text(str(target))
    # Act
    facts = describe_install("pkg", site, version_of=lambda d: "0.9.0")
    # Assert
    assert facts.is_broken is False


def test_an_unrelated_editable_does_not_match(tmp_path):
    """One package's .pth must not classify a different package as editable."""
    # Arrange
    site = _sp(tmp_path)
    target = tmp_path / "src"
    target.mkdir()
    (site / "_editable_impl_figrecipe.pth").write_text(str(target))
    # Act
    facts = describe_install("scitex-cards", site, version_of=lambda d: "0.32.1")
    # Assert
    assert facts.kind is InstallKind.RESOLVED


def test_editable_without_a_target_is_refused():
    """The validator: an EDITABLE with no path is the un-sayable state."""
    # Arrange
    kind = InstallKind.EDITABLE
    # Act
    def build():
        return InstallFacts(distribution="pkg", kind=kind)

    # Assert
    with pytest.raises(ValueError):
        build()


def test_a_resolved_install_may_not_carry_a_target():
    """Symmetric guard — `target` means nothing outside EDITABLE."""
    # Arrange
    kind = InstallKind.RESOLVED
    # Act
    def build():
        return InstallFacts(
            distribution="pkg", kind=kind, version="1.0", target=Path("/tmp")
        )

    # Assert
    with pytest.raises(ValueError):
        build()


# EOF
