#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Install-currency DISPATCH — the safety of non-negotiable #2 lives here.

The headline test is ``test_editable_behind_metadata_but_current_tree_is_fresh``
(and its partner ``..._never_emits_pip_install_u``): an editable checkout whose
FROZEN metadata trails PyPI but whose working tree is current must resolve
FRESH by CONTENT and must NEVER be handed a ``pip install -U`` remedy — which
would clobber the checkout with a wheel. sac's ``check_host_behind_pypi``
would fail exactly this case, which is why it is deliberately NOT applied to
editable installs.
"""

from __future__ import annotations

import subprocess

from scitex_dev.versioning._checks import build_report, check_install_currency
from scitex_dev.versioning._config import VersioningConfig
from scitex_dev.versioning._editable import (
    editable_ahead_behind,
    editable_behind_upstream,
)
from scitex_dev.versioning._model import Currency
from scitex_dev.versioning._sources import StaticSources

CFG = VersioningConfig(dist="scitex-dev")


# -- wheel: the version compare is honest and DOES fire --------------------


def test_wheel_behind_pypi_is_stale():
    # Arrange
    kind, installed, latest = "wheel", "0.29.0", "0.31.0"
    # Act
    finding = check_install_currency(
        kind, dist="scitex-dev", effective=installed, metadata=installed,
        latest=latest, ahead_behind=None, python="/v/py",
    )
    # Assert
    assert finding.state is Currency.STALE


def test_wheel_behind_pypi_remedy_is_pip_install_u():
    # Arrange
    kind, installed, latest = "wheel", "0.29.0", "0.31.0"
    # Act
    finding = check_install_currency(
        kind, dist="scitex-dev", effective=installed, metadata=installed,
        latest=latest, ahead_behind=None, python="/v/py",
    )
    # Assert
    assert finding.remedy == "/v/py -m pip install -U 'scitex-dev==0.31.0'"


def test_wheel_current_is_fresh():
    # Arrange
    kind, v = "wheel", "0.31.0"
    # Act
    finding = check_install_currency(
        kind, dist="scitex-dev", effective=v, metadata=v, latest=v,
        ahead_behind=None, python="py",
    )
    # Assert
    assert finding.state is Currency.FRESH


# -- editable: the CONTENT probe, the dangerous compare is refused ----------


def test_editable_behind_metadata_but_current_tree_is_fresh():
    # Arrange — frozen metadata 0.21.21 trails PyPI 0.31.0, but the working
    # tree is 5 commits ahead of its own latest tag and 0 behind.
    kind = "editable"
    # Act
    finding = check_install_currency(
        kind, dist="scitex-dev", effective="0.31.0+dev", metadata="0.21.21",
        latest="0.31.0", ahead_behind=(5, 0), python="/v/py",
    )
    # Assert
    assert finding.state is Currency.FRESH


def test_editable_current_tree_never_emits_pip_install_u():
    # Arrange
    kind = "editable"
    # Act
    finding = check_install_currency(
        kind, dist="scitex-dev", effective="0.31.0+dev", metadata="0.21.21",
        latest="0.31.0", ahead_behind=(5, 0), python="/v/py",
    )
    # Assert
    assert "pip install -U" not in finding.remedy


def test_editable_behind_its_tracking_remote_is_stale():
    # Arrange — the remote HAS 3 commits this tree lacks: a pull closes it.
    kind = "editable"
    # Act
    finding = check_install_currency(
        kind, dist="scitex-dev", effective="0.30.0", metadata="0.30.0",
        latest="0.31.0", ahead_behind=(0, 3), behind_upstream=3,
        repo="/home/dev/scitex-dev", python="/v/py",
    )
    # Assert
    assert finding.state is Currency.STALE


def test_editable_behind_remote_remedy_is_a_pull_that_can_work():
    # Arrange — `-C <repo>` so it works from any CWD, `--ff-only` so it can
    # never rewrite the developer's unpushed commits.
    kind = "editable"
    # Act
    finding = check_install_currency(
        kind, dist="scitex-dev", effective="0.30.0", metadata="0.30.0",
        latest="0.31.0", ahead_behind=(0, 3), behind_upstream=3,
        repo="/home/dev/scitex-dev", python="/v/py",
    )
    # Assert
    assert finding.remedy == "git -C /home/dev/scitex-dev pull --ff-only"


def test_editable_behind_remote_remedy_is_never_pip_install_u():
    # Arrange
    kind = "editable"
    # Act
    finding = check_install_currency(
        kind, dist="scitex-dev", effective="0.30.0", metadata="0.30.0",
        latest="0.31.0", ahead_behind=(0, 3), behind_upstream=3,
        repo="/home/dev/scitex-dev", python="/v/py",
    )
    # Assert
    assert "pip install -U" not in finding.remedy


def test_editable_behind_remote_remedy_never_rebases():
    # Arrange — `--rebase` rewrites unpushed work; a WARNING's remedy must
    # not be able to cost anybody their commits.
    kind = "editable"
    # Act
    finding = check_install_currency(
        kind, dist="scitex-dev", effective="0.30.0", metadata="0.30.0",
        latest="0.31.0", ahead_behind=(0, 3), behind_upstream=3,
        repo="/home/dev/scitex-dev", python="/v/py",
    )
    # Assert
    assert "--rebase" not in finding.remedy


# -- editable: behind a tag that is NOT on this branch ----------------------
# The operator's 2026-08-31 report. sac's `develop` measured +46/-3 against
# v0.27.0 (a tag on `main`) while sitting exactly level with origin/develop.
# The check said STALE and printed `git pull --rebase`; git answered "Already
# up to date" and the identical warning came back, forever.


def test_editable_behind_a_tag_on_another_branch_is_not_stale():
    # Arrange — the operator's exact numbers: ahead 46 / behind 3 of the tag,
    # and 0 behind its own tracking remote.
    kind = "editable"
    # Act
    finding = check_install_currency(
        kind, dist="scitex-agent-container", effective="0.27.0+dev",
        metadata="0.21.21", latest="0.27.0", ahead_behind=(46, 3),
        behind_upstream=0, repo="/home/dev/sac", python="/v/py",
    )
    # Assert
    assert finding.state is not Currency.STALE


def test_editable_behind_a_tag_on_another_branch_emits_no_remedy():
    # Arrange — a remedy that provably cannot change the finding must not be
    # printed at all.
    kind = "editable"
    # Act
    finding = check_install_currency(
        kind, dist="scitex-agent-container", effective="0.27.0+dev",
        metadata="0.21.21", latest="0.27.0", ahead_behind=(46, 3),
        behind_upstream=0, repo="/home/dev/sac", python="/v/py",
    )
    # Assert
    assert finding.remedy == ""


def test_editable_ahead_of_its_tag_is_not_stale():
    # Arrange — the normal, healthy state of any development branch.
    kind = "editable"
    # Act
    finding = check_install_currency(
        kind, dist="scitex-dev", effective="0.31.0+dev", metadata="0.21.21",
        latest="0.31.0", ahead_behind=(46, 0), behind_upstream=0,
        repo="/home/dev/scitex-dev", python="/v/py",
    )
    # Assert
    assert finding.state is Currency.FRESH


def test_editable_behind_tag_with_no_upstream_is_unknown():
    # Arrange — behind the tag, and NOTHING can say whether a pull would
    # bring those commits. UNKNOWN is the honest verdict, not STALE.
    kind = "editable"
    # Act
    finding = check_install_currency(
        kind, dist="scitex-dev", effective="0.30.0", metadata="0.30.0",
        latest="0.31.0", ahead_behind=(0, 3), behind_upstream=None,
        python="/v/py",
    )
    # Assert
    assert finding.state is Currency.UNKNOWN


def test_editable_behind_tag_with_no_upstream_emits_no_remedy():
    # Arrange
    kind = "editable"
    # Act
    finding = check_install_currency(
        kind, dist="scitex-dev", effective="0.30.0", metadata="0.30.0",
        latest="0.31.0", ahead_behind=(0, 3), behind_upstream=None,
        python="/v/py",
    )
    # Assert
    assert finding.remedy == ""


def test_editable_records_the_upstream_distance_as_evidence():
    # Arrange — the fact the verdict turns on must be readable in --json.
    kind = "editable"
    # Act
    finding = check_install_currency(
        kind, dist="scitex-dev", effective="0.31.0+dev", metadata="0.21.21",
        latest="0.31.0", ahead_behind=(46, 3), behind_upstream=0,
        repo="/home/dev/scitex-dev", python="/v/py",
    )
    # Assert
    assert finding.data["behind_upstream"] == 0


def test_editable_without_checkout_is_unknown():
    # Arrange
    kind = "editable"
    # Act
    finding = check_install_currency(
        kind, dist="scitex-dev", effective=None, metadata="0.21.21",
        latest="0.31.0", ahead_behind=None, python="/v/py",
    )
    # Assert
    assert finding.state is Currency.UNKNOWN


# -- orphaned: metadata with no code behind it -----------------------------


def test_orphaned_install_is_stale():
    # Arrange
    kind = "orphaned"
    # Act
    finding = check_install_currency(
        kind, dist="scitex-dev", effective=None, metadata="0.29.0",
        latest="0.31.0", ahead_behind=None, python="py",
    )
    # Assert
    assert finding.state is Currency.STALE


def test_absent_install_is_unknown():
    # Arrange
    kind = "absent"
    # Act
    finding = check_install_currency(
        kind, dist="scitex-dev", effective=None, metadata=None,
        latest="0.31.0", ahead_behind=None, python="py",
    )
    # Assert
    assert finding.state is Currency.UNKNOWN


# -- name-the-binary: every finding names WHO answered ---------------------


def test_every_finding_summary_names_the_binary():
    # Arrange — a source that reports its origin and interpreter.
    sources = StaticSources(
        install_kind="wheel",
        effective_version="0.31.0",
        metadata_version="0.31.0",
        module_origin="/opt/venv/lib/scitex_dev/__init__.py",
        executable="/opt/venv/bin/python3",
        pypi_latest="0.31.0",
    )
    # Act
    report = build_report(CFG, sources, now=1.0)
    tells_who = all(
        "/opt/venv/bin/python3" in f.summary and "scitex-dev @" in f.summary
        for f in report.findings
    )
    # Assert
    assert tells_who is True


def test_shadowed_old_install_origin_is_named():
    # Arrange — an OLD install shadowing from a repo .venv that predates use.
    sources = StaticSources(
        install_kind="wheel",
        effective_version="0.29.0",
        metadata_version="0.29.0",
        module_origin="/home/x/proj/old/.venv/lib/scitex_dev/__init__.py",
        executable="/home/x/proj/old/.venv/bin/python3",
        pypi_latest="0.31.0",
    )
    # Act
    report = build_report(CFG, sources, now=1.0)
    currency = report.findings[0]
    # Assert
    assert "/home/x/proj/old/.venv/lib/scitex_dev/__init__.py" in currency.summary


# -- aggregate: blind report is UNKNOWN, incident replay is STALE ----------


def test_blind_report_is_not_fresh():
    # Arrange — every source dark.
    sources = StaticSources()
    # Act
    report = build_report(CFG, sources, now=1.0)
    # Assert
    assert report.state is not Currency.FRESH


def test_blind_report_is_unknown():
    # Arrange
    sources = StaticSources()
    # Act
    report = build_report(CFG, sources, now=1.0)
    # Assert
    assert report.state is Currency.UNKNOWN


# -- the same verdict, driven by REAL git instead of recorded numbers -------


def _verdict_for(repo):
    """The install-currency verdict for a real editable checkout at ``repo``."""
    return check_install_currency(
        "editable",
        dist="scitex-agent-container",
        effective="1.0.0+dev",
        metadata="0.9.0",
        latest="1.1.0",
        ahead_behind=editable_ahead_behind(repo),
        behind_upstream=editable_behind_upstream(repo),
        repo=str(repo),
        python="/opt/venv-sac/bin/python3",
    )


def test_real_gitflow_checkout_is_not_stale(gitflow_repo):
    # Arrange — real repo, real tags, real remote: develop is behind v1.1.0
    # (cut on main) and exactly level with origin/develop.
    # Act
    finding = _verdict_for(gitflow_repo)
    # Assert
    assert finding.state is not Currency.STALE


def test_real_gitflow_checkout_gets_no_unrunnable_remedy(gitflow_repo):
    # Arrange — same real checkout as above.
    # Act
    finding = _verdict_for(gitflow_repo)
    # Assert
    assert finding.remedy == ""


def test_a_no_op_pull_leaves_the_checkout_fresh(gitflow_repo):
    # Arrange — the operator's loop, replayed: pull, then check again. Before
    # the fix the verdict came back byte-identical after this no-op pull,
    # which is what proved the remedy could not work.
    subprocess.run(
        ["git", "-C", str(gitflow_repo), "pull", "--ff-only"],
        check=True, capture_output=True,
    )
    # Act
    finding = _verdict_for(gitflow_repo)
    # Assert — the pull is a no-op here, and the check now agrees it is fine.
    assert finding.state is Currency.FRESH


def test_real_checkout_behind_its_remote_is_still_stale(gitflow_repo):
    # Arrange — rewind develop one commit so the remote genuinely has work
    # this tree lacks. This is the case a pull DOES fix, and it must survive.
    subprocess.run(
        ["git", "-C", str(gitflow_repo), "reset", "-q", "--hard", "HEAD~1"],
        check=True, capture_output=True,
    )
    # Act
    finding = _verdict_for(gitflow_repo)
    # Assert
    assert finding.state is Currency.STALE


def test_real_checkout_behind_its_remote_gets_a_pull_that_works(gitflow_repo):
    # Arrange
    subprocess.run(
        ["git", "-C", str(gitflow_repo), "reset", "-q", "--hard", "HEAD~1"],
        check=True, capture_output=True,
    )
    finding = _verdict_for(gitflow_repo)
    # Act — run exactly what the finding printed, then re-ask.
    subprocess.run(finding.remedy.split(), check=True, capture_output=True)
    after = _verdict_for(gitflow_repo)
    # Assert — the remedy CLEARED the finding. That is the property the old
    # `git pull --rebase` could never satisfy.
    assert after.state is Currency.FRESH


# EOF
