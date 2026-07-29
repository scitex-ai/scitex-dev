"""§10 — import-budget gate, and the trust gate that guards its verdict.

Extracted from `_audit.py` (legacy-oversized) so the §10 fix could be
made at all; `_audit.py` re-exports both public names via its PEP 562
`__getattr__`, so every historical import keeps working.

WHY THE TRUST GATE EXISTS
=========================
§10 measures ``marginal = full - baseline`` and asserts it is under a
500ms budget. The budget is real — import cost is a genuine regression
axis, Click re-runs the program once per Tab press — so it is NOT
raised here. What was broken is the *decision procedure around* the
measurement.

The old guard skipped the assertion only when ``baseline > threshold``
(i.e. the bare interpreter alone cost more than the whole budget). That
left a hole, measured on the SAME branch and SAME code within minutes
of each other (PR #447):

    CI (spartan-cpu-org-01): baseline=167ms  full=781ms -> marginal 614ms
                             -> §10 ERROR, guard did NOT fire
    local:                   baseline=1796ms            -> guard FIRED
                             -> §10w SKIPPED, exit 0

A node with a *fast bare interpreter* but *slow cold-cache package I/O*
sits in the strictly-enforcing regime and blows the budget. Controls
established at the time: `develop`'s tip passed on that same runner 14s
later; the same branch at an earlier sha passed on another runner; the
branch's only diff was a workflow YAML that cannot affect import time.
So the verdict was decided by the runner's I/O weather, not by the code
under test — and a RED that is not about the change trains people to
re-run rather than read, the worst habit a gate can teach.

Independently corroborated from the other direction on PR #448, which
hit the same gate while diagnosing something unrelated: ``import
scitex_dev`` pulls a BYTE-IDENTICAL 248-module set on that branch and on
`origin/develop`, and nothing the PR touched is on the import path — yet
the branch went green -> red -> green across shas. §10's verdict moved
while the artifact it measures did not. Two independent diagnoses, one
from this guard's threshold logic and one from proving the measured
artifact identical, converge on the same conclusion: `develop` is green
on §10 by accident of runner load, and any PR can be hit.

(That report also offered a coverage-tracing hypothesis for the timing
itself. It is explicitly NOT adopted here — its author could not measure
import timings reliably in that container and labelled it unverified.
The 248-module identity is the measured claim; the explanation is not.)

THE MODEL ERROR
---------------
Subtracting ``baseline`` assumes the environment adds a CONSTANT
overhead. It does not. A slow-I/O node applies a roughly MULTIPLICATIVE
slowdown to I/O-bound work, and the package import performs strictly
more file I/O than bare interpreter startup. So on a slow node
``full - baseline`` systematically UNDER-corrects: the residual still
contains environment. That is the defect, and it is why the guard has
to key on "is the environment near its healthy floor", not on "is the
baseline bigger than the entire budget".

THE HARD RULE
-------------
When the measurement cannot be trusted the gate must SAY SO. §10w is
that outcome — a distinct, always-printed, warn-tier "COULD NOT MEASURE
RELIABLY" finding. It is not a silent pass (it prints, and it is
counted in the per-severity warning tally) and it is not a misleading
error (it does not fail CI over the runner's disk). The trust gate is
evaluated BEFORE the verdict, so an untrustworthy measurement is
reported as unmeasurable no matter which side of the budget the number
happened to land on: a check that could not run must never report what
a check that passed reports.

DESIGN ALTERNATIVES CONSIDERED AND REJECTED
-------------------------------------------
* **Raise the 500ms budget.** Rejected outright: it hides the flakiness
  instead of fixing it and silently weakens a real regression axis. The
  failing measurement was 614ms; any number that absorbs it also
  absorbs a genuine 600ms regression.
* **Warm the cache with an untimed priming run.** Rejected on evidence:
  best-of-N already provides warm runs 2..N, and the CI failure had
  ``full`` = best-of-3 = 781ms, i.e. all three runs were slow. Warming
  does not help a *sustained* slow-I/O node, which is the regime that
  actually failed.
* **Best-of-N on the marginal instead of the components.** Rejected: it
  does not touch the additive-vs-multiplicative model error at all, and
  taking a min over paired differences is MORE noise-sensitive, not
  less (it picks the pairing where noise happened to cancel).
* **WARN-only on "shared runners", ERROR where the environment is
  controlled.** Rejected: it needs a reliable "am I on a shared runner"
  signal, and the available ones (`CI=true`, runner labels) are
  metadata about *permission and context*, never about *measurement
  quality* — a dedicated node can be thrashing and a shared one idle.
  The property we actually care about ("can this node resolve a 500ms
  difference?") is DIRECTLY measurable from samples we already take.
  Measuring beats declaring.

WHAT IS IMPLEMENTED INSTEAD
---------------------------
Two independent pieces of evidence, both derived from the measurement
itself, either of which makes the run unmeasurable; plus a
noise-vs-margin check on the verdict:

1. **Baseline sanity (ratio form).** The additive correction is only
   credible while the bare interpreter is near its healthy cost. See
   ``_BASELINE_SANITY_FRACTION`` for the derivation of the bound.
2. **Sample dispersion.** If either series' samples scatter by more
   than the entire budget, the node demonstrably cannot resolve a
   budget-sized difference. This is why the measurement keeps all N
   samples rather than only the min.

   Best-of-N alone cannot substitute for this. Measured on an agent
   container while investigating PR #448: the BARE-interpreter baseline
   swung 684ms -> 1607ms between runs minutes apart on one machine, and
   the marginal went negative. Any design that subtracts two separately
   timed measurements inherits that variance, and best-of-3 is exactly
   what produced the 167ms baseline that failed CI. Keeping the spread
   is what makes the instability visible instead of averaged away.
3. **Margin within noise.** Even on an otherwise sane node, a verdict
   whose excess over budget is smaller than the observed jitter is not
   a conclusion — it is noise. Reported as §10w, not as a pass.

On a healthy runner (baseline ≈ 20ms, tight samples) none of these
fire and §10 stays exactly as strict as before: a genuine import-time
regression still ERRORs. That is asserted by a mutation test, because
a "fix" that quietly neuters the gate is the same failure class this
change exists to remove.
"""

