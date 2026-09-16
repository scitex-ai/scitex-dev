#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared helpers for the `scitex-dev skills` command family."""

import os
import uuid
from pathlib import Path

import click


def _default_skills_destination(*, _user_path_fn=None) -> Path:
    """Resolve the canonical user-scoped store through scitex-config."""

    if _user_path_fn is None:
        from scitex_config._ecosystem import local_state

        _user_path_fn = local_state.user_path
    return _user_path_fn("dev", "skills")


def _git_checkout_containing(path: Path) -> Path | None:
    """Return the Git authority checkout containing a real path, if any."""

    resolved = path.resolve(strict=False)
    for candidate in (resolved, *resolved.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _require_external_destination(path: Path) -> Path:
    """Reject generated state whose real path lands in a Git checkout."""

    checkout = _git_checkout_containing(path)
    if checkout is not None:
        raise click.ClickException(
            f"refusing skills destination {path}: its real path "
            f"{path.resolve(strict=False)} is inside Git authority {checkout}"
        )
    return path


def _require_symlink_slot(link: Path) -> None:
    """Fail before export when a projection would overwrite real content."""

    if link.exists() and not link.is_symlink():
        raise click.ClickException(
            f"cannot project skills: {link} exists and is not a symlink"
        )


def _ensure_symlink(link: Path, target: Path) -> None:
    """Atomically install ``link`` and verify its observable postcondition.

    Existing real files/directories are never removed. Existing symlinks,
    including broken or wrong ones, are replaced with ``os.replace`` so a
    consumer never observes an unlink/create gap.
    """

    target = target.resolve(strict=True)
    link.parent.mkdir(parents=True, exist_ok=True)
    _require_symlink_slot(link)
    temporary = link.with_name(f".{link.name}.tmp-{os.getpid()}-{uuid.uuid4().hex}")
    try:
        os.symlink(target, temporary)
        os.replace(temporary, link)
    finally:
        if temporary.is_symlink():
            temporary.unlink()
    if not link.is_symlink() or link.resolve(strict=True) != target:
        raise click.ClickException(
            "skills projection postcondition failed: "
            f"{link} does not resolve to {target}"
        )


def _print_export_result(exported, dest_path, as_json=False):
    """Print export results."""
    import json as json_mod

    if as_json:
        click.echo(
            json_mod.dumps(
                {k: [str(f) for f in v] for k, v in exported.items()}, indent=2
            )
        )
    elif not exported:
        click.echo("No skills found to export.")
    else:
        total = sum(len(v) for v in exported.values())
        click.echo(
            f"Exported {total} files across {len(exported)} packages to {dest_path}"
        )
        for k, v in sorted(exported.items()):
            click.echo(f"  {k}: {len(v)} files")


def _report_symlink(link: Path, target: Path) -> None:
    """Keep projection diagnostics off the machine-readable stdout channel."""

    click.echo(f"linked: {link} → {target.resolve()}", err=True)


__all__ = [
    "_default_skills_destination",
    "_ensure_symlink",
    "_git_checkout_containing",
    "_print_export_result",
    "_report_symlink",
    "_require_external_destination",
    "_require_symlink_slot",
]
