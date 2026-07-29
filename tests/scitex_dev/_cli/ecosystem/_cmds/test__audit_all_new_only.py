"""`--new-only` must stay able to fail on findings its parser cannot read.

REGRESSION GUARD. Measured 2026-07-29 on scitex-dev PR #457 (run
30447489901): the REQUIRED `audit` check printed

    ERRO:   [§2] ... mutating verb 'install' missing --yes/-y flag
    ERRO:   [E] [PS-202 ...] .../_rules: no matching tests/.../_rules/
    --new-only: 0 net-new violation(s)

and exited 0. Both violations were genuinely new. `_FINDING_RE` matches
only ``LEVEL: [TAG] <single-token-dist>: <msg>``, so on real audit output
**9 finding lines produced 1 key** — the errors were absent from the diff,
and `filter_to_net_new_lines` (which preserves lines it does not recognise
as findings) reprinted them as if they were prose.

These tests pin the fallback that closed it. Without them the defect
reintroduces itself silently, which is exactly how it arrived: nothing
failed when the parser stopped seeing a format.

No mocks (STX-NM002): every assertion runs the real functions over real
audit output text.
"""

from __future__ import annotations

import pytest

from scitex_dev._cli.audit._diff import extract_violation_keys
from scitex_dev._cli.ecosystem._cmds._audit_all_new_only import (
    unparsed_finding_lines,
)

# Verbatim shapes taken from real `audit-all` output, not invented. An
# earlier version of this investigation tested the parser against
# hand-typed lines and got the OPPOSITE answer — testing a parser against
# imagined input measures your imagination, not the parser.
_PS_ERROR = (
    "ERRO:   [E] [PS-202 §2 src-tests-mirror-dir-missing] "
    "/tree/src/scitex_dev/_cli/audit/_project/_rules: "
    "no matching tests/scitex_dev/_cli/audit/_project/_rules/"
)
_CLI_ERROR = (
    "ERRO:   [§2] scitex-dev ecosystem install-cross-package-gate: "
    "mutating verb 'install' missing --yes/-y flag"
)
_UNREADABLE_ERRORS = (_PS_ERROR, _CLI_ERROR)


@pytest.mark.parametrize("line", _UNREADABLE_ERRORS)
def test_the_key_parser_now_keys_these_error_shapes(line):
    """GAP CLOSED 2026-07-29 — this test is the inverse of what it was.

    It used to assert ``keys == set()``, pinning the known gap with a
    tripwire: "if someone widens `_FINDING_RE` so these parse, this
    test fails loudly and tells them to re-check the fallback rather
    than letting coverage change silently underneath it."

    The tripwire fired, as designed. The gap was closed NOT by widening
    the regex — these shapes still do not parse structurally — but by
    `extract_violation_keys` failing OPEN: an ERRO line it cannot key
    now becomes an ``UNPARSED`` key instead of vanishing. That is what
    let a required gate print errors and exit 0.

    `unparsed_finding_lines` below is now belt-and-braces rather than
    the only net. Both are kept: the fallback compares raw TEXT with
    checkout roots stripped, which stays useful for non-ERRO shapes the
    core deliberately refuses to key.
    """
    # Arrange
    # Act
    keys = extract_violation_keys(line)
    # Assert
    assert len(keys) == 1


@pytest.mark.parametrize("line", _UNREADABLE_ERRORS)
def test_unreadable_error_lines_are_recovered_by_the_fallback(line):
    # Arrange
    # Act
    recovered = unparsed_finding_lines(line, ())
    # Assert — what the key diff cannot see, the text diff must.
    assert len(recovered) == 1


def test_a_new_unreadable_error_is_net_new_against_a_baseline_without_it():
    # Arrange — the baseline carries an unrelated finding; HEAD adds the error.
    base = "WARN:   [§13] scitex-dev cron: self-maintenance command at top level"
    head = base + "\n" + _PS_ERROR
    # Act
    net_new = unparsed_finding_lines(head, ()) - unparsed_finding_lines(base, ())
    # Assert — this is the case that reported "0 net-new" and exited 0.
    assert net_new == {_PS_ERROR}


def test_a_pre_existing_unreadable_error_is_not_net_new():
    # Arrange — same finding on both sides: inherited debt, not new.
    # Act
    net_new = unparsed_finding_lines(_PS_ERROR, ()) - unparsed_finding_lines(
        _PS_ERROR, ()
    )
    # Assert — the filter must still do its job, or the fix would simply
    # make --new-only equivalent to a strict audit and block unrelated PRs.
    assert net_new == set()


def test_checkout_roots_are_normalised_before_comparison():
    # Arrange — the baseline runs in a temporary worktree, so every absolute
    # path differs from HEAD's. Without normalisation every line looks new.
    head = _PS_ERROR.replace("/tree", "/head/checkout")
    base = _PS_ERROR.replace("/tree", "/tmp/base-worktree")
    # Act
    net_new = unparsed_finding_lines(
        head, ("/head/checkout", "/tmp/base-worktree")
    ) - unparsed_finding_lines(base, ("/head/checkout", "/tmp/base-worktree"))
    # Assert
    assert net_new == set()


def test_non_finding_output_is_not_treated_as_a_finding():
    # Arrange — banners and summaries must not become phantom findings.
    noise = (
        "INFO: scitex-dev: auditing /tree (branch HEAD, via cwd)\n"
        "SUCC: scitex-dev: no skills violations\n"
        "summary: scitex-dev: 0 unmasked error(s)\n"
    )
    # Act
    # Assert
    assert unparsed_finding_lines(noise, ()) == set()

# EOF
