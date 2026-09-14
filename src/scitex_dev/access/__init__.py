# -*- coding: utf-8 -*-
"""``scitex_dev.access`` — the one access primitive every SciTeX app asks.

    check(principal, action, resource, *, grants, memberships) -> AccessDecision
    accessible(principal, action, kind, *, grants, memberships) -> AccessFilter

Pure Python, no Django and no database: adapters load grants and translate the
``AccessFilter``; ``scitex_dev.access.testing`` proves a translation agrees with
``check()``. Roles and visibility are ``scitex_dev.scope``'s. Every answer is an
``AccessDecision`` (spec ``scitex-access/1``) wrapping ``scitex_dev.status``.
See docs/adr/0014-access-primitive-v1.md.
"""

from ._check import (
    check,
    decide_missing,
    decide_unresolved,
    kind_unregistered,
    require,
    role_sources,
)
from ._decision import CHECK_NAME, AccessDecision
from ._errors import AccessConfigError, AccessDenied, AccessUnresolved
from ._filter import AccessFilter, accessible, select
from ._fixture import AccessFixture
from ._kinds import ENTRY_POINT_GROUP, KindProvider, KindRegistry, discover_kinds
from ._reasons import (
    SPEC,
    AuditReason,
    DecisionKind,
    Reason,
    load_decision_schema,
    load_reasons_spec,
)
from ._types import (
    ANONYMOUS,
    ROLE_ORDER,
    AccessRequest,
    Grant,
    KindSpec,
    Membership,
    Principal,
    PrincipalKind,
    Resource,
    resource_ref,
    split_resource_ref,
)

__all__ = [
    "ANONYMOUS",
    "CHECK_NAME",
    "ENTRY_POINT_GROUP",
    "ROLE_ORDER",
    "SPEC",
    "AccessConfigError",
    "AccessDecision",
    "AccessDenied",
    "AccessFilter",
    "AccessFixture",
    "AccessRequest",
    "AccessUnresolved",
    "AuditReason",
    "DecisionKind",
    "Grant",
    "KindProvider",
    "KindRegistry",
    "KindSpec",
    "Membership",
    "Principal",
    "PrincipalKind",
    "Reason",
    "Resource",
    "accessible",
    "check",
    "decide_missing",
    "decide_unresolved",
    "discover_kinds",
    "kind_unregistered",
    "load_decision_schema",
    "load_reasons_spec",
    "require",
    "resource_ref",
    "role_sources",
    "select",
    "split_resource_ref",
]
