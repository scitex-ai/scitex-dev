# -*- coding: utf-8 -*-
"""GPG-backed secret store for the SciTeX ecosystem.

Public surface. The CLI (``<app> dev secret …``) is a thin wrapper over these;
all behaviour lives here so it is testable without a terminal.

A leaf package needs three things from this module and nothing else:

    SecretContext  an app + a scitex_dev.scope.Scope: whose secret is wanted
    resolve     get a credential, the same way in every situation
    register_secret_group  (in ``.cli``) mount `<app> dev secret …`
"""

from ._context import SecretContext, RESERVED_SEGMENTS, name_reservation_error
from ._resolve import (
    SecretUnavailable,
    env_var_for,
    resolve,
    resolve_source,
    store_for,
)
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
    # The leaf-facing primitive: what scitex-hub and every other leaf calls.
    "SecretContext",
    "resolve",
    "resolve_source",
    "store_for",
    "env_var_for",
    "SecretUnavailable",
    "RESERVED_SEGMENTS",
    "name_reservation_error",
    # The store itself, for tools that manage rather than consume secrets.
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
