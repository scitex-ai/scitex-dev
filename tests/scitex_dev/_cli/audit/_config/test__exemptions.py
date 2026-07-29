"""`audit.exemptions` parsing — a config that cannot take effect must SAY SO.

Regression suite for the field defect scitex-hub hit within an hour of
v0.38.1: a non-mapping `exemptions:` block returned `(), ()`, so every
exemption the author wrote was dropped with NO output at all. Hub wrote the
LIST form and could only find out why nothing happened by downloading the
wheel and reading the parser source.

Every malformed shape must produce a notice that NAMES THE TYPE IT RECEIVED
and NAMES THE LIKELY MISTAKE. The POSITIVE CONTROL at the bottom is not
optional: a suite that only asserts the new errors would pass just as happily
on a parser that rejects everything.

No mocks (NM001-003): `parse_exemptions` is called with the REAL Python
values PyYAML hands it, and the end-to-end cases in `test__loader.py` go
through a REAL `.scitex/dev/config.yaml`. Nothing is patched.

One assert per test (STX-TQ007), Arrange/Act/Assert markers (STX-TQ002).
"""

from __future__ import annotations

import pytest

from scitex_dev._cli.audit._config._exemptions import (
    EXEMPTION_BLOCK_PREFIX,
    Exemption,
    exemption_notice_applies,
    format_exemption_notice,
    parse_exemptions,
)

#: Exactly what scitex-hub wrote — the shape the parser used to swallow.
_HUB_LIST_FORM = [
    {
        "rule": "PS-224",
        "path": ".github/workflows/e2e-mobile.yml::playwright-mobile",
        "reason": "mobile browsers ship only on the hosted image",
    }
]

#: The shape the parser actually wants.
_GOOD = {
    "PS-224": [
        {
            "path": ".github/workflows/e2e-mobile.yml::playwright-mobile",
            "line": 0,
            "reason": "mobile browsers ship only on the hosted image",
        }
    ]
}


def _errors(raw: object) -> tuple[str, ...]:
    return parse_exemptions(raw)[1]


def _accepted(raw: object) -> tuple[Exemption, ...]:
    return parse_exemptions(raw)[0]


# -------- block level: a non-mapping block is REPORTED, never dropped -------


def test_list_block_produces_a_notice():
    # Arrange — hub's spelling.
    # Act
    errors = _errors(_HUB_LIST_FORM)
    # Assert — the silent `(), ()` return is what shipped; anything but a
    # notice here is that bug.
    assert len(errors) == 1


def test_list_block_notice_names_the_received_type():
    # Arrange
    # Act
    errors = _errors(_HUB_LIST_FORM)
    # Assert
    assert "got a list" in errors[0]


def test_list_block_notice_names_the_expected_shape():
    # Arrange
    # Act
    errors = _errors(_HUB_LIST_FORM)
    # Assert
    assert "expected a mapping of rule-code -> [entries]" in errors[0]


def test_list_block_notice_names_the_likely_mistake():
    # Arrange — the message must hand back the fix, not just the diagnosis.
    # Act
    errors = _errors(_HUB_LIST_FORM)
    # Assert
    assert "Did you write `- rule: PS-224` instead of `PS-224:`?" in errors[0]


def test_list_block_accepts_nothing():
    # Arrange — the notice replaces the drop; it must not also start honouring
    # a shape the parser cannot read.
    # Act
    accepted = _accepted(_HUB_LIST_FORM)
    # Assert
    assert accepted == ()


def test_str_block_notice_names_the_received_type():
    # Arrange
    # Act
    errors = _errors("PS-224")
    # Assert
    assert "got a str" in errors[0]


def test_str_block_notice_names_the_likely_mistake():
    # Arrange
    # Act
    errors = _errors("PS-224")
    # Assert
    assert "Did you write `exemptions: PS-224`" in errors[0]


def test_int_block_notice_names_the_received_type():
    # Arrange — the article is chosen so the type reads correctly.
    # Act
    errors = _errors(7)
    # Assert
    assert "got an int" in errors[0]


def test_int_block_notice_names_the_expected_spelling():
    # Arrange
    # Act
    errors = _errors(7)
    # Assert
    assert "Each rule code is a KEY whose value is a list of entries" in errors[0]


def test_absent_block_is_silent():
    # Arrange — nothing written means nothing lost; only a WRITTEN config that
    # cannot work deserves a notice.
    # Act
    result = parse_exemptions(None)
    # Assert
    assert result == ((), ())


# -------- rule level: a non-list rule value is REPORTED ---------------------


def test_rule_value_str_notice_names_the_received_type():
    # Arrange
    # Act
    errors = _errors({"PS-220": "src/pkg/_report.py"})
    # Assert
    assert "got a str" in errors[0]


def test_rule_value_str_notice_is_rule_prefixed():
    # Arrange — the per-rule config-error arms filter on this prefix.
    # Act
    errors = _errors({"PS-220": "src/pkg/_report.py"})
    # Assert
    assert errors[0].startswith("PS-220:")


def test_rule_value_mapping_notice_names_the_likely_mistake():
    # Arrange — a single entry written directly under the rule key, with the
    # `- ` list marker forgotten.
    raw = {"PS-220": {"path": "src/pkg/_report.py", "line": 88, "reason": "x"}}
    # Act
    errors = _errors(raw)
    # Assert
    assert "Did you write the entry directly under `PS-220:`" in errors[0]


