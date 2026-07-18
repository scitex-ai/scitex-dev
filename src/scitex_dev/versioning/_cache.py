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

WHERE THE RULES ACTUALLY LIVE: ``_fastpath``
---------------------------------------------
The TTL, the ``$SCITEX_DIR`` / ``<PREFIX>_CACHE`` path resolution and the
"do we trust this file?" rule are DEFINED IN :mod:`._fastpath` and imported
here — not the other way round. That module is stdlib-only so a consumer can
pre-gate on a warm cache in ~0.02 ms without paying ~200 ms to import this
package (see its docstring for the measurement). The dependency points
cheap <- heavy deliberately: if it were reversed, the first import added to
this module would silently un-fast the fast path.

This module keeps only what genuinely needs the :class:`Report` type: the
writer, and the reader's final ``dict -> Report`` step.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from ._fastpath import DEFAULT_TTL_S, cache_path, read_cache_raw, scitex_dir, ttl_s
from ._model import Report

__all__ = [
    "DEFAULT_TTL_S",
    "cache_path",
    "read_cache",
    "scitex_dir",
    "ttl_s",
    "write_cache",
]


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

    The trust rule itself is :func:`._fastpath.read_cache_raw` — stated once,
    so the cheap pre-gate and this reader can never disagree about which
    caches are warm. All this adds is the ``dict -> Report`` step.
    """
    target = path if path is not None else cache_path(config)
    limit = ttl_s(config) if max_age_s is None else max_age_s
    raw = read_cache_raw(target, now=now, max_age_s=limit)
    if raw is None:
        return None
    return Report.from_dict(raw)


# EOF
