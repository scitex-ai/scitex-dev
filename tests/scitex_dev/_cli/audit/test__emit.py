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

EXCEPT FOR audit-cli, which is asserted on BEHAVIOUR instead. Its renderer
now takes the category as a required argument (because `_mcp_audit.py`
reuses it and was inheriting "CLI convention" from a default, printing that
noun for a population it had not audited). So no literal ": CLI conventions: "
exists in any source file to grep for — a source check would report the
property missing while the behaviour is correct. That auditor is cheap to
provoke, needing one `Violation` rather than a package fixture, so the
stronger assertion is also the affordable one here.
"""

from __future__ import annotations

import inspect
import logging

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


def test_cli_failure_headline_names_its_category(caplog):
    """audit-cli names 'CLI conventions' on the failure line.

    Asserts the RENDERED line, not the module source. The other cases in
    this file grep `inspect.getsource` for a literal, which worked while
    each auditor hardcoded its own noun. `_emit_human` now takes the noun
    as a required argument, so no literal ": CLI conventions: " exists in
    any source file to find — and a source check would have reported this
    property missing while the behaviour was correct.

    That is the same substring-versus-behaviour trap this rule exists to
    catch elsewhere: a scan keyed on the presence of a STRING reads the
    absence of the string as the absence of the property.
    """
    # Arrange
    from scitex_dev._cli.audit._summary._run import _emit_human
    from scitex_dev._cli.audit._summary._audit import Violation

    violations = [Violation("scitex-dev", "§10", "import budget blown")]
    # Act
    with caplog.at_level(logging.INFO):
        _emit_human(
            "scitex-dev", "warn", violations, category="CLI convention"
        )
    # Assert
    assert any(": CLI conventions: " in r.getMessage() for r in caplog.records)


def test_the_renderer_refuses_to_guess_which_auditor_it_speaks_for():
    """Omitting `category` is a TypeError, not a borrowed noun.

    The MCP auditor reused this renderer and inherited "CLI convention"
    from a default, printing another leg's verdict for a population it had
    not audited (measured 2026-08-16). Making the argument required turns
    that class of mistake into a failure at the call site.
    """
    # Arrange
    from scitex_dev._cli.audit._summary._run import _emit_human

    # Act
    caught = pytest.raises(TypeError)
    # Assert
    with caught:
        _emit_human("scitex-dev", "ok", [])
