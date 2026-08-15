# scitex_dev.ci — CI infrastructure tools (runner, template, etc.)
"""CI verdicts a script can gate on, not just a human can read.

`readiness()` answers one question — "is this pull request ACTUALLY
mergeable?" — three-valued, per check, pinned to the commit under review.
Each of those three qualifiers corresponds to a green that misled someone
on 2026-08-09; see :mod:`._mergeable` for the measurements.

Imported lazily via ``__getattr__`` so that merely importing
``scitex_dev.ci`` (which the CI template does) does not drag in the
mergeability machinery.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ._mergeable import (
        EXIT_NOT_READY,
        EXIT_READY,
        EXIT_UNKNOWN,
        EXIT_USAGE,
        FRAMEWORK_RESERVED_EXIT_CODES,
        CheckRun,
        ExitCode,
        MergeReadiness,
        Readiness,
        readiness,
    )

_MERGEABLE_EXPORTS = {
    "CheckRun",
    "EXIT_NOT_READY",
    "EXIT_READY",
    "EXIT_UNKNOWN",
    "EXIT_USAGE",
    "FRAMEWORK_RESERVED_EXIT_CODES",
    "ExitCode",
    "MergeReadiness",
    "Readiness",
    "readiness",
}

__all__ = sorted(_MERGEABLE_EXPORTS)


def __getattr__(name: str):
    """Defer the mergeability import until something actually asks for it."""
    if name in _MERGEABLE_EXPORTS:
        from . import _mergeable

        return getattr(_mergeable, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
