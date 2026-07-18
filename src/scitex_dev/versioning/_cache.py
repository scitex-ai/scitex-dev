#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: scitex_dev/versioning/_cache.py

"""The cache: written by the refresher, read by every CLI invocation.

WHY A CACHE AND NOT A LOOKUP
----------------------------
The warning has to appear when the operator types the leaf's command — that
is the whole point; a README nobody opens is not a control. But a PyPI lookup
on the CLI hot path would be a ~200-2000 ms network round trip on every
command, and would HANG the CLI on a flaky link. A version check that makes
the CLI slow, or wedges it when the network is bad, gets switched off within
a day, and then there is no check at all.

So the two halves are split by who can afford to wait: the REFRESHER (cron)
pays the network cost off the interactive path and writes this file; the CLI
reads this file and nothing else.

STALE CACHE IS UNKNOWN, AND UNKNOWN IS SILENT
---------------------------------------------
Beyond the TTL we do not trust our own file. An old cache means the refresher
died, and a dead refresher's last answer is a fossil, not evidence about the
present. So an expired cache reads as ``None`` (=> UNKNOWN => silence) — the
same class of honesty the whole primitive is built on. **All four of
missing / unreadable / malformed / expired collapse to ``None``.**

Everything is resolved AT CALL TIME. Nothing here is a module-level
``Path.home()`` constant: ``$HOME`` differs between a container
(``/home/agent``) and the host (``/home/ywatanabe``), and an import-time
constant cannot be redirected by a test fixture (or a container) that sets
the env afterwards. That bug has already cost days elsewhere.

PARAMETERISATION
----------------
Every path/knob is driven by the :class:`VersioningConfig` handed in, so two
leaves never collide: each has its own ``<PREFIX>_CACHE`` override, its own
``<PREFIX>_TTL_S``, and its own cache subpath under ``$SCITEX_DIR``.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from ._model import Report

__all__ = ["DEFAULT_TTL_S", "cache_path", "read_cache", "scitex_dir", "write_cache"]

# 24 h against an hourly refresher: 24 consecutive misses before we fall
# silent. Deliberately generous — a loaded host may simply not schedule a
# cron job for a long while, and a tight TTL there just makes us blind.
DEFAULT_TTL_S = 24 * 60 * 60

_ENV_SCITEX_DIR = "SCITEX_DIR"


def scitex_dir() -> Path:
    """``$SCITEX_DIR``, else ``~/.scitex``. Resolved per call.

    Mirrors the ecosystem's ``local_state.user_root()`` one-line contract in
    stdlib, so no heavy import lands on the CLI hot path.
    """
    env = os.environ.get(_ENV_SCITEX_DIR)
    return Path(env) if env else Path.home() / ".scitex"


def cache_path(config) -> Path:
    """Where this leaf's currency cache lives. Resolved per call.

    ``<PREFIX>_CACHE`` overrides it outright — the seam tests use, and the
    way a container can be pointed at the host's cache instead of its own
    empty ``$HOME``.
    """
    override = os.environ.get(config.env_cache)
    if override:
        return Path(override)
    return scitex_dir().joinpath(*config.cache_subpath)


def ttl_s(config) -> int:
    """Cache lifetime. ``<PREFIX>_TTL_S`` overrides the default.

    A garbage value falls back to the default rather than raising — a typo in
    an env var must not break the CLI.
    """
    raw = os.environ.get(config.env_ttl)
    if not raw:
        return DEFAULT_TTL_S
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_TTL_S
    return value if value > 0 else DEFAULT_TTL_S


def write_cache(config, report: Report, path: Path | None = None) -> Path:
    """Atomically publish a report. Returns the path written.

    tmp + ``os.replace`` so a reader never catches a half-written file: the
    CLI reads this on every invocation, and a torn read would surface as a
    spurious UNKNOWN at best.
    """
    target = path or cache_path(config)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    os.replace(tmp, target)
    return target


def read_cache(
    config,
    path: Path | None = None,
    *,
    now: float | None = None,
    max_age_s: int | None = None,
) -> Report | None:
    """Load the cached report, or ``None`` when it cannot be trusted.

    ``None`` (=> UNKNOWN => silence) for every one of: no file, an unreadable
    file, malformed JSON, a report with no timestamp, and a report older than
    the TTL. Each of those is an absence of current evidence, and this
    function refuses to dress any of them up as an answer.
    """
    target = path or cache_path(config)
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None

    report = Report.from_dict(raw)
    if not report.generated_at:
        return None

    age = (time.time() if now is None else now) - report.generated_at
    limit = ttl_s(config) if max_age_s is None else max_age_s
    if age > limit:
        return None
    return report


# EOF
