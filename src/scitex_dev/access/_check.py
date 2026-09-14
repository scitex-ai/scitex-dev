#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``check()`` — may this principal perform this action on this resource?

A pure function of its arguments: no session, no database, no clock except the
exchange id. Rules, in the order a reason is chosen when several allow:

    owner       the resource's owner holds admin
    grant       an explicit grant on the resource
    inherited   a default grant on the resource's parent
    org         via an org membership, capped by the membership role
    public      public visibility gives read to everyone, signed in or not

An agent (``agent:<owner>/<name>``) gets nothing from its owner implicitly: its
own grants count, each capped by what the owner holds on the same resource
(``scitex_dev.scope.effective_role``). There is no staff bypass anywhere; an
instance administrator is an org membership plus an ordinary grant.
"""

from __future__ import annotations

from typing import Iterable, Optional

from ..scope import Role
from ..status import StatusCode
from ._decision import AccessDecision
from ._errors import AccessConfigError
from ._kinds import KindRegistry, discover_kinds
from ._reasons import DecisionKind, Reason
from ._types import (
    AccessRequest,
    Grant,
    KindSpec,
    Membership,
    Principal,
    Resource,
    role_at_least,
    split_resource_ref,
    stronger_role,
    weaker_role,
)

ALLOWING_REASONS_IN_PRECEDENCE = (
    Reason.OWNER,
    Reason.GRANT,
    Reason.INHERITED,
    Reason.ORG,
    Reason.PUBLIC,
)


def _strongest(roles: Iterable[Optional[Role]]) -> Optional[Role]:
    best: Optional[Role] = None
    for role in roles:
        best = stronger_role(best, role)
    return best


def role_sources(
    principal: Principal,
    resource: Resource,
    grants: Iterable[Grant],
    memberships: Iterable[Membership],
) -> dict[Reason, Role]:
    """The strongest role each non-public rule gives ``principal`` on ``resource``."""
    grants = tuple(grants)
    sources: dict[Reason, Optional[Role]] = {}

    if resource.owner == principal:
        sources[Reason.OWNER] = "admin"

    sources[Reason.GRANT] = _strongest(
        grant.role
        for grant in grants
        if grant.principal == principal and not grant.default and grant.target == resource.ref
    )
    sources[Reason.INHERITED] = _strongest(
        grant.role
        for grant in grants
        if grant.principal == principal and grant.default and grant.target == resource.parent
    )

    org_roles: list[Optional[Role]] = []
    for membership in memberships:
        if membership.principal != principal:
            continue
        if resource.owner == membership.org:
            org_roles.append(membership.role)
        for grant in grants:
            if grant.principal != membership.org:
                continue
            applies = (
                grant.target == resource.parent if grant.default else grant.target == resource.ref
            )
            if applies:
                org_roles.append(weaker_role(grant.role, membership.role))
    sources[Reason.ORG] = _strongest(org_roles)

    return {reason: role for reason, role in sources.items() if role is not None}


def _resolve_kind(kind: str, kinds: Optional[KindRegistry]) -> Optional[KindSpec]:
    registry = kinds if kinds is not None else discover_kinds()
    return registry.get(kind)


def kind_unregistered(principal: Principal, action: str, ref: str) -> AccessDecision:
    kind, _ = split_resource_ref(ref)
    return AccessDecision(
        request=AccessRequest(principal=principal, action=action, resource=ref),
        reason=Reason.KIND_UNREGISTERED,
        detail=f"no installed package registers the resource kind {kind!r}, so no access rule applies",
        hint=(
            f"install or fix the package that owns {kind!r}; `<pkg> dev access list-kinds` "
            "lists what is registered"
        ),
    )


def _not_found_for(principal: Principal, action: str, ref: str, required: Role) -> AccessDecision:
    """The denial for a principal with no role: identical whether or not the resource exists."""
    request = AccessRequest(principal=principal, action=action, resource=ref)
    if not principal.is_signed_in:
        return AccessDecision(
            request=request,
            reason=Reason.NOT_SIGNED_IN,
            detail=f"{action} on {ref} is not available without signing in",
            hint="sign in, then ask again",
            required_role=required,
        )
    return AccessDecision(
        request=request,
        reason=Reason.NOT_VISIBLE,
        detail=f"no resource {ref} is visible to {principal}",
        hint="check the path, or ask the owner to share it with you",
        required_role=required,
    )


def decide_missing(
    principal: Principal,
    action: str,
    ref: str,
    *,
    kinds: Optional[KindRegistry] = None,
) -> AccessDecision:
    """The decision for a resource an adapter could not find; renders like a private one."""
    kind, _ = split_resource_ref(ref)
    spec = _resolve_kind(kind, kinds)
    if spec is None:
        return kind_unregistered(principal, action, ref)
    return _not_found_for(principal, action, ref, spec.required_role(action))


def decide_unresolved(
    principal: Principal,
    action: str,
    ref: str,
    *,
    reason: Reason,
    detail: str,
    hint: str,
    cause: Optional[StatusCode] = None,
) -> AccessDecision:
    """For adapters: the enforcer or the asker's identity could not be reached."""
    decision = AccessDecision(
        request=AccessRequest(principal=principal, action=action, resource=ref),
        reason=reason,
        detail=detail,
        hint=hint,
        cause=cause,
    )
    if decision.kind is not DecisionKind.UNRESOLVED:
        raise AccessConfigError(f"{reason.value} is not an unresolved reason")
    return decision


