#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/scitex_dev/_cli/audit/_project/test__gate_skip_scope.py

"""A skip on the ROOT is legitimate; a skip on the FULL path hides renames.

The check under test has TWO ways to be useless, and the tests below are
split evenly between them rather than piled on the first:

    always-True  -> flags legitimate root-level skips, so 19 repos get a
                    finding they must not act on, and the rule gets disabled
    always-False -> flags nothing, and the fleet-wide defect stays invisible
                    while an audit rule exists that claims to cover it

The second is the one that looks like success. scitex-hpc caught exactly this
in their own guard an hour before these were written: it asserted over a repo
whose dependencies carry no markers, so it evaluated `[] == []` and would have
passed against a predicate that always returned True.
"""

from __future__ import annotations

from scitex_dev._cli.audit._project._gate_skip_scope import find_full_path_skips

PARAMETRIZED = '''
import importlib
import pytest

CROSS_PACKAGE_IMPORTS = ["scitex_io._cache"]


@pytest.mark.parametrize("module_name", CROSS_PACKAGE_IMPORTS)
def test_it(module_name):
    pytest.importorskip(module_name)
    importlib.import_module(module_name)
'''

ROOT_ONLY = '''
import importlib
import pytest

CROSS_PACKAGE_IMPORTS = ["scitex_io._cache"]


@pytest.mark.parametrize("module_name", CROSS_PACKAGE_IMPORTS)
def test_it(module_name):
    pytest.importorskip(module_name.split(".")[0])
    importlib.import_module(module_name)
'''


def test_a_parametrized_skip_is_flagged():
    """This is the shape all 19 deployed gates carry."""
    # Arrange
    source = PARAMETRIZED
    # Act
    found = find_full_path_skips(source)
    # Assert
    assert len(found) == 1


def test_the_flagged_call_reports_its_line():
    """A finding without a line makes the reader search the file.

    The expected line is derived from the fixture rather than hard-coded: my
    first version asserted 11 against a call on line 10 and failed for a
    reason that had nothing to do with the code under test. A literal here
    breaks whenever the fixture gains a line, which trains people to
    re-baseline the number instead of reading the failure.
    """
    # Arrange
    expected = next(
        i
        for i, line in enumerate(PARAMETRIZED.splitlines(), 1)
        if "importorskip" in line
    )
    # Act
    found = find_full_path_skips(PARAMETRIZED)
    # Assert
    assert found[0].line == expected


def test_a_root_only_skip_is_NOT_flagged():
    """The control against an always-True check.

    Root-skip is the CORRECT form. Flagging it would hand 19 repos a finding
    they must not act on, and a rule that cries wolf gets exempted rather
    than fixed.
    """
    # Arrange
    source = ROOT_ONLY
    # Act
    found = find_full_path_skips(source)
    # Assert
    assert found == ()


def test_a_bare_root_literal_is_NOT_flagged():
    """`importorskip("django")` is an absent third-party peer, not a rename."""
    # Arrange
    source = 'import pytest\npytest.importorskip("django")\n'
    # Act
    found = find_full_path_skips(source)
    # Assert
    assert found == ()


def test_a_dotted_literal_IS_flagged():
    """A literal submodule skip hides the same rename the variable form does."""
    # Arrange
    source = 'import pytest\npytest.importorskip("scitex_app._django")\n'
    # Act
    found = find_full_path_skips(source)
    # Assert
    assert len(found) == 1


def test_the_parametrize_variable_name_is_not_hard_coded():
    """The deployed gates do not agree on the variable's spelling.

    Hard-coding `module_name` would silently pass every gate that named it
    something else — a check that cannot fail, added while fixing a gate that
    cannot fail.
    """
    # Arrange
    source = PARAMETRIZED.replace("module_name", "mod_path")
    # Act
    found = find_full_path_skips(source)
    # Assert
    assert len(found) == 1


def test_an_unrelated_local_variable_is_not_flagged():
    """Only names BOUND BY parametrize carry the full path."""
    # Arrange
    source = (
        "import pytest\n"
        "def test_it():\n"
        "    name = 'django'\n"
        "    pytest.importorskip(name)\n"
    )
    # Act
    found = find_full_path_skips(source)
    # Assert
    assert found == ()


def test_a_clean_gate_yields_nothing():
    # Arrange
    source = "CROSS_PACKAGE_IMPORTS = ['scitex_io']\n"
    # Act
    found = find_full_path_skips(source)
    # Assert
    assert found == ()


def test_an_unparseable_gate_does_not_double_report():
    """PS-140 already reports an unparseable gate through its own path."""
    # Arrange
    source = "def broken( :\n"
    # Act
    found = find_full_path_skips(source)
    # Assert
    assert found == ()


# EOF
