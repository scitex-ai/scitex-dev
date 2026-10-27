#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ecosystem `prune-disk` — the config-gated disk guard's CLI surface.

Click only. Every decision lives in :mod:`scitex_dev.hygiene`, so this
verb, the ``disk-guard`` cron job and any future caller share ONE engine
rather than drifting copies.

Host-level, not per-repo: disk acts on the machine, so there is no
``--repo``/``--package`` selection. OFF unless
``~/.scitex/dev/config.yaml`` sets ``cleanup.disk.enabled`` to literal
true; even then ``--apply`` is required to delete anything.
"""

from __future__ import annotations

import click

from ...._ecosystem.help_spec import CliHelp, Example, SpecCommand

_MARK = {"deleted": "x", "would-delete": ".", "kept": "-"}


def register(ecosystem):
    @ecosystem.command(
        "prune-disk",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Config-gated host disk hygiene (DEFAULT OFF, dry-run default).",
            description=(
                "Reclaims host disk, and only when four legs pass: dated SIF "
                "builds superseded by newer ones (never the live symlink "
                "target, never the newest N per family, never anything held "
                "open by a live process), stale /tmp/ci-* runner dirs past "
                "the age floor, and Docker build cache — cache ONLY at or "
                "above the use threshold and never mid-build.",
                "Any leg that cannot be evaluated reads as KEEP, never as "
                "pass. OFF unless ~/.scitex/dev/config.yaml sets "
                "cleanup.disk.enabled to literal true; even then --apply is "
                "required. No checkout, image, container or volume is ever "
                "touched.",
            ),
            examples=(
                Example(
                    "{prog} ecosystem prune-disk",
                    "Dry-run this host: what it would delete and why the rest is kept.",
                ),
                Example(
                    "{prog} ecosystem prune-disk --apply",
                    "Delete (requires cleanup.disk.enabled: true).",
                ),
                Example(
                    "{prog} ecosystem prune-disk --json",
                    "Dry-run with structured output.",
                ),
            ),
        ),
    )
    @click.option(
        "--apply",
        "do_apply",
        is_flag=True,
        help="Actually delete (default is dry-run). Also requires the config gate.",
    )
    @click.option(
        "--max-delete",
        "max_delete",
        type=int,
        default=None,
        help="Bound deletions this pass. Deferred candidates are REPORTED, not hidden.",
    )
    @click.option("--json", "as_json", is_flag=True, help="Emit structured JSON.")
    def ecosystem_prune_disk(do_apply, max_delete, as_json):
        import json as _json
        import sys as _sys

        from ....hygiene import disk_exit_code_for, sweep_host
        from ....hygiene._disk_guard_model import DiskGuardOutcome

        result = sweep_host(apply=do_apply, max_delete=max_delete)
        outcome = DiskGuardOutcome(results=(result,))

        if as_json:
            click.echo(
                _json.dumps(
                    {
                        "apply": do_apply,
                        "summary": outcome.summary_line(),
                        "results": [result.to_dict()],
                    },
                    indent=2,
                    default=str,
                )
            )
            _sys.exit(disk_exit_code_for(outcome))

        _render(result, do_apply)
        _sys.exit(disk_exit_code_for(outcome))

    def _render(result, do_apply):
        click.echo(f"host: {result.host}")
        state = "ENABLED" if result.enabled else "DISABLED (default OFF)"
        click.echo(f"  config   {state}; threshold {result.threshold_pct}%")
        if result.config_error and not result.enabled:
            click.echo(f"  reason   {result.config_error}")
        if result.aborted:
            click.echo(f"  ABORTED  {result.aborted}")
            return
        if result.use_before_pct is not None:
            click.echo(
                f"  use      {result.use_before_pct}% -> {result.use_after_pct}%"
            )
        verb = "deleted" if do_apply and result.enabled else "would-delete"
        for verdict in result.candidates:
            if verdict.deleted or verdict.action == "delete":
                mark = _MARK["deleted" if verdict.deleted else "would-delete"]
                size = f" ({verdict.size_bytes} B)" if verdict.size_bytes else ""
                click.echo(
                    f"  {mark} {verb:12} {verdict.path}{size} [{verdict.reason}]"
                )
        breakdown = result.keep_reason_breakdown
        if breakdown:
            detail = ", ".join(f"{k}={v}" for k, v in breakdown.items())
            click.echo(
                f"  {_MARK['kept']} protected   {len(result.kept)} kept: {detail}"
            )
        if not do_apply:
            click.echo(
                "Dry run. --apply deletes, and ONLY if cleanup.disk.enabled "
                "is literally true in ~/.scitex/dev/config.yaml.",
                err=True,
            )


# EOF
