"""§10 timing findings must never be attributed to a diff.

The defect these tests pin, measured by scitex-cards on 2026-07-30: a full
audit of a develop baseline against each branch produced 132 findings vs
132, with the SOLE difference being the §10 import-budget line. One of
those branches adds a JavaScript file; the other DELETES a call and
measurably imports faster than develop. Both were reported as introducing
an import-time regression, because the measurement straddles the 500ms
threshold depending on machine load.

A timing measurement is a property of the repo AND the machine at that
instant. Net-new keying claims it is a property of the change. Excluding
it from attribution is the fix; excluding it SILENTLY would rebuild the
defect the UNPARSED fail-open exists to prevent, so the exclusion is
handed back to the caller to disclose.
"""

from __future__ import annotations

from scitex_dev._cli.audit._diff import (
    NON_ATTRIBUTABLE_RULES,
    ViolationKey,
    compute_net_new,
    compute_net_new_detailed,
    is_attributable,
    partition_attributable,
)

# A real §10 line, reduced from scitex-cards' report.
S10_AT_HEAD = (
    "ERRO: [§10] scitex-cards: `import scitex_cards` adds 571ms "
    "(>500ms; import=681ms, baseline=110ms, best-of-3)\n"
)
# A genuine, attributable finding that must keep working.
PS224_AT_HEAD = (
    "ERRO: [PS-224] scitex-cards: .github/workflows/ci.yml::test: job "
    "targets `[ubuntu-latest]`\n"
)
BASE_CLEAN = "INFO: scitex-cards: auditing /repo\n"


def test_s10_is_declared_non_attributable():
    # Arrange
    rules = NON_ATTRIBUTABLE_RULES
    # Act
    present = "§10" in rules
    # Assert
    assert present is True


def test_s10w_the_could_not_measure_sibling_is_also_non_attributable():
    """§10w means "could not measure reliably" — even less diff-attributable."""
    # Arrange
    rules = NON_ATTRIBUTABLE_RULES
    # Act
    present = "§10w" in rules
    # Assert
    assert present is True


def test_s1u_the_umbrella_bridge_sibling_is_also_non_attributable():
    """§1u grades a file that ships in the umbrella, not in the diff.

    Whether it appears at all depends on which `scitex` the job resolved:
    scitex-io PR #167 resolved none and showed no finding, while a sibling
    PR resolved 2.28.13 and showed one, from identical source. Net-new
    keying would hand that coin-flip to whoever pushed.
    """
    # Arrange
    rules = NON_ATTRIBUTABLE_RULES
    # Act
    present = "§1u" in rules
    # Assert
    assert present is True


def test_is_attributable_rejects_a_timing_key():
    # Arrange
    key = ViolationKey(rule="§10", file_line="", message_excerpt="adds 571ms")
    # Act
    verdict = is_attributable(key)
    # Assert
    assert verdict is False


def test_is_attributable_accepts_an_ordinary_rule():
    # Arrange
    key = ViolationKey(rule="PS-224", file_line="ci.yml", message_excerpt="x")
    # Act
    verdict = is_attributable(key)
    # Assert
    assert verdict is True


def test_partition_returns_both_halves():
    """The second half is what makes the exclusion disclosable."""
    # Arrange
    timing = ViolationKey(rule="§10", file_line="", message_excerpt="adds 571ms")
    real = ViolationKey(rule="PS-224", file_line="ci.yml", message_excerpt="x")
    # Act
    attributable, excluded = partition_attributable({timing, real})
    # Assert
    assert (attributable, excluded) == ({real}, {timing})


def test_s10_present_at_head_and_absent_at_base_is_not_net_new():
    """THE positive control for the reported defect.

    Under the old behaviour this returned a non-empty set, and `--new-only`
    blamed whoever pushed.
    """
    # Arrange
    head = S10_AT_HEAD
    # Act
    net_new = compute_net_new(head, BASE_CLEAN, distribution="scitex-cards")
    # Assert
    assert net_new == set()


def test_a_real_finding_is_still_net_new():
    """The negative control: this must not become a blanket suppressor."""
    # Arrange
    head = PS224_AT_HEAD
    # Act
    net_new = compute_net_new(head, BASE_CLEAN, distribution="scitex-cards")
    # Assert
    assert len(net_new) == 1


def test_the_excluded_s10_is_handed_back_not_dropped():
    """Excluded from ATTRIBUTION, never from REPORTING."""
    # Arrange
    head = S10_AT_HEAD
    # Act
    _net_new, excluded = compute_net_new_detailed(
        head, BASE_CLEAN, distribution="scitex-cards"
    )
    # Assert
    assert len(excluded) == 1


def test_a_mixed_run_separates_the_two_cleanly():
    # Arrange
    head = S10_AT_HEAD + PS224_AT_HEAD
    # Act
    net_new, excluded = compute_net_new_detailed(
        head, BASE_CLEAN, distribution="scitex-cards"
    )
    # Assert
    assert (len(net_new), len(excluded)) == (1, 1)


def test_s10_already_present_at_base_is_excluded_too():
    """Not net-new by either test — must not resurface via the timing path."""
    # Arrange
    head = S10_AT_HEAD
    # Act
    net_new, excluded = compute_net_new_detailed(
        head, S10_AT_HEAD, distribution="scitex-cards"
    )
    # Assert
    assert (net_new, excluded) == (set(), set())


# EOF
