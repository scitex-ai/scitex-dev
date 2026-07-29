"""audit-cli orchestration: severity, filtering, reporting, run entry points.

Extracted from `_audit.py` (legacy-oversized) in slice 4 of the
CLI-standardization plan. `_audit.py` forwards the moved names via a
PEP 562 module `__getattr__`, so historical imports keep working.

Slice-4 addition: the `--baseline` ratchet (see `_baseline.py`) —
`run_audit` / `run_audit_all` suppress previously-recorded violations
and fail/warn only on NEW ones.
"""

from __future__ import annotations

from pathlib import Path

import click

from ._baseline import (
    load_baseline,
    partition_violations,
    resolve_baseline_path,
    write_baseline,
)
from ._behavioral import _check_behavioral
from ._severity import (
    EMIT_LEVEL,
    RULE_SEVERITY,
    SEVERITY_ORDER,
    format_severity_counts,
    severity_counts,
    severity_of,
)
from ._severity import filter_violations as _filter_violations
from ._severity import max_severity as _max_severity

__all__ = [
    "RULE_SEVERITY",
    "SEVERITY_ORDER",
    "run_audit",
    "run_audit_all",
]

# Rule severity, per-severity tallies and --rule/--exclude/--severity
# filtering live in `_severity.py` (imported above and re-exported here,
# so `from ._run import RULE_SEVERITY` and the `_audit.py` PEP 562
# forwarder are unchanged).


def _audit_one(
    package: str,
    behavioral: bool = False,
    timeout: float = 30.0,
    ep_value_for=None,
    repo_root=None,
) -> tuple[str, list]:
    """Audit a single package; return (status, violations).

    Status is one of: "ok", "warn", "skip-mcp", "not-found", "not-auditable".

    ``repo_root`` (from ``--path`` via ``resolve_target_tree``) roots the
    static §2/§11 source scans at that checkout (`_cli_repo_scans`) so
    audit-cli honours ``--path``; the command-tree walk stays import-based.
    """
    from ._audit import (
        _check_cli_framework,
        _check_config_help,
        _check_introspection,
        _check_no_interactive_prompts,
        _check_option_positional_ordering,
        _check_startup_speed,
        _ep_value_for,
        _is_mcp_server_entry,
        _isolated_streams,
        _resolve_entry_point,
        _scan_env_vars,
        _walk,
    )
    from ._dev_group import check_dev_command_group
    from ._gui_group import check_gui_command_group
    from ._std_rules import (
        check_deprecated_alias_metadata,
        check_verb_exception_comments,
    )

    if ep_value_for is None:
        ep_value_for = _ep_value_for
    ep_value = ep_value_for(package)
    if ep_value is None:
        return "not-found", []
    if _is_mcp_server_entry(ep_value):
        return "skip-mcp", []

    # MCP / argparse entry points may close stdio on import or write protocol
    # frames to stdout — `_isolated_streams` redirects the three standard
    # streams to /dev/null and restores them on exit.
    with _isolated_streams():
        cmd = _resolve_entry_point(package)

    if cmd is None:
        last_err = getattr(_resolve_entry_point, "_last_err", None)
        if hasattr(_resolve_entry_point, "_last_err"):
            delattr(_resolve_entry_point, "_last_err")
        return f"not-auditable: {last_err or 'unknown'}", []

    out: list = []
    _walk(cmd, [], out, root_display=package)
    _check_introspection(cmd, package, out)
    _check_config_help(cmd, package, out)
    _scan_env_vars(package, out)
    _check_startup_speed(package, out)
    if repo_root is None:
        _check_no_interactive_prompts(package, out)
        _check_cli_framework(package, out)
    else:
        from ._cli_repo_scans import scan_repo_source

        scan_repo_source(package, repo_root, out)
    _check_option_positional_ordering(package, cmd, out)
    # §1f — verb_exceptions entries must carry a `# why` comment.
    check_verb_exception_comments(package, out)
    # §5 — static `_deprecated_alias` metadata verification.
    check_deprecated_alias_metadata(cmd, package, out)
    # §12 — canonical `gui {open,serve,status,stop}` command group.
    check_gui_command_group(cmd, package, out)
    # §13 — self-maintenance commands must nest under a `dev` group.
    check_dev_command_group(cmd, package, out)
    if behavioral:
        _check_behavioral(package, out, cmd, timeout=timeout)
    return ("ok" if not out else "warn"), out


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


