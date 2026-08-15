#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The two ``message`` rules, DERIVED from ``spec/kinds.yaml``.

``message`` is a HINT, and it is load-bearing. It does two jobs:

  (a) it declares what the SENDER is doing or will do;
  (b) it tells the RECEIVER that verification is THEIRS, and hands over the
      means — how to check, how to ask.

Clause (b) is the constitutional rule *"confirm arrival, not dispatch; A->B
without an observed B->A is not a handshake, it is a hope"* turned into a
field. Measured 2026-08-11: scitex-dev sent an a2a message to scitex-cards,
got back no error worth acting on, and treated SENDING as DELIVERY. Nothing
in the return said confirmation was still owed.

M1 — NO INFERRED CAUSE
----------------------
A message states what was MEASURED and what to DO NEXT. It never names a
cause it did not observe. Hints inform; they do not conclude.

Measured 2026-08-11: a transport-failure message printed "THEREFORE the fault
is specific to POST /agents" on the strength of two control probes that
cannot see that route. A reader acted on it within TWO MINUTES and filed a P1
against the wrong component. The route was fine — the client had stopped
listening after 30 s while the server worked the request for 5 min 12 s.
Fixed in scitex-agent-container PR #956.

M2 — A NON-FINAL CODE MUST SAY HOW TO ASK
-----------------------------------------
``http 102`` / ``http 202`` mean the work is still running. Without a named
probe the reader can only wait and then guess, which is the same incident
seen from the other side.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from ._errors import InferredCauseError, MissingProbeError
from ._kinds import requires_probe
from ._spec import load_kinds

__all__ = ["forbidden_markers", "names_a_probe", "validate_message"]

#: A probe named in a message: a backtick-quoted command, a URL, or a path.
#: All three name a SOURCE the reader can consult, which is the point — "check
#: later" names nothing and would satisfy no reader.
_PROBE = re.compile(r"`[^`]+`|https?://\S+|(?<![\w.])/[\w./-]+")


@lru_cache(maxsize=None)
def forbidden_markers() -> tuple[str, ...]:
    """Phrases that assert an INFERENCE rather than report an observation.

    Spec-sourced, so the rule is normative rather than a habit of this file.
    Observation words (``because``, ``due to``) are deliberately absent: M1
    bans CONCLUDING a cause, not REPORTING one you saw.
    """
    rules = load_kinds()["message"]["no_inferred_cause"]
    return tuple(marker.lower() for marker in rules["forbidden_markers"])


def names_a_probe(message: str) -> bool:
    """Does ``message`` name something the reader can go and consult?"""
    return _PROBE.search(message) is not None


def validate_message(kind: str, code: Any, message: Any) -> None:
    """Enforce M1 and M2, or raise."""
    if not isinstance(message, str) or not message.strip():
        raise ValueError(
            "message must be a non-empty string. It is a HINT and it is "
            "load-bearing: it declares what the sender is doing, and it "
            "hands the receiver the means to verify and to ask. An empty "
            "message leaves the receiver with a bare code and a guess."
        )

    lowered = message.lower()
    for marker in forbidden_markers():
        if marker in lowered:
            raise InferredCauseError(
                f"message contains {marker!r}, which asserts a CAUSE rather "
                f"than reporting a MEASUREMENT (rule M1). Stating a cause "
                f"you OBSERVED is fine; concluding one you did not is not. "
                f"Measured 2026-08-11: 'THEREFORE the fault is specific to "
                f"POST /agents' was printed from control probes that cannot "
                f"see that route, and a reader filed a P1 against the wrong "
                f"component within two minutes. Use the shape from PR #956: "
                f"OBSERVED / RULED OUT / NOT ESTABLISHED / NEXT, to find out "
                f"rather than guess."
            )

    if requires_probe(kind, code) and not names_a_probe(message):
        raise MissingProbeError(
            f"{kind}/{code} means 'received, still working', so message "
            f"MUST name a way to ask about it (rule M2) — a backtick-quoted "
            f"command, a URL, or a path. Without one the reader can only "
            f"wait and then guess, which is the 2026-08-11 incident exactly: "
            f"a client gave up at 30 s while the server worked the request "
            f"for 5 min 12 s. e.g. 'accepted as <exchange-id>; poll "
            f"`sac agents list <name>`'."
        )


# EOF
