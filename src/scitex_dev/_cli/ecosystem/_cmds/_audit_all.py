#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ecosystem `audit-all` — run every audit-* on each DISTRIBUTION."""

import click

from ...._ecosystem.help_spec import CliHelp, Example, SpecCommand


def register(ecosystem):
    @ecosystem.command(
        "audit-all",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Run every audit-* on each DISTRIBUTION; aggregate exit codes.",
            description=(
                "DISTRIBUTIONS accepts: a single name, multiple names as "
                "separate args, comma-separated names, or the literal "
                "`all` to expand to every registered ecosystem package. "
                "Overall exit=1 if any auditor on any package reports "
                "violations. For cross-leaf rollups across the whole "
                "ecosystem with cross-pkg dedup, use audit-summary "
                "instead.",
            ),
            examples=(
                Example("{prog} ecosystem audit-all scitex-io", "One package."),
                Example(
                    "{prog} ecosystem audit-all scitex-io scitex-stats",
                    "Multiple packages.",
                ),
                Example(
                    "{prog} ecosystem audit-all scitex-io,scitex-stats",
                    "Comma-separated packages.",
                ),
                Example(
                    "{prog} ecosystem audit-all all --severity error",
                    "Every registered package.",
                ),
                Example("{prog} ecosystem audit-all scitex-io --json", "Structured JSON output."),
            ),
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
    @click.option(
        "--path",
        "explicit_path",
        type=click.Path(exists=True, file_okay=False, dir_okay=True),
        default=None,
        help=(
            "Audit a SPECIFIC checkout path (e.g. a git worktree). "
            "Lets worktree-based agents self-verify before pushing instead "
            "of relying on CI. When given, the path is threaded through to "
            "every sub-auditor's `--path` option (alias of the legacy "
            "`--repo`); the distribution NAME is still required and is "
            "used for skill/rule lookup only — the source under audit is "
            "rooted at this path. Only ONE distribution may be passed "
            "with --path."
        ),
    )
    @click.option(
        "--new-only",
        is_flag=True,
        help=(
            "Diff-aware audit (lead task #40b): report only NET-NEW "
            "violations vs the base ref (default `develop`; override with "
            "--since). Inherited debt the PR didn't introduce stops "
            "blocking new PRs; the strict full audit stays the default. "
            "Requires git on PATH and a clean working tree (the base ref "
            "is staged via `git worktree add --detach`). Only ONE "
            "distribution may be paired with --new-only."
        ),
    )
    @click.option(
        "--since",
        "since_ref",
        default="develop",
        show_default=True,
        help=(
            "Base ref for --new-only diff. Stages a temporary worktree at "
            "this ref so the caller's HEAD never moves; cleans up after."
        ),
    )
    def ecosystem_audit_all(
        distributions,
        as_json,
        severity,
        jobs,
        audit_jobs,
        no_version_check,
        explicit_path,
        new_only,
        since_ref,
    ):
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

        # --path scoping: only ONE distribution may be paired with a
        # specific path. A worktree IS one repo, even if `audit-all` is
        # nominally polyrepo-capable; rolling up multiple distributions
        # against one path is a bug magnet.
        if explicit_path and len(pkgs) != 1:
            click.echo(
                "error: --path requires exactly ONE distribution "
                f"(got {len(pkgs)}: {', '.join(pkgs) or '<empty>'}).",
                err=True,
            )
            _sys.exit(2)

        # --new-only scoping: same single-distribution constraint. The
        # diff-aware compare runs audit-all twice (HEAD + base worktree)
        # against ONE distribution; rolling up multiple dists into one
        # diff would just confuse the violation-key set arithmetic.
        if new_only and len(pkgs) != 1:
            click.echo(
                "error: --new-only requires exactly ONE distribution "
                f"(got {len(pkgs)}: {', '.join(pkgs) or '<empty>'}).",
                err=True,
            )
            _sys.exit(2)

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
            # Thread --path through to EVERY sub-auditor. All six now
            # accept `--path` (alias `--repo`) and resolve their target
            # tree through the SAME shared `resolve_target_tree`, so an
            # explicit worktree / CI checkout wins uniformly. Previously
            # only project/django/python-apis honoured --path while
            # cli/mcp-tools/skills silently graded the registry/import-
            # location tree (the operator's ~/proj/<pkg> develop checkout
            # on CI) — a false result that reported as if it graded the
            # PR. Fixed so --path wins for all six.
            if explicit_path:
                cmd += ["--path", str(explicit_path)]
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, env=sub_env)
            except Exception as e:
                click.echo(
                    f"error: {a} on {distribution} failed to launch: {e}",
                    err=True,
                )
                return a, {"exit": 1, "error": str(e)}
            # `_raw` carries the auditor's combined text for skip-rule
            # classification and is POPPED before the JSON payload is
            # assembled, so it never changes the published shape. Without
            # it, --json mode parsed stdout into `data` and kept no text,
            # so masking silently classified nothing and every declared
            # deferral was ignored for machine consumers.
            raw_text = (r.stdout or "") + "\n" + (r.stderr or "")
            if as_json:
                payload = r.stdout.strip() or "null"
                try:
                    res = {"exit": r.returncode, "data": _json.loads(payload)}
                except _json.JSONDecodeError:
                    res = {"exit": r.returncode, "raw": payload}
                res["_raw"] = raw_text
                return a, res
            return a, {
                "exit": r.returncode,
                "stdout": r.stdout,
                "stderr": r.stderr,
                "_raw": raw_text,
            }

        # Declared deferrals (`audit.skip-rules`). Honoured NATIVELY here
        # so the org reusable workflow and the per-repo pytest wrapper
        # grade the same thing — they used to disagree, leaving develop
        # green while unified CI was red on identical code. Honouring is
        # never silent: see the masked inventory emitted below.
        #
        # A malformed / rationale-less entry raises, and we let it: a
        # deferral config we cannot trust must not be graded as if the
        # repo had declared no deferrals at all.
        from ...audit._config._skip_rules import SkipRuleConfigError
        from ._audit_masking import (
            classify_output,
            json_payload,
            label_masked_lines,
            render_inventory,
            render_summary,
            resolve_skip_rules,
        )
        from ._audit_verdict import decide_pkg_exit

        try:
            skip_rules_by_pkg = resolve_skip_rules(pkgs, explicit_path)
        except SkipRuleConfigError as e:
            click.echo(f"error: {e}", err=True)
            _sys.exit(2)

        def _run_one(distribution: str) -> tuple[str, int, dict, object]:
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

            # Re-classify against declared skips. A sub-auditor that
            # failed ONLY on deferred rules no longer fails the run; one
            # that reported anything undeclared still does.
            # Classify ALWAYS, even with zero declared skips, so the
            # summary's error/masked counts are measured rather than
            # inferred from a subprocess exit code.
            rules = skip_rules_by_pkg.get(distribution) or []
            raw_by_audit = {a: (r.pop("_raw", "") or "") for a, r in results.items()}
            report = classify_output("\n".join(raw_by_audit.values()), rules)
            # The downgrade is decided against the audits that actually
            # FAILED, not against the whole run's concatenated output: a
            # WARN from an audit that exited 0 used to veto it, keeping
            # the package red beside its own "0 unmasked error(s), 1
            # masked by skip-rules" summary (#590). `report` is still the
            # whole run, so the inventory and the summary are unchanged.
            pkg_exit, warning = decide_pkg_exit(
                pkg_exit,
                distribution=distribution,
                report=report,
                failing_raw={
                    a: raw
                    for a, raw in raw_by_audit.items()
                    if results[a].get("exit", 0) != 0
                },
                skip_rules=rules,
            )
            if warning:
                click.echo(warning, err=True)
            return distribution, pkg_exit, results, report

        # --new-only orchestration: stage the base ref via worktree-
        # detach + run the SAME audit-all against the base path + diff
        # the violation key sets against the HEAD run + re-emit only
        # net-new findings. Falls back to strict audit on setup failure
        # (caller sees a warning, not a crash).
        if new_only and not as_json:
            from pathlib import Path as _Path

            from ._audit_all_new_only import drop_masked_lines, run_new_only_and_exit

            head_path = _Path(explicit_path).expanduser() if explicit_path else _Path.cwd()
            distribution = pkgs[0]
            # Run audit-all against HEAD first; reuse the existing
            # dispatch path so behaviour matches strict mode 1:1.
            # KEEP THE MASK REPORT. This branch used to discard it (`..., _`)
            # and rebuild the text from raw stdout/stderr, so `audit.skip-rules`
            # masked correctly in a strict local run and masked NOTHING in CI —
            # which is the flag repo quality workflows actually pass. A
            # maintainer configured it, watched the mask apply locally, shipped,
            # and the rule kept firing while the config claimed it was handled.
            # A SUPPRESSION THAT CANNOT SUPPRESS, lying in the direction that
            # wastes the most time (reported by scitex-cards, 2026-08-10).
            _, _head_exit, head_results, _head_report = _run_one(distribution)
            head_combined = "\n".join(
                (res.get("stdout") or "") + "\n" + (res.get("stderr") or "")
                for res in head_results.values()
            )
            head_combined = drop_masked_lines(head_combined, _head_report)
            # Never returns — the comparison owns the exit status.
            run_new_only_and_exit(
                head_path=head_path,
                distribution=distribution,
                since_ref=since_ref,
                head_combined=head_combined,
                head_exit=_head_exit,
                scitex_dev_bin=scitex_dev_bin,
                sub_env=sub_env,
            )

        all_results: dict[str, dict] = {}
        mask_reports: dict[str, object] = {}
        overall_exit = 0

        multi = len(pkgs) > 1

        def _emit_pkg(name: str, res: dict, report=None) -> None:
            """Print one package's captured audit output in audit order.

            MASKED findings are re-stamped `MASK: ` on the way out. Without
            it a masked finding reaches the reader still labelled `ERRO`
            while being provably unable to fail the gate, so the printed
            error count contradicts the exit code.
            """
            if as_json:
                return
            if multi:
                click.echo(f"\n###### {name} ######", err=True)
            for a in audits:
                r = res[a]
                header = f"\n=== {name} :: {a} ===" if multi else f"\n=== {a} ==="
                click.echo(header, err=True)
                if r.get("stdout"):
                    click.echo(label_masked_lines(r["stdout"], report))
                if r.get("stderr"):
                    click.echo(r["stderr"], err=True)

        def _emit_mask(name: str, report) -> None:
            """Print the masked inventory. NEVER behind a verbosity flag.

            Routed to stderr alongside the auditor headlines so it lands
            in CI logs on the same stream as the findings it explains.
            """
            if as_json or report is None:
                return
            for line in render_inventory(report, name):
                click.echo(line, err=True)

        # Run packages. When multiple packages run in parallel, collect all
        # results first, then print in the input `pkgs` order so the summary
        # is deterministic regardless of completion order.
        # PER-PACKAGE exit codes, recorded on BOTH paths. The summary line
        # below needs each package's own rc to say whether its tally is
        # accompanied by a red run; `overall_exit` cannot answer that in a
        # multi-package sweep, and the sequential path used to keep `rc`
        # only as a loop-local.
        rc_by_pkg: dict[str, int] = {}
        if jobs <= 1 or not multi:
            for d in pkgs:
                name, rc, res, rep = _run_one(d)
                all_results[name] = res
                mask_reports[name] = rep
                rc_by_pkg[name] = rc
                _emit_pkg(name, res, rep)
                _emit_mask(name, rep)
                if rc != 0:
                    overall_exit = 1
        else:
            with ThreadPoolExecutor(max_workers=jobs) as ex:
                futs = {ex.submit(_run_one, d): d for d in pkgs}
                for f in as_completed(futs):
                    name, rc, res, rep = f.result()
                    all_results[name] = res
                    mask_reports[name] = rep
                    rc_by_pkg[name] = rc
            for d in pkgs:
                _emit_pkg(d, all_results[d], mask_reports[d])
                _emit_mask(d, mask_reports[d])
                if rc_by_pkg[d] != 0:
                    overall_exit = 1

        if as_json:
            click.echo(
                _json.dumps(
                    {
                        "distributions": pkgs,
                        "results": all_results,
                        "skip_rules": json_payload(mask_reports, pkgs),
                        "exit_code": overall_exit,
                    },
                    indent=2,
                )
            )
        else:
            from ...._audit_disclaimer import emit_disclaimer, emit_skill_hints

            # Per-package summary — ALWAYS, single or multi. It must state
            # BOTH numbers: real errors AND masked count. A summary that
            # reports only "0 errors" while 150 are masked is a lie of
            # omission, and is exactly how develop stayed green while the
            # unified CI was red on identical code.
            click.echo("", err=True)
            for d in pkgs:
                rep = mask_reports.get(d)
                if rep is None:
                    continue
                click.echo(
                    render_summary(
                        d,
                        unmasked_errors=rep.unmasked_error_count,
                        unmasked_total=rep.unmasked_count,
                        masked=rep.masked_count,
                        declared=len(rep.skip_rules),
                        inspected=rep.inspected,
                        unreadable=len(rep.unreadable),
                        exit_code=rc_by_pkg.get(d, 0),
                    ),
                    err=True,
                )
            if len(pkgs) > 1:
                click.echo(f"summary: audited {len(pkgs)} package(s)", err=True)
                fails = [
                    n
                    for n, res in all_results.items()
                    if any(r.get("exit", 0) != 0 for r in res.values())
                ]
                # "all packages pass" is a STRONGER claim than exit 0, and it
                # was being printed on the exit codes alone. A package whose
                # findings could not be CLASSIFIED never established
                # cleanliness — the per-package line directly above already
                # says so ("N UNREADABLE ... NOT counted as clean"), and this
                # line was contradicting it in the same output block. The
                # reassuring sentence is the one humans read, so it must not
                # outrun the evidence.
                #
                # Deliberately OUTPUT-ONLY: the exit code is untouched here.
                # Folding unreadable into the VERDICT is the real fix and is
                # tracked separately — it needs the corpus measured first
                # (a recorded run had 366 UNREADABLE of 374 inspected), or
                # turning it on red-lights the fleet in one release.
                unreadable_total = sum(
                    len(rep.unreadable)
                    for d in pkgs
                    if (rep := mask_reports.get(d)) is not None
                )
                if fails:
                    click.echo(f"  failures: {', '.join(sorted(fails))}", err=True)
                elif unreadable_total:
                    click.echo(
                        f"  NOT a pass: {unreadable_total} line(s) claimed to be "
                        "findings and could not be classified, so cleanliness "
                        "was never established for every package",
                        err=True,
                    )
                else:
                    click.echo("  all packages pass", err=True)
            click.echo("", err=True)
            emit_disclaimer()
            if overall_exit:
                emit_skill_hints()
        _sys.exit(overall_exit)
