#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One small, hand-built world shared by the access tests. Plain values, no mocks."""

from __future__ import annotations

from scitex_dev.access import (
    AccessFixture,
    Grant,
    KindRegistry,
    KindSpec,
    Membership,
    Principal,
    Resource,
)

ACTIONS = {"view": "read", "edit": "write", "share": "admin"}
DOC = KindSpec(name="demo.doc", path_prefix="/", actions=ACTIONS, package="tests")
PROJECT = KindSpec(name="demo.project", path_prefix="/", actions=ACTIONS, package="tests")
KINDS = KindRegistry([DOC, PROJECT])

ALICE_PROJECT_REF = "demo.project:/users/alice/p1"

ALICE_DOC = Resource(
    kind="demo.doc",
    path="/users/alice/d1",
    owner=Principal.parse("user:alice"),
    parent=ALICE_PROJECT_REF,
)
LAB_DOC = Resource(kind="demo.doc", path="/orgs/lab/d2", owner=Principal.parse("org:lab"))
PUBLIC_DOC = Resource(
    kind="demo.doc",
    path="/users/alice/pub",
    owner=Principal.parse("user:alice"),
    visibility="public",
)
GHOST = Resource(kind="ghost.thing", path="/users/alice/g1", owner=Principal.parse("user:alice"))

GRANTS = (
    Grant(Principal.parse("user:bob"), "write", ALICE_DOC.ref),
    Grant(Principal.parse("user:frank"), "read", ALICE_DOC.ref),
    Grant(Principal.parse("user:dave"), "write", ALICE_PROJECT_REF, default=True),
    Grant(Principal.parse("org:reviewers"), "admin", ALICE_DOC.ref),
    Grant(Principal.parse("agent:alice/bot"), "write", ALICE_DOC.ref),
    Grant(Principal.parse("agent:bob/helper"), "admin", ALICE_DOC.ref),
    Grant(Principal.parse("agent:erin/bot"), "write", ALICE_DOC.ref),
)

MEMBERSHIPS = (
    Membership(Principal.parse("user:carol"), Principal.parse("org:lab"), "write"),
    Membership(Principal.parse("user:rita"), Principal.parse("org:reviewers"), "read"),
    Membership(Principal.parse("user:staff"), Principal.parse("org:scitex-staff"), "admin"),
)

FIXTURE = AccessFixture(
    kinds=KINDS,
    resources=(ALICE_DOC, LAB_DOC, PUBLIC_DOC),
    grants=GRANTS,
    memberships=MEMBERSHIPS,
)

# EOF
