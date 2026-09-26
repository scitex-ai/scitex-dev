#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The values ``check()`` and ``accessible()`` reason over.

Roles and visibility are ``scitex_dev.scope``'s, not a second vocabulary.
Everything here is a frozen value validated where it is built, so a malformed
principal or grant fails at the adapter that produced it, not inside a decision.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, Mapping, Optional

from ..scope import Role, Visibility
from ._errors import AccessConfigError

PrincipalKind = Literal["user", "org", "agent", "anonymous"]

ROLE_ORDER: tuple[Role, ...] = ("read", "write", "admin")

_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@+-]*$")
_KIND_NAME = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$")
_ANONYMOUS_ID = "anonymous"


def role_rank(role: Role) -> int:
    return ROLE_ORDER.index(role)


def role_at_least(role: Optional[Role], required: Role) -> bool:
    return role is not None and role_rank(role) >= role_rank(required)


def weaker_role(first: Optional[Role], second: Optional[Role]) -> Optional[Role]:
    if first is None or second is None:
        return None
    return min(first, second, key=role_rank)


def stronger_role(first: Optional[Role], second: Optional[Role]) -> Optional[Role]:
    if first is None:
        return second
    if second is None:
        return first
    return max(first, second, key=role_rank)


def _require_role(value: object, where: str) -> Role:
    if value not in ROLE_ORDER:
        raise AccessConfigError(
            f"{where}: unknown role {value!r}; expected one of {list(ROLE_ORDER)}"
        )
    return value  # type: ignore[return-value]


def _require_segment(value: str, where: str) -> str:
    if not isinstance(value, str) or not _SEGMENT.match(value) or ".." in value:
        raise AccessConfigError(
            f"{where}: unusable identifier {value!r}; must match "
            f"{_SEGMENT.pattern} and contain no '..'"
        )
    return value


@dataclass(frozen=True)
class Principal:
    """Who is asking or being granted: ``user:alice``, ``org:lab``,
    ``agent:alice/bot`` or ``anonymous``.

    An agent's id is ``<owner>/<name>`` so its owner is part of its identity;
    the operator's own fleet agents are ``agent:ywatanabe/<name>`` like anyone's.
    """

    kind: PrincipalKind
    id: str

    def __post_init__(self) -> None:
        if self.kind == "anonymous":
            if self.id != _ANONYMOUS_ID:
                raise AccessConfigError(
                    f"the anonymous principal has id {_ANONYMOUS_ID!r}, not {self.id!r}"
                )
            return
        if self.kind in ("user", "org"):
            _require_segment(self.id, f"{self.kind} principal")
            return
        if self.kind == "agent":
            parts = self.id.split("/")
            if len(parts) != 2:
                raise AccessConfigError(
                    f"agent principal {self.id!r} must be <owner>/<name>; an "
                    "agent without an owner has no ceiling to sit under"
                )
            for part in parts:
                _require_segment(part, "agent principal")
            return
        raise AccessConfigError(
            f"unknown principal kind {self.kind!r}; expected user, org, agent or anonymous"
        )

    @classmethod
    def parse(cls, text: str) -> "Principal":
        if text == _ANONYMOUS_ID:
            return ANONYMOUS
        kind, separator, identifier = text.partition(":") if isinstance(text, str) else ("", "", "")
        if not separator:
            raise AccessConfigError(
                f"principal {text!r} must be <kind>:<id>, e.g. user:alice, "
                "org:lab, agent:alice/bot, or the bare word anonymous"
            )
        return cls(kind=kind, id=identifier)  # type: ignore[arg-type]

    def __str__(self) -> str:
        return _ANONYMOUS_ID if self.kind == "anonymous" else f"{self.kind}:{self.id}"

    @property
    def is_signed_in(self) -> bool:
        return self.kind != "anonymous"

    @property
    def agent_owner(self) -> Optional["Principal"]:
        """The user an agent acts for; ``None`` for everyone else."""
        if self.kind != "agent":
            return None
        return Principal(kind="user", id=self.id.split("/")[0])


ANONYMOUS = Principal(kind="anonymous", id=_ANONYMOUS_ID)


