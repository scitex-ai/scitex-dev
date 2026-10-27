#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The ``cleanup.disk`` config block — DEFAULT OFF, FAIL CLOSED.

Schema, in the user-scope ``~/.scitex/dev/config.yaml``::

    cleanup:
      disk:
        enabled: true          # ABSENT / not literal YAML true => OFF
        threshold_pct: 88      # build cache touched at/above this use%
        min_age_days: 2        # clamped UP to HARD_MIN_AGE_DAYS
        sif_keep_newest: 2     # clamped UP to HARD_MIN_SIF_KEEP
        protect:               # extra never-touch path globs, ADDITIVE
          - "/tmp/ci-keep-*"

ONE SURFACE, not two. Branch GC deletes per-repo and so needs the repo's
own config ANDed with the user's. Disk acts per-HOST — there is no repo
whose history could carry the decision — so the user-scope file alone
arms it. The enabled test is the same identity check (``is True``) and
every loader doubt (missing file, unreadable file, malformed YAML,
``cleanup`` not a mapping, PyYAML absent) yields ``enabled=False`` with
the reason in ``error``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ._disk_guard_model import (
    DEFAULT_MIN_AGE_DAYS,
    DEFAULT_SIF_KEEP_NEWEST,
    DEFAULT_THRESHOLD_PCT,
    clamp_min_age_days,
    clamp_sif_keep_newest,
    clamp_threshold_pct,
)

__all__ = [
    "USER_CONFIG_REL_PATH",
    "DiskCleanupConfig",
    "load_disk_cleanup_config",
]

USER_CONFIG_REL_PATH = Path(".scitex") / "dev" / "config.yaml"


@dataclass(frozen=True)
class DiskCleanupConfig:
    """Resolved ``cleanup.disk`` config for ONE host.

    ``enabled`` defaults to ``False`` at the dataclass level — gate #1.
    Constructing this object with no arguments at all yields a config
    that deletes nothing.
    """

    enabled: bool = False
    threshold_pct: int = DEFAULT_THRESHOLD_PCT
    min_age_days: float = DEFAULT_MIN_AGE_DAYS
    sif_keep_newest: int = DEFAULT_SIF_KEEP_NEWEST
    protect: tuple[str, ...] = ()
    user_source: str | None = None
    #: Why the sweep is OFF, when off for a reason other than "not armed".
    error: str | None = None


def load_disk_cleanup_config(home: Path | None = None) -> DiskCleanupConfig:
    """Read the user-scope config. Every doubt returns OFF with a reason."""
    base = Path(home).expanduser() if home is not None else Path.home()
    path = base / USER_CONFIG_REL_PATH
    try:
        raw_text = path.read_text()
    except FileNotFoundError:
        return DiskCleanupConfig()
    except OSError as exc:
        return DiskCleanupConfig(error=f"unreadable config {path}: {exc}")

    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        return DiskCleanupConfig(error="PyYAML absent; cannot evaluate config")

    try:
        data = yaml.safe_load(raw_text)
    except Exception as exc:  # noqa: BLE001 - any parse failure is OFF
        return DiskCleanupConfig(error=f"malformed YAML in {path}: {exc}")
    if data is None:
        return DiskCleanupConfig(user_source=str(path))
    if not isinstance(data, dict):
        return DiskCleanupConfig(
            error=f"top level of {path} is not a mapping",
            user_source=str(path),
        )
    cleanup = data.get("cleanup")
    if cleanup is None:
        return DiskCleanupConfig(user_source=str(path))
    if not isinstance(cleanup, dict):
        return DiskCleanupConfig(
            error=f"cleanup block of {path} is not a mapping",
            user_source=str(path),
        )
    disk = cleanup.get("disk")
    if disk is None:
        return DiskCleanupConfig(user_source=str(path))
    if not isinstance(disk, dict):
        return DiskCleanupConfig(
            error=f"cleanup.disk block of {path} is not a mapping",
            user_source=str(path),
        )
    protect_raw = disk.get("protect", ())
    protect = (
        tuple(str(p) for p in protect_raw)
        if isinstance(protect_raw, (list, tuple))
        else ()
    )
    return DiskCleanupConfig(
        enabled=disk.get("enabled") is True,
        threshold_pct=clamp_threshold_pct(disk.get("threshold_pct")),
        min_age_days=clamp_min_age_days(disk.get("min_age_days")),
        sif_keep_newest=clamp_sif_keep_newest(disk.get("sif_keep_newest")),
        protect=protect,
        user_source=str(path),
    )


# EOF
