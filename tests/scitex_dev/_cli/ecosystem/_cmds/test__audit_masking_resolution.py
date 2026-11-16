"""Unresolved targets and unexpected resolver failures are different outcomes."""

import pytest

from scitex_dev._cli.audit._config._skip_rules import SkipRule
from scitex_dev._cli.ecosystem._cmds._audit_masking import resolve_skip_rules


def test_unknown_distribution_has_no_declarations():
    # Arrange
    name = "scitex-owned-unresolvable-fixture-ae95d7"
    # Act
    result = resolve_skip_rules([name], None)
    # Assert
    assert result == {name: []}


def test_unexpected_resolver_failure_is_not_empty_declarations():
    # Arrange: invalid internal input makes the real name resolver fail.
    distributions = [None]
    # Act
    # Assert: refuse the invalid input instead of returning an empty inventory.
    with pytest.raises(AttributeError, match="strip"):
        resolve_skip_rules(distributions, None)


def test_explicit_target_retains_its_declared_rules(tmp_path):
    # Arrange: owned configuration fixture, not a repository waiver.
    config = tmp_path / ".scitex/dev/config.yaml"
    config.parent.mkdir(parents=True)
    config.write_text('audit:\n  skip-rules:\n    PA-307: "owned resolution fixture"\n')
    # Act
    result = resolve_skip_rules(["owned-fixture"], tmp_path)
    # Assert
    assert result == {
        "owned-fixture": [SkipRule(rule="PA-307", reason="owned resolution fixture")]
    }
