#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the critical-package drift check (`_package_watch.py`).

No network, no real interpreter installs, no dependence on this
MACHINE's particular set of mounted local checkouts — ``installed_fn``
/ ``pypi_fn`` / ``local_path_fn`` are injected fakes throughout,
mirroring the ``_sac.py`` injected-runner test style.

The ``local_path_fn`` seam matters specifically here: scitex-dev's own
dev container happens to have every sibling repo checked out under
``~/proj`` (broad read visibility, per its role), so the REAL
``get_local_path`` would silently resolve a "local-checkout" reference
for every test here and never exercise the "lean container, no
checkout" branch this module exists to cover. ``_NO_LOCAL_CHECKOUT``
pins every test to that lean-container scenario unless a test opts in
to a local checkout explicitly.
"""

from __future__ import annotations

from scitex_dev._ecosystem._drift_report._package_watch import (
    CRITICAL_PACKAGES,
    PackageDriftWarning,
    check_critical_package_drift,
    render_package_drift_banner,
)


def _installed(mapping):
    return lambda pypi_name: mapping.get(pypi_name)


def _pypi(mapping):
    return lambda pypi_name: mapping.get(pypi_name)


def _NO_LOCAL_CHECKOUT(pkg):
    return None


class _FakeLocalPath:
    """Minimal stand-in for the ``Path`` returned by ``get_local_path`` —
    only needs ``.exists()``; ``toml_fn`` is injected separately so this
    never touches a real filesystem."""

    def exists(self) -> bool:
        return True


# ── check_critical_package_drift ───────────────────────────────────────────


def test_behind_package_is_reported_exactly_once():
    # Arrange — installed 0.7.28, fleet-current (PyPI) 0.8.4 (the incident shape)
    installed_fn = _installed({"scitex-todo": "0.7.28"})
    pypi_fn = _pypi({"scitex-todo": "0.8.4"})
    # Act
    warnings = check_critical_package_drift(
        packages=("scitex-todo",),
        installed_fn=installed_fn,
        pypi_fn=pypi_fn,
        local_path_fn=_NO_LOCAL_CHECKOUT,
    )
    # Assert
    assert len(warnings) == 1


def test_behind_package_warning_carries_installed_version():
    # Arrange
    installed_fn = _installed({"scitex-todo": "0.7.28"})
    pypi_fn = _pypi({"scitex-todo": "0.8.4"})
    # Act
    warnings = check_critical_package_drift(
        packages=("scitex-todo",),
        installed_fn=installed_fn,
        pypi_fn=pypi_fn,
        local_path_fn=_NO_LOCAL_CHECKOUT,
    )
    # Assert
    assert warnings[0].installed == "0.7.28"


def test_behind_package_warning_carries_reference_version():
    # Arrange
    installed_fn = _installed({"scitex-todo": "0.7.28"})
    pypi_fn = _pypi({"scitex-todo": "0.8.4"})
    # Act
    warnings = check_critical_package_drift(
        packages=("scitex-todo",),
        installed_fn=installed_fn,
        pypi_fn=pypi_fn,
        local_path_fn=_NO_LOCAL_CHECKOUT,
    )
    # Assert
    assert warnings[0].reference == "0.8.4"


def test_behind_package_warning_carries_pypi_reference_source():
    # Arrange — no local checkout injected, so the reference must fall back to PyPI
    installed_fn = _installed({"scitex-todo": "0.7.28"})
    pypi_fn = _pypi({"scitex-todo": "0.8.4"})
    # Act
    warnings = check_critical_package_drift(
        packages=("scitex-todo",),
        installed_fn=installed_fn,
        pypi_fn=pypi_fn,
        local_path_fn=_NO_LOCAL_CHECKOUT,
    )
    # Assert
    assert warnings[0].reference_source == "pypi"


def test_local_checkout_reference_is_preferred_over_pypi():
    # Arrange — a local checkout IS available; it must win over the PyPI fallback
    installed_fn = _installed({"scitex-todo": "0.7.28"})
    pypi_fn = _pypi({"scitex-todo": "0.7.28"})  # would look "current" via PyPI alone
    local_path_fn = lambda pkg: _FakeLocalPath()  # noqa: E731
    toml_fn = lambda path: "0.8.5"  # noqa: E731
    # Act
    warnings = check_critical_package_drift(
        packages=("scitex-todo",),
        installed_fn=installed_fn,
        pypi_fn=pypi_fn,
        local_path_fn=local_path_fn,
        toml_fn=toml_fn,
    )
    # Assert — behind the LOCAL checkout's 0.8.5, not the (stale) PyPI 0.7.28
    assert warnings[0].reference_source == "local-checkout"


def test_local_checkout_reference_value_wins_over_pypi():
    # Arrange
    installed_fn = _installed({"scitex-todo": "0.7.28"})
    pypi_fn = _pypi({"scitex-todo": "0.7.28"})
    local_path_fn = lambda pkg: _FakeLocalPath()  # noqa: E731
    toml_fn = lambda path: "0.8.5"  # noqa: E731
    # Act
    warnings = check_critical_package_drift(
        packages=("scitex-todo",),
        installed_fn=installed_fn,
        pypi_fn=pypi_fn,
        local_path_fn=local_path_fn,
        toml_fn=toml_fn,
    )
    # Assert
    assert warnings[0].reference == "0.8.5"


def test_current_package_is_not_reported():
    # Arrange
    installed_fn = _installed({"scitex-todo": "0.8.4"})
    pypi_fn = _pypi({"scitex-todo": "0.8.4"})
    # Act
    warnings = check_critical_package_drift(
        packages=("scitex-todo",),
        installed_fn=installed_fn,
        pypi_fn=pypi_fn,
        local_path_fn=_NO_LOCAL_CHECKOUT,
    )
    # Assert
    assert warnings == []


def test_ahead_of_reference_is_not_reported():
    # Arrange — local install newer than PyPI (about to be released) is not "behind"
    installed_fn = _installed({"scitex-todo": "0.9.0"})
    pypi_fn = _pypi({"scitex-todo": "0.8.4"})
    # Act
    warnings = check_critical_package_drift(
        packages=("scitex-todo",),
        installed_fn=installed_fn,
        pypi_fn=pypi_fn,
        local_path_fn=_NO_LOCAL_CHECKOUT,
    )
    # Assert
    assert warnings == []


def test_not_installed_is_silently_skipped():
    # Arrange — package absent from this interpreter entirely
    installed_fn = _installed({})
    pypi_fn = _pypi({"scitex-todo": "0.8.4"})
    # Act
    warnings = check_critical_package_drift(
        packages=("scitex-todo",),
        installed_fn=installed_fn,
        pypi_fn=pypi_fn,
        local_path_fn=_NO_LOCAL_CHECKOUT,
    )
    # Assert — unknown is never reported as drift
    assert warnings == []


def test_reference_unavailable_is_silently_skipped():
    # Arrange — installed, but PyPI lookup fails too (offline) and no local checkout
    installed_fn = _installed({"scitex-todo": "0.7.28"})
    pypi_fn = _pypi({})
    # Act
    warnings = check_critical_package_drift(
        packages=("scitex-todo",),
        installed_fn=installed_fn,
        pypi_fn=pypi_fn,
        local_path_fn=_NO_LOCAL_CHECKOUT,
    )
    # Assert — no reference to compare against is unknown, not drift
    assert warnings == []


def test_pep440_equivalent_versions_are_not_drift():
    # Arrange — '0.8.4-alpha' and '0.8.4a0' are the same PEP 440 version
    installed_fn = _installed({"scitex-todo": "0.8.4a0"})
    pypi_fn = _pypi({"scitex-todo": "0.8.4-alpha"})
    # Act
    warnings = check_critical_package_drift(
        packages=("scitex-todo",),
        installed_fn=installed_fn,
        pypi_fn=pypi_fn,
        local_path_fn=_NO_LOCAL_CHECKOUT,
    )
    # Assert
    assert warnings == []


def test_checks_only_the_given_packages_not_the_whole_ecosystem():
    # Arrange — scitex-io is stale too, but not in the critical list passed in
    installed_fn = _installed({"scitex-todo": "0.8.4", "scitex-io": "0.1.0"})
    pypi_fn = _pypi({"scitex-todo": "0.8.4", "scitex-io": "9.0.0"})
    # Act
    warnings = check_critical_package_drift(
        packages=("scitex-todo",),
        installed_fn=installed_fn,
        pypi_fn=pypi_fn,
        local_path_fn=_NO_LOCAL_CHECKOUT,
    )
    # Assert
    assert warnings == []


def test_default_packages_include_scitex_todo():
    # Arrange — CRITICAL_PACKAGES is the module's default list
    packages = CRITICAL_PACKAGES
    # Act — membership check IS the behaviour under test
    present = "scitex-todo" in packages
    # Assert — scitex-todo must never fall out of the default list by accident
    assert present is True


def test_default_packages_include_scitex_agent_container():
    # Arrange
    packages = CRITICAL_PACKAGES
    # Act
    present = "scitex-agent-container" in packages
    # Assert
    assert present is True


def test_default_packages_include_scitex_dev():
    # Arrange
    packages = CRITICAL_PACKAGES
    # Act
    present = "scitex-dev" in packages
    # Assert
    assert present is True


def test_multiple_packages_each_evaluated_independently():
    # Arrange
    installed_fn = _installed({"scitex-todo": "0.7.28", "scitex-agent-container": "0.21.13"})
    pypi_fn = _pypi({"scitex-todo": "0.8.4", "scitex-agent-container": "0.21.13"})
    # Act
    warnings = check_critical_package_drift(
        packages=("scitex-todo", "scitex-agent-container"),
        installed_fn=installed_fn,
        pypi_fn=pypi_fn,
        local_path_fn=_NO_LOCAL_CHECKOUT,
    )
    # Assert — only the actually-behind package is reported
    assert [w.package for w in warnings] == ["scitex-todo"]


# ── render_package_drift_banner ─────────────────────────────────────────────


def test_banner_empty_when_no_warnings():
    # Arrange
    warnings = []
    # Act
    text = render_package_drift_banner(warnings)
    # Assert
    assert text == ""


def test_banner_flags_as_a_package_drift_warning():
    # Arrange
    warnings = [
        PackageDriftWarning(
            package="scitex-todo",
            installed="0.7.28",
            reference="0.8.4",
            reference_source="pypi",
        )
    ]
    # Act
    text = render_package_drift_banner(warnings)
    # Assert
    assert "PACKAGE-DRIFT WARNING" in text


def test_banner_names_the_stale_package():
    # Arrange
    warnings = [
        PackageDriftWarning(
            package="scitex-todo",
            installed="0.7.28",
            reference="0.8.4",
            reference_source="pypi",
        )
    ]
    # Act
    text = render_package_drift_banner(warnings)
    # Assert
    assert "scitex-todo" in text


def test_banner_shows_installed_version():
    # Arrange
    warnings = [
        PackageDriftWarning(
            package="scitex-todo",
            installed="0.7.28",
            reference="0.8.4",
            reference_source="pypi",
        )
    ]
    # Act
    text = render_package_drift_banner(warnings)
    # Assert
    assert "0.7.28" in text


def test_banner_shows_reference_version():
    # Arrange
    warnings = [
        PackageDriftWarning(
            package="scitex-todo",
            installed="0.7.28",
            reference="0.8.4",
            reference_source="pypi",
        )
    ]
    # Act
    text = render_package_drift_banner(warnings)
    # Assert
    assert "0.8.4" in text


def test_warning_to_dict_roundtrips_fields():
    # Arrange
    w = PackageDriftWarning(
        package="scitex-todo",
        installed="0.7.28",
        reference="0.8.4",
        reference_source="pypi",
    )
    # Act
    d = w.to_dict()
    # Assert
    assert d == {
        "package": "scitex-todo",
        "installed": "0.7.28",
        "reference": "0.8.4",
        "reference_source": "pypi",
    }


# EOF
