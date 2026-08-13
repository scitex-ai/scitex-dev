"""Decide ONE package's ``audit-all`` exit status from its auditors.

Separate from ``_audit_masking`` (which classifies output lines) and from
``_audit_all`` (which runs the fan-out): given what each auditor exited
with, and what the classifier could read, is this package red?

The question is asked PER AUDITOR. ``audit-all`` fans out to six
auditors and concatenates their captured output; classifying that one
blob loses the attribution, and the downgrade needs it — see
:func:`failing_audits_are_fully_masked`.
"""

from __future__ import annotations

from ._audit_masking import classify_output


def failing_audits_are_fully_masked(raw_by_audit, skip_rules) -> bool:
    """True iff EVERY auditor here reported findings that are ALL masked.

    ``raw_by_audit`` maps auditor name -> that auditor's captured output,
    and must carry exactly the auditors whose exit code was NON-ZERO.
    Asking per auditor is the whole point: the downgrade claims "every
    audit that FAILED failed only on declared rules", and only the audits
    that failed can be asked that. Over one concatenated blob the
    attribution is gone, so a finding printed by an auditor that exited 0
    vetoes a downgrade it had no part in.

    Measured 2026-08-13 on scitex-agent-container: ``audit-project``
    failed on a single ``PS-226`` the repo had declared, with a written
    rationale; three WARN-tier findings came from ``audit-cli``, which
    exited 0. ``audit-all`` printed the masked inventory, printed
    ``summary: 0 unmasked error(s) (+3 warning/info finding(s)), 1 masked
    by skip-rules (1 declared)`` — and still exited 1, because those
    three warnings sat in the combined report's ``unmasked`` list. A skip
    rule that clears the report but not the status cannot do the one job
    it exists for (scitex-ai/scitex-dev#590).

    SEVERITY IS DELIBERATELY NOT THE DISCRIMINATOR. The tempting one-line
    fix — downgrade when ``unmasked_error_count == 0`` — is unsound:
    ``audit-skills`` and ``audit-python-apis`` return ``0 if not
    violations else 1``, so they fail on WARN-tier findings too, and a
    run those two legitimately failed would go green. Each auditor is
    asked the strict question instead ("is everything YOU reported
    masked?"), which holds whatever severity policy it exits on — at the
    cost of keeping a package red when a failing auditor mixes a masked
    error with an undeclared warning, which is the conservative side of
    an unprovable case.

    An auditor that failed while reporting nothing attributable — a
    crash, a launch failure, a line the classifier could not read — is
    not fully masked and keeps the run red:
    :attr:`~._audit_masking.MaskReport.fully_masked` already requires at
    least one masked finding and refuses on anything unreadable.

    Empty input returns False. "No audit failed" is not a licence to
    downgrade; it means the caller had nothing to downgrade.
    """
    if not raw_by_audit:
        return False
    return all(
        classify_output(raw, skip_rules).fully_masked
        for raw in raw_by_audit.values()
    )


def decide_pkg_exit(
    pkg_exit: int,
    *,
    distribution: str,
    report,
    failing_raw,
    skip_rules,
) -> tuple[int, str | None]:
    """Return ``(exit_code, warning_or_None)`` for one package.

    ``report`` is the WHOLE run's :class:`~._audit_masking.MaskReport` —
    it still drives the inventory and the summary, so what is REPORTED is
    unchanged by this function. Only the verdict's inputs are narrowed,
    to ``failing_raw``: the captured output of the auditors that actually
    exited non-zero.

    The unreadable guard stays global on purpose. A finding-shaped line
    nobody could parse might have been an undeclared ERROR from any
    auditor, so it withholds the downgrade for the package rather than
    for one audit — and, because a run that stays red for a reason
    nobody prints is the same debugging dead-end as one that goes green
    silently, it comes back as a warning to echo rather than as silence.
    """
    if not pkg_exit:
        return pkg_exit, None
    if report.is_answerable() and failing_audits_are_fully_masked(
        failing_raw, skip_rules
    ):
        return 0, None
    if report.unmasked_count == 0 and not report.is_answerable():
        return pkg_exit, (
            f"WARN: {distribution}: exit stays NON-ZERO — "
            f"{len(report.unreadable)} line(s) claimed to be findings "
            "and could not be classified, so they cannot be shown to "
            "be covered by a declared skip-rule. First unreadable "
            f"line: {report.unreadable[0]!r}. Fix the emitter's line "
            "format, or declare the rule if it is a real finding."
        )
    return pkg_exit, None


__all__ = ["decide_pkg_exit", "failing_audits_are_fully_masked"]
