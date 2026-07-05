#!/usr/bin/env python3
# Timestamp: 2026-07-05
# File: scitex_dev/trace_env/report.py

"""Human-readable rendering for :class:`TraceEnvResult`.

The CLI stays thin by delegating all text formatting here. ``--json``
callers use :meth:`TraceEnvResult.to_dict` directly; these helpers cover
the default report and the ``--quiet`` one-line summary.
"""

from __future__ import annotations

from .config import TraceEnvResult


def format_report(result: TraceEnvResult) -> str:
    """Full human-readable report for scan or trace mode."""
    lines: list[str] = []
    if result.error:
        lines.append(f"error: {result.error}")
        if result.mode == "scan":
            return "\n".join(lines)

    if result.mode == "scan":
        lines.append(
            f"scanned {result.scanned_files} file(s); "
            f"tmux global env: {'read' if result.tmux_available else 'unavailable'}"
        )
        for v in result.variables:
            lines.append("")
            state = "SET" if v.currently_set else "unset"
            val = f" = {v.current_value}" if v.currently_set else ""
            lines.append(f"{v.name}: currently {state}{val}")
            if not v.assignments:
                lines.append("  (no assignment sites found)")
            for a in v.assignments:
                lines.append(f"  [{a.surface}] {a.file}:{a.line}: {a.text}")
        return "\n".join(lines)

    # trace mode
    lines.append(f"observed {result.exec_stages} execve stage(s)")
    for v in result.variables:
        lines.append("")
        hit = next(
            (h for h in result.trace_hits if h.var == v.name), None
        )
        if hit is None:
            lines.append(f"{v.name}: never appears in any exec stage")
            continue
        val = f" = {hit.value}" if hit.value else ""
        argv = " ".join(hit.argv) if hit.argv else ""
        lines.append(
            f"{v.name}: first appears at exec stage #{hit.stage_index}{val}"
        )
        lines.append(f"  binary: {hit.binary}")
        lines.append(f"  argv:   {argv}")
    return "\n".join(lines)


def format_quiet(result: TraceEnvResult) -> str:
    """One-line summary (mirrors rename-symbols' ``--quiet``)."""
    if result.error:
        return f"error: {result.error.splitlines()[0]}"
    if result.mode == "trace":
        located = sum(1 for h in result.trace_hits)
        return (
            f"trace: {located}/{len(result.variables)} vars located "
            f"across {result.exec_stages} exec stages"
        )
    set_n = sum(1 for v in result.variables if v.currently_set)
    sites = sum(len(v.assignments) for v in result.variables)
    return (
        f"scan: {set_n}/{len(result.variables)} vars set / "
        f"{sites} assignment sites / {result.scanned_files} files"
    )


# EOF
