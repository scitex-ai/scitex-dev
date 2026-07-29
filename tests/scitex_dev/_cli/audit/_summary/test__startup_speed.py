"""§10 import-budget — the verdict AND the trust gate that guards it.

Moved here from `test__audit.py` alongside the `_startup_speed.py`
extraction, and extended with the fast-baseline/slow-import regression.

No mocks (STX-NM002): `_startup_speed_violation` is a pure function of
already-measured timings. Every test drives it through that real value
seam — the numbers passed in are the numbers a real subprocess
measurement produced on a real runner — so nothing patches a clock,
`time.perf_counter`, or `subprocess.run`.
"""

from __future__ import annotations

import pytest

pytest.importorskip("click")

from scitex_dev._cli.audit._summary._audit import (  # noqa: E402
    RULE_SEVERITY,
    _max_severity,
    _startup_speed_violation,
)


THRESHOLD = 500


def _verdict(baseline, full, baseline_samples=None, full_samples=None):
    """Run the real §10 decision over one real set of timings."""
    return _startup_speed_violation(
        "scitex-demo",
        "scitex_demo",
        baseline,
        full,
        THRESHOLD,
        3,
        baseline_samples=baseline_samples,
        full_samples=full_samples,
    )


def _steady(*values):
    """A sample series with negligible scatter — a quiet, healthy node."""
    return list(values)


# --------------------------------------------------------------------- #
# THE REGRESSION: fast bare interpreter, slow cold-cache package I/O.    #
#                                                                        #
# Measured on spartan-cpu-org-01 (PR #447, py3.13 leg, sha 1696b80):     #
# baseline=167ms, full=781ms -> marginal 614ms. The old guard fired only #
# when baseline > 500ms, so this regime was STRICTLY ENFORCED and the    #
# gate reported a §10 ERROR about a branch whose only diff was a         #
# workflow YAML. On develop this test fails: it gets `§10`.              #
# --------------------------------------------------------------------- #


class TestFastBaselineSlowColdImport:
    """The measured CI hole: fast interpreter, slow cold-cache package I/O."""

    # The real numbers off the failing CI leg.
    CI_BASELINE = 167.0
    CI_FULL = 781.0

    def _ci_verdict(self):
        return _verdict(
            self.CI_BASELINE,
            self.CI_FULL,
            baseline_samples=_steady(167.0, 181.0, 174.0),
            full_samples=_steady(781.0, 802.0, 794.0),
        )

    def test_ci_regime_is_reported_as_unmeasurable_not_as_an_error(self):
        # Arrange
        # Act
        v = self._ci_verdict()
        # Assert — §10w ("could not measure"), NOT the §10 error it gave.
        assert v.rule == "§10w"

    def test_ci_regime_is_not_a_silent_pass(self):
        # Arrange
        # Act — the other half of the hard rule: an unmeasurable
        # run must not look like a clean one either.
        v = self._ci_verdict()
        # Assert
        assert v is not None

    def test_ci_regime_says_it_could_not_measure(self):
        # Arrange
        # Act
        v = self._ci_verdict()
        # Assert — the outcome must SAY the measurement failed.
        assert "COULD NOT MEASURE RELIABLY" in v.message

    def test_ci_regime_disclaims_a_verdict_in_either_direction(self):
        # Arrange
        # Act
        v = self._ci_verdict()
        # Assert
        assert "No verdict is claimed" in v.message

    def test_ci_regime_names_the_measured_baseline(self):
        # Arrange
        # Act — a reader must be able to check the reasoning.
        v = self._ci_verdict()
        # Assert
        assert "167ms" in v.message

    def test_ci_regime_keeps_audit_all_exit_zero(self):
        # Arrange — audit-all exits 1 only when _max_severity == "error".
        # Act
        sev = _max_severity([self._ci_verdict()])
        # Assert
        assert sev != "error"


# --------------------------------------------------------------------- #
# MUTATION PROOF: the gate must still bite on a trustworthy measurement. #
# Without this, a suite would pass on a §10 accidentally neutered into   #
# "always warn" — the exact defect class this change exists to remove.   #
# --------------------------------------------------------------------- #