from __future__ import annotations

__all__ = ["_check_startup_speed", "_startup_speed_violation"]

# A healthy bare-interpreter `python -c "pass"` costs ~20ms (the figure
# the original §10 docstring recorded as "normal"). It is the reference
# the environment's slowdown factor is expressed against.
_HEALTHY_BASELINE_MS = 20.0

# The bare-interpreter baseline may consume at most this fraction of the
# import budget before the measurement is declared unmeasurable.
#
# Derivation (not a round number picked for taste). At 0.2 x 500ms the
# bound is 100ms == 5x the healthy baseline, i.e. the node's own startup
# I/O path is running 5x slow. The package import performs strictly MORE
# file I/O than bare startup, so on such a node the environmental
# component of `full` is also inflated ~5x while `full - baseline`
# removes only one baseline's worth of it. The un-corrected residual is
# therefore >= 4 x (the package's healthy import-I/O time) -- which for
# any package with >=125ms of genuine import I/O already fills the whole
# 500ms budget on its own, before the package has regressed at all.
#
# The CI failure that motivated this sat at baseline=167ms == 8.4x
# healthy, well past the bound, and its residual term was >= 7x the
# package's honest I/O cost. The old bound (1.0, i.e. baseline > the
# entire budget) corresponds to a 25x-slow node -- far too permissive to
# catch the regime that actually fails.
_BASELINE_SANITY_FRACTION = 0.2


def _spread(samples) -> float:
    """Peak-to-peak scatter of a sample series, in ms (0.0 if <2 samples)."""
    if not samples or len(samples) < 2:
        return 0.0
    return max(samples) - min(samples)


