"""Category I: scitex-umbrella import-hygiene rules (STX-I001-I007).

These rules nudge callers toward the scitex umbrella API
(``stx.plt`` / ``stx.stats`` / ``stx.io`` / injected ``rngg`` / ``logger``)
instead of importing the raw third-party libraries directly.

They were absorbed into the engine in-house (umbrella-thinning Phase A)
from the umbrella's ``scitex._linter_plugin`` so an ``stx.io`` /
``stx.plt`` API change forces a same-repo rule update. Every id,
severity, category, message, suggestion, and the ``requires="scitex"``
gate is preserved verbatim — they fire only when scitex is installed.
"""

from ._base import Rule

I001 = Rule(
    id="STX-I001",
    severity="warning",
    category="import",
    message="Use `stx.plt` instead of importing matplotlib.pyplot directly",
    suggestion="Replace with `stx.plt` (or `plt` injected by @stx.session).",
    requires="scitex",
)

I002 = Rule(
    id="STX-I002",
    severity="warning",
    category="import",
    message="Use `stx.stats` instead of importing scipy.stats directly",
    suggestion="Replace with `stx.stats` which adds effect sizes, CI, and power analysis.",
    requires="scitex",
)

I003 = Rule(
    id="STX-I003",
    severity="warning",
    category="import",
    message="Use `stx.io` instead of pickle for file I/O",
    suggestion="Replace with `stx.io.save(obj, 'file.pkl')` / `stx.io.load('file.pkl')`.",
    requires="scitex",
)

I004 = Rule(
    id="STX-I004",
    severity="warning",
    category="import",
    message="Use `stx.io` for CSV/DataFrame I/O instead of pandas I/O functions",
    suggestion="Replace `pd.read_csv()` with `stx.io.load()`, `df.to_csv()` with `stx.io.save()`.",
    requires="scitex",
)

I005 = Rule(
    id="STX-I005",
    severity="warning",
    category="import",
    message="Use `stx.io` for array I/O instead of numpy save/load",
    suggestion="Replace `np.save()`/`np.load()` with `stx.io.save()`/`stx.io.load()`.",
    requires="scitex",
)

I006 = Rule(
    id="STX-I006",
    severity="info",
    category="import",
    message="Use `rngg` (injected by @stx.session) for reproducible randomness",
    suggestion="Remove `import random` and use `rngg` from @stx.session injection.",
    requires="scitex",
)

I007 = Rule(
    id="STX-I007",
    severity="warning",
    category="import",
    message="Use `logger` (injected by @stx.session) instead of logging module",
    suggestion="Remove `import logging` and use `logger` from @stx.session injection.",
    requires="scitex",
)