def test_rule_value_mapping_accepts_nothing():
    # Arrange
    raw = {"PS-220": {"path": "src/pkg/_report.py", "line": 88, "reason": "x"}}
    # Act
    accepted = _accepted(raw)
    # Assert
    assert accepted == ()


# -------- entry level: a non-mapping entry is REPORTED ----------------------


def test_entry_str_notice_names_the_received_type():
    # Arrange — a bare path written as the list item.
    # Act
    errors = _errors({"PS-220": ["src/pkg/_report.py"]})
    # Assert
    assert "got a str" in errors[0]


def test_entry_str_notice_names_the_likely_mistake():
    # Arrange
    # Act
    errors = _errors({"PS-220": ["src/pkg/_report.py"]})
    # Assert
    assert (
        "Did you write `- src/pkg/_report.py` instead of "
        "`- path: src/pkg/_report.py`?" in errors[0]
    )


def test_entry_str_notice_is_indexed():
    # Arrange — with several entries the author needs to know WHICH one.
    # Act
    errors = _errors({"PS-220": ["a.py"]})
    # Assert
    assert errors[0].startswith("PS-220[0]:")


def test_entry_int_notice_names_the_received_type():
    # Arrange
    # Act
    errors = _errors({"PS-220": [88]})
    # Assert
    assert "got an int" in errors[0]


def test_non_integer_line_notice_names_the_received_type():
    # Arrange — the sibling drop: `line:` that will not parse.
    raw = {"PS-220": [{"path": "a.py", "line": "eighty-eight", "reason": "why"}]}
    # Act
    errors = _errors(raw)
    # Assert
    assert "got a str" in errors[0]


def test_blank_reason_is_still_rejected():
    # Arrange — the constitution §2 rule this surface was built for must
    # survive the new reporting.
    raw = {"PS-220": [{"path": "a.py", "line": 88, "reason": "   "}]}
    # Act
    errors = _errors(raw)
    # Assert
    assert "REJECTED" in errors[0]


# -------- POSITIVE CONTROL: the correct form still parses and exempts -------


def test_good_mapping_form_accepts_one_exemption():
    # Arrange — without this, a parser that rejects EVERYTHING passes every
    # test above.
    # Act
    accepted = _accepted(_GOOD)
    # Assert
    assert len(accepted) == 1


def test_good_mapping_form_reports_no_errors():
    # Arrange
    # Act
    errors = _errors(_GOOD)
    # Assert
    assert errors == ()


def test_good_mapping_form_keeps_the_site_key_verbatim():
    # Arrange — the site key is job-qualified for PS-224; it must survive the
    # parse unchanged or the exemption matches nothing.
    # Act
    accepted = _accepted(_GOOD)
    # Assert
    assert accepted[0].path == ".github/workflows/e2e-mobile.yml::playwright-mobile"


def test_good_mapping_form_keeps_the_rule_code():
    # Arrange
    # Act
    accepted = _accepted(_GOOD)
    # Assert
    assert accepted[0].rule == "PS-224"


def test_good_mapping_form_keeps_the_reason():
    # Arrange
    # Act
    accepted = _accepted(_GOOD)
    # Assert
    assert accepted[0].reason == "mobile browsers ship only on the hosted image"


def test_windows_separators_are_normalised():
    # Arrange — the matcher compares POSIX paths verbatim.
    raw = {"PS-220": [{"path": r"src\pkg\_report.py", "line": 88, "reason": "why"}]}
    # Act
    accepted = _accepted(raw)
    # Assert
    assert accepted[0].path == "src/pkg/_report.py"


# -------- the notice must REACH every arm ----------------------------------


@pytest.mark.parametrize("rule", ["PS-220", "PS-222", "PS-223", "PS-224"])
def test_block_notice_applies_to_every_rule_arm(rule):
    # Arrange — a malformed block costs EVERY rule its exemptions, so a
    # `startswith(rule)` filter would drop the report of the drop.
    notice = _errors(_HUB_LIST_FORM)[0]
    # Act
    applies = exemption_notice_applies(notice, rule)
    # Assert
    assert applies is True


def test_entry_notice_applies_to_its_own_rule():
    # Arrange
    notice = _errors({"PS-220": ["a.py"]})[0]
    # Act
    applies = exemption_notice_applies(notice, "PS-220")
    # Assert
    assert applies is True


def test_entry_notice_does_not_apply_to_another_rule():
    # Arrange — an entry-level rejection stays pinned to ONE rule.
    notice = _errors({"PS-220": ["a.py"]})[0]
    # Act
    applies = exemption_notice_applies(notice, "PS-224")
    # Assert
    assert applies is False


def test_block_notice_starts_with_the_block_prefix():
    # Arrange — the prefix IS the block/entry discriminator.
    # Act
    notice = _errors(_HUB_LIST_FORM)[0]
    # Assert
    assert notice.startswith(EXEMPTION_BLOCK_PREFIX)


def test_formatted_block_notice_says_nothing_was_exempted():
    # Arrange
    notice = _errors(_HUB_LIST_FORM)[0]
    # Act
    detail = format_exemption_notice(notice, "PS-224")
    # Assert
    assert "NO PS-224 exemption took effect" in detail


def test_formatted_entry_notice_says_the_entry_exempts_nothing():
    # Arrange — wording relied on by the PS-222 arm's test.
    notice = _errors({"PS-220": ["a.py"]})[0]
    # Act
    detail = format_exemption_notice(notice, "PS-220")
    # Assert
    assert "does NOT exempt anything" in detail


# EOF
