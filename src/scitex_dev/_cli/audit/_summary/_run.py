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

import sys

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
from ._report import (
    _emit_baseline_suppressed,
    _emit_baseline_written,
    _emit_human,
    _emit_json,
    _violation_to_dict,
)
from ._severity import filter_violations as _filter_violations
from ._severity import max_severity as _max_severity

__all__ = [
    "RULE_SEVERITY",
    "SEVERITY_ORDER",
    "run_audit",
    "run_audit_all",
]

# Verdict RENDERING lives in `_report.py` (imported above and re-exported
# here, so `from ._run import _emit_human` in `_mcp_audit.py` is unchanged).
# It moved when `_emit_human` gained a required `category`: the noun used to
# be hardcoded "CLI convention", and the MCP auditor reusing this renderer
# printed that noun for a population it had not audited.

# Rule severity, per-severity tallies and --rule/--exclude/--severity
# filtering live in `_severity.py` (imported above and re-exported here,
# so `from ._run import RULE_SEVERITY` and the `_audit.py` PEP 562
# forwarder are unchanged).


def _no_entry_point_reason(package: str) -> str:
    """Explain a `not-auditable` that the resolver left unattributed.

    The resolver records a reason for every failure it can SEE -- a load
    exception, an object that is neither click nor argparse. It records
    nothing for the commonest case of all: no ``console_scripts`` entry point
    by that name, which it treats as an early return. The caller then printed
    ``not-auditable: unknown``.

    ``unknown`` is the least actionable string available and it hid a
    completely different fact. Measured 2026-08-17 on scitex-agent-container:
    the package declares a ``scitex-agent-container`` console script and
    audits cleanly at 0.48.0 and 0.51.0, yet an auditor resolved out of an
    UNRELATED package's venv reported ``not-auditable: unknown`` as an ERROR
    and took that repo's develop red. The subject was never at fault -- the
    grading interpreter simply did not have it installed.

    So this names the interpreter. "Not installed HERE" and "this CLI is
    malformed" demand opposite actions from the reader, and `unknown` let
    neither be chosen. Similar entry-point names are listed because the other
    realistic cause is a console script whose name differs from the
    distribution name, which is then visible at a glance.
    """
    try:
        import importlib.metadata as im

        try:
            eps = im.entry_points(group="console_scripts")
        except TypeError:  # pragma: no cover - Python < 3.10 shape
            eps = im.entry_points().get("console_scripts", [])
        stem = package.split("-")[0]
        near = sorted({n for n in (getattr(e, "name", "") for e in eps) if stem in n})
    except Exception:  # pragma: no cover - metadata backend variance
        near = []
    reason = (
        f"no console_scripts entry point named {package!r} in {sys.executable} "
        f"-- the package is very likely not installed in the interpreter "
        f"running this audit, which says nothing about its CLI"
    )
    if near:
        reason += f" (similar names present: {', '.join(near[:6])})"
    return reason


def _audit_one(
    package: str,
    behavioral: bool = False,
    timeout: float = 30.0,
    ep_value_for=None,
    repo_root=None,
    coverage=None,
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
        return f"not-auditable: {last_err or _no_entry_point_reason(package)}", []

    out: list = []
    # The DENOMINATOR, accumulated alongside `out` so a verdict can state how
    # many commands it actually inspected instead of leaving a reader unable
    # to tell forty from zero. A caller that wants the figure passes one in
    # (it fills in place, like `out`); callers that do not still work, and
    # `describe_or_unknown` renders their absent denominator as NOT REPORTED.
    from ._coverage import SurfaceCoverage

    if coverage is None:
        coverage = SurfaceCoverage()
    _walk(cmd, [], out, root_display=package, coverage=coverage)
    _check_introspection(cmd, package, out)
    _check_config_help(cmd, package, out)
    _scan_env_vars(package, out, repo_root=repo_root)
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
    # REFUSE rather than pass. Zero inspected commands is not a clean CLI, it
    # is an unanswered question — and it would otherwise render exactly like a
    # package with forty conforming commands. Reachable when the root command
    # itself is hidden.
    if not coverage.is_answerable():
        return (
            "not-auditable: the CLI walker inspected 0 commands, so no "
            "verdict is possible (is the root command hidden?)",
            out,
        )
    return ("ok" if not out else "warn"), out



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

    from ._coverage import SurfaceCoverage

    coverage = SurfaceCoverage()
    status, violations = _audit_one(
        package,
        behavioral=behavioral,
        timeout=timeout,
        repo_root=repo_root,
        coverage=coverage,
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
        _emit_human(package, status, violations, coverage, category="CLI convention")
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
    from ._coverage import SurfaceCoverage

    for name, ep, hint in targets:
        # Fresh per package — coverage is per-CLI, and reusing one accumulator
        # would make every package after the first report the union.
        coverage = SurfaceCoverage()
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
                        name,
                        behavioral=behavioral,
                        timeout=timeout,
                        coverage=coverage,
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
            _emit_human(name, status, violations, coverage, category="CLI convention")
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