class TestGenuineRegressionStillErrors:
    """A real import-time regression, measured on a healthy quiet node."""

    def _regression_verdict(self):
        # Healthy bare interpreter, tight samples, 880ms of real marginal.
        return _verdict(
            20.0,
            900.0,
            baseline_samples=_steady(20.0, 21.0, 22.0),
            full_samples=_steady(900.0, 906.0, 903.0),
        )

    def test_genuine_regression_emits_a_finding(self):
        # Arrange
        # Act
        v = self._regression_verdict()
        # Assert
        assert v is not None

    def test_genuine_regression_uses_the_error_tier_rule(self):
        # Arrange
        # Act
        v = self._regression_verdict()
        # Assert — §10, not the §10w escape hatch.
        assert v.rule == "§10"

    def test_genuine_regression_is_error_severity(self):
        # Arrange
        # Act
        sev = _max_severity([self._regression_verdict()])
        # Assert — audit-all must still exit 1.
        assert sev == "error"

    def test_genuine_regression_reports_the_marginal_cost(self):
        # Arrange
        # Act
        v = self._regression_verdict()
        # Assert
        assert "880ms" in v.message

    def test_healthy_node_fast_import_is_a_clean_pass(self):
        # Arrange
        # Act — the gate must still be able to say "fine".
        v = _verdict(
            20.0,
            45.0,
            baseline_samples=_steady(20.0, 21.0, 22.0),
            full_samples=_steady(45.0, 46.0, 47.0),
        )
        # Assert
        assert v is None


# --------------------------------------------------------------------- #
# Trust-gate criteria, one at a time.                                    #
# --------------------------------------------------------------------- #


class TestBaselineSanityCriterion:
    """Criterion 1 — the bare interpreter must be near its healthy floor."""

    def test_baseline_at_the_sanity_bound_stays_strict(self):
        # Arrange — 0.2 * 500 == 100ms is the bound; AT it is still sane,
        # and marginal (120 - 100) is under budget.
        # Act
        v = _verdict(
            100.0,
            120.0,
            baseline_samples=_steady(100.0, 101.0, 102.0),
            full_samples=_steady(120.0, 121.0, 122.0),
        )
        # Assert
        assert v is None

    def test_baseline_just_past_the_sanity_bound_is_unmeasurable(self):
        # Arrange — one ms past the bound, with a marginal that would
        # otherwise be a clean pass. Trust is evaluated BEFORE the verdict.
        # Act
        v = _verdict(
            101.0,
            150.0,
            baseline_samples=_steady(101.0, 102.0, 103.0),
            full_samples=_steady(150.0, 151.0, 152.0),
        )
        # Assert
        assert v.rule == "§10w"

    def test_very_high_baseline_still_unmeasurable(self):
        # Arrange — the original NFS-Spartan regime the old guard caught.
        # Act
        v = _verdict(
            1072.0,
            1180.0,
            baseline_samples=_steady(1072.0, 1090.0, 1080.0),
            full_samples=_steady(1180.0, 1200.0, 1190.0),
        )
        # Assert
        assert v.rule == "§10w"

    def test_very_high_baseline_message_names_the_baseline(self):
        # Arrange
        # Act
        v = _verdict(
            1072.0,
            1200.0,
            baseline_samples=_steady(1072.0, 1090.0, 1080.0),
            full_samples=_steady(1200.0, 1210.0, 1205.0),
        )
        # Assert
        assert "1072ms" in v.message

    def test_high_baseline_fires_even_when_marginal_is_negative(self):
        # Arrange — on a noisy runner the marginal can flip sign.
        # Act
        v = _verdict(
            1100.0,
            812.0,
            baseline_samples=_steady(1100.0, 1120.0, 1110.0),
            full_samples=_steady(812.0, 830.0, 820.0),
        )
        # Assert
        assert v.rule == "§10w"

    def test_warn_rule_registered_as_warn_severity(self):
        # Arrange
        # Act
        severity = RULE_SEVERITY["§10w"]
        # Assert
        assert severity == "warn"


class TestDispersionCriterion:
    """Criterion 2 — the node must be able to resolve a budget-sized gap."""

    def test_wild_import_scatter_is_unmeasurable(self):
        # Arrange — healthy baseline, but repeated identical imports differ
        # by more than the whole budget. The min alone hides this entirely.
        # Act
        v = _verdict(
            30.0,
            200.0,
            baseline_samples=_steady(30.0, 31.0, 32.0),
            full_samples=[200.0, 900.0, 250.0],
        )
        # Assert
        assert v.rule == "§10w"

    def test_wild_scatter_message_reports_the_spread(self):
        # Arrange
        # Act
        v = _verdict(
            30.0,
            200.0,
            baseline_samples=_steady(30.0, 31.0, 32.0),
            full_samples=[200.0, 900.0, 250.0],
        )
        # Assert — 900 - 200 == 700ms of scatter.
        assert "700ms" in v.message

    def test_wild_baseline_scatter_is_unmeasurable(self):
        # Arrange — scatter in the REFERENCE series is just as disqualifying.
        # Act
        v = _verdict(
            30.0,
            120.0,
            baseline_samples=[30.0, 640.0, 45.0],
            full_samples=_steady(120.0, 125.0, 122.0),
        )
        # Assert
        assert v.rule == "§10w"

    def test_over_budget_but_inside_the_noise_is_unmeasurable(self):
        # Arrange — sane baseline, sane spread, marginal 540ms: over the
        # 500ms budget by 40ms, but the node's own jitter is 50ms. An
        # excess smaller than the noise is not a conclusion.
        # Act
        v = _verdict(
            20.0,
            560.0,
            baseline_samples=_steady(20.0, 25.0, 30.0),
            full_samples=_steady(560.0, 610.0, 600.0),
        )
        # Assert
        assert v.rule == "§10w"

    def test_over_budget_well_beyond_the_noise_still_errors(self):
        # Arrange — same jitter, but the excess (380ms) dwarfs it. The
        # noise check must not become a blanket excuse.
        # Act
        v = _verdict(
            20.0,
            900.0,
            baseline_samples=_steady(20.0, 25.0, 30.0),
            full_samples=_steady(900.0, 950.0, 940.0),
        )
        # Assert
        assert v.rule == "§10"

    def test_samples_omitted_keeps_the_baseline_criterion(self):
        # Arrange — a caller that supplies no series loses the dispersion
        # axis only; the gate itself must not disappear.
        # Act
        v = _verdict(1072.0, 1180.0)
        # Assert
        assert v.rule == "§10w"

    def test_samples_omitted_still_errors_on_a_real_regression(self):
        # Arrange
        # Act
        v = _verdict(20.0, 900.0)
        # Assert
        assert v.rule == "§10"


