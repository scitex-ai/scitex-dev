"""Deferred `__version__` resolution — kept OFF the import path.

``importlib.metadata`` drags in ``email.message``, ``email.utils`` and
``zipfile``: you pay an email parser to learn a version string. Measured by
scitex-cards on their own package, 2026-07-30 — 223ms of a 425ms cold
import, 52%, for one module-scope statement.

scitex-dev had the identical shape, and it sat directly above this
package's own PEP 562 lazy loader. A fully correct lazy design defeated by
one line — which is what §10 exists to catch and what a human reviewer
reads past.

This lives in its own module rather than in ``__init__.py`` so that
``__init__`` need not name ``importlib.metadata`` at all: ``__getattr__``
imports THIS module on first ``__version__`` access, and nothing before
that. It also gives the test file a real mirror (PS-204) instead of an
orphan — the rule was right, and the naming it forced is the better
factoring.
"""

from __future__ import annotations

__all__ = ["resolve_version"]

_FALLBACK = "0.0.0+local"


def resolve_version(distribution: str = "scitex-dev") -> str:
    """Read the installed version. Called on demand, never at import."""
    try:
        from importlib.metadata import PackageNotFoundError, version
    except ImportError:  # pragma: no cover — only on ancient Pythons
        return _FALLBACK
    try:
        return version(distribution)
    except PackageNotFoundError:
        return _FALLBACK


# EOF
