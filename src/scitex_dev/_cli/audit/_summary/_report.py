#!/usr/bin/env python3
"""Rendering an audit verdict — human lines and JSON records.

Extracted from `_run.py` (which had reached the 512-line cap) when
`_emit_human` gained a required `category`. Pure move plus that parameter;
`_run.py` re-exports both public names, so `_mcp_audit.py`'s
`from ._run import _emit_human` keeps resolving.

WHY THE CATEGORY IS A PARAMETER AND NOT A CONSTANT
--------------------------------------------------
It used to be the literal string "CLI convention", baked into both the clean
line and the failure line. `_mcp_audit.py` reuses this renderer — so the MCP
leg printed *another auditor's noun* for a population it had not audited.

Measured 2026-08-16 on one live `audit-all scitex-hpc` run:

    line  6  WARN: scitex-hpc: CLI conventions: 0 error(s), 24 warning(s)
    line 35  === audit-mcp-tools ===
    line 36  SUCC: scitex-hpc: no CLI convention violations
             (coverage NOT REPORTED — this verdict has no denominator)

Both lines, same run. Two agents read that output and came away with
contradictory beliefs about which auditor was clean, and the disagreement
took a direct re-run to resolve. Note the second line is *true* in every
part except its subject: there really was no denominator, and the caveat
really is honest — which is what made it credible enough to mislead.

It is also worse than a silent leg. A leg that says nothing about its
denominator is visibly uninformative; a leg that borrows a working leg's
verdict string is indistinguishable from a leg that has the infrastructure.

KEYWORD-ONLY AND REQUIRED, deliberately. A default is what allowed the wrong
caller to inherit the right-looking noun by omission. Requiring it turns that
into a TypeError at the call site instead of a mislabelled line inside a
report someone trusts.
"""

from __future__ import annotations

from pathlib import Path

import click

from ._severity import (
    EMIT_LEVEL,
    format_severity_counts,
    severity_of,
)

__all__ = [
    "_emit_baseline_suppressed",
    "_emit_baseline_written",
    "_emit_human",
    "_emit_json",
    "_violation_to_dict",
]


def _max_severity(violations: list) -> str:
    from ._severity import max_severity

    return max_severity(violations)


def _violation_to_dict(v) -> dict:
    """One violation as a JSON record — severity as its OWN named field.

    The machine path never mislabelled warnings as errors (it carried no
    severity at all, and `status` is a coarse "ok"/"warn"), so no consumer
    was ever told 6 warnings were errors. But it also gave a consumer no
    way to tell the bands apart without re-implementing `RULE_SEVERITY`.
    Emitting `severity` closes that: the human and machine renderers now
    read the SAME per-violation severity from `severity_of`.
    """
    return {
        "command": v.command,
        "rule": v.rule,
        "message": v.message,
        "severity": severity_of(v),
    }


def _emit_human(
    package: str,
    status: str,
    violations: list,
    coverage=None,
    *,
    category: str,
) -> None:
    """Render one auditor's verdict. ``category`` names WHOSE verdict it is."""
    if status == "skip-mcp":
        click.echo(
            f"info  {package}: MCP / protocol server — skipped (use audit-mcp-tools when available)"
        )
        return
    from .._emit import emit as _emit

    if status == "not-found":
        # No console script is a legitimate state for utility packages
        # (types, base/core libraries, etc.) — audit-cli can't enforce
        # a CLI convention on a package that has no CLI. Surface as info.
        _emit("info", f"{package}: no console script — skipped")
        return
    if status.startswith("not-auditable"):
        _emit("error", f"{package}: {category}s: {status}", err=True)
        return
    from ...._audit_disclaimer import emit_disclaimer, emit_skill_hints

    if status == "ok":
        # WITH ITS DENOMINATOR. "no violations" alone read identically whether
        # forty commands were inspected or zero, which is the whole defect:
        # a clean verdict was indistinguishable from a run that never happened.
        from ._coverage import describe_or_unknown

        _emit(
            "success",
            f"{package}: no {category} violations "
            f"({describe_or_unknown(coverage)})",
        )
        emit_disclaimer()
        return
    sev = _max_severity(violations)
    # The HEADLINE level tracks the run's worst finding (so a red run is
    # visibly red, and so the line clears the audit logger's WARNING
    # default). The COUNTS are per-severity, and each finding below is
    # emitted at ITS OWN severity.
    #
    # This used to be one level for everything: `sev` labelled the
    # headline noun AND every finding line. Measured on CI (PR #447), a
    # single §10 breach relabelled six standing §12/§13 warn-tier
    # findings as `ERRO:` and printed "7 error(s)" for 1 error and 6
    # warnings. That is not only a wrong noun — `_audit_masking.
    # is_error_line` reads severity off this very `ERRO:` prefix, so the
    # collapse propagated into audit-all's "N unmasked error(s)" tally,
    # defeating a downstream counter that was already correct. And a
    # narrow timing breach read as a broad structural break, which cost
    # real diagnosis time.
    #
    # Category-named failure line — mirrors the clean line above. Both take
    # the noun from `category` for the same reason: a borrowed noun here is
    # how the MCP leg reported CLI findings.
    headline_level = "error" if sev == "error" else "warning"
    _emit(
        headline_level,
        f"{package}: {category}s: {format_severity_counts(violations)}",
    )
    for v in violations:
        _emit(EMIT_LEVEL[severity_of(v)], f"  [{v.rule}] {v.command}: {v.message}")
    emit_disclaimer()
    emit_skill_hints()


def _emit_json(records: list[dict], registry_provenance: str) -> None:
    import json as _json

    payload = {
        "registry_source": registry_provenance,
        "results": records,
    }
    click.echo(_json.dumps(payload, indent=2))


# --------------------------------------------------------------------- #
# Baseline ratchet helpers                                                #
# --------------------------------------------------------------------- #


def _emit_baseline_suppressed(n_suppressed: int, bl_path: Path) -> None:
    from .._emit import emit as _emit

    _emit(
        "info",
        f"baseline: {n_suppressed} previously-recorded violation(s) "
        f"suppressed ({bl_path})",
    )


def _emit_baseline_written(n_written: int, bl_path: Path) -> None:
    from .._emit import emit as _emit

    _emit(
        "info",
        f"baseline written: {bl_path} ({n_written} fingerprint(s) recorded "
        f"— future runs fail/warn only on NEW violations)",
    )


# EOF
