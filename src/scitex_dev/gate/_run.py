#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/gate/_run.py
"""Run the aggregated submission gate for a workdir + stage.

Applies the config-driven enforcement overlay: a failed check BLOCKS
(contributes to a non-zero exit) only when its id is listed under
``gate.enforce`` in ``.scitex/dev/config.yaml``; otherwise its failure is
advisory (rendered as a warning, exit 0). A check that raises fails
CLOSED — a broken provenance check must never silently pass a submission,
but it only BLOCKS if that check is enforced (consistent with the model).
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ._config import GateConfig, load_gate_config
from ._discover import discover_gate_checks
from ._spec import Finding, GateCheck
from ._undetermined import is_undetermined, undetermined_reason
from ._undetermined import with_undetermined_finding as _with_undetermined_finding


@dataclass(frozen=True)
class CheckOutcome:
    """The per-check result after the enforcement overlay."""

    id: str
    stage: str
    ran: bool
    passed: bool | None  # None ⇒ skipped (see skipped_reason)
    enforced: bool
    findings: tuple[Finding, ...]
    skipped_reason: str = ""
    #: The check RAN and could not tell. Distinct from `passed is None`,
    #: which means the runner deliberately did not run it (disabled in
    #: config, or `requires` not importable). Those are decisions; this is
    #: a limit on observation, and rendering them the same way misreports
    #: one of them. `passed` is False alongside it, so `blocked` needs no
    #: change and a consumer that has never heard of this field still
    #: blocks.
    undetermined: bool = False
    undetermined_reason: str = ""

    @property
    def blocked(self) -> bool:
        """True iff this check FAILED or COULD NOT TELL, and is ENFORCED.

        Unchanged in form: an undetermined result carries ``passed=False``,
        so it is caught here by construction rather than by a second
        condition somebody could forget to add.
        """
        return self.ran and self.passed is False and self.enforced


@dataclass(frozen=True)
class GateReport:
    stage: str
    workdir: str
    outcomes: tuple[CheckOutcome, ...]
    config_source: str | None = None

    @property
    def blocking(self) -> bool:
        """True iff any enforced check failed ⇒ CLI exits 2."""
        return any(o.blocked for o in self.outcomes)

    @property
    def passed(self) -> bool:
        return not self.blocking


def _importable(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def run_gate(
    workdir: str | Path,
    stage: str,
    *,
    config: GateConfig | None = None,
    extra_providers: list[Callable[[], list[GateCheck]]] | None = None,
    include_entry_points: bool = True,
    include_builtins: bool = True,
) -> GateReport:
    """Discover the stage's checks, run each, apply the enforce overlay."""
    wd = Path(workdir)
    gcfg = config if config is not None else load_gate_config(wd)
    checks = discover_gate_checks(
        stage,
        extra_providers=extra_providers,
        include_entry_points=include_entry_points,
        include_builtins=include_builtins,
    )

    outcomes: list[CheckOutcome] = []
    for check in checks:
        enforced = gcfg.is_enforced(check.id)

        if gcfg.is_disabled(check.id):
            outcomes.append(
                CheckOutcome(
                    id=check.id,
                    stage=check.stage,
                    ran=False,
                    passed=None,
                    enforced=enforced,
                    findings=(),
                    skipped_reason="disabled in .scitex/dev/config.yaml",
                )
            )
            continue

        if check.requires and not _importable(check.requires):
            outcomes.append(
                CheckOutcome(
                    id=check.id,
                    stage=check.stage,
                    ran=False,
                    passed=None,
                    enforced=enforced,
                    findings=(),
                    skipped_reason=f"requires {check.requires!r} (not importable)",
                )
            )
            continue

        try:
            result = check.run(wd, dict(gcfg.raw))
        except Exception as exc:  # fail-closed
            crash = Finding(
                check_id=check.id,
                kind="check_crashed",
                message=f"gate check crashed: {exc!r}",
                severity="error",
                fix_hint="report to the owning package; the gate fails closed on a crash",
            )
            outcomes.append(
                CheckOutcome(
                    id=check.id,
                    stage=check.stage,
                    ran=True,
                    passed=False,
                    enforced=enforced,
                    findings=(crash,),
                )
            )
            continue

        outcomes.append(
            CheckOutcome(
                id=check.id,
                stage=check.stage,
                ran=True,
                passed=bool(result.passed),
                enforced=enforced,
                findings=_with_undetermined_finding(check, result),
                undetermined=is_undetermined(result),
                undetermined_reason=undetermined_reason(result),
            )
        )

    return GateReport(
        stage=stage,
        workdir=str(wd),
        outcomes=tuple(outcomes),
        config_source=gcfg.source,
    )


def report_to_dict(report: GateReport) -> dict:
    """JSON-serializable view of a GateReport (for ``gate --json``)."""
    return {
        "stage": report.stage,
        "workdir": report.workdir,
        "blocking": report.blocking,
        "passed": report.passed,
        "config_source": report.config_source,
        "checks": [
            {
                "id": o.id,
                "stage": o.stage,
                "ran": o.ran,
                "passed": o.passed,
                "enforced": o.enforced,
                "blocked": o.blocked,
                "skipped_reason": o.skipped_reason,
                # Emitted alongside `passed` rather than folded into it: a
                # consumer that treats false-as-failed stays correct, and one
                # that wants to distinguish "failed" from "could not tell"
                # now can. Folding them would have made every existing JSON
                # reader silently wrong about which it was looking at.
                "undetermined": o.undetermined,
                "undetermined_reason": o.undetermined_reason,
                "findings": [
                    {
                        "check_id": f.check_id,
                        "kind": f.kind,
                        "message": f.message,
                        "severity": f.severity,
                        "fix_hint": f.fix_hint,
                    }
                    for f in o.findings
                ],
            }
            for o in report.outcomes
        ],
    }


__all__ = ["CheckOutcome", "GateReport", "run_gate", "report_to_dict"]
