#!/usr/bin/env python3
# -*- coding: utf-8 -*-
""":class:`StatusCode` — the whole type.

Three fields, frozen, validated where it is BUILT.

    StatusCode(kind="http",    code=503,            message=...)
    StatusCode(kind="process", code=137,            message=...)
    StatusCode(kind="grpc",    code="UNAVAILABLE",  message=...)
    StatusCode(kind="dns",     code="NXDOMAIN",     message=...)

``kind`` says HOW TO READ ``code``. The native code is preserved verbatim and
NOTHING translates it: ``http 503`` is a real HTTP 503, ``process 137`` is a
real SIGKILL exit. That is the point — folding 137 into some canonical
"resource exhausted" would destroy the only fact usually worth knowing, which
is that the process was KILLED.

``message`` is a HINT, and it is load-bearing: it declares what the sender is
doing, and it hands the receiver the means to verify and to ask. It never
asserts a cause the sender did not observe. Both rules are enforced.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ._kinds import (
    KIND_DNS,
    KIND_GRPC,
    KIND_HTTP,
    KIND_PROCESS,
    validate_code,
    validate_kind,
)
from ._message import validate_message

__all__ = ["StatusCode"]


@dataclass(frozen=True)
class StatusCode:
    """One status, borrowed verbatim from a named vocabulary.

    Validated in ``__post_init__``, so a malformed value cannot be
    constructed at all. That is the whole reason the validator exists: a
    malformed status that survives construction is discovered layers
    downstream, where the context that would explain it is gone.
    """

    kind: str
    code: int | str
    message: str

    def __post_init__(self) -> None:
        validate_kind(self.kind)
        validate_code(self.kind, self.code)
        validate_message(self.kind, self.code, self.message)

    # -- derived, never stored ---------------------------------------------
    #
    # `ok` and `final` are PROPERTIES. Neither is ever serialised beside
    # `code`, because two fields that can disagree eventually will, and a
    # reader then has to guess which one to trust. There is exactly one
    # function computing each.

    @property
    def ok(self) -> bool:
        """Does this code report success, within its own vocabulary?

        NOT the same question as :attr:`final`. ``http 202`` is ``ok`` —
        the request really was accepted — and is NOT final, because the work
        it accepted has not finished. Conflating the two is the 2026-08-11
        incident in miniature: a client that reads "accepted" as "done" and a
        client that reads "not done yet" as "failed" make opposite mistakes
        from the same missing distinction.
        """
        if self.kind == KIND_HTTP:
            return 200 <= int(self.code) < 300
        if self.kind == KIND_PROCESS:
            return self.code == 0
        if self.kind == KIND_GRPC:
            return self.code == "OK"
        if self.kind == KIND_DNS:
            return self.code == "NOERROR"
        # errno names and scitex codes exist only to report a problem.
        return False

    @property
    def final(self) -> bool:
        """Does this code report a FINISHED outcome?

        Derived from the kind's ``non_final`` list in ``spec/kinds.yaml``, so
        the spec decides and this is a reader of it.
        """
        non_final = validate_kind(self.kind).get("non_final", ())
        return self.code not in non_final

    def to_dict(self) -> dict[str, Any]:
        """The wire form — exactly three keys.

        ``ok`` and ``final`` are deliberately absent. They are derivable, and
        a derivable field on the wire is a field that can arrive disagreeing
        with the value it was derived from.
        """
        return {"kind": self.kind, "code": self.code, "message": self.message}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "StatusCode":
        """Parse a wire form, validating it.

        Refuses unknown keys rather than ignoring them. A silently dropped
        key is how a sender believes it said something the receiver never
        heard — and ``ok``/``retryable`` are exactly the keys someone will
        helpfully add back.
        """
        extra = set(payload) - {"kind", "code", "message"}
        if extra:
            raise ValueError(
                f"unexpected key(s) {sorted(extra)} in a StatusCode payload. "
                f"The type is three fields. `ok` and `retryable` in "
                f"particular are DERIVED and must never be sent: `ok` from "
                f"the code within its kind, and retryability likewise (503 "
                f"yes, 403 no) — with `message` carrying the useful version, "
                f"'retry in 10s, or poll `...`'."
            )
        return cls(
            kind=payload["kind"],
            code=payload["code"],
            message=payload["message"],
        )


# EOF
