#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Timestamp: 2026-07-12
# File: tests/scitex_dev/_ecosystem/_drift_report/test__untrustworthy_installs.py

"""The drift detector must not be fooled by a fossilised ``.dist-info``.

Incident 2026-07-12. ``check_critical_package_drift`` read
``importlib.metadata.version()`` and compared it against fleet-current. But that
string comes from a ``.dist-info`` directory, and **a .dist-info can outlive the
code it describes**:

* scitex-todo's container: metadata said 0.7.26; the code importing was 0.8.7.
* scitex-agent-container: a baked dist-info fossil over current bound code.
* 2026-07-10: an editable install deleted the package and left the metadata, so
  every version check passed against code that was not there.

Comparing against a fossil is wrong in BOTH directions, and this file pins both:

* :func:`test_a_fossil_no_longer_produces_a_false_stale_alarm`
* :func:`test_an_orphaned_install_is_surfaced_not_silently_blessed`

A drift detector that reads a fossilised version is a drift detector turned off.
"""

from __future__ import annotations

from scitex_dev._ecosystem._drift_report._package_watch import (
    check_critical_package_drift,
    check_untrustworthy_installs,
    render_untrustworthy_install_banner,
)
from scitex_dev._release._install_probe import (
    KIND_ABSENT,
    KIND_EDITABLE,
    KIND_ORPHANED,
    KIND_WHEEL,
    InstallProbe,
)


def _probe(**kw) -> InstallProbe:
    base = dict(dist="scitex-todo", kind=KIND_WHEEL, honest=True)
    base.update(kw)
    return InstallProbe(**base)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# The bug: a fossil must not drive the comparison.
# --------------------------------------------------------------------------


def test_a_fossil_no_longer_produces_a_false_stale_alarm():
    """Metadata says 0.7.26; the CODE is 0.8.7; fleet-current is 0.8.7.

    The old check compared 0.7.26 vs 0.8.7 and screamed "STALE — DEPLOY NOW" at a
    container that was already current. Repeat that 12x a day and its reader
    learns to ignore the whole report.
    """
    fossil = _probe(
        kind=KIND_EDITABLE,
        metadata_version="0.7.26",  # the fossil
        code_version="0.8.7",  # what actually runs
        honest=False,
    )

    warnings = check_critical_package_drift(
        packages=("scitex-todo",),
        # the verified reader returns what is RUNNING, not what is claimed
        installed_fn=lambda pkg: fossil.effective_version,
        pypi_fn=lambda pkg: "0.8.7",
        local_path_fn=lambda pkg: None,
        toml_fn=lambda p: None,
    )

    assert warnings == [], "a current install must not be reported as behind"


def test_genuinely_behind_is_still_reported():
    """The true signal must survive the fix — this is what the check is FOR."""
    warnings = check_critical_package_drift(
        packages=("scitex-todo",),
        installed_fn=lambda pkg: "0.7.50",
        pypi_fn=lambda pkg: "0.8.8",
        local_path_fn=lambda pkg: None,
        toml_fn=lambda p: None,
    )

    assert [w.package for w in warnings] == ["scitex-todo"]
    assert warnings[0].installed == "0.7.50"
    assert warnings[0].reference == "0.8.8"


def test_unknowable_running_version_is_never_reported_as_drift():
    """``None`` from the verified reader means UNKNOWN, never agreement."""
    warnings = check_critical_package_drift(
        packages=("scitex-todo",),
        installed_fn=lambda pkg: None,  # cannot establish what is running
        pypi_fn=lambda pkg: "0.8.8",
        local_path_fn=lambda pkg: None,
        toml_fn=lambda p: None,
    )

    assert warnings == [], "unknown must be silent, never a confident drift claim"


# --------------------------------------------------------------------------
# The new, louder finding: "I cannot tell what you are running."
# --------------------------------------------------------------------------


def test_a_drifted_metadata_is_surfaced_as_untrustworthy():
    fossil = _probe(
        kind=KIND_EDITABLE,
        metadata_version="0.7.26",
        code_version="0.8.7",
        honest=False,
        detail="VERSION STRING LIES: metadata says 0.7.26 ... code is 0.8.7",
        hint="uv pip install -e <root> --no-deps",
    )

    out = check_untrustworthy_installs(
        packages=("scitex-todo",), probe_fn=lambda pkg: fossil
    )

    assert len(out) == 1
    assert out[0].package == "scitex-todo"
    assert out[0].claimed == "0.7.26"
    assert out[0].actual == "0.8.7"
    assert "fossil" in out[0].line()


def test_an_orphaned_install_is_surfaced_not_silently_blessed():
    """Metadata present, NO code. The worst case, and the old check missed it.

    A container whose package was deleted but whose .dist-info survived would
    compare "0.8.8 vs 0.8.8" and be pronounced healthy — while running nothing.
    """
    orphan = _probe(
        kind=KIND_ORPHANED,
        metadata_version="0.8.8",
        code_version=None,
        honest=False,
        detail="metadata claims 0.8.8 but `import scitex_todo` FAILED",
        hint="pip install --force-reinstall --no-deps scitex-todo",
    )

    out = check_untrustworthy_installs(
        packages=("scitex-todo",), probe_fn=lambda pkg: orphan
    )

    assert len(out) == 1
    assert out[0].kind == KIND_ORPHANED
    assert "NO CODE" in out[0].line()


def test_a_healthy_wheel_is_not_reported():
    healthy = _probe(kind=KIND_WHEEL, metadata_version="0.8.8", honest=True)

    out = check_untrustworthy_installs(
        packages=("scitex-todo",), probe_fn=lambda pkg: healthy
    )

    assert out == []


def test_an_absent_package_is_not_reported_as_a_liar():
    """Not installed is not a lie. Reporting it as one is a confidently wrong hint."""
    absent = _probe(kind=KIND_ABSENT, metadata_version=None, honest=False)

    out = check_untrustworthy_installs(
        packages=("scitex-todo",), probe_fn=lambda pkg: absent
    )

    assert out == []


# --------------------------------------------------------------------------
# The banner must be loud and actionable.
# --------------------------------------------------------------------------


def test_banner_is_empty_when_there_is_nothing_to_say():
    assert render_untrustworthy_install_banner([]) == ""


def test_banner_names_the_problem_and_the_repair():
    fossil = _probe(
        kind=KIND_EDITABLE,
        metadata_version="0.7.26",
        code_version="0.8.7",
        honest=False,
        detail="VERSION STRING LIES",
        hint="uv pip install -e /repo --no-deps",
    )
    out = check_untrustworthy_installs(
        packages=("scitex-todo",), probe_fn=lambda pkg: fossil
    )

    banner = render_untrustworthy_install_banner(out)

    assert "UNTRUSTWORTHY INSTALL" in banner
    assert "scitex-todo" in banner
    # It must say WHY every other line is now suspect for this package.
    assert "meaningless" in banner
    # And it must carry the actual repair, not just a complaint.
    assert "--no-deps" in banner