@dataclass(frozen=True)
class KindSpec:
    """What a package registers for one resource kind.

    ``actions`` maps each verb the kind supports to the role it requires.
    """

    name: str
    path_prefix: str
    actions: Mapping[str, Role]
    package: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not _KIND_NAME.match(self.name):
            raise AccessConfigError(
                f"kind name {self.name!r} must be dotted lowercase, e.g. cards.card"
            )
        if not isinstance(self.path_prefix, str) or not self.path_prefix.startswith("/"):
            raise AccessConfigError(
                f"kind {self.name}: path_prefix {self.path_prefix!r} must start with '/'"
            )
        if not self.actions:
            raise AccessConfigError(f"kind {self.name}: declares no actions")
        for action, role in self.actions.items():
            _require_segment(action, f"kind {self.name} action")
            _require_role(role, f"kind {self.name} action {action!r}")
        object.__setattr__(self, "actions", MappingProxyType(dict(self.actions)))

    def required_role(self, action: str) -> Role:
        if action not in self.actions:
            raise AccessConfigError(
                f"kind {self.name} has no action {action!r}; it declares "
                f"{sorted(self.actions)}"
            )
        return self.actions[action]

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "path_prefix": self.path_prefix,
            "actions": dict(self.actions),
            "package": self.package,
        }


def resource_ref(kind: str, path: str) -> str:
    return f"{kind}:{path}"


def split_resource_ref(ref: str) -> tuple[str, str]:
    kind, separator, path = ref.partition(":")
    if not separator or not path.startswith("/"):
        raise AccessConfigError(
            f"resource {ref!r} must be <kind>:<path>, e.g. cards.card:/users/alice/cards/c1"
        )
    return kind, path


@dataclass(frozen=True)
class Resource:
    """One piece of content: its kind, canonical path, owner and visibility.

    ``parent`` is the ref (``kind:path``) whose default grants flow down to
    this resource, e.g. the project a figure lives in.
    """

    kind: str
    path: str
    owner: Principal
    visibility: Visibility = "private"
    parent: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.path, str) or not self.path.startswith("/") or ".." in self.path:
            raise AccessConfigError(
                f"resource path {self.path!r} must start with '/' and contain no '..'"
            )
        if self.owner.kind not in ("user", "org"):
            # An agent's content belongs to the agent's owner, so the ceiling rule has someone to cap against.
            raise AccessConfigError(
                f"resource {self.ref} is owned by {self.owner}; an owner must be a "
                "user or an org (record agent-made content under the agent's owner)"
            )
        if self.visibility not in ("public", "private"):
            raise AccessConfigError(
                f"resource {self.ref}: unknown visibility {self.visibility!r}; "
                "expected public or private"
            )
        if self.parent is not None:
            split_resource_ref(self.parent)

    @property
    def ref(self) -> str:
        return resource_ref(self.kind, self.path)

    @property
    def is_public(self) -> bool:
        return self.visibility == "public"


@dataclass(frozen=True)
class Grant:
    """``principal`` holds ``role`` on the resource ``target`` (a ``kind:path`` ref).

    A ``default`` grant is the POSIX default-ACL analogue: it applies to the
    target's children, not to the target itself.
    """

    principal: Principal
    role: Role
    target: str
    default: bool = False

    def __post_init__(self) -> None:
        _require_role(self.role, f"grant to {self.principal}")
        split_resource_ref(self.target)
        if self.principal.kind == "anonymous":
            raise AccessConfigError(
                "a grant to anonymous is not a grant; make the resource public instead"
            )


@dataclass(frozen=True)
class Membership:
    """``principal`` belongs to ``org`` and may act for it up to ``role``."""

    principal: Principal
    org: Principal
    role: Role

    def __post_init__(self) -> None:
        _require_role(self.role, f"membership of {self.principal} in {self.org}")
        if self.org.kind != "org":
            raise AccessConfigError(
                f"membership target {self.org} is not an org principal"
            )
        if self.principal.kind in ("org", "anonymous"):
            raise AccessConfigError(
                f"{self.principal} cannot be an org member; members are users or agents"
            )


@dataclass(frozen=True)
class AccessRequest:
    """The question as asked: who, which verb, on what."""

    principal: Principal
    action: str
    resource: str

    def to_dict(self) -> dict:
        return {
            "principal": str(self.principal),
            "action": self.action,
            "resource": self.resource,
        }


__all__ = [
    "ANONYMOUS",
    "AccessRequest",
    "Grant",
    "KindSpec",
    "Membership",
    "Principal",
    "PrincipalKind",
    "ROLE_ORDER",
    "Resource",
    "resource_ref",
    "role_at_least",
    "split_resource_ref",
]

# EOF