def _untrustworthy_reason(
    baseline: float,
    threshold_ms: int,
    baseline_samples,
    full_samples,
) -> str | None:
    """Why this measurement cannot support a verdict, or ``None`` if it can.

    Evaluated BEFORE the budget comparison on purpose — see the module
    docstring's HARD RULE. Both criteria are properties of the
    ENVIRONMENT, so neither can be satisfied by the package under test
    getting slower.
    """
    sanity_ms = _BASELINE_SANITY_FRACTION * threshold_ms
    if baseline > sanity_ms:
        factor = baseline / _HEALTHY_BASELINE_MS
        return (
            f"bare-interpreter baseline {baseline:.0f}ms exceeds the "
            f"{sanity_ms:.0f}ms sanity bound "
            f"({_BASELINE_SANITY_FRACTION:.0%} of the {threshold_ms}ms budget) "
            f"— this node's own startup I/O is ~{factor:.0f}x a healthy "
            f"node's ~{_HEALTHY_BASELINE_MS:.0f}ms, and a slow-I/O node "
            "inflates the package import MULTIPLICATIVELY while "
            "`full - baseline` only corrects for it ADDITIVELY, so the "
            "residual is dominated by the environment"
        )

    # Dispersion: keeping every sample (not just the min) is what makes
    # this observable at all. A node whose repeated identical runs differ
    # by more than the whole budget cannot resolve a budget-sized change.
    for label, samples in (("baseline", baseline_samples), ("import", full_samples)):
        spread = _spread(samples)
        if spread > threshold_ms:
            return (
                f"{label} timings scatter by {spread:.0f}ms across "
                f"{len(samples)} runs (min {min(samples):.0f}ms, "
                f"max {max(samples):.0f}ms) — more than the entire "
                f"{threshold_ms}ms budget, so this node cannot resolve a "
                "budget-sized difference"
            )
    return None


def _startup_speed_violation(
    package: str,
    module_name: str,
    baseline: float,
    full: float,
    threshold_ms: int,
    runs: int,
    baseline_samples=None,
    full_samples=None,
) -> "object | None":
    """Decide the §10 finding from already-measured timings (pure, testable).

    Returns a §10 ERROR when the package's marginal import cost exceeds
    ``threshold_ms`` on a TRUSTWORTHY measurement, a §10w WARN when the
    environment cannot support a verdict, or ``None`` when the import is
    comfortably under budget on a trustworthy measurement.

    ``baseline_samples`` / ``full_samples`` are the full per-run series
    behind ``baseline`` / ``full`` (which are their minima). They are the
    value seam the dispersion evidence comes through — pass real timings,
    no clock patching required. When omitted the dispersion criterion is
    simply not evaluated; the baseline-sanity criterion still applies, so
    an omitting caller loses one axis of evidence, never the whole gate.
    """
    from ._audit import Violation

    reason = _untrustworthy_reason(
        baseline, threshold_ms, baseline_samples, full_samples
    )
    if reason is not None:
        return Violation(
            package,
            "§10w",
            f"§10 import-budget SKIPPED — COULD NOT MEASURE RELIABLY: {reason}. "
            "No verdict is claimed in either direction: this is neither a pass "
            "nor a failure of the budget. Re-run on a node with a healthy "
            "bare-interpreter baseline to enforce §10.",
        )

    marginal = full - baseline
    if marginal <= threshold_ms:
        return None

    # Over budget on a sane node — but a verdict whose excess is inside
    # the environment's own jitter is not a conclusion. Report it as
    # unmeasurable rather than as an error we cannot stand behind.
    noise = max(_spread(baseline_samples), _spread(full_samples))
    excess = marginal - threshold_ms
    if noise >= excess:
        return Violation(
            package,
            "§10w",
            f"§10 import-budget SKIPPED — COULD NOT MEASURE RELIABLY: marginal "
            f"{marginal:.0f}ms exceeds the {threshold_ms}ms budget by only "
            f"{excess:.0f}ms, which is within the {noise:.0f}ms run-to-run "
            "jitter observed on this node — the excess is indistinguishable "
            "from noise. No verdict is claimed. Re-run on a quieter node to "
            "enforce §10.",
        )

    return Violation(
        package,
        "§10",
        f"`import {module_name}` adds {marginal:.0f}ms over bare-interpreter "
        f"startup (>{threshold_ms}ms threshold; import={full:.0f}ms, "
        f"baseline={baseline:.0f}ms, best-of-{runs}). Slow tab-completion: Click "
        "runs the program once per Tab press. Convert "
        f"{module_name}/__init__.py to PEP 562 lazy `__getattr__` (see python-api "
        "skill 04_lazy-imports-and-optional-deps.md, 'PEP 562 module __getattr__' section).",
    )


