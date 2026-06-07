"""Category I: cross-package private-submodule import rule (I008).

Flags importing a *peer* scitex package's underscore-prefixed (private)
submodule, e.g. ``from scitex_gen._numeric._norm import to_z``. Reaching
into a peer's private internals is fragile: when scitex-gen reorganized
``scitex_gen._norm`` into ``scitex_gen._numeric._norm`` it silently broke
scitex-dsp and scitex-nn, which had imported the private path directly.

Packages must depend only on a peer's *public* API
(``from scitex_gen import to_z``). Same-package private imports — a module
inside ``scitex_gen`` importing ``scitex_gen._numeric`` — are allowed; only
*cross*-package private imports are flagged.
"""

from ._base import Rule

I008 = Rule(
    id="STX-I008",
    severity="warning",
    category="import",
    message=(
        "Cross-package import of a peer's PRIVATE submodule — import the "
        "peer's public API instead"
    ),
    suggestion=(
        "Reaching into another scitex package's underscore-prefixed module "
        "(e.g. `from scitex_gen._numeric._norm import to_z`) is fragile: "
        "the peer can rename or move that private path without notice. "
        "Import the public symbol instead (e.g. `from scitex_gen import "
        "to_z`). If the symbol is not yet public, ask the owning package "
        "to export it."
    ),
)
