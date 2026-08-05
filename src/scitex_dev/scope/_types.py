#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The five types every SciTeX app agrees on.

Operator directive 2026-08-03: constrain it from below. scitex-dev ships these
types; Django, Gitea, the CLI and every leaf conform to them. A Django model
becomes a projection of this shape rather than a rival definition of it.

WHO IS AUTHORITATIVE — the test is who ENFORCES, not who stores
---------------------------------------------------------------
A system that merely holds a copy is a reflection. Gitea does not store
visibility, it enforces it: a private repo refuses `git clone` at the protocol
level, without consulting anything here. scitex cannot do that and never will.

    the shape (this module)              scitex     nothing else defines it
    repo exists / visibility / human ACL Gitea      it is what blocks a clone
    agents as principals                 scitex     Gitea has no such concept
    anything in Django                   reflection it enforces nothing

Making scitex authoritative over visibility would put the same fact in two
places, needing sync and drifting. On disagreement the thing that still stops a
clone is Gitea — so the scitex copy would be the wrong one while looking
authoritative, which is the worse failure because it reads as correct.

WHAT IS DELIBERATELY ABSENT
---------------------------
The ASKER. No type here carries "who is making this request". That identity
comes from the session in hub and from the OS account locally — never from data
a caller supplies, because a caller who can name themselves can name someone
else.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal, Optional

PrincipalKind = Literal["user", "org", "agent"]
Visibility = Literal["public", "private"]
Role = Literal["admin", "write", "read"]
DataLivesAt = Literal["owner", "project"]
ViewKind = Literal["pinned", "cross"]

#: Identifiers become path segments and URL components, so they must not
#: travel. Rejected rather than sanitised: silently rewriting an identifier
#: makes two distinct principals collapse into one without anyone being told.
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@+-]*$")


def _check_id(kind: str, value: str) -> str:
    if not _SAFE_ID.match(value) or ".." in value:
        raise ValueError(
            f"unusable {kind} {value!r}: must match {_SAFE_ID.pattern} and "
            "contain no '..'. An identifier that can traverse would let one "
            "owner address another's data."
        )
    return value


@dataclass(frozen=True)
class Principal:
    """Someone or something that can be granted access.

    Users, orgs and agents are ONE type rather than parallel ones, because they
    go on the same membership list and an agent must be removable without
    touching whoever owns it. An agent is a principal in its own right, not a
    mode its owner is operating in — otherwise revoking the agent would mean
    revoking the person.
    """

    id: str
    kind: PrincipalKind
    #: The user an agent acts for. Meaningless for users and orgs.
    owner: Optional[str] = None

    def __post_init__(self) -> None:
        _check_id("principal id", self.id)
        if self.kind not in ("user", "org", "agent"):
            raise ValueError(
                f"unknown principal kind {self.kind!r}; expected user, org or agent"
            )
        if self.kind == "agent" and self.owner is None:
            raise ValueError(
                f"agent {self.id!r} has no owner. An agent acts for someone, and "
                "an agent nobody owns is one nobody can be asked about."
            )
        if self.kind != "agent" and self.owner is not None:
            raise ValueError(
                f"{self.kind} {self.id!r} carries owner={self.owner!r}. Only "
                "agents act on behalf of someone."
            )
        if self.owner is not None:
            _check_id("owner", self.owner)

    @property
    def is_human(self) -> bool:
        return self.kind == "user"


@dataclass(frozen=True)
class Project:
    """A named unit of work under an owner. One Gitea repository.

    ``visibility`` is recorded here because callers need to reason about it,
    NOT because this is where it is decided — Gitea decides it. A value here
    that disagrees with Gitea is stale, and Gitea wins.
    """

    owner: str
    name: str
    visibility: Visibility = "private"

    def __post_init__(self) -> None:
        _check_id("project owner", self.owner)
        _check_id("project name", self.name)
        if self.visibility not in ("public", "private"):
            raise ValueError(
                f"unknown visibility {self.visibility!r}; expected public or private"
            )

    @property
    def is_public(self) -> bool:
        """Anonymous read is a shipped feature, so this is a real state."""
        return self.visibility == "public"

    def path(self) -> str:
        """``owner/name`` — the GitHub-shaped identity already in the URLs."""
        return f"{self.owner}/{self.name}"


@dataclass(frozen=True)
class Member:
    """A principal's role on a project."""

    principal: Principal
    role: Role

    def __post_init__(self) -> None:
        if self.role not in ("admin", "write", "read"):
            raise ValueError(
                f"unknown role {self.role!r}; expected admin, write or read"
            )

    @property
    def may_write(self) -> bool:
        return self.role in ("admin", "write")


#: Roles from weakest to strongest. Order is the definition of "at most".
_ROLE_ORDER: tuple[Role, ...] = ("read", "write", "admin")


