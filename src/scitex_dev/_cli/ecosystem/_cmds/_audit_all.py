#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ecosystem `audit-all` — run every audit-* on each DISTRIBUTION."""

import click


def register(ecosystem):
    @ecosystem.command(
        "audit-all",
        epilog=(
            "Examples:\n"
            "  $ scitex-dev ecosystem audit-all scitex-io\n"
            "  $ scitex-dev ecosystem audit-all scitex-io scitex-stats\n"
            "  $ scitex-dev ecosystem audit-all scitex-io,scitex-stats\n"
            "  $ scitex-dev ecosystem audit-all all --severity error\n"
            "  $ scitex-dev ecosystem audit-all scitex-io --json\n"
            "\n"
            "Runs every audit-* on each given distribution and\n"
            "aggregates exit codes (overall exit=1 if any auditor on any\n"
            "package reports violations). Pass `all` to run across every\n"
            "registered ecosystem package. For cross-leaf rollups across\n"
            "the whole ecosystem with cross-pkg dedup, use audit-summary\n"
            "instead."
        ),
    )
    @click.argument("distributions", nargs=-1, required=True)
    @click.option("--json", "as_json", is_flag=True, help="Emit JSON output.")
    @click.option(
        "--severity",
        type=click.Choice(["info", "warn", "error"]),
        default="warn",
        help="Minimum severity to report (passed through to each auditor).",
    )
    @click.option(
        "--jobs",
        "-j",
        default=1,
        show_default=True,
        type=int,
        help="Run packages in parallel.",
    )
    @click.option(
        "--audit-jobs",
        default=0,
        show_default=True,
        type=int,
        help=(
            "Concurrent audits within a single package "
            "(0 = run all audits at once). Each audit is an independent "
            "subprocess, so this is the main wall-clock win."
        ),
    )
    @click.option(
        "--no-version-check",
        is_flag=True,
        help=(
            "Skip the pre-audit check that compares the installed "
            "scitex-dev version against PyPI's latest. Useful on "
            "air-gapped boxes or when you intentionally want to run "
            "an older rule corpus."
        ),
    )
    def ecosystem_audit_all(
        distributions, as_json, severity, jobs, audit_jobs, no_version_check
    ):
        """Run every audit-* on each DISTRIBUTION; aggregate exit codes.

        DISTRIBUTIONS accepts: a single name, multiple names as separate
        args, comma-separated names, or the literal `all` to expand to
        every registered ecosystem package.
        """
        import json as _json
        import os as _os
        import shutil as _shutil
        import subprocess
        import sys as _sys
        from concurrent.futures import ThreadPoolExecutor, as_completed

        from ...._ecosystem._core import ECOSYSTEM

        # Self-freshness check: warn (don't block) if installed
        # scitex-dev is older than PyPI's latest. Stale auditors
        # produced six false-positives on scitex-io in 2026-05; this
        # gate makes the staleness visible up front.
        if not no_version_check and not as_json:
            try:
                from ...audit._version_check import warn_if_stale

                warn_if_stale()
            except Exception:
                pass  # never let the freshness check break the audit

        # Expand input: split on commas, flatten, then resolve `all`.
        raw: list[str] = []
        for d in distributions:
            raw.extend(p.strip() for p in d.split(",") if p.strip())
        if "all" in raw:
            pkgs = list(ECOSYSTEM.keys())
        else:
            pkgs = []
            for name in raw:
                if name not in pkgs:
                    pkgs.append(name)

        # Order: cheap-to-fast → slow. Each audit-* honours --json + --severity
        # idempotently. audit-summary excluded — it's the cross-leaf rollup.
        audits = [
            "audit-cli",
            "audit-mcp-tools",
            "audit-skills",
            "audit-python-apis",
            "audit-project",
            "audit-django",
        ]

        sub_env = {**_os.environ, "SCITEX_DEV_NO_AUDIT_DISCLAIMER": "1"}
        scitex_dev_bin = _shutil.which("scitex-dev") or "scitex-dev"

        # Per-audit concurrency. 0 = run all audits for a package at once.
        # Each audit is an independent subprocess (no shared state), so the
        # bottleneck is process wall-clock — threads suffice and avoid the
        # pickling cost of a process pool. Output is always captured, never
        # streamed, so concurrent subprocesses can't interleave on the
        # terminal; results are reassembled in the fixed `audits` order
        # below for deterministic reporting.
        per_pkg_workers = audit_jobs if audit_jobs > 0 else len(audits)
        per_pkg_workers = max(1, min(per_pkg_workers, len(audits)))

        def _run_audit(distribution: str, a: str) -> tuple[str, dict]:
            cmd = [scitex_dev_bin, "ecosystem", a, distribution]
            if as_json:
                cmd.append("--json")
            if a == "audit-cli":
                cmd += ["--severity", severity]
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, env=sub_env)
            except Exception as e:
                click.echo(
                    f"error: {a} on {distribution} failed to launch: {e}",
                    err=True,
                )
                return a, {"exit": 1, "error": str(e)}
            if as_json:
                payload = r.stdout.strip() or "null"
                try:
                    return a, {"exit": r.returncode, "data": _json.loads(payload)}
                except _json.JSONDecodeError:
                    return a, {"exit": r.returncode, "raw": payload}
            return a, {
                "exit": r.returncode,
                "stdout": r.stdout,
                "stderr": r.stderr,
            }

        def _run_one(distribution: str) -> tuple[str, int, dict]:
            collected: dict = {}
            if per_pkg_workers == 1:
                for a in audits:
                    _, res = _run_audit(distribution, a)
                    collected[a] = res
            else:
                with ThreadPoolExecutor(max_workers=per_pkg_workers) as ex:
                    futs = [ex.submit(_run_audit, distribution, a) for a in audits]
                    for f in as_completed(futs):
                        a, res = f.result()
                        collected[a] = res
            # Reassemble in the fixed `audits` order — deterministic output
            # regardless of which audit finished first.
            results = {a: collected[a] for a in audits}
            pkg_exit = 1 if any(r.get("exit", 0) != 0 for r in results.values()) else 0
            return distribution, pkg_exit, results

        all_results: dict[str, dict] = {}
        overall_exit = 0

        multi = len(pkgs) > 1

        def _emit_pkg(name: str, res: dict) -> None:
            """Print one package's captured audit output in audit order."""
            if as_json:
                return
            if multi:
                click.echo(f"\n###### {name} ######", err=True)
            for a in audits:
                r = res[a]
                header = f"\n=== {name} :: {a} ===" if multi else f"\n=== {a} ==="
                click.echo(header, err=True)
                if r.get("stdout"):
                    click.echo(r["stdout"])
                if r.get("stderr"):
                    click.echo(r["stderr"], err=True)

        # Run packages. When multiple packages run in parallel, collect all
        # results first, then print in the input `pkgs` order so the summary
        # is deterministic regardless of completion order.
        if jobs <= 1 or not multi:
            for d in pkgs:
                name, rc, res = _run_one(d)
                all_results[name] = res
                _emit_pkg(name, res)
                if rc != 0:
                    overall_exit = 1
        else:
            with ThreadPoolExecutor(max_workers=jobs) as ex:
                futs = {ex.submit(_run_one, d): d for d in pkgs}
                rc_by_pkg: dict[str, int] = {}
                for f in as_completed(futs):
                    name, rc, res = f.result()
                    all_results[name] = res
                    rc_by_pkg[name] = rc
            for d in pkgs:
                _emit_pkg(d, all_results[d])
                if rc_by_pkg[d] != 0:
                    overall_exit = 1

        if as_json:
            click.echo(
                _json.dumps(
                    {
                        "distributions": pkgs,
                        "results": all_results,
                        "exit_code": overall_exit,
                    },
                    indent=2,
                )
            )
        else:
            from ...._audit_disclaimer import emit_disclaimer, emit_skill_hints

            if len(pkgs) > 1:
                click.echo("", err=True)
                click.echo(f"summary: audited {len(pkgs)} package(s)", err=True)
                fails = [
                    n
                    for n, res in all_results.items()
                    if any(r.get("exit", 0) != 0 for r in res.values())
                ]
                if fails:
                    click.echo(f"  failures: {', '.join(sorted(fails))}", err=True)
                else:
                    click.echo("  all packages pass", err=True)
            click.echo("", err=True)
            emit_disclaimer()
            if overall_exit:
                emit_skill_hints()
        _sys.exit(overall_exit)
