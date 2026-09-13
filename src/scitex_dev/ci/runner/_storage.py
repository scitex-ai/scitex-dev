"""Move a local GitHub Actions runner home off the root filesystem safely."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import click

from ..._ecosystem.help_spec import CliHelp, Example, SpecCommand
from ...status import Check, StatusCode

_MIN_HEADROOM = 1024**3


@dataclass(frozen=True)
class StorageAssessment:
    source: Path
    destination: Path
    checks: tuple[Check, ...]

    @property
    def ok(self) -> bool:
        return all(check.verdict.ok is True for check in self.checks)

    def to_dict(self) -> dict:
        return {
            "source": str(self.source),
            "destination": str(self.destination),
            "ok": self.ok,
            "checks": [check.to_dict() for check in self.checks],
        }


def _tree_bytes(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def assess_storage(source: Path, destination: Path) -> StorageAssessment:
    """Return evidence-backed preflight checks without changing either path."""
    source = Path(os.path.abspath(source.expanduser()))
    destination = destination.expanduser().resolve()
    checks: list[Check] = []

    if source.is_symlink():
        if source.resolve() == destination:
            checks.append(
                Check.ok(
                    "runner_storage_relocated",
                    f"{source} points to the requested destination {destination}",
                )
            )
            if (source / ".runner").is_file():
                checks.append(
                    Check.ok("runner_identity", f"observed {source / '.runner'}")
                )
            else:
                checks.append(
                    Check.not_ok(
                        "runner_identity",
                        f"{source / '.runner'} does not exist",
                        "Restore a valid runner home before starting its service.",
                    )
                )
            return StorageAssessment(source, destination, tuple(checks))
        checks.append(
            Check.not_ok(
                "source_not_symlink",
                f"{source} points to {source.resolve()}, not {destination}",
                "Inspect the current target; do not layer runner-home links.",
            )
        )
        return StorageAssessment(source, destination, tuple(checks))
    elif source.is_dir():
        checks.append(Check.ok("source_directory", f"{source} is a directory"))
    else:
        checks.append(
            Check.not_ok(
                "source_directory",
                f"{source} is not a directory",
                "Pass the registered runner home containing .runner and run.sh.",
            )
        )
        return StorageAssessment(source, destination, tuple(checks))

    identity = source / ".runner"
    if identity.is_file():
        checks.append(Check.ok("runner_identity", f"observed {identity}"))
    else:
        checks.append(
            Check.not_ok(
                "runner_identity",
                f"{identity} does not exist",
                "Refuse relocation until the source is proven to be a runner home.",
            )
        )

    destination_parent = destination.parent
    capacity_probe = destination_parent
    while not capacity_probe.exists() and capacity_probe != capacity_probe.parent:
        capacity_probe = capacity_probe.parent
    source_device = source.stat().st_dev
    destination_device = capacity_probe.stat().st_dev
    if source_device != destination_device:
        checks.append(
            Check.ok(
                "different_filesystem",
                f"source device={source_device}; destination device={destination_device}",
            )
        )
    else:
        checks.append(
            Check.not_ok(
                "different_filesystem",
                f"source and destination are both on device {source_device}",
                "Choose a destination on the capacity filesystem (normally /scratch).",
            )
        )

    if destination.exists() and (
        not destination.is_dir() or any(destination.iterdir())
    ):
        checks.append(
            Check.not_ok(
                "destination_empty",
                f"{destination} exists and is not empty",
                "Use a new destination or explicitly reconcile the existing copy first.",
            )
        )
    else:
        checks.append(Check.ok("destination_empty", f"{destination} is absent or empty"))

    required = _tree_bytes(source) + _MIN_HEADROOM
    available = shutil.disk_usage(capacity_probe).free
    if available >= required:
        checks.append(
            Check.ok(
                "destination_capacity",
                f"available={available} bytes; required={required} bytes",
            )
        )
    else:
        checks.append(
            Check.not_ok(
                "destination_capacity",
                f"available={available} bytes; required={required} bytes",
                "Free destination capacity or choose a larger filesystem.",
                cause=StatusCode(
                    kind="errno",
                    code="ENOSPC",
                    message="relocation was not started; free space, then rerun the preflight",
                ),
            )
        )
    return StorageAssessment(source, destination, tuple(checks))


def relocate_storage(
    source: Path,
    destination: Path,
    *,
    service: str,
    run=subprocess.run,
) -> StorageAssessment:
    """Relocate an idle runner atomically, rolling back if service health fails."""
    assessment = assess_storage(source, destination)
    if not assessment.ok:
        return assessment
    source = assessment.source
    destination = assessment.destination
    backup = source.with_name(f"{source.name}.relocation-backup")
    if backup.exists():
        raise click.ClickException(f"refusing: rollback path already exists: {backup}")

    def command(argv: list[str]) -> None:
        result = run(argv, text=True, capture_output=True)
        if result.returncode:
            raise click.ClickException(
                f"command failed ({result.returncode}): {' '.join(argv)}\n"
                f"{result.stderr.strip()}"
            )

    destination.mkdir(parents=True, exist_ok=True)
    command(["systemctl", "--user", "stop", service])
    try:
        command(["rsync", "-aH", "--numeric-ids", f"{source}/", f"{destination}/"])
        verify = run(
            [
                "rsync", "-aHn", "--delete", "--itemize-changes",
                f"{source}/", f"{destination}/",
            ],
            text=True,
            capture_output=True,
        )
        if verify.returncode or verify.stdout.strip():
            raise click.ClickException(
                "copied runner did not verify cleanly; source was preserved"
            )
        source.rename(backup)
        source.symlink_to(destination, target_is_directory=True)
        command(["systemctl", "--user", "start", service])
        command(["systemctl", "--user", "is-active", "--quiet", service])
    except Exception:
        if source.is_symlink():
            source.unlink()
        if backup.exists() and not source.exists():
            backup.rename(source)
        run(["systemctl", "--user", "start", service], text=True, capture_output=True)
        raise

    shutil.rmtree(backup)
    return assess_storage(source, destination)


def register(group: click.Group) -> None:
    @group.command(
        "relocate-storage",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Relocate a local runner home to a capacity filesystem.",
            examples=(
                Example(
                    "{prog} ci runner relocate-storage --source ~/actions-runner-org "
                    "--destination /scratch/$USER/actions-runner-org",
                    "Print the validated plan without changing the runner.",
                ),
            ),
        ),
    )
    @click.option("--source", type=click.Path(path_type=Path), required=True)
    @click.option("--destination", type=click.Path(path_type=Path), required=True)
    @click.option("--service", default="actions-runner-org.service", show_default=True)
    @click.option("--apply", "apply_", is_flag=True, help="Stop, copy, verify, switch, restart.")
    def relocate_storage_command(
        source: Path, destination: Path, service: str, apply_: bool
    ) -> None:
        result = (
            relocate_storage(source, destination, service=service)
            if apply_
            else assess_storage(source, destination)
        )
        click.echo(json.dumps(result.to_dict(), indent=2))
        if not result.ok:
            raise click.exceptions.Exit(1)
