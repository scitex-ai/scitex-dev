#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: scitex_dev/versioning/_fastpath.py

"""The cheap pre-gate: "is the cached verdict still warm?" in ~1 ms.

WHY THIS MODULE EXISTS (a measurement, not a preference)
--------------------------------------------------------
A consumer measured ``import scitex_dev.versioning`` at **201 ms**. sac's
ENTIRE CLI startup budget is ~150 ms *including* tab-completion, so a leaf
that hooks the currency check onto every invocation MORE THAN DOUBLES its own
startup — and the first thing an operator does with a CLI that got slow is
switch the check off. A check that gets switched off is not a check.

sac worked around it with a hand-rolled ~1 ms stdlib-only cache read
(measured 0.32 ms, with ``scitex_dev`` provably absent from ``sys.modules``,
pinned by a subprocess test). That workaround was correct, and that is the
problem: every future consumer would reinvent it, and each reinvention would
re-derive the TTL and the cache-path rules by hand until one of them drifted.
So the PRIMITIVE owns the cheap path, and the workaround has a home.

WHERE THE 201 ms ACTUALLY IS (read this before "optimising" the wrong file)
---------------------------------------------------------------------------
Measured on this checkout, cold process, per import:

    import scitex_dev                     ~236 / 484 / 351 ms
    import scitex_dev  (drift disabled)   ~153 / 186 / 113 ms
    import scitex_dev.versioning          ~188 / 172 / 252 ms
    this module, loaded standalone          ~0.6-5 ms

Read the last two lines together: ``scitex_dev.versioning`` costs what
``scitex_dev`` costs. Essentially ALL of it is the PARENT package's
``__init__`` (``importlib.metadata`` for ``__version__``, plus the eager
``emit_if_drift`` call), and ``versioning/__init__`` itself adds ~nothing —
it is already lazy (PEP 562).

That has a consequence you cannot import your way out of: Python imports
parent packages first, so ``import scitex_dev.versioning._fastpath`` still
pays the full ~200 ms. **The cheap path is therefore a STANDALONE LOAD.**
This module holds no relative imports and touches nothing but the stdlib, so
a consumer on the hot path loads it by file location and never imports
``scitex_dev`` at all::

    import importlib.util
    spec = importlib.util.spec_from_file_location("_currency_fastpath", path)
    fastpath = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fastpath)
    if fastpath.cache_is_fresh(CACHE_PATH):
        ...          # warm cache — skip the full check this invocation

``scitex_dev.versioning`` also re-exports :func:`cache_is_fresh` lazily, for
callers already off the hot path who just want the predicate.

ONE DEFINITION, AND IT LIVES HERE
---------------------------------
The TTL, ``$SCITEX_DIR`` resolution, the ``<PREFIX>_CACHE`` override and the
trust rule are defined in THIS module, and ``_cache`` imports them from here
rather than the other way round. The dependency points cheap <- heavy on
purpose: the expensive module may depend on the cheap one, never the reverse,
or the fastpath stops being fast the first time someone adds an import to
``_cache``.

THE CHEAP GATE ANSWERS EXACTLY ONE QUESTION: "CAN I SKIP?"
-----------------------------------------------------------
It does NOT reproduce the tri-state. Tri-state (FRESH / STALE / UNKNOWN)
belongs to :class:`~scitex_dev.versioning.Currency` and stays there; a second
implementation of a three-way verdict is exactly how two answers to one
question get shipped. Here the answer is a bool, and every one of
missing / unreadable / malformed / undated / expired returns ``False`` —
"no, do not skip, run the full check". **Unsure is never "fresh".** The cost
of a wrong ``False`` is one slow invocation; the cost of a wrong ``True`` is
the silent blindness this whole subsystem exists to kill.

WHY ``pathlib`` IS IMPORTED LAZILY AND NOT AT MODULE LEVEL
-----------------------------------------------------------
``pathlib`` is stdlib, but it is not free: a COLD ``from pathlib import Path``
costs ~10-15 ms, which is a tenth of sac's entire CLI budget spent on a
convenience type. It is usually already in ``sys.modules`` (a venv ``.pth``
tends to pull it in during ``site`` processing) and then it is free — but
"usually already loaded" is an assumption about someone else's interpreter,
not a property of this module, and the whole point here is to depend on
nothing.

So the READ path (:func:`read_cache_raw` and everything on top of it) uses
``os.path`` + builtin ``open`` and never touches ``pathlib`` at all. Only
:func:`scitex_dir` / :func:`cache_path` import it, lazily, because they must
return ``Path`` to stay compatible with ``_cache``'s writer. A consumer that
passes its cache path as a plain string pays for nothing.
"""

