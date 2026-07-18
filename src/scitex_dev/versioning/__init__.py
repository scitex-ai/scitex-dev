#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: scitex_dev/versioning/__init__.py

"""scitex_dev.versioning — the version-currency primitive every leaf consumes.

THE QUESTION IT ANSWERS
-----------------------
    Is the code I am ACTUALLY RUNNING current — and if not, WHOSE install is
    behind, and what exactly do I run to fix it (without breaking anything)?

This is scitex-dev's half of the operator's "dev holds the primitive, leaves
consume it to self-update" architecture. It was EXTRACTED from
scitex-agent-container's reviewed ``_freshness`` subsystem (PR #677 — credit
to that review for the four-checks design, the tri-state model, the incident
regression test, and the every-invocation warning) and reconciled with the
content-probe machinery scitex-dev already owns
(``_release.check_editable_drift`` and ``_release._install_probe``).

FOUR NON-NEGOTIABLES (the point of the primitive)
-------------------------------------------------
1. TRI-STATE, never a bare bool/str. :class:`Currency` is FRESH / STALE /
   UNKNOWN, UNKNOWN is representable in the TYPE, and an EMPTY report is
   UNKNOWN — never FRESH.
2. CONTENT-PROBE for editable installs, NEVER version-string-vs-tag. A wheel's
   frozen metadata is a fossil for an editable checkout; comparing it to PyPI
   fires a FALSE STALE whose ``pip install -U`` remedy would CLOBBER the
   checkout. So editable installs are judged by CONTENT (working tree vs its
   tag, via ``check_editable_drift``) and never handed a ``pip install -U``.
3. NAME THE BINARY THAT ANSWERED. Every finding's summary carries the package
   ORIGIN and the INTERPRETER, so "0.21.21 is behind 0.21.24" always says
   whose 0.21.21 — the mechanism that let sac find FIVE installs, and that
   lets a caller notice it is running an OLD shadowed install.
4. A recorded-incident regression test proving the primitive returns
   STALE/UNKNOWN on real data that once slipped past everyone.

PUBLIC API
----------
    from scitex_dev.versioning import VersioningConfig, check_currency, Currency

    cfg = VersioningConfig(dist="scitex-dev", release_workflow="pypi.yml")
    report = check_currency(cfg)          # -> Report
    if report.state is Currency.STALE:
        for f in report.stale:
            print(f.summary, "->", f.remedy)

CONSUMER MIGRATION IS A FOLLOW-UP: this package deliberately does NOT rewire
scitex-dev's own ``__version__`` / ``_version_check`` onto itself, and does
NOT wire sac. It ships the tested, reusable primitive; the leaves adopt it
next.

Imports are LAZY (PEP 562): ``_sources`` pulls in urllib/subprocess, and a
leaf may import this package on its CLI hot path — an eager import would put
that cost on every ``--help``.

THE HOT PATH IS CHEAPER STILL: ``_fastpath``
---------------------------------------------
Lazy is not free. Importing this package at all costs ~200 ms, and almost
none of that is this file — it is the PARENT ``scitex_dev`` package, which
Python must import first. sac measured 201 ms against its own ~150 ms
whole-CLI budget.

So a consumer that wants to hook the currency check onto EVERY invocation
pre-gates on the warm cache instead, via :mod:`._fastpath` — stdlib-only,
no relative imports, ~0.02 ms when loaded standalone by file location::

    if fastpath.cache_is_fresh(CACHE_PATH):
        ...          # warm — skip the ~200 ms full check this invocation

:func:`cache_is_fresh` is re-exported here (lazily) for callers already off
the hot path. Read ``_fastpath``'s docstring before wiring it: the standalone
load is the part that actually buys the speed.
"""

from __future__ import annotations

__all__ = [
    "Currency",
    "Finding",
    "Report",
    "SymbolExpectation",
    "VersioningConfig",
    "LiveSources",
    "StaticSources",
    "build_report",
    "cache_is_fresh",
    "cache_path",
    "cached_generated_at",
    "cached_state",
    "check_currency",
    "check_ghost_tags",
    "check_install_currency",
    "check_release_runs",
    "check_running_vs_installed",
    "check_symbols",
    "emit_once",
    "probe",
    "read_cache",
    "warn_if_stale",
    "write_cache",
]


def check_currency(config, sources=None, *, now=None) -> Report:
    """THE entry point: a :class:`Report` for one package's version-currency.

    ``config`` is a :class:`VersioningConfig`. ``sources`` defaults to a live
    :class:`LiveSources` (real PyPI / git / gh / systemd + content-verified
    install probe); pass a :class:`StaticSources` to drive it from recorded
    evidence in tests. The returned report is tri-state and every finding
    names the binary that answered.
    """
    from ._checks import build_report
    from ._sources import LiveSources

    src = sources if sources is not None else LiveSources(config)
    return build_report(config, src, now=now)


# name -> submodule holding it. Resolved on first attribute access so a leaf
# never pays for urllib/subprocess merely by importing the package.
#
# The model types are lazy too, not just the expensive ones. They are cheap
# in themselves, but an eager `from ._model import ...` here would put
# `_model` in `sys.modules` for anyone who touched this package at all — and
# "is `_model` loaded?" is precisely the assertion that pins the fastpath's
# cheapness (tests/scitex_dev/versioning/test__fastpath.py). A guarantee you
# cannot assert on is not a guarantee.
_LAZY = {
    "Currency": "._model",
    "Finding": "._model",
    "Report": "._model",
    "cache_is_fresh": "._fastpath",
    "cached_generated_at": "._fastpath",
    "cached_state": "._fastpath",
    "SymbolExpectation": "._symbols",
    "probe": "._symbols",
    "VersioningConfig": "._config",
    "LiveSources": "._sources",
    "StaticSources": "._sources",
    "build_report": "._checks",
    "check_install_currency": "._checks",
    "check_ghost_tags": "._checks",
    "check_release_runs": "._checks",
    "check_running_vs_installed": "._checks",
    "check_symbols": "._checks",
    "cache_path": "._cache",
    "read_cache": "._cache",
    "write_cache": "._cache",
    "warn_if_stale": "._warn",
    "emit_once": "._warn",
}


def __getattr__(name: str):
    module = _LAZY.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    return getattr(import_module(module, __name__), name)


def __dir__():
    return sorted(__all__)


# EOF
