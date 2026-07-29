"""The rule corpus assembles correctly from its per-section literal modules.

These pin the properties the 1286-line -> package split could plausibly have
broken. `test__registry_severity_overrides.py` (one directory up) already pins
the ORDERING invariant — that `_patch` runs after every co-located merge — by
reading this package's source; these tests cover the assembly itself.
"""

from __future__ import annotations

import pytest

from scitex_dev._cli.audit._project import _registry, _rules
from scitex_dev._cli.audit._project._rules._rule import Rule
from scitex_dev._cli.audit._project._rules._s1_layout import RULES_S1_LAYOUT
from scitex_dev._cli.audit._project._rules._s1_readme_extended import (
    RULES_S1_README_EXTENDED,
)
from scitex_dev._cli.audit._project._rules._s2_src_tests import RULES_S2_SRC_TESTS
from scitex_dev._cli.audit._project._rules._s3_tests_examples import (
    RULES_S3_TESTS_EXAMPLES,
)
from scitex_dev._cli.audit._project._rules._s4_docs import RULES_S4_DOCS

_SECTIONS = {
    "_s1_layout": RULES_S1_LAYOUT,
    "_s1_readme_extended": RULES_S1_README_EXTENDED,
    "_s2_src_tests": RULES_S2_SRC_TESTS,
    "_s3_tests_examples": RULES_S3_TESTS_EXAMPLES,
    "_s4_docs": RULES_S4_DOCS,
}

_SECTION_NAMES = sorted(_SECTIONS)


@pytest.mark.parametrize("name", _SECTION_NAMES)
def test_every_section_module_contributes_at_least_one_rule(name):
    # Arrange
    section = _SECTIONS[name]
    # Act
    # Assert — an empty section means a seam landed in the wrong place and the
    # rules silently vanished from the corpus.
    assert section, f"{name} contributed no rules"


@pytest.mark.parametrize("name", _SECTION_NAMES)
def test_every_section_entry_is_a_rule_instance(name):
    # Arrange
    section = _SECTIONS[name]
    # Act
    non_rules = [r for r in section if not isinstance(r, Rule)]
    # Assert
    assert non_rules == []


def test_no_rule_code_is_defined_in_two_sections():
    # Arrange
    seen: dict[str, str] = {}
    duplicates: dict[str, tuple[str, str]] = {}
    # Act
    for name, section in _SECTIONS.items():
        for rule in section:
            if rule.code in seen:
                duplicates[rule.code] = (seen[rule.code], name)
            seen[rule.code] = name
    # Assert — the dict comprehension that builds RULES silently keeps the LAST
    # of any duplicate pair, so a code in two sections loses one definition
    # without any error.
    assert duplicates == {}


def test_every_section_rule_reaches_the_assembled_corpus():
    # Arrange
    declared = {r.code for section in _SECTIONS.values() for r in section}
    # Act
    missing = declared - set(_rules.RULES)
    # Assert
    assert missing == set()


def test_registry_reexports_the_same_rules_mapping():
    # Arrange
    # Act
    # Assert — `_registry` is a thin re-export kept for existing call sites;
    # if it diverged, half the codebase would grade against a stale corpus.
    assert _registry.RULES is _rules.RULES


def test_registry_reexports_the_same_rule_class():
    # Arrange
    # Act
    # Assert
    assert _registry.Rule is _rules.Rule


def test_a_colocated_rule_is_absent_from_the_literal_sections():
    # Arrange — PS-220 ships from `_check_no_print`, not from any `_s*.py`.
    # Act
    literal_codes = {r.code for section in _SECTIONS.values() for r in section}
    # Assert
    assert "PS-220" not in literal_codes


def test_a_colocated_rule_is_merged_into_the_corpus():
    # Arrange
    # Act
    # Assert — proves the co-located merge ran, not just the literal assembly.
    assert "PS-220" in _rules.RULES


def test_the_severity_table_reaches_a_literal_rule():
    # Arrange — PS-101 is declared without an explicit severity and promoted to
    # E by `_SEVERITY_OVERRIDES`; the cheapest end-to-end proof that the
    # override pass ran over the literal sections after assembly.
    # Act
    rule = _rules.RULES["PS-101"]
    # Assert
    assert rule.severity == "E"


def test_ps140_remediation_does_not_name_a_tmp_path():
    # Arrange — this rule's message used to tell readers to run
    # `python /tmp/write-integration-tests.py <pkg-dir>`, a path in a
    # world-writable directory that shipped nowhere.
    # Act
    message = _rules.RULES["PS-140"].message
    # Assert
    assert "/tmp/" not in message


def test_ps140_remediation_names_the_real_generator_verb():
    # Arrange
    # Act
    message = _rules.RULES["PS-140"].message
    # Assert
    assert "install-cross-package-gate" in message

# EOF
