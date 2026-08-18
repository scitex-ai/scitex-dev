#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The caveat that belongs on every remedy offering ``deprecated_alias()``.

ONE SENTENCE, ONE PLACE. §12 and §13 both prescribe the helper, and the
caveat is a fact about the HELPER rather than about either rule — two
copies would drift, and the copy that drifted would keep telling somebody
to delete working behaviour.

WHY IT EXISTS
-------------
Reported by figrecipe, 2026-08-18, who followed §12's remedy exactly and
had CI catch a capability loss. Their hand-rolled ``start-gui`` was
ALREADY a deprecation alias — it warned, forwarded to ``gui open``, and
additionally accepted two options ``gui open`` does not have:

    --force     kills whatever holds the port, sleeps, then hands off
    -y/--yes    accepted for back-compat, deliberately ignored

``deprecated_alias()`` forwards argv to the target and nothing else. So
the prescribed swap turned ``start-gui --force`` into a usage error and
SILENTLY DROPPED THE PORT-KILL. The test that caught it reported a
help-text mismatch; the lost capability was underneath.

The rule was WARN-tier and did not gate their build. So the remedy, as
written, asked a package to trade working behaviour for a quieter report
that was not blocking anything.

THE DISCRIMINATION IS THE POINT
-------------------------------
figrecipe kept §13's migration and reverted §12's. Their ``skills``
command genuinely is a pure forward, so the helper costs nothing there;
``start-gui`` is not, so it costs ``--force``. The two findings look
identical in the report and only one remedy is safe — which is precisely
what an unconditional sentence invites a reader to miss, because applying
it uniformly is the obvious reading.
"""

#: Appended to any finding text that offers ``deprecated_alias()``.
ALIAS_REMEDY_CAVEAT: str = (
    " NOTE: `deprecated_alias()` forwards argv to the target and nothing "
    "else, so it fits an alias that is a PURE FORWARD. If this command "
    "accepts options the target does NOT have, or does work of its own "
    "before handing off, the swap turns those invocations into usage "
    "errors and silently drops that work. In that case keep the "
    "hand-rolled body (and say why beside the registration), or have the "
    "target grow the options first. Never trade a working capability for "
    "a quieter report — least of all for a warn-tier finding that is not "
    "gating your build."
)

__all__ = ["ALIAS_REMEDY_CAVEAT"]

# EOF
