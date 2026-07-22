# -*- coding: utf-8 -*-
"""Regression: `_SEVERITY_OVERRIDES` must be honest for EVERY registered rule.

`_registry.py` builds `RULES` in two phases: a big literal dict, then a
series of merges that pull in co-located / sidecar rule sets
(`_extra_rules`, `_check_precommit_hooks`, `_check_no_url_deps`,
`_check_skills_federation`, `_check_doctor_health_naming`,
`_check_version_flag`, `_check_no_print`, `_check_extras_all_closure`).

`_patch` — which applies `_SEVERITY_OVERRIDES` and `_SLUGS` — used to run
BETWEEN those two phases. Every rule merged afterwards therefore silently
ignored the override table: adding `"PS-220": "E"` to `_SEVERITY_OVERRIDES`
did nothing at all, with no error and no warning. 31 rules were affected.

That is the same class of defect as the rule it was hiding: a severity table
that silently drops entries is itself a gate that cannot fail. These tests
pin the fix from both sides — structurally (the statement order in the
module source) and behaviourally (re-executing the module with an injected
override for a late-merged rule and observing it take effect).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from scitex_dev._cli.audit._project import _registry

_SOURCE = Path(_registry.__file__).read_text(encoding="utf-8")

# The statement that applies the override table.
_APPLY_RE = re.compile(r"^RULES = \{code: _patch\(rule\) for code, rule in RULES", re.M)
# The merge loops that register co-located / sidecar rule sets.
_MERGE_RE = re.compile(r"^\s+RULES\[_c\] = Rule\(", re.M)

# Anchor for the behavioural test's injection. Asserted separately so a
# refactor that renames it fails loudly instead of silently no-op'ing.
_OVERRIDES_ANCHOR = "_SEVERITY_OVERRIDES: dict[str, str] = {"

# A rule that is merged LATE (from `_check_no_print`), i.e. exactly the class
# of rule the trap made unreachable.
_LATE_RULE = "PS-220"

# The severity injected by the behavioural test. It MUST differ from the
# rule's own registered severity, or the test is a tautology that passes even
# under the broken ordering. PS-220 is registered at "W" (its staged-rollout
# default), so the injection promotes it to "E".
_INJECTED_SEVERITY = "E"


# --- structural: the apply must come after every merge ----------------------


def test_registry_applies_overrides_exactly_once():
    # Arrange
    # Act
    matches = _APPLY_RE.findall(_SOURCE)
    # Assert
    assert len(matches) == 1


def test_registry_applies_overrides_after_every_merge():
    # Arrange
    apply_at = _APPLY_RE.search(_SOURCE).start()
    # Act
    last_merge_at = max(m.start() for m in _MERGE_RE.finditer(_SOURCE))
    # Assert — a merge after the apply is a rule the override table cannot see
    assert apply_at > last_merge_at


def test_late_merged_rule_is_registered_at_all():
    # Arrange
    # Act
    codes = set(_registry.RULES)
    # Assert
    assert _LATE_RULE in codes


# --- invariant: every override entry actually took effect --------------------


def test_every_severity_override_is_reflected_in_rules():
    # Arrange
    overrides = _registry._SEVERITY_OVERRIDES
    # Act
    mismatched = {
        code: (_registry.RULES[code].severity, want)
        for code, want in overrides.items()
        if code in _registry.RULES and _registry.RULES[code].severity != want
    }
    # Assert
    assert mismatched == {}


def test_every_slug_entry_is_reflected_in_rules():
    # Arrange
    slugs = _registry._SLUGS
    # Act
    missing = {
        code
        for code, want in slugs.items()
        if code in _registry.RULES and _registry.RULES[code].slug != want
    }
    # Assert
    assert missing == set()


# --- behavioural: an injected override for a LATE-merged rule takes effect ---


def _exec_registry_with_override(code: str, severity: str) -> dict:
    """Re-execute `_registry.py` with `{code: severity}` prepended to the table.

    Executes the real module source in a fresh namespace (relative imports
    resolve because `__package__` is set), so this exercises the actual
    ordering of the module body rather than a reimplementation of it.
    """
    injected = _SOURCE.replace(
        _OVERRIDES_ANCHOR,
        f'{_OVERRIDES_ANCHOR}\n    "{code}": "{severity}",',
        1,
    )
    assert injected != _SOURCE, "override-table anchor not found; test is stale"
    ns: dict = {
        "__name__": _registry.__name__,
        "__file__": _registry.__file__,
        "__package__": _registry.__package__,
    }
    exec(compile(injected, _registry.__file__, "exec"), ns)
    return ns["RULES"]


def test_injected_severity_differs_from_the_rules_registered_one():
    # Arrange — guards the two tests below from becoming tautologies
    # Act
    registered = _registry.RULES[_LATE_RULE].severity
    # Assert
    assert registered != _INJECTED_SEVERITY


def test_injected_override_reaches_a_late_merged_rule():
    # Arrange — promote PS-220 to E purely inside the re-executed namespace.
    # Under the old ordering this had NO effect; PS-220 kept its co-located
    # severity and the table lied.
    # Act
    rules = _exec_registry_with_override(_LATE_RULE, _INJECTED_SEVERITY)
    # Assert
    assert rules[_LATE_RULE].severity == _INJECTED_SEVERITY


def test_injected_override_does_not_mutate_the_live_registry():
    # Arrange
    before = _registry.RULES[_LATE_RULE].severity
    # Act
    _exec_registry_with_override(_LATE_RULE, _INJECTED_SEVERITY)
    # Assert
    assert _registry.RULES[_LATE_RULE].severity == before


@pytest.mark.parametrize("severity", ["E", "W", "I"])
def test_injected_override_applies_each_severity_level(severity):
    # Arrange
    # Act
    rules = _exec_registry_with_override(_LATE_RULE, severity)
    # Assert
    assert rules[_LATE_RULE].severity == severity


# EOF