def check(
    principal: Principal,
    action: str,
    resource: Resource,
    *,
    grants: Iterable[Grant],
    memberships: Iterable[Membership],
    kinds: Optional[KindRegistry] = None,
) -> AccessDecision:
    grants = tuple(grants)
    memberships = tuple(memberships)
    spec = _resolve_kind(resource.kind, kinds)
    if spec is None:
        return kind_unregistered(principal, action, resource.ref)
    required = spec.required_role(action)
    if not resource.path.startswith(spec.path_prefix):
        raise AccessConfigError(
            f"resource {resource.ref} is outside kind {spec.name}'s path prefix {spec.path_prefix!r}"
        )
    request = AccessRequest(principal=principal, action=action, resource=resource.ref)

    own_sources = role_sources(principal, resource, grants, memberships) if principal.is_signed_in else {}
    owner = principal.agent_owner
    owner_role: Optional[Role] = None
    if owner is None:
        effective_sources = dict(own_sources)
    else:
        owner_role = _strongest(role_sources(owner, resource, grants, memberships).values())
        effective_sources = {
            reason: capped
            for reason, role in own_sources.items()
            if (capped := weaker_role(role, owner_role)) is not None
        }
    if resource.is_public:
        effective_sources[Reason.PUBLIC] = "read"

    held = _strongest(effective_sources.values())
    for reason in ALLOWING_REASONS_IN_PRECEDENCE:
        if role_at_least(effective_sources.get(reason), required):
            return AccessDecision(
                request=request,
                reason=reason,
                detail=(
                    f"{principal} may {action} {resource.ref}: holds "
                    f"{effective_sources[reason]} via {reason.value}, needs {required}"
                ),
                role=held,
                required_role=required,
            )

    own_best = _strongest(own_sources.values())
    if owner is not None and role_at_least(own_best, required):
        if owner_role is None:
            return AccessDecision(
                request=request,
                reason=Reason.OWNER_HAS_NO_ROLE,
                detail=(
                    f"agent {principal} is delegated {own_best} on {resource.ref}, "
                    f"but its owner {owner} holds no role there"
                ),
                hint=f"grant {owner} access to {resource.ref}, or remove the agent's grant",
                role=held,
                required_role=required,
            )
        return AccessDecision(
            request=request,
            reason=Reason.AGENT_CEILING,
            detail=(
                f"agent {principal} is delegated {own_best} on {resource.ref}, but its "
                f"owner {owner} holds only {owner_role}; {action} needs {required}"
            ),
            hint=f"grant {owner} {required} on {resource.ref}; an agent never exceeds its owner",
            role=held,
            required_role=required,
        )

    if held is None or not principal.is_signed_in:
        return _not_found_for(principal, action, resource.ref, required)

    return AccessDecision(
        request=request,
        reason=Reason.ROLE_TOO_LOW,
        detail=f"{principal} holds {held} on {resource.ref}; {action} needs {required}",
        hint=f"ask an admin of {resource.ref} for a {required} grant",
        role=held,
        required_role=required,
    )


def require(
    principal: Principal,
    action: str,
    resource: Resource,
    *,
    grants: Iterable[Grant],
    memberships: Iterable[Membership],
    kinds: Optional[KindRegistry] = None,
) -> AccessDecision:
    """``check()`` that raises ``AccessDenied`` / ``AccessUnresolved`` unless allowed."""
    return check(
        principal, action, resource, grants=grants, memberships=memberships, kinds=kinds
    ).raise_if_not_allowed()


__all__ = [
    "check",
    "decide_missing",
    "decide_unresolved",
    "kind_unregistered",
    "require",
    "role_sources",
]

# EOF