def _emit_human(package: str, status: str, violations: list) -> None:
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
        _emit("error", f"{package}: CLI conventions: {status}", err=True)
        return
    from ...._audit_disclaimer import emit_disclaimer, emit_skill_hints

    if status == "ok":
        _emit("success", f"{package}: no CLI convention violations")
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
    # Category-named failure line — mirrors the clean line's
    # "no CLI convention violations". See the note in _project/_audit.py.
    headline_level = "error" if sev == "error" else "warning"
    _emit(
        headline_level,
        f"{package}: CLI conventions: {format_severity_counts(violations)}",
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


def run_audit(
    package: str,
    behavioral: bool = False,
    output_json: bool = False,
    registry_provenance: str = "",
    rules: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    min_severity: str | None = None,
    timeout: float = 30.0,
    baseline_path: str | Path | None = None,
    repo_root: Path | None = None,
) -> int:
    """Audit a single package (single-target mode).

    Baseline ratchet: when the resolved baseline file exists (the
    `--baseline` flag or the default `.scitex/dev/cli-audit-baseline.yaml`
    in the cwd), previously-recorded violations are suppressed and only
    NEW ones are reported / drive the exit code. When `--baseline` is
    passed and the file does not exist yet, the current violations are
    reported and then recorded (ratchet initialization — exits 0).
    """
    # Category-aware skip: archived packages, templates, etc. — see
    # `scitex_dev._ecosystem._core.should_skip_audit` for the per-auditor
    # category map.
    try:
        from ...._ecosystem import should_skip_audit
    except ImportError:
        should_skip_audit = lambda *_a, **_k: (False, "")  # noqa: E731
    skip, reason = should_skip_audit(package, "audit-cli")
    if skip:
        if output_json:
            rec = {"package": package, "status": f"skip-{reason}", "violations": []}
            _emit_json([rec], registry_provenance or "single-package mode")
        else:
            from .._emit import emit as _emit_skip

            _emit_skip("skip", f"{package}: {reason}")
        return 0

    status, violations = _audit_one(
        package, behavioral=behavioral, timeout=timeout, repo_root=repo_root
    )
    violations = _filter_violations(violations, rules, exclude, min_severity)

    bl_path = resolve_baseline_path(baseline_path)
    write_requested = baseline_path is not None and not bl_path.exists()
    suppressed: list = []
    if bl_path.exists():
        violations, suppressed = partition_violations(
            violations, load_baseline(bl_path)
        )

    if not violations and status == "warn":
        status = "ok"
    if output_json:
        rec = {
            "package": package,
            "status": status,
            "severity_counts": severity_counts(violations),
            "violations": [_violation_to_dict(v) for v in violations],
        }
        if suppressed or bl_path.exists():
            rec["baseline_suppressed"] = len(suppressed)
        _emit_json([rec], registry_provenance or "single-package mode")
    else:
        _emit_human(package, status, violations)
        if suppressed:
            _emit_baseline_suppressed(len(suppressed), bl_path)
    if write_requested:
        n_written = write_baseline(bl_path, violations)
        if not output_json:
            _emit_baseline_written(n_written, bl_path)
        return 0
    if status.startswith("not-auditable"):
        return 2
    if status == "not-found":
        # Legitimate "no CLI" — exit 0, audit-cli has nothing to enforce.
        return 0
    # Exit 1 if any violation reaches `error` severity. Warnings alone exit 0.
    return 1 if _max_severity(violations) == "error" else 0


def run_audit_all(
    behavioral: bool = False,
    output_json: bool = False,
    dry_run: bool = False,
    registry_path: str | Path | None = None,
    rules: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    min_severity: str | None = None,
    timeout: float = 30.0,
    baseline_path: str | Path | None = None,
) -> int:
    """Audit every package in the registry (ecosystem-wide mode).

    With dry_run=True, lists the targets without auditing. Baseline
    ratchet semantics match `run_audit` (fingerprints are keyed by
    command path, which includes the package name, so one baseline file
    covers the whole fleet run).
    """
    from ._audit import (
        _PackageTimeout,
        _ep_value_for,
        _is_mcp_server_entry,
        _load_registry,
        _watchdog,
    )

    registry, provenance = _load_registry(registry_path)
    targets: list[tuple[str, str, str]] = []  # (name, ep_value, status_hint)
    for name, _info in registry.items():
        ep_value = _ep_value_for(name)
        if ep_value is None:
            targets.append((name, "", "not-found"))
            continue
        if _is_mcp_server_entry(ep_value):
            targets.append((name, ep_value, "skip-mcp"))
            continue
        targets.append((name, ep_value, "audit"))

    if dry_run:
        if output_json:
            payload = {
                "registry_source": provenance,
                "dry_run": True,
                "targets": [
                    {"package": n, "entry_point": ep, "action": s}
                    for n, ep, s in targets
                ],
            }
            import json as _json

            click.echo(_json.dumps(payload, indent=2))
        else:
            click.echo(f"# registry: {provenance}")
            click.echo(f"# {len(targets)} package(s) — dry-run, no audit performed")
            for name, ep, status in targets:
                click.echo(f"  {status:<12} {name:<28} {ep}")
        return 0

    bl_path = resolve_baseline_path(baseline_path)
    write_requested = baseline_path is not None and not bl_path.exists()
    baseline = load_baseline(bl_path) if bl_path.exists() else set()

    records: list[dict] = []
    counts = {"ok": 0, "warn": 0, "skip-mcp": 0, "not-found": 0, "not-auditable": 0}
    any_error = False
    all_new_violations: list = []
    total_suppressed = 0
    for name, ep, hint in targets:
        if hint == "not-found":
            status, violations = "not-found", []
        elif hint == "skip-mcp":
            status, violations = "skip-mcp", []
        else:
            # Wall-clock watchdog so a single hanging package can't wedge --all.
            # Budget = behavioral subprocess cap + 5s slack for static checks.
            wall_budget = max(timeout + 5.0, 10.0)
            try:
                with _watchdog(wall_budget):
                    status, violations = _audit_one(
                        name, behavioral=behavioral, timeout=timeout
                    )
            except _PackageTimeout:
                status, violations = (
                    f"not-auditable: timed out after {wall_budget:.0f}s",
                    [],
                )
        violations = _filter_violations(violations, rules, exclude, min_severity)
        suppressed: list = []
        if baseline:
            violations, suppressed = partition_violations(violations, baseline)
            total_suppressed += len(suppressed)
        all_new_violations.extend(violations)
        if not violations and status == "warn":
            status = "ok"
        if not output_json:
            _emit_human(name, status, violations)
            if suppressed:
                _emit_baseline_suppressed(len(suppressed), bl_path)
        if _max_severity(violations) == "error" or status.startswith("not-auditable"):
            any_error = True
        rec = {
            "package": name,
            "status": status,
            "severity_counts": severity_counts(violations),
            "violations": [_violation_to_dict(v) for v in violations],
        }
        if baseline:
            rec["baseline_suppressed"] = len(suppressed)
        records.append(rec)
        bucket = "not-auditable" if status.startswith("not-auditable") else status
        counts[bucket] = counts.get(bucket, 0) + 1

    if write_requested:
        n_written = write_baseline(bl_path, all_new_violations)

    if output_json:
        _emit_json(records, provenance)
    else:
        click.echo("")
        click.echo(f"# registry: {provenance}")
        summary = (
            f"# summary: {counts['ok']} ok, {counts['warn']} warn, "
            f"{counts['skip-mcp']} skipped (MCP), "
            f"{counts['not-found']} not-found, {counts['not-auditable']} not-auditable"
        )
        if baseline:
            summary += f", {total_suppressed} baseline-suppressed"
        click.echo(summary)
        if write_requested:
            _emit_baseline_written(n_written, bl_path)
    if write_requested:
        return 0
    return 1 if any_error else 0
