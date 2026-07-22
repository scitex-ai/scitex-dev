"""Every auditor summary line must NAME its category — pass or fail.

The clean lines always did ("no project-structure violations"). The
FAILURE lines did not: audit-project printed a bare
`scitex-hub (/path): 3 error(s)`. In an audit-all log interleaving six
auditors that line is unattributable, and sac PRs #813 and #814 both
read a real violation as a broken gate because of it, costing a CI
cycle.

These tests read the emitted format strings from source rather than
provoking each auditor into a failing state, which would require six
package fixtures. The string IS the contract here.
"""

from __future__ import annotations

import inspect

import pytest


def _source_of(module_path: str, func_name: str) -> str:
    import importlib

    mod = importlib.import_module(module_path)
    return inspect.getsource(getattr(mod, func_name))


# (module, function, category label expected on the FAILURE headline)
_FAILURE_HEADLINES = [
    ("scitex_dev._cli.audit._project._audit", "audit_project", "project-structure"),
    ("scitex_dev._cli.audit._django._audit", "audit_django", "Django-standard"),
    ("scitex_dev._cli.audit._skills._audit", "audit_skills", "skills"),
]


@pytest.mark.parametrize("module_path, func_name, label", _FAILURE_HEADLINES)
def test_failure_headline_names_its_category(module_path, func_name, label):
    """A failing auditor must say WHICH audit failed."""
    # Arrange
    expected = f": {label}: "
    # Act
    src = _source_of(module_path, func_name)
    # Assert
    assert expected in src


def test_python_api_failure_headline_names_its_category():
    """audit-python-apis names 'Python API' on the failure line."""
    # Arrange
    expected = ": Python API: "
    # Act
    src = _source_of("scitex_dev._cli.audit._api._audit", "audit_api")
    # Assert
    assert expected in src


def test_cli_failure_headline_names_its_category():
    """audit-cli names 'CLI conventions' on the failure line."""
    # Arrange
    import scitex_dev._cli.audit._summary._run as run_mod

    expected = ": CLI conventions: "
    # Act
    src = inspect.getsource(run_mod)
    # Assert
    assert expected in src
