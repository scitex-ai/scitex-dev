"""Tests for `audit.skip-rules` parsing + rationale enforcement.

The load-bearing behaviour is the REJECTION: a skip entry with no written
rationale must fail loudly, naming the offending entry. A deferral that
cannot say why is the abandonment the mechanism exists to catch, so
"parses fine, silently honoured" is the defect, not the feature.
"""

from __future__ import annotations

import pytest

from scitex_dev._cli.audit._config._skip_rules import (
    SkipRule,
    SkipRuleConfigError,
    load_skip_rules,
    parse_skip_rules,
)


def _rejection_message(raw) -> str:
    """Return the rejection text for `raw`, or "" if it was accepted.

    Lets a test assert ONCE on the message while still proving the call
    was rejected — an accepted input yields "" and fails the membership
    assertion.
    """
    try:
        parse_skip_rules(raw)
    except SkipRuleConfigError as exc:
        return str(exc)
    return ""


def _write_config(repo, body: str):
    cfg = repo / ".scitex" / "dev" / "config.yaml"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(body, encoding="utf-8")
    return cfg


# --------------------------------------------------------------------- #
# Accepted shapes                                                        #
# --------------------------------------------------------------------- #


def test_mapping_form_parses_rule_and_reason():
    """`{rule: reason}` yields one entry carrying the written rationale."""
    # Arrange
    raw = {"PS-139": "TQ-migration campaign — tracked in scitex-hub#412"}
    # Act
    entries = parse_skip_rules(raw)
    # Assert
    assert entries == [
        SkipRule("PS-139", "TQ-migration campaign — tracked in scitex-hub#412")
    ]


def test_list_of_mappings_form_parses():
    """`[{rule: ..., reason: ...}]` is the equivalent long form."""
    # Arrange
    raw = [{"rule": "PS-202", "reason": "CLI noun-verb migration"}]
    # Act
    entries = parse_skip_rules(raw)
    # Assert
    assert entries == [SkipRule("PS-202", "CLI noun-verb migration")]


def test_section_rule_ids_survive_parsing():
    """Section-style ids (`§6`) are legal rule ids, not just `PS-nnn`."""
    # Arrange
    raw = {"§6": "MCP parity lands with the umbrella-thinning wave"}
    # Act
    entries = parse_skip_rules(raw)
    # Assert
    assert entries[0].rule == "§6"


def test_absent_block_yields_no_entries():
    """A repo declaring nothing defers nothing."""
    # Arrange
    raw = None
    # Act
    entries = parse_skip_rules(raw)
    # Assert
    assert entries == []


# --------------------------------------------------------------------- #
# Rejected shapes — the rationale requirement                            #
# --------------------------------------------------------------------- #


def test_bare_rule_id_without_rationale_is_rejected():
    """A bare id says WHAT is deferred but never WHY — reject it."""
    # Arrange
    raw = ["PS-139"]
    # Act
    act = lambda: parse_skip_rules(raw)  # noqa: E731
    # Assert
    with pytest.raises(SkipRuleConfigError):
        act()


def test_bare_rule_id_rejection_names_the_offending_entry():
    """The error must name the entry so the fix is mechanical."""
    # Arrange
    raw = ["PS-139"]
    # Act
    message = _rejection_message(raw)
    # Assert
    assert "PS-139" in message


def test_empty_reason_is_rejected():
    """An empty rationale is no rationale."""
    # Arrange
    raw = {"PS-139": ""}
    # Act
    act = lambda: parse_skip_rules(raw)  # noqa: E731
    # Assert
    with pytest.raises(SkipRuleConfigError):
        act()


def test_empty_reason_rejection_names_the_offending_entry():
    """Naming the rule is what makes the failure actionable."""
    # Arrange
    raw = {"PS-139": ""}
    # Act
    message = _rejection_message(raw)
    # Assert
    assert "PS-139" in message


