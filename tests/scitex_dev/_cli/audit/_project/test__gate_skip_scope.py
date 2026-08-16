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


def test_an_alias_of_the_parametrize_variable_is_still_reported():
    """The shape that defeated the first version, measured on three repos.

    scitex-logging, figrecipe and scitex-notification all do
    `name = module_name` then `importorskip(name)`. The first version asked
    "can I prove this is a full-path skip?" and stayed SILENT when it could
    not — reporting all three CLEAN while they skipped on the full path.
    scitex-hpc predicted this under review; the measurement confirmed it on
    the same three files minutes later.
    """
    # Arrange
    source = (
        "import pytest\n"
        "def test_it(module_name):\n"
        "    name = module_name\n"
        "    pytest.importorskip(name)\n"
    )
    # Act
    found = find_full_path_skips(source)
    # Assert
    assert len(found) == 1


def test_an_uninterpretable_argument_is_marked_undetermined():
    """Reported, and reported as what it is — not silently promoted."""
    # Arrange
    source = (
        "import pytest\n"
        "def test_it(module_name):\n"
        "    name = module_name\n"
        "    pytest.importorskip(name)\n"
    )
    # Act
    found = find_full_path_skips(source)
    # Assert
    assert found[0].determined is False


def test_a_loop_target_is_reported():
    """hpc's shape 4: a hand-written gate looping over the list."""
    # Arrange
    source = (
        "import pytest\n"
        "CROSS_PACKAGE_IMPORTS = ['scitex_io._cache']\n"
        "def test_all():\n"
        "    for name in CROSS_PACKAGE_IMPORTS:\n"
        "        pytest.importorskip(name)\n"
    )
    # Act
    found = find_full_path_skips(source)
    # Assert
    assert len(found) == 1


def test_comma_form_argnames_still_resolve():
    """hpc's shape 1: pytest accepts one comma-separated argnames string."""
    # Arrange
    source = (
        "import pytest\n"
        '@pytest.mark.parametrize("module_name,expected", [])\n'
        "def test_it(module_name, expected):\n"
        "    pytest.importorskip(module_name)\n"
    )
    # Act
    found = find_full_path_skips(source)
    # Assert
    assert found[0].determined is True


def test_the_canonical_root_idiom_is_still_silent():
    """The control against the new default reporting everything.

    Inverting to "report unless provably root" is only safe if the proof
    actually recognises the correct form. If this test fails, every fixed
    repo stays red forever and the rule becomes one nobody can satisfy — a
    gate that cannot PASS.
    """
    # Arrange
    source = (
        "import pytest\n"
        "def test_it(module_name):\n"
        '    pytest.importorskip(module_name.split(".")[0])\n'
    )
    # Act
    found = find_full_path_skips(source)
    # Assert
    assert found == ()


def test_the_readable_two_line_fix_is_not_flagged():
    """The clearest spelling of the CORRECT answer must not be reported.

    This is scitex-hpc's fixed gate verbatim (develop, post-#88/#89):

        root = module_name.split(".")[0]
        pytest.importorskip(root)

    The first inversion flagged it "undetermined", because `root` is a local
    name it would not resolve. Flagging the most readable form of the fix
    would push people toward cramming it into one line to satisfy the
    checker — a rule that shapes code away from readability is doing harm,
    and it would have landed on the repo that fixed this first.
    """
    # Arrange
    source = (
        "import pytest\n"
        "def test_it(module_name):\n"
        '    root = module_name.split(".")[0]\n'
        "    pytest.importorskip(root)\n"
    )
    # Act
    found = find_full_path_skips(source)
    # Assert
    assert found == ()


def test_a_rooted_name_in_ANOTHER_function_does_not_silence_this_one():
    """Bindings are per-scope, or the fix reintroduces a false negative.

    A module-wide map would let `root = x.split(".")[0]` in one test silence
    a genuinely unsafe `importorskip(root)` in a different test — exactly the
    silent under-coverage this module was rewritten to eliminate.
    """
    # Arrange
    source = (
        "import pytest\n"
        "def test_safe(module_name):\n"
        '    root = module_name.split(".")[0]\n'
        "    pytest.importorskip(root)\n"
        "def test_unsafe(root):\n"
        "    pytest.importorskip(root)\n"
    )
    # Act
    found = find_full_path_skips(source)
    # Assert
    assert len(found) == 1


def test_prose_describing_the_hazard_is_not_itself_the_hazard():
    """A docstring explaining the defect must not be flagged AS the defect.

    Contributed by scitex-hpc, who noticed their own gate is a free
    discriminating fixture: two of its three `importorskip` occurrences are
    DOCUMENTATION, and line 220 literally reads "importorskip on the full
    path swallows ModuleNotFoundError" — the exact thing this rule hunts,
    written as an explanation of why it is wrong.

    An AST matcher passes it; a regex matcher fails the pilot repo on prose.
    The general form is theirs too: a control must match the PHENOMENON, not
    the VOCABULARY of the phenomenon — source, comments and docstrings share
    a vocabulary, which is why text checks match their own explanations.

    The sharp end: a rule that flags documentation about a defect teaches
    people to stop documenting the defect, which is worse than the bug. This
    test exists so a future refactor to a cheaper text match fails here
    rather than in 19 repositories.
    """
    # Arrange
    source = (
        '"""importorskip on the full path swallows ModuleNotFoundError.\n\n'
        "Do not write pytest.importorskip(module_name) — it hides renames.\n"
        '"""\n'
        "# pytest.importorskip(module_name) would be wrong here too\n"
        "CROSS_PACKAGE_IMPORTS = ['scitex_io']\n"
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