def effective_role(granted: Role, owner_role: Optional[Role]) -> Role:
    """An agent's real permission: never more than the person behind it.

    ``owner_role`` is what the agent's OWNER holds on the same project, or
    ``None`` when the owner holds nothing there.

    Without this rule, creating an agent is a privilege escalation: a user with
    `read` grants their own agent `admin` and now acts as an admin through it.
    With it, three things follow at once and none of them need separate code:

      * an agent can be revoked on its own (drop its grant) …
      * … but can never exceed its owner, so making one gains nothing;
      * revoking the OWNER silently revokes every agent they run, because the
        ceiling drops with them — no cascade to remember, no orphaned agent
        still holding access after the person is gone.

    Raises when the owner holds nothing: an agent acting on a project its owner
    cannot touch has no legitimate reading, and returning `read` there would
    quietly invent access nobody granted.
    """
    if owner_role is None:
        raise PermissionError(
            "an agent's owner holds no role on this project, so the agent has "
            "no ceiling to sit under. Grant the owner access, or remove the "
            "agent's grant — an agent must not reach where its owner cannot."
        )
    return min(granted, owner_role, key=_ROLE_ORDER.index)


@dataclass(frozen=True)
class Scope:
    """WHAT is being looked at. Never who is looking.

    Both fields absent means "across everything the asker may see" — the
    cross-cutting view. That is a legitimate value, not a missing one, which is
    why neither field has a guessed default: a default here would silently
    narrow a query the caller meant to be broad, or broaden one they meant to
    be narrow, and both look like success.
    """

    owner: Optional[str] = None
    project: Optional[str] = None

    def __post_init__(self) -> None:
        if self.owner is not None:
            _check_id("scope owner", self.owner)
        if self.project is not None:
            _check_id("scope project", self.project)
        if self.project is not None and self.owner is None:
            raise ValueError(
                "scope names a project with no owner. A project is identified "
                "by owner/name, so a bare project name matches whatever the "
                "reader assumes — which is how a write lands in the wrong one."
            )

    @classmethod
    def standalone(cls) -> "Scope":
        """No owner dimension at all — the OS account IS the boundary.

        A named constructor rather than an omitted argument, because
        `Scope()` reads as "I forgot to say" and `Scope.standalone()` reads
        as "I mean this". Callers that must state their scope explicitly
        (see `SecretContext`, where `scope` has no default) need a way to say
        "there is no owner here" that is a DECLARATION, not an empty value.

        It never looks the current user up. `os.getenv("USER")` here would
        turn a forgotten scope in a web request into a silent read of the
        service account's store — a successful-looking lookup of the wrong
        data, which is worse than the TypeError a missing argument gives.
        """
        return cls()

    @classmethod
    def everything(cls) -> "Scope":
        """Across everything the asker may see — the cross-cutting view.

        Identical in value to `standalone()`, deliberately distinct in NAME.
        Both mean "no owner named", but they are different intentions: one
        says "there is no owner dimension", the other says "every owner I am
        allowed to see". A reader of `cards.list(scope=Scope.everything())`
        should not have to work out which was meant.
        """
        return cls()

    @property
    def is_cross_cutting(self) -> bool:
        return self.owner is None and self.project is None

    def query(self) -> dict[str, str]:
        """The URL query for this scope. Two keys at most, ever.

        Membership does not appear here. A project with a hundred
        collaborators has the same query as an empty one — what is being
        looked at does not grow with who may look at it.
        """
        out: dict[str, str] = {}
        if self.owner is not None:
            out["owner"] = self.owner
        if self.project is not None:
            out["project"] = self.project
        return out


@dataclass(frozen=True)
class AppSpec:
    """What an app declares about itself. Two independent axes.

    Collapsing these into one is the mistake this type exists to prevent —
    checked against the five shipped apps, two of them need the combination the
    single-axis version could not express::

        Writer      project / pinned
        FigRecipe   project / pinned
        Cards       project / cross
        Scholar     owner   / …      a library is not rebuilt per manuscript
        Storage     owner   / …      files belong to a person

    ``view`` decides whether an ambient current scope may exist. A cross app
    must NOT have one: a default scope there is a silent write into the wrong
    project that looks exactly like success. A pinned app must have one: asking
    someone to name the project their window already shows trains them to
    answer without reading.
    """

    app: str
    data_lives_at: DataLivesAt
    view: ViewKind
    #: Names of secrets, settings or other resources this app expects. Free
    #: for now; declared here so a leaf has one place to put it.
    resources: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        _check_id("app", self.app)
        if self.data_lives_at not in ("owner", "project"):
            raise ValueError(
                f"unknown data_lives_at {self.data_lives_at!r}; expected owner "
                "or project"
            )
        if self.view not in ("pinned", "cross"):
            raise ValueError(
                f"unknown view {self.view!r}; expected pinned or cross"
            )

    @property
    def wants_ambient_scope(self) -> bool:
        """May this app carry a 'current project'? Only pinned apps may."""
        return self.view == "pinned"


__all__ = [
    "AppSpec",
    "DataLivesAt",
    "Member",
    "Principal",
    "PrincipalKind",
    "Project",
    "Role",
    "Scope",
    "ViewKind",
    "Visibility",
    "effective_role",
]


# EOF
