#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: scitex_dev/versioning/_symbols.py

"""Symbol probes — ask the code what it IS, not what it CLAIMS to be.

A version string lies in both directions, and has (sac's outage, and
scitex-dev's own 2026-07-12 fossil incident, both proved it):

* **Stale in memory.** A daemon imported its modules at boot. Upgrading the
  package on disk does not reload them — Python has no such mechanism. The
  ``--version`` reports the NEW number while the process still executes the
  OLD bytecode.
* **Stale on disk.** A host sat on one version for a full day while three
  tags came and went. The number was self-consistent and completely wrong
  about what was fixed.
* **Fossil metadata.** A leftover ``.dist-info`` makes
  ``importlib.metadata.version()`` report a release whose code is not the
  code being imported.

A number cannot see any of this, because a fix that does not bump the
version does not move the number, and a number that is bumped does not
prove the code moved with it. **The symbol can.** ``hasattr(mod, name)`` is
evaluated against the module object actually loaded into the running
interpreter, so it answers the only question anybody ever really asks:

    is the fix *in the code I am running right now*?

This module is the generic MECHANISM (extracted from sac
``_freshness._symbols``). The registry CONTENTS stay in each leaf and are
passed in via :attr:`VersioningConfig.expectations` — only the leaf knows
which of its own symbols prove which of its own fixes.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["SymbolExpectation", "probe", "probe_all"]


@dataclass(frozen=True)
class SymbolExpectation:
    """A symbol whose PRESENCE proves a specific fix is in the loaded code.

    Attributes:
        module: Dotted path of the module the fix landed in.
        symbol: A name that exists ONLY in the fixed code. Pick something
            the fix genuinely introduced — a counter, a new function, a new
            class. A symbol that predates the fix proves nothing.
        since: The release that first carried it. Informational only: it is
            never used to decide the verdict, because deciding on the number
            is precisely the failure this module exists to end.
        why: What breaks when it is missing. This lands in front of a human
            when something is wrong; make it mean something.
    """

    module: str
    symbol: str
    since: str
    why: str

    @property
    def dotted(self) -> str:
        return f"{self.module}.{self.symbol}"


def probe(exp: SymbolExpectation) -> bool | None:
    """Is ``exp.symbol`` present in the loaded ``exp.module``?

    Returns:
        ``True``  — the symbol is there. The fix is in the running code.
        ``False`` — the module imported fine and the symbol is absent, OR
            the module itself does not exist. Both are positive evidence the
            fix is not here.
        ``None``  — UNKNOWN. The module exists but could not be imported
            because something *it* depends on is broken. That tells us
            nothing about our symbol, so we say nothing.

    The ``exc.name`` check is what separates the last two cases. A bare
    ``except ImportError: return False`` would report "fix missing" when the
    truth is "this module's dependency is broken" — a false RED, and a false
    RED is the dangerous kind, because someone acts on it.
    """
    try:
        mod = __import__(exp.module, fromlist=["_"])
    except ModuleNotFoundError as exc:
        # Our module genuinely isn't in this install -> the fix isn't here.
        # A DIFFERENT module missing (a broken dependency of ours) is not
        # evidence about our symbol.
        if getattr(exc, "name", None) == exp.module:
            return False
        return None
    except Exception:  # noqa: BLE001 - any other import failure is about the dependency, not our symbol; UNKNOWN is the honest answer
        return None
    return hasattr(mod, exp.symbol)


def probe_all(
    expectations,
) -> list[tuple[SymbolExpectation, bool | None]]:
    """Probe every expectation against the LOADED code."""
    return [(e, probe(e)) for e in expectations]


# EOF
