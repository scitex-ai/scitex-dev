# -*- coding: utf-8 -*-
"""A MASKED finding must not reach the reader still labelled `ERRO`.

The sub-auditor prints its findings with its own `ERRO: ` prefix and that
text is echoed verbatim; masking is applied afterwards and shows up only as
a COUNT in the inventory. So a masked finding arrives labelled ERROR while
being provably unable to fail the gate — only `unmasked` findings drive the
exit code.

Reported by scitex-storage 2026-08-11, who read a CI log showing
`[PS-221] 25 violation(s) masked` above a still-red run and could not tell
whether masking was inert. It was not; the run was red on 29 unrelated
unmasked errors. Nothing in the text distinguished "this is why you are
red" from "this is inventory".

`label_masked_lines` is pure — text in, text out — so these tests hand it
real `MaskReport`s built by the real `classify_output`. No mocks
(NM001-003). One assert per test (STX-TQ007), AAA markers (STX-TQ002).
"""

from __future__ import annotations

from scitex_dev._cli.ecosystem._cmds._audit_masking import (
    MASKED_PREFIX,
    classify_output,
    label_masked_lines,
)
from scitex_dev._cli.audit._config._skip_rules import SkipRule


_DEFERRED = "ERRO:   [E] [PS-139 tq-migration] tests/test_a.py:1: needs AAA markers"
_LIVE = "ERRO:   [E] [PS-202 src-tests-mirror] src/pkg/_b.py: no mirror test file"


def _report(text: str, rules):
    return classify_output(text, tuple(rules))


def _rule(code: str) -> SkipRule:
    return SkipRule(rule=code, reason="tracked in a named campaign")


def test_a_masked_finding_is_restamped():
    # Arrange — PS-139 is deferred, so its finding cannot fail the gate.
    report = _report(_DEFERRED, [_rule("PS-139")])
    # Act
    out = label_masked_lines(_DEFERRED, report)
    # Assert
    assert out.startswith(MASKED_PREFIX)


def test_an_unmasked_finding_keeps_its_original_label():
    # Arrange — POSITIVE CONTROL. The test above passes both when only
    # masked lines are re-stamped and when EVERY line is, which would be a
    # worse bug than the one being fixed.
    text = f"{_DEFERRED}\n{_LIVE}"
    report = _report(text, [_rule("PS-139")])
    # Act
    out = label_masked_lines(text, report)
    # Assert
    assert _LIVE in out.splitlines()


def test_exactly_one_line_is_restamped_when_one_rule_is_deferred():
    # Arrange — the count matters: relabelling is driven by the same
    # `report.masked` that drove the exit code, so the two cannot disagree.
    text = f"{_DEFERRED}\n{_LIVE}"
    report = _report(text, [_rule("PS-139")])
    # Act
    stamped = [l for l in label_masked_lines(text, report).splitlines()
               if l.startswith(MASKED_PREFIX)]
    # Assert
    assert len(stamped) == 1


def test_no_declared_skips_leaves_the_text_byte_identical():
    # Arrange — the overwhelmingly common case. A repo declaring nothing
    # must see exactly what it saw before this change.
    text = f"{_DEFERRED}\n{_LIVE}"
    report = _report(text, [])
    # Act
    out = label_masked_lines(text, report)
    # Assert
    assert out == text


def test_a_missing_report_is_a_passthrough_not_a_crash():
    # Arrange — `_emit_pkg` defaults `report=None`; a caller that has no
    # classification must still get its output, unmodified.
    text = _LIVE
    # Act
    out = label_masked_lines(text, None)
    # Assert
    assert out == text


# EOF