from __future__ import annotations

import json
import os
import time

__all__ = [
    "DEFAULT_TTL_S",
    "cache_is_fresh",
    "cache_path",
    "cached_generated_at",
    "cached_state",
    "read_cache_raw",
    "scitex_dir",
    "ttl_s",
]

# 24 h against an hourly refresher: 24 consecutive misses before we fall
# silent. Deliberately generous — a loaded host may simply not schedule a
# cron job for a long while, and a tight TTL there just makes us blind.
DEFAULT_TTL_S = 24 * 60 * 60

_ENV_SCITEX_DIR = "SCITEX_DIR"


def scitex_dir() -> "Path":  # noqa: F821 — lazily imported, see module docstring
    """``$SCITEX_DIR``, else ``~/.scitex``. Resolved per call.

    Never a module-level constant: ``$HOME`` differs between a container
    (``/home/agent``) and the host (``/home/ywatanabe``), and an import-time
    constant cannot be redirected by a test fixture (or a container) that
    sets the env afterwards. That bug has already cost days elsewhere.
    """
    from pathlib import Path

    env = os.environ.get(_ENV_SCITEX_DIR)
    return Path(env) if env else Path.home() / ".scitex"


def cache_path(config) -> "Path":  # noqa: F821 — lazily imported
    """Where this leaf's currency cache lives. Resolved per call.

    ``<PREFIX>_CACHE`` overrides it outright — the seam tests use, and the
    way a container can be pointed at the host's cache instead of its own
    empty ``$HOME``.
    """
    from pathlib import Path

    override = os.environ.get(config.env_cache)
    if override:
        return Path(override)
    return scitex_dir().joinpath(*config.cache_subpath)


def ttl_s(config) -> int:
    """Cache lifetime. ``<PREFIX>_TTL_S`` overrides the default.

    A garbage value falls back to the default rather than raising — a typo
    in an env var must not break the CLI.
    """
    raw = os.environ.get(config.env_ttl)
    if not raw:
        return DEFAULT_TTL_S
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_TTL_S
    return value if value > 0 else DEFAULT_TTL_S


def _resolve(config_or_path) -> tuple[str | None, int]:
    """Normalise the one argument into ``(filesystem path str, ttl)``.

    Accepts either a :class:`~scitex_dev.versioning.VersioningConfig` (whose
    ``env_cache`` / ``cache_subpath`` / ``env_ttl`` drive both answers) or a
    bare path, so a hot-path consumer that already knows its cache location
    can pre-gate without constructing a config — which would mean importing
    ``_config``, which would mean paying for the import this module exists to
    avoid.

    Returns a ``str``, not a ``Path``: the read path is deliberately
    ``os.path``-only (see the module docstring), and ``os.fspath`` accepts a
    ``Path`` the caller already has without importing ``pathlib`` here.

    Returns ``(None, DEFAULT_TTL_S)`` for anything unrecognisable; the caller
    turns that into "not fresh". Nothing here raises.
    """
    if isinstance(config_or_path, (str, os.PathLike)):
        try:
            return os.fspath(config_or_path), DEFAULT_TTL_S
        except TypeError:
            return None, DEFAULT_TTL_S
    try:
        return os.fspath(cache_path(config_or_path)), ttl_s(config_or_path)
    except (AttributeError, TypeError):
        return None, DEFAULT_TTL_S


