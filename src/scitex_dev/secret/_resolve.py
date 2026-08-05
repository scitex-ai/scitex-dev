#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The leaf-facing primitive: get a credential, in whatever situation you are in.

``SecretStore`` is the SSOT for a secret's VALUE, and ``SecretContext`` — an
app plus a ``scitex_dev.scope.Scope`` — says whose secret is being asked for.
This module is what a leaf package (scitex-hub, scitex-writer, scitex-scholar,
figrecipe, …) calls at runtime, so every leaf resolves credentials the same way
instead of each inventing its own ``os.environ.get`` with its own fallback
rules.

    from scitex_dev.scope import Scope
    from scitex_dev.secret import SecretContext, resolve

    resolve("api/openai", ctx=SecretContext(
        app="writer", scope=Scope.standalone()))                    # CLI
    resolve("api/openai", ctx=SecretContext(
        app="writer", scope=Scope(owner=request.user.username)))    # in hub

TWO SOURCES, AND WHY ENV WINS — BUT ONLY SOMETIMES
--------------------------------------------------
The store is the SSOT; the environment is the INJECTION CHANNEL. A process
running where the private key does not live — a container, a CI job, a systemd
unit on a deploy host — cannot decrypt anything, so it must be handed the value
some other way. If the store were consulted first, injecting a value would
silently do nothing wherever a stale copy happened to exist.

THE ENVIRONMENT IS CONSULTED ONLY FOR STANDALONE CONTEXTS, and that limit is
load-bearing rather than tidy. ``os.environ`` is process-wide, while a Django
worker serves many users from one process: honouring an env override for a
per-user secret would hand user A's injected value to user B's request, and it
would look like a successful lookup on both. A context with a ``user`` is
answered by that user's store or by nothing.

WHAT IS NOT A VALUE
-------------------
An empty string is never a secret. An exported-but-empty variable is the classic
silent-empty-credential: falsy, so it reads as "unset" in one place and as "the
password" in another. Empty is treated as ABSENT, and the absence is reported.

Nothing here returns a diagnostic in the value position — the ``decrypt.sh``
defect, where a 61-byte ANSI error string was captured as a password and fed to
``sudo -S``. A failure raises or returns ``None``; it never returns a string a
caller could mistake for a credential.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Literal, Optional

from ._context import SecretContext, name_reservation_error
from ._store import OK, SecretStore

Source = Literal["env", "store", "default"]


class SecretUnavailable(RuntimeError):
    """A required secret was in neither the environment nor the store.

    Carries every place that was looked, because "secret not found" without
    saying WHERE sends the reader to guess among several.
    """

    def __init__(self, name: str, ctx: SecretContext, env_var: Optional[str],
                 root: Path, detail: str):
        self.name = name
        self.ctx = ctx
        self.env_var = env_var
        self.root = root
        env_line = (
            f"  environment: {env_var} is unset or empty\n"
            if env_var is not None
            else "  environment: not consulted — a user-scoped context is never "
                 "answered from the process environment\n"
        )
        super().__init__(
            f"secret {name!r} is unavailable for {ctx.describe()}.\n"
            + env_line
            + f"  store:       {root / (name + '.gpg')} — {detail}\n"
            f"  fix: `scitex-dev dev secret set {name} --pkg {ctx.app}` where the "
            "key lives"
            + (f", or export {env_var} where it does not." if env_var else ".")
        )


def store_for(ctx: SecretContext) -> SecretStore:
    """The ``SecretStore`` this context reads and writes."""
    return SecretStore(ctx.secret_root())


def env_var_for(ctx: SecretContext, name: str) -> Optional[str]:
    """The environment variable that overrides ``name``, or ``None``.

    ``None`` for any context carrying a user: see the module docstring — a
    process-wide variable cannot answer a per-user question safely.

    For standalone contexts the name is DERIVED, never registered: a leaf must
    be able to work the variable out from the secret name, and an operator must
    be able to work the secret out from a variable seen in a unit file. Both
    directions matter, so it is a documented transformation rather than a table
    that can drift from what the code reads.

        SecretContext(app="hub", scope=Scope.standalone()),
        "auth/oidc-client-secret"
          -> SCITEX_HUB_SECRET_AUTH_OIDC_CLIENT_SECRET
    """
    if not ctx.is_standalone:
        return None
    slug = re.sub(r"[^A-Za-z0-9]+", "_", f"{ctx.app}_secret_{name}")
    return f"SCITEX_{slug.strip('_').upper()}"


def _from_env(env_var: Optional[str]) -> Optional[str]:
    """The env value, or None. Empty and whitespace-only count as ABSENT."""
    if env_var is None:
        return None
    raw = os.environ.get(env_var)
    if raw is None or not raw.strip():
        return None
    return raw


def resolve_source(
    name: str,
    *,
    ctx: SecretContext,
    default: Optional[str] = None,
    required: bool = True,
) -> tuple[Optional[str], Optional[Source]]:
    """``resolve``, but also reporting WHICH source answered.

    Use this where a service logs its own configuration at start-up: "loaded
    auth/oidc-client-secret from env" is the line that makes a stale override
    findable in one read instead of one outage.
    """
    reserved = name_reservation_error(name)
    if reserved is not None:
        # Raise regardless of `required`: this is a malformed request, not an
        # absent secret, and returning None would let a caller treat a name it
        # can never store as merely "not set yet".
        raise ValueError(reserved)

    env_var = env_var_for(ctx, name)

    from_env = _from_env(env_var)
    if from_env is not None:
        return from_env, "env"

    store = store_for(ctx)
    result = store.show(name)
    if result.code == OK and result.value:
        return result.value, "store"

    if default is not None:
        return default, "default"

    if required:
        raise SecretUnavailable(name, ctx, env_var, store.root, result.detail)
    return None, None


def resolve(
    name: str,
    *,
    ctx: SecretContext,
    default: Optional[str] = None,
    required: bool = True,
) -> Optional[str]:
    """Return the secret ``name`` for ``ctx``, or raise if it is required.

    This is the call a leaf package makes. ``required=False`` returns ``None``
    for a genuinely optional credential — ``None``, not ``""``, so an optional
    secret cannot be silently used as an empty password.
    """
    value, _source = resolve_source(
        name, ctx=ctx, default=default, required=required
    )
    return value


__all__ = [
    "SecretUnavailable",
    "Source",
    "env_var_for",
    "resolve",
    "resolve_source",
    "store_for",
]


# EOF
