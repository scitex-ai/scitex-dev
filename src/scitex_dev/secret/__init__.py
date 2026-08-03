# -*- coding: utf-8 -*-
"""GPG-backed secret store for the SciTeX ecosystem.

Public surface. The CLI (``<pkg> dev secret …``) is a thin wrapper over these;
all behaviour lives here so it is testable without a terminal.
"""

from ._store import (
    ALREADY_EXISTS,
    GPG_FAILED,
    GPG_MISSING,
    INVALID_NAME,
    NO_RECIPIENT,
    NOT_FOUND,
    OK,
    SecretResult,
    SecretStore,
    generate_value,
)

__all__ = [
    "SecretStore",
    "SecretResult",
    "generate_value",
    "OK",
    "INVALID_NAME",
    "NO_RECIPIENT",
    "NOT_FOUND",
    "ALREADY_EXISTS",
    "GPG_MISSING",
    "GPG_FAILED",
]