def read_cache_raw(
    config_or_path,
    *,
    now: float | None = None,
    max_age_s: int | None = None,
) -> dict | None:
    """The still-warm cache payload as a plain dict, or ``None``.

    ``None`` for every one of: no file, an unreadable file, malformed JSON, a
    non-object payload, a payload with no usable timestamp, and a payload
    older than the TTL. Each of those is an absence of current evidence, and
    this function refuses to dress any of them up as an answer.

    This is the raw-JSON twin of
    :func:`scitex_dev.versioning._cache.read_cache`, which wraps the same
    payload in a :class:`~scitex_dev.versioning.Report`. The trust rule is
    implemented once, here; ``read_cache`` delegates to it.

    Args:
        config_or_path: A ``VersioningConfig`` or a path to the cache file.
        now: Current epoch seconds; defaults to :func:`time.time`. Injected
            by tests so expiry is exercised without sleeping.
        max_age_s: TTL override in seconds. Defaults to the config's TTL
            (or :data:`DEFAULT_TTL_S` when handed a bare path).

    Returns:
        The cached payload dict when it is present, parseable and within the
        TTL; ``None`` otherwise.
    """
    target, config_ttl = _resolve(config_or_path)
    if target is None:
        return None
    try:
        with open(target, encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None

    try:
        generated_at = float(raw.get("generated_at") or 0.0)
    except (TypeError, ValueError):
        return None
    if not generated_at:
        return None

    age = (time.time() if now is None else now) - generated_at
    limit = config_ttl if max_age_s is None else max_age_s
    if age > limit:
        return None
    return raw


def cache_is_fresh(
    config_or_path,
    *,
    now: float | None = None,
    max_age_s: int | None = None,
) -> bool:
    """THE pre-gate. ``True`` only when the cached verdict is still warm.

    Ask this BEFORE importing the full package. ``True`` means a refresher
    wrote a verdict recently enough to trust, so this invocation may skip the
    ~200 ms full check. ``False`` means run it (or, on a hot path that cannot
    afford to, stay silent and let the next refresher tick sort it out).

    Note what this does NOT say: nothing about whether the package is
    up to date. A warm cache holding a STALE verdict is still warm — the
    verdict itself lives in the payload (:func:`cached_state`), not in this
    predicate. This is a cache-warmth question, not a currency question.
    """
    return read_cache_raw(config_or_path, now=now, max_age_s=max_age_s) is not None


def cached_state(
    config_or_path,
    *,
    now: float | None = None,
    max_age_s: int | None = None,
) -> str | None:
    """The cached verdict STRING (``"fresh"`` / ``"stale"`` / ``"unknown"``).

    ``None`` when the cache is not warm — indistinguishable, on purpose, from
    a warm cache that recorded ``"unknown"``: both mean "no current evidence
    of staleness", which is the only distinction a hot-path caller may act
    on. A caller that needs the real tri-state object imports
    :class:`~scitex_dev.versioning.Currency` and pays for it.

    Deliberately a ``str``, not an enum: importing the enum means importing
    ``_model``, which is the cost this module exists to avoid.
    """
    raw = read_cache_raw(config_or_path, now=now, max_age_s=max_age_s)
    if raw is None:
        return None
    state = raw.get("state")
    return state if isinstance(state, str) and state else None


def cached_generated_at(
    config_or_path,
    *,
    now: float | None = None,
    max_age_s: int | None = None,
) -> float | None:
    """When the warm cache was written (epoch seconds), else ``None``.

    For a consumer that wants to show "checked 3 min ago" without paying for
    the full package.
    """
    raw = read_cache_raw(config_or_path, now=now, max_age_s=max_age_s)
    if raw is None:
        return None
    try:
        return float(raw.get("generated_at") or 0.0) or None
    except (TypeError, ValueError):
        return None


# EOF
