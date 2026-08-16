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
* :func:`test_an_orphaned_install_kind_is_reported`

A drift detector that reads a fossilised version is a drift detector turned off.
"""

from __future__ import annotations

from scitex_dev._ecosystem._drift_report._package_watch import (
    check_critical_package_drift,
)
from scitex_dev._ecosystem._drift_report._untrustworthy_installs import (
    check_untrustworthy_installs,
    default_scan_packages,
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
# The scope: the default scan must cover packages nobody hand-picked.
# --------------------------------------------------------------------------


def _only_this_one_lies(target: str):
    """A probe reader where exactly ONE package is untrustworthy.

    The positive control for scope. Without a planted liar the scan returns
    zero whether it inspects 3 packages or 70, so a green proves only that
    the loop ran — the same "instrument that never returned a known answer"
    this module exists to prevent elsewhere.
    """

    def probe_fn(name: str) -> InstallProbe:
        if name == target:
            return _probe(
                dist=name,
                kind=KIND_ORPHANED,
                metadata_version="9.9.9",
                code_version=None,
                honest=False,
            )
        return _probe(dist=name, kind=KIND_ABSENT, honest=True)

    return probe_fn


def test_the_default_scan_reports_a_package_outside_the_hand_picked_three():
    """scitex-plt is not in CRITICAL_PACKAGES; a lie there must still surface.

    The old default inspected three names against a registry of seventy, so a
    fossilised install anywhere else was invisible — and the banner said
    nothing about scope, making silence indistinguishable from coverage.
    """
    # Arrange
    probe_fn = _only_this_one_lies("scitex-plt")
    # Act
    warnings = check_untrustworthy_installs(probe_fn=probe_fn)
    # Assert
    assert [w.package for w in warnings] == ["scitex-plt"]


def test_the_default_scan_is_the_whole_registry_not_a_short_list():
    # Arrange
    expected = len(default_scan_packages())
    # Act
    seen: list[str] = []

    def probe_fn(name: str) -> InstallProbe:
        seen.append(name)
        return _probe(dist=name, kind=KIND_ABSENT, honest=True)

    check_untrustworthy_installs(probe_fn=probe_fn)
    # Assert
    assert len(seen) == expected


# --------------------------------------------------------------------------
# The bug: a fossil must not drive the comparison.
# --------------------------------------------------------------------------


def test_a_fossil_no_longer_produces_a_false_stale_alarm():
    """Metadata says 0.7.26; the CODE is 0.8.7; fleet-current is 0.8.7.

    The old check compared 0.7.26 vs 0.8.7 and screamed "STALE — DEPLOY NOW" at a
    container that was already current. Repeat that 12x a day and its reader
    learns to ignore the whole report.
    """
    # Arrange
    fossil = _probe(
        kind=KIND_EDITABLE,
        metadata_version="0.7.26",  # the fossil
        code_version="0.8.7",  # what actually runs
        honest=False,
    )
    # Act
    warnings = check_critical_package_drift(
        packages=("scitex-todo",),
        # the verified reader returns what is RUNNING, not what is claimed
        installed_fn=lambda pkg: fossil.effective_version,
        pypi_fn=lambda pkg: "0.8.7",
        local_path_fn=lambda pkg: None,
        toml_fn=lambda p: None,
    )
    # Assert
    assert warnings == [], "a current install must not be reported as behind"


def _genuinely_behind_warnings():
    """Shared setup for the split ``test_genuinely_behind_*`` tests below."""
    return check_critical_package_drift(
        packages=("scitex-todo",),
        installed_fn=lambda pkg: "0.7.50",
        pypi_fn=lambda pkg: "0.8.8",
        local_path_fn=lambda pkg: None,
        toml_fn=lambda p: None,
    )


def test_genuinely_behind_is_still_reported():
    """The true signal must survive the fix — this is what the check is FOR."""
    # Arrange
    # (setup lives in the shared helper above)
    # Act
    warnings = _genuinely_behind_warnings()
    # Assert
    assert [w.package for w in warnings] == ["scitex-todo"]


def test_genuinely_behind_reports_the_installed_version():
    # Arrange
    # (setup lives in the shared helper above)
    # Act
    warnings = _genuinely_behind_warnings()
    # Assert
    assert warnings[0].installed == "0.7.50"


def test_genuinely_behind_reports_the_reference_version():
    # Arrange
    # (setup lives in the shared helper above)
    # Act
    warnings = _genuinely_behind_warnings()
    # Assert
    assert warnings[0].reference == "0.8.8"


def test_unknowable_running_version_is_never_reported_as_drift():
    """``None`` from the verified reader means UNKNOWN, never agreement."""
    # Arrange
    # (setup lives in the shared helper above)
    # Act
    warnings = check_critical_package_drift(
        packages=("scitex-todo",),
        installed_fn=lambda pkg: None,  # cannot establish what is running
        pypi_fn=lambda pkg: "0.8.8",
        local_path_fn=lambda pkg: None,
        toml_fn=lambda p: None,
    )
    # Assert
    assert warnings == [], "unknown must be silent, never a confident drift claim"


# --------------------------------------------------------------------------
# The new, louder finding: "I cannot tell what you are running."
# --------------------------------------------------------------------------


def _drifted_metadata_probe() -> InstallProbe:
    """Shared setup for the split ``test_a_drifted_metadata_*`` tests below."""
    return _probe(
        kind=KIND_EDITABLE,
        metadata_version="0.7.26",
        code_version="0.8.7",
        honest=False,
        detail="VERSION STRING LIES: metadata says 0.7.26 ... code is 0.8.7",
        hint="uv pip install -e <root> --no-deps",
    )


def _drifted_metadata_findings():
    fossil = _drifted_metadata_probe()
    return check_untrustworthy_installs(
        packages=("scitex-todo",), probe_fn=lambda pkg: fossil
    )


def test_a_drifted_metadata_is_surfaced_exactly_once():
    # Arrange
    # (setup lives in the shared helper above)
    # Act
    out = _drifted_metadata_findings()
    # Assert
    assert len(out) == 1


def test_a_drifted_metadata_names_the_package():
    # Arrange
    # (setup lives in the shared helper above)
    # Act
    out = _drifted_metadata_findings()
    # Assert
    assert out[0].package == "scitex-todo"


def test_a_drifted_metadata_reports_the_claimed_version():
    # Arrange
    # (setup lives in the shared helper above)
    # Act
    out = _drifted_metadata_findings()
    # Assert
    assert out[0].claimed == "0.7.26"


def test_a_drifted_metadata_reports_the_actual_version():
    # Arrange
    # (setup lives in the shared helper above)
    # Act
    out = _drifted_metadata_findings()
    # Assert
    assert out[0].actual == "0.8.7"


def test_a_drifted_metadata_line_names_it_a_fossil():
    # Arrange
    # (setup lives in the shared helper above)
    # Act
    out = _drifted_metadata_findings()
    # Assert
    assert "fossil" in out[0].line()


def _orphaned_install_probe() -> InstallProbe:
    """Shared setup for the split ``test_an_orphaned_install_*`` tests below.

    Metadata present, NO code. The worst case, and the old check missed it: a
    container whose package was deleted but whose .dist-info survived would
    compare "0.8.8 vs 0.8.8" and be pronounced healthy — while running nothing.
    """
    return _probe(
        kind=KIND_ORPHANED,
        metadata_version="0.8.8",
        code_version=None,
        honest=False,
        detail="metadata claims 0.8.8 but `import scitex_todo` FAILED",
        hint="pip install --force-reinstall --no-deps scitex-todo",
    )


def _orphaned_install_findings():
    orphan = _orphaned_install_probe()
    return check_untrustworthy_installs(
        packages=("scitex-todo",), probe_fn=lambda pkg: orphan
    )


def test_an_orphaned_install_is_surfaced_exactly_once():
    # Arrange
    # (setup lives in the shared helper above)
    # Act
    out = _orphaned_install_findings()
    # Assert
    assert len(out) == 1


def test_an_orphaned_install_kind_is_reported():
    # Arrange
    # (setup lives in the shared helper above)
    # Act
    out = _orphaned_install_findings()
    # Assert
    assert out[0].kind == KIND_ORPHANED


def test_an_orphaned_install_line_says_no_code():
    # Arrange
    # (setup lives in the shared helper above)
    # Act
    out = _orphaned_install_findings()
    # Assert
    assert "NO CODE" in out[0].line()


def test_a_healthy_wheel_is_not_reported():
    # Arrange
    healthy = _probe(kind=KIND_WHEEL, metadata_version="0.8.8", honest=True)
    # Act
    out = check_untrustworthy_installs(
        packages=("scitex-todo",), probe_fn=lambda pkg: healthy
    )
    # Assert
    assert out == []


def test_an_absent_package_is_not_reported_as_a_liar():
    """Not installed is not a lie. Reporting it as one is a confidently wrong hint."""
    # Arrange
    absent = _probe(kind=KIND_ABSENT, metadata_version=None, honest=False)
    # Act
    out = check_untrustworthy_installs(
        packages=("scitex-todo",), probe_fn=lambda pkg: absent
    )
    # Assert
    assert out == []


# --------------------------------------------------------------------------
# The banner must be loud and actionable.
# --------------------------------------------------------------------------


def test_banner_is_empty_when_there_is_nothing_to_say():
    # Arrange
    # (setup lives in the shared helper above)
    # Act
    banner = render_untrustworthy_install_banner([])
    # Assert
    assert banner == ""


def _repair_banner() -> str:
    """Shared setup for the split ``test_banner_names_*`` tests below."""
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
    return render_untrustworthy_install_banner(out)


def test_banner_names_the_finding():
    # Arrange
    # (setup lives in the shared helper above)
    # Act
    banner = _repair_banner()
    # Assert
    assert "UNTRUSTWORTHY INSTALL" in banner


def test_banner_names_the_package():
    # Arrange
    # (setup lives in the shared helper above)
    # Act
    banner = _repair_banner()
    # Assert
    assert "scitex-todo" in banner


def test_banner_explains_why_other_lines_are_suspect():
    # Arrange
    # (setup lives in the shared helper above)
    # Act
    banner = _repair_banner()
    # Assert
    assert "meaningless" in banner


def test_banner_carries_the_actual_repair_command():
    # Arrange
    # (setup lives in the shared helper above)
    # Act
    banner = _repair_banner()
    # Assert
    assert "--no-deps" in banner


def test_banner_names_the_interpreter_it_judged():
    """"in this interpreter" is unrecoverable to a reader.

    A verdict about /opt/venv-sac says nothing to someone who believes it
    describes their checkout's venv, and the old wording gave them no way to
    tell. Measured 2026-08-16: reporting a venv by BASENAME cost two agents a
    round trip when the same name existed at two paths.

    Same principle as the auditors' `N file(s) inspected under <root>` — the
    scope clause must name the fact the reader cannot otherwise recover.
    """
    # Arrange
    import sys

    # Act
    banner = _repair_banner()
    # Assert
    assert sys.executable in banner