class TestDidNotRunIsDistinguishableFromRanAndFoundNothing:
    """§10 never measuring must not render as §10 measuring and passing.

    Imported from `._startup_speed` rather than the `._audit` re-export
    shim: the shim lists only the two older names, and `_audit.py` is over
    the repo's file-size cap so it cannot be edited to add a third. The
    direct import is the honest path and does not depend on the shim.
    """

    def test_did_not_run_carries_the_warn_band(self):
        # Arrange — the gate not running is not evidence the import is slow,
        # so it must not be able to assert a §10 ERROR.
        from scitex_dev._cli.audit._summary._startup_speed import (
            _did_not_run_violation,
        )

        # Act
        v = _did_not_run_violation("pkg", "no entry point")
        # Assert
        assert v.rule == "§10w"

    def test_did_not_run_says_so_in_words(self):
        # Arrange
        from scitex_dev._cli.audit._summary._startup_speed import (
            _did_not_run_violation,
        )

        # Act
        v = _did_not_run_violation("pkg", "no entry point")
        # Assert
        assert "DID NOT RUN" in v.message

    def test_did_not_run_denies_being_a_pass(self):
        # Arrange — the whole defect was this state reading as a pass.
        from scitex_dev._cli.audit._summary._startup_speed import (
            _did_not_run_violation,
        )

        # Act
        v = _did_not_run_violation("pkg", "no entry point")
        # Assert
        assert "NOT a pass" in v.message

    def test_did_not_run_is_distinguished_from_the_trust_band(self):
        # Arrange — both are §10w, so the TEXT must separate "never
        # measured" from "measured, numbers unusable"; a reader seeing only
        # the rule id cannot tell them apart.
        from scitex_dev._cli.audit._summary._startup_speed import (
            _did_not_run_violation,
        )

        # Act
        v = _did_not_run_violation("pkg", "no entry point")
        # Assert
        assert "COULD NOT MEASURE RELIABLY" in v.message

    def test_did_not_run_names_the_cause(self):
        # Arrange — an error that only says what broke is half-written.
        from scitex_dev._cli.audit._summary._startup_speed import (
            _did_not_run_violation,
        )

        # Act
        v = _did_not_run_violation("pkg", "entry point 'x:' yields no module")
        # Assert
        assert "entry point 'x:' yields no module" in v.message

    def test_absent_entry_point_now_emits_instead_of_staying_silent(self):
        # Arrange — POSITIVE CONTROL for the actual bug: a distribution with
        # no console script used to append nothing at all, which is exactly
        # what a comfortably-under-budget package appends.
        from scitex_dev._cli.audit._summary._startup_speed import (
            _check_startup_speed,
        )

        out: list = []
        # Act
        _check_startup_speed("definitely-not-a-real-distribution-xyz", out)
        # Assert
        assert len(out) == 1

    def test_absent_entry_point_emits_the_warn_band_not_an_error(self):
        # Arrange
        from scitex_dev._cli.audit._summary._startup_speed import (
            _check_startup_speed,
        )

        out: list = []
        # Act
        _check_startup_speed("definitely-not-a-real-distribution-xyz", out)
        # Assert
        assert out[0].rule == "§10w"

    def test_a_clean_under_budget_run_still_emits_nothing(self):
        # Arrange — NEGATIVE CONTROL, and the one that keeps this fix
        # honest. Making the silent case loud is only a fix if the
        # genuinely-clean case stays silent; otherwise every package grows
        # a §10w and the distinction is destroyed from the other side.
        # Act
        v = _verdict(
            100.0,
            120.0,
            baseline_samples=_steady(100.0, 101.0, 100.0),
            full_samples=_steady(120.0, 121.0, 120.0),
        )
        # Assert
        assert v is None
