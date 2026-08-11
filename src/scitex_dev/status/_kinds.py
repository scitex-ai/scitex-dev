#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Per-kind validation, DERIVED from ``spec/kinds.yaml``.

A ``kind`` is a discriminated-union tag: it says HOW TO READ ``code`` and
nothing more. There is no translation here and there is nothing to translate
to — ``http 503`` stays a real HTTP 503 all the way through.

Everything in this module reads its tables out of the packaged spec, so the
spec is the source of truth and this file is a reader of it. The one
exception is ``errno``, whose valid names come from the PLATFORM's own
``errno`` table rather than a list in the YAML: a hand-typed list of a hundred
errno names is a list with a typo in it, and the platform already knows.

The ``message`` rules live next door in :mod:`._message`. They read the same
spec file, but they answer a different question — "is this hint honest and
actionable" rather than "is this code real within its kind" — and keeping them
apart is what lets each have a test file that mirrors it.
"""

from __future__ import annotations

import errno as _errno
from functools import lru_cache
from typing import Any

from ._errors import UnknownCodeError, UnknownKindError
from ._spec import load_kinds, load_scitex_codes

__all__ = [
    "KIND_DNS",
    "KIND_ERRNO",
    "KIND_GRPC",
    "KIND_HTTP",
    "KIND_PROCESS",
    "KIND_SCITEX",
    "RESERVED_PROCESS_CODES",
    "kinds",
    "requires_probe",
    "validate_code",
    "validate_kind",
]

KIND_HTTP = "http"
KIND_PROCESS = "process"
KIND_GRPC = "grpc"
KIND_DNS = "dns"
KIND_ERRNO = "errno"
KIND_SCITEX = "scitex"

#: POSIX exit codes that MUST NOT carry a SciTeX meaning. They already mean
#: "generic failure" and "usage error" in every CLI framework — and argparse
#: and click both exit 2 for an UNKNOWN SUBCOMMAND, so overloading 2 lets a
#: missing or renamed verb impersonate a real value. Measured in this fleet:
#: a `may-stop` verb absent from an older install exited 2, indistinguishable
#: from a usage error, and a Stop hook failed open on it.
#:
#: These are still VALID process codes — a program really can exit 1 — so
#: they are not rejected. They are reserved from being *assigned* a meaning.
RESERVED_PROCESS_CODES = (1, 2)


@lru_cache(maxsize=None)
def _registry() -> dict[str, dict[str, Any]]:
    """The kind registry, indexed by kind name."""
    return {entry["kind"]: entry for entry in load_kinds()["kinds"]}


@lru_cache(maxsize=None)
def _scitex_codes() -> frozenset[str]:
    """The closed enumeration of ``kind="scitex"`` codes."""
    return frozenset(entry["code"] for entry in load_scitex_codes()["codes"])


def kinds() -> tuple[str, ...]:
    """Every registered kind, in spec order."""
    return tuple(_registry())


def validate_kind(kind: Any) -> dict[str, Any]:
    """Return the registry entry for ``kind``, or raise.

    An unknown kind is REFUSED, never defaulted. A default would mean the tag
    no longer says which dictionary to open, and every reader downstream
    depends on it saying exactly that.
    """
    if kind not in _registry():
        raise UnknownKindError(
            f"unknown kind {kind!r}. Registered kinds: "
            f"{', '.join(kinds())}. Pick the one whose vocabulary already "
            f"says what you mean — borrowing is always preferred to minting. "
            f"If none can, add a scitex code with its admission test in "
            f"spec/scitex-codes.yaml; registering a whole new kind is a spec "
            f"change because every reader has to learn it."
        )
    return _registry()[kind]


def _check_int_code(kind: str, code: Any, domain: dict[str, Any]) -> None:
    """Range- and enumeration-check an integer code."""
    if isinstance(code, bool) or not isinstance(code, int):
        raise UnknownCodeError(
            f"kind {kind!r} carries an INTEGER code; got {code!r} "
            f"({type(code).__name__}). e.g. StatusCode(kind={kind!r}, "
            f"code=503, message=...)."
        )
    low, high = domain["range"]
    if not low <= code <= high:
        raise UnknownCodeError(
            f"{kind}/{code} is outside the valid range {low}-{high}."
        )
    allowed = domain.get("enum")
    if allowed is not None and code not in allowed:
        raise UnknownCodeError(
            f"{kind}/{code} is not a defined {kind} code. The range check "
            f"alone would have accepted it, which is why the domain is "
            f"enumerated: a code nobody defined is a typo wearing a uniform. "
            f"Use a real {kind} code and put the specifics in `message`."
        )


def _check_errno_code(code: Any) -> None:
    """Require a portable errno NAME, never a platform-local number."""
    if isinstance(code, int):
        name = _errno.errorcode.get(code, "<unmapped>")
        raise UnknownCodeError(
            f"errno codes are NAMES, not numbers; got {code!r} "
            f"(locally {name}). errno NUMBERS are platform-specific — the "
            f"same integer is a different error on another OS — so a number "
            f"crossing a host boundary is a value that changes meaning in "
            f"transit. Send the name instead."
        )
    if code not in set(_errno.errorcode.values()):
        raise UnknownCodeError(
            f"errno/{code!r} is not an errno name known to this platform. "
            f"Valid names come from the platform's own errno table (e.g. "
            f"ENOENT, EACCES, ECONNREFUSED, ETIMEDOUT)."
        )


def _check_scitex_code(code: Any) -> None:
    """Enforce the closed enumeration in ``spec/scitex-codes.yaml``."""
    if code not in _scitex_codes():
        raise UnknownCodeError(
            f"scitex/{code!r} is not in the closed enumeration "
            f"{sorted(_scitex_codes())}. Before adding one, check the "
            f"admission test in spec/scitex-codes.yaml: if any http, grpc, "
            f"dns, errno or process code can express the condition, borrow "
            f"that instead. This list staying short IS the design working."
        )


def validate_code(kind: str, code: Any) -> None:
    """Check ``code`` against its declared ``kind``, or raise."""
    domain = validate_kind(kind)["code_domain"]

    if kind == KIND_ERRNO:
        _check_errno_code(code)
        return
    if kind == KIND_SCITEX:
        _check_scitex_code(code)
        return
    if "range" in domain:
        _check_int_code(kind, code, domain)
        return

    allowed = domain["enum"]
    if code not in allowed:
        raise UnknownCodeError(
            f"{kind}/{code!r} is not a defined {kind} code. Valid: "
            f"{', '.join(map(str, allowed))}."
        )


def requires_probe(kind: str, code: Any) -> bool:
    """Does this code's native meaning mean "received, not finished"?"""
    return code in validate_kind(kind).get("requires_probe", ())


# EOF
