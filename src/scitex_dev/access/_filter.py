#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``accessible()`` — which resources of a kind may this principal act on?

Returns a backend-neutral ``AccessFilter`` that an adapter translates once
(Django ``Q``, a store ``either/is_in``), so a list view filters rows with the
same rules ``check()`` applies to one row. ``AccessFilter.matches`` is the
in-memory evaluator the equivalence suite compares both against.

A resource matches when::

    (public and resource is public)
    or (grant_match(self) and (ceiling is None or grant_match(ceiling)))

    grant_match(f) = resource.owner in f.owners
                     or resource.ref in f.resources
                     or resource.parent in f.parents
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional

from ..scope import Role
from ._errors import AccessUnresolved
from ._kinds import KindRegistry, discover_kinds
from ._types import (
    Grant,
    Membership,
    Principal,
    Resource,
    role_at_least,
    weaker_role,
)


@dataclass(frozen=True)
class AccessFilter:
    kind: str
    action: str
    required_role: Role
    owners: frozenset[str]
    resources: frozenset[str]
    parents: frozenset[str]
    public: bool
    #: For an agent: its owner's filter, which every non-public match must also satisfy.
    ceiling: Optional["AccessFilter"] = None

    def matches_grants(self, resource: Resource) -> bool:
        return (
            str(resource.owner) in self.owners
            or resource.ref in self.resources
            or (resource.parent is not None and resource.parent in self.parents)
        )

    def matches(self, resource: Resource) -> bool:
        if resource.kind != self.kind:
            return False
        if self.public and resource.is_public:
            return True
        if not self.matches_grants(resource):
            return False
        return self.ceiling is None or self.ceiling.matches_grants(resource)

    @property
    def is_empty(self) -> bool:
        return not (self.owners or self.resources or self.parents or self.public)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "action": self.action,
            "required_role": self.required_role,
            "owners": sorted(self.owners),
            "resources": sorted(self.resources),
            "parents": sorted(self.parents),
            "public": self.public,
            "ceiling": None if self.ceiling is None else self.ceiling.to_dict(),
        }


def select(access_filter: AccessFilter, resources: Iterable[Resource]) -> list[Resource]:
    """The in-memory evaluator: the resources a filter admits, in input order."""
    return [resource for resource in resources if access_filter.matches(resource)]


def _grant_sets(
    principal: Principal,
    kind: str,
    required: Role,
    grants: tuple[Grant, ...],
    memberships: tuple[Membership, ...],
) -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
    owners: set[str] = set()
    resources: set[str] = set()
    parents: set[str] = set()
    if not principal.is_signed_in:
        return frozenset(), frozenset(), frozenset()

    if principal.kind in ("user", "org"):
        owners.add(str(principal))

    # Each acting identity pairs a principal with the ceiling its path to the grant imposes.
    acting: list[tuple[Principal, Optional[Role]]] = [(principal, None)]
    for membership in memberships:
        if membership.principal != principal:
            continue
        acting.append((membership.org, membership.role))
        if role_at_least(membership.role, required):
            owners.add(str(membership.org))

    for grant in grants:
        for identity, cap in acting:
            if grant.principal != identity:
                continue
            role = grant.role if cap is None else weaker_role(grant.role, cap)
            if not role_at_least(role, required):
                continue
            if grant.default:
                parents.add(grant.target)
            elif grant.target.startswith(f"{kind}:"):
                resources.add(grant.target)
    return frozenset(owners), frozenset(resources), frozenset(parents)


def accessible(
    principal: Principal,
    action: str,
    kind: str,
    *,
    grants: Iterable[Grant],
    memberships: Iterable[Membership],
    kinds: Optional[KindRegistry] = None,
) -> AccessFilter:
    grants = tuple(grants)
    memberships = tuple(memberships)
    registry = kinds if kinds is not None else discover_kinds()
    spec = registry.get(kind)
    if spec is None:
        raise AccessUnresolved(
            f"kind-unregistered: no installed package registers the resource kind {kind!r}"
        )
    required = spec.required_role(action)
    public = required == "read"

    owners, resources, parents = _grant_sets(principal, kind, required, grants, memberships)
    owner = principal.agent_owner
    ceiling: Optional[AccessFilter] = None
    if owner is not None:
        ceiling_owners, ceiling_resources, ceiling_parents = _grant_sets(
            owner, kind, required, grants, memberships
        )
        ceiling = AccessFilter(
            kind=kind,
            action=action,
            required_role=required,
            owners=ceiling_owners,
            resources=ceiling_resources,
            parents=ceiling_parents,
            public=False,
        )
    return AccessFilter(
        kind=kind,
        action=action,
        required_role=required,
        owners=owners,
        resources=resources,
        parents=parents,
        public=public,
        ceiling=ceiling,
    )


__all__ = ["AccessFilter", "accessible", "select"]

# EOF