def _check_startup_speed(
    package: str,
    out: list,
    threshold_ms: int = 500,
    runs: int = 3,
) -> None:
    """§10 — the MARGINAL cost of `import <module>` (above bare-interpreter
    startup) must be < threshold_ms.

    Click bash-completion calls the program once per Tab press to resolve
    dynamic completions, so a slow import = unusable tab-completion. The
    fix is PEP 562 lazy `__getattr__` in the top-level `__init__.py`
    (see `_skills/general/03_interface/01_python-api/
    04_lazy-imports-and-optional-deps.md`).

    Measurement (2026-06-19): the metric is ``T - B`` — ``T`` is the wall-clock
    of ``python -c "import <module>"`` and ``B`` is the wall-clock of a bare
    ``python -c "pass"`` reference, each taken as the *best of N* runs.
    Subtracting ``B`` cancels the interpreter + site + coverage startup baseline
    (and the machine-speed factor inside it), so the check reflects the
    PACKAGE's own import cost — not the runner's filesystem or CPU load.
    best-of-N (min) warms the file cache and drops transient load spikes: the
    earlier absolute-time check false-failed on the shared/NFS Spartan CI node,
    where a cold first import over the network FS measured 937ms while the
    package's real marginal cost is a few ms.

    That cancellation is only PARTIAL, though — it is additive and the
    environment's effect is multiplicative. Every sample is therefore kept
    and handed to ``_startup_speed_violation``, whose trust gate decides
    whether this environment can support a verdict at all. See that
    module docstring.
    """
    import subprocess as _sp
    import sys as _sys
    import time as _time

    from ._audit import _ep_value_for

    ep_value = _ep_value_for(package)
    if ep_value is None:
        return
    # Entry-point format is "module.path:object"; take the TOP-LEVEL package.
    module_name = ep_value.split(":", 1)[0].split(".", 1)[0]
    if not module_name:
        return

    def _samples_ms(code: str) -> list[float] | None:
        """Every wall-clock sample (ms) of ``python -c <code>``; None on failure.

        Returns ALL ``runs`` samples, not just the best. The scatter
        across them is the only direct evidence of whether this node can
        resolve a ``threshold_ms`` difference, and a min-only view throws
        exactly that evidence away — which is how a measurement nobody
        could trust ended up being reported as a verdict.
        """
        samples: list[float] = []
        for _ in range(max(1, runs)):
            t0 = _time.perf_counter()
            try:
                r = _sp.run(
                    [_sys.executable, "-c", code],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
            except Exception:
                return None
            if r.returncode != 0:
                return None  # import failure — covered elsewhere
            samples.append((_time.perf_counter() - t0) * 1000.0)
        return samples

    # Bare interpreter reference, then the package import — same env, so site +
    # coverage + machine-speed largely cancel in the difference.
    baseline_samples = _samples_ms("pass")
    full_samples = _samples_ms(f"import {module_name}")
    if baseline_samples is None or full_samples is None:
        return  # import failure — covered elsewhere

    v = _startup_speed_violation(
        package,
        module_name,
        min(baseline_samples),
        min(full_samples),
        threshold_ms,
        runs,
        baseline_samples=baseline_samples,
        full_samples=full_samples,
    )
    if v is not None:
        out.append(v)
