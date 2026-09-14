#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Conformance suite: a backend's ``accessible()`` translation must agree with ``check()``.

An adopter (the hub's Django queryset, a store query) supplies a selector that
turns an ``AccessFilter`` into the refs its backend returns for a fixture::

    from scitex_dev.access.testing import assert_equivalent

    def select_with_django(access_filter, fixture):
        load_into_test_db(fixture)          # adopter-owned, cache by fixture
        return {row.ref for row in Doc.objects.filter(to_q(access_filter))}

    def test_queryset_matches_check():
        assert_equivalent(select_with_django)

Every (principal, action, resource) in each random fixture is decided by
``check()``; the selector must return exactly the allowed resources. No pytest
import here, so the module is usable from any runner.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable, Iterable, Optional

from ._check import check
from ._filter import AccessFilter, accessible, select
from ._fixture import AccessFixture
from ._kinds import KindRegistry
from ._types import ANONYMOUS, ROLE_ORDER, Grant, KindSpec, Membership, Principal, Resource

DOC_KIND = KindSpec(
    name="conformance.doc",
    path_prefix="/",
    actions={"view": "read", "edit": "write", "share": "admin"},
    package="scitex-dev",
)
FOLDER_KIND = KindSpec(
    name="conformance.folder",
    path_prefix="/",
    actions={"view": "read", "edit": "write", "share": "admin"},
    package="scitex-dev",
)

Selector = Callable[[AccessFilter, AccessFixture], Iterable[str]]


@dataclass(frozen=True)
class Mismatch:
    seed: Optional[int]
    principal: str
    action: str
    resource: str
    check_allows: bool
    selected: bool

    def __str__(self) -> str:
        side = "check allows but the selector omitted" if self.check_allows else "the selector returned but check denies"
        return f"seed={self.seed} {self.principal} {self.action} {self.resource}: {side} it"


def select_in_memory(access_filter: AccessFilter, fixture: AccessFixture) -> set[str]:
    """The reference selector: ``AccessFilter.matches`` over the fixture's resources."""
    return {resource.ref for resource in select(access_filter, fixture.resources)}


def random_fixture(
    seed: int,
    *,
    users: int = 4,
    orgs: int = 2,
    agents_per_user: int = 1,
    folders: int = 3,
    docs: int = 10,
    grants: int = 14,
    memberships: int = 5,
) -> AccessFixture:
    rng = random.Random(seed)
    user_principals = [Principal("user", f"u{index}") for index in range(users)]
    org_principals = [Principal("org", f"o{index}") for index in range(orgs)]
    agent_principals = [
        Principal("agent", f"{user.id}/a{index}")
        for user in user_principals
        for index in range(agents_per_user)
    ]
    owners = user_principals + org_principals
    visibilities = ("private", "private", "public")

    folder_resources = [
        Resource(
            kind=FOLDER_KIND.name,
            path=f"/f{index}",
            owner=rng.choice(owners),
            visibility=rng.choice(visibilities),
        )
        for index in range(folders)
    ]
    doc_resources = [
        Resource(
            kind=DOC_KIND.name,
            path=f"/d{index}",
            owner=rng.choice(owners),
            visibility=rng.choice(visibilities),
            parent=rng.choice([None, *(folder.ref for folder in folder_resources)]),
        )
        for index in range(docs)
    ]

    grantees = user_principals + org_principals + agent_principals
    targets = folder_resources + doc_resources
    grant_values = []
    for _ in range(grants):
        target = rng.choice(targets)
        grant_values.append(
            Grant(
                principal=rng.choice(grantees),
                role=rng.choice(ROLE_ORDER),
                target=target.ref,
                default=target.kind == FOLDER_KIND.name and rng.random() < 0.8,
            )
        )

    members = user_principals + agent_principals
    membership_values = [
        Membership(
            principal=rng.choice(members),
            org=rng.choice(org_principals),
            role=rng.choice(ROLE_ORDER),
        )
        for _ in range(memberships)
    ] if org_principals else []

    return AccessFixture(
        kinds=KindRegistry([DOC_KIND, FOLDER_KIND]),
        resources=tuple(folder_resources + doc_resources),
        grants=tuple(grant_values),
        memberships=tuple(membership_values),
    )


def askers_of(fixture: AccessFixture) -> list[Principal]:
    """Every principal the fixture mentions, each agent's owner, and anonymous."""
    seen: dict[str, Principal] = {}
    candidates: list[Principal] = [ANONYMOUS]
    candidates += [resource.owner for resource in fixture.resources]
    candidates += [grant.principal for grant in fixture.grants]
    candidates += [membership.principal for membership in fixture.memberships]
    for principal in candidates:
        seen.setdefault(str(principal), principal)
        if principal.agent_owner is not None:
            seen.setdefault(str(principal.agent_owner), principal.agent_owner)
    return [seen[key] for key in sorted(seen)]


def find_mismatches(
    fixture: AccessFixture,
    selector: Selector = select_in_memory,
    *,
    seed: Optional[int] = None,
) -> list[Mismatch]:
    mismatches: list[Mismatch] = []
    for kind in fixture.kinds.values():
        kind_resources = [resource for resource in fixture.resources if resource.kind == kind.name]
        for principal in askers_of(fixture):
            for action in kind.actions:
                access_filter = accessible(
                    principal,
                    action,
                    kind.name,
                    grants=fixture.grants,
                    memberships=fixture.memberships,
                    kinds=fixture.kinds,
                )
                selected = set(selector(access_filter, fixture))
                for resource in kind_resources:
                    allowed = check(
                        principal,
                        action,
                        resource,
                        grants=fixture.grants,
                        memberships=fixture.memberships,
                        kinds=fixture.kinds,
                    ).is_allowed
                    if allowed != (resource.ref in selected):
                        mismatches.append(
                            Mismatch(
                                seed=seed,
                                principal=str(principal),
                                action=action,
                                resource=resource.ref,
                                check_allows=allowed,
                                selected=resource.ref in selected,
                            )
                        )
    return mismatches


def assert_equivalent(selector: Selector = select_in_memory, *, seeds: Iterable[int] = range(40)) -> None:
    """Raise ``AssertionError`` naming the first mismatches across the seeded fixtures."""
    mismatches: list[Mismatch] = []
    for seed in seeds:
        mismatches.extend(find_mismatches(random_fixture(seed), selector, seed=seed))
    if mismatches:
        listed = "\n".join(str(mismatch) for mismatch in mismatches[:10])
        raise AssertionError(
            f"{len(mismatches)} access mismatch(es) between check() and the selector:\n{listed}"
        )


__all__ = [
    "DOC_KIND",
    "FOLDER_KIND",
    "Mismatch",
    "Selector",
    "askers_of",
    "assert_equivalent",
    "find_mismatches",
    "random_fixture",
    "select_in_memory",
]

# EOF
