#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`audit.skip-rules` must mask on the `--new-only` path, which is the one CI runs.

Reported by scitex-cards 2026-08-10, located to the line 2026-08-12, fixed here.

THE DEFECT. `_audit_all.py` computed a `MaskReport` and then, in the
`--new-only` branch, threw it away and rebuilt the text from raw sub-auditor
stdout/stderr. So a `skip-rules` entry:

    strict local run   prints a reassuring masked inventory — looks like it works
    CI (`--new-only`)  masks exactly nothing

That is worse than an unsupported option. A maintainer configures it, verifies
it locally, watches the mask apply, ships — and the rule keeps firing in CI
while the config file says it is handled. **A suppression that cannot
suppress**, failing in the direction that wastes the most time.

WHY MASKING THE HEAD SIDE ALONE IS CORRECT. The base side audits in a separate
worktree and its output is unmasked, so the diff is deliberately asymmetric.
Removing lines from HEAD can only ever REMOVE net-new findings, never invent
one: a line absent from HEAD cannot be counted as newly appearing there.

BOTH DIRECTIONS ARE ASSERTED BELOW, and the second is the one that must not be
forgotten — a "fix" that masked everything would pass a suite written only for
the first, and would be exactly the permissive-gate defect this card exists to
remove.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from scitex_dev._cli.ecosystem._cmds._audit_all_new_only import drop_masked_lines

_DECLARED = "ERRO:   [PS-108b] 133 flat .py files at `pkg/` root"
_UNDECLARED = "ERRO:   [PS-204] orphan test file: tests/test__ghost.py"


@dataclass
class _StubReport:
    """Minimal stand-in for `MaskReport` — only `.masked` is read.

    A stub rather than the real classifier because these tests are about the
    PLUMBING that was missing, not about classification, which has its own
    suite. The real report's `masked` is `dict[rule -> list[line]]`.
    """

    masked: dict = field(default_factory=dict)


@pytest.fixture()
def combined_output() -> str:
    return "\n".join([_DECLARED, _UNDECLARED])


def test_a_declared_skip_rule_line_is_removed_from_head(combined_output: str) -> None:
    # Arrange
    report = _StubReport(masked={"PS-108b": [_DECLARED]})
    # Act
    masked_out = drop_masked_lines(combined_output, report)
    # Assert
    assert _DECLARED not in masked_out


def test_an_undeclared_line_survives_masking(combined_output: str) -> None:
    """THE DIRECTION THAT MUST NOT BE FORGOTTEN.

    A fix that dropped everything would satisfy the test above and silently
    convert the gate into a pass-through.
    """
    # Arrange
    report = _StubReport(masked={"PS-108b": [_DECLARED]})
    # Act
    masked_out = drop_masked_lines(combined_output, report)
    # Assert
    assert _UNDECLARED in masked_out


def test_no_declared_skips_leaves_the_text_byte_identical(combined_output: str) -> None:
    """The zero-config case must cost nothing and change nothing.

    Every repo without `skip-rules` takes this path on every CI run, so a
    normalisation applied here would alter net-new keying fleet-wide for
    repos that asked for no masking at all.
    """
    # Arrange
    report = _StubReport(masked={})
    # Act
    masked_out = drop_masked_lines(combined_output, report)
    # Assert
    assert masked_out == combined_output


def test_a_report_without_a_masked_attribute_is_tolerated(combined_output: str) -> None:
    """`None` reaches here if a caller ever drops the report again.

    Failing closed (raising) would turn a plumbing regression into a crashed
    gate; returning the text unchanged reproduces exactly today's behaviour,
    which is the safe direction for an accessor.
    """
    # Arrange
    report = None
    # Act
    masked_out = drop_masked_lines(combined_output, report)
    # Assert
    assert masked_out == combined_output


def test_masking_matches_on_the_stripped_line(combined_output: str) -> None:
    """Sub-auditor output reaches the diff with indentation the report's
    captured line does not carry, so an exact-string filter would silently
    match nothing — the same do-nothing failure, one layer down."""
    # Arrange
    indented = "    " + _DECLARED
    report = _StubReport(masked={"PS-108b": [_DECLARED]})
    # Act
    masked_out = drop_masked_lines(indented + "\n" + _UNDECLARED, report)
    # Assert
    assert _DECLARED not in masked_out


def test_the_new_only_branch_actually_calls_the_masker() -> None:
    """THE DEFECT WAS THE WIRING, SO THE WIRING IS WHAT MUST BE PINNED.

    Every test above exercises `drop_masked_lines` directly, and every one of
    them would still pass if the `--new-only` branch went back to discarding
    the report — which is precisely the regression being fixed. A helper with
    no caller is the original bug wearing a green suite.

    Read from source rather than by invoking `audit-all`, because reproducing
    the real path needs a git worktree, a base ref and sub-auditor subprocesses;
    the thing worth asserting is one call that must not disappear.
    """
    # Arrange
    from pathlib import Path

    import scitex_dev._cli.ecosystem._cmds._audit_all as audit_all_mod

    source = Path(audit_all_mod.__file__).read_text(encoding="utf-8")
    # Act
    wired = "head_combined = drop_masked_lines(" in source
    # Assert
    assert wired, (
        "the `--new-only` branch no longer routes HEAD output through "
        "`drop_masked_lines`, so `audit.skip-rules` masks nothing on the path "
        "CI runs — the exact defect reported by scitex-cards on 2026-08-10"
    )


def test_the_new_only_branch_keeps_the_mask_report() -> None:
    """The report was discarded as `_` in the tuple unpack. Naming it is the
    whole fix; an unnamed value cannot be passed anywhere."""
    # Arrange
    from pathlib import Path

    import scitex_dev._cli.ecosystem._cmds._audit_all as audit_all_mod

    source = Path(audit_all_mod.__file__).read_text(encoding="utf-8")
    # Act
    discarded = "_, _head_exit, head_results, _ = _run_one(" in source
    # Assert
    assert not discarded, (
        "the MaskReport is being thrown away again at the `_run_one` call in "
        "the `--new-only` branch"
    )


# EOF