def test_whitespace_only_reason_is_rejected():
    """`"   "` must not buy a silent pass that `""` is denied."""
    # Arrange
    raw = {"PS-204": "   "}
    # Act
    act = lambda: parse_skip_rules(raw)  # noqa: E731
    # Assert
    with pytest.raises(SkipRuleConfigError):
        act()


def test_whitespace_only_rejection_names_the_offending_entry():
    """A whitespace park still names which entry to fix."""
    # Arrange
    raw = {"PS-204": "   "}
    # Act
    message = _rejection_message(raw)
    # Assert
    assert "PS-204" in message


def test_missing_reason_key_in_list_form_is_rejected():
    """The long form must carry `reason:`, not just `rule:`."""
    # Arrange
    raw = [{"rule": "PS-302"}]
    # Act
    act = lambda: parse_skip_rules(raw)  # noqa: E731
    # Assert
    with pytest.raises(SkipRuleConfigError):
        act()


def test_missing_reason_key_rejection_names_the_offending_entry():
    """Long-form rejections name the rule too."""
    # Arrange
    raw = [{"rule": "PS-302"}]
    # Act
    message = _rejection_message(raw)
    # Assert
    assert "PS-302" in message


def test_entry_without_rule_key_is_rejected():
    """An entry with a reason but no rule id defers nothing identifiable."""
    # Arrange
    raw = [{"reason": "because"}]
    # Act
    act = lambda: parse_skip_rules(raw)  # noqa: E731
    # Assert
    with pytest.raises(SkipRuleConfigError):
        act()


def test_non_string_reason_is_rejected():
    """A truthy non-string (e.g. `true`) is not a written rationale."""
    # Arrange
    raw = {"PS-139": True}
    # Act
    act = lambda: parse_skip_rules(raw)  # noqa: E731
    # Assert
    with pytest.raises(SkipRuleConfigError):
        act()


# --------------------------------------------------------------------- #
# Config-file integration                                                #
# --------------------------------------------------------------------- #


def test_load_skip_rules_reads_the_repo_config(tmp_path):
    """`audit-all` sources deferrals from `<repo>/.scitex/dev/config.yaml`."""
    # Arrange
    _write_config(
        tmp_path,
        'audit:\n  skip-rules:\n    PS-139: "TQ-migration campaign"\n',
    )
    # Act
    entries = load_skip_rules(tmp_path)
    # Assert
    assert entries == [SkipRule("PS-139", "TQ-migration campaign")]


def test_load_skip_rules_on_repo_without_config(tmp_path):
    """No config file is not an error — it declares no deferrals."""
    # Arrange
    repo = tmp_path
    # Act
    entries = load_skip_rules(repo)
    # Assert
    assert entries == []


def test_load_skip_rules_rejects_rationale_less_config(tmp_path):
    """A rationale-less config must fail loudly, not degrade to 'no skips'."""
    # Arrange
    _write_config(tmp_path, "audit:\n  skip-rules:\n    - PS-139\n")
    # Act
    act = lambda: load_skip_rules(tmp_path)  # noqa: E731
    # Assert
    with pytest.raises(SkipRuleConfigError):
        act()


def test_legacy_audit_skip_list_still_loads(tmp_path):
    """The legacy bare `audit.skip` knob is untouched by this change."""
    # Arrange
    _write_config(tmp_path, "audit:\n  skip:\n    - PS-108\n")
    from scitex_dev._cli.audit._config._loader import load_config

    # Act
    cfg = load_config(tmp_path)
    # Assert
    assert "PS-108" in cfg.skip


def test_legacy_audit_skip_list_is_not_read_as_skip_rules(tmp_path):
    """`audit.skip` and `audit.skip-rules` are distinct keys."""
    # Arrange
    _write_config(tmp_path, "audit:\n  skip:\n    - PS-108\n")
    # Act
    entries = load_skip_rules(tmp_path)
    # Assert
    assert entries == []
