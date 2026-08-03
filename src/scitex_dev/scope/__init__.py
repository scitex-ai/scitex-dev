# -*- coding: utf-8 -*-
"""The scope and identity contract every SciTeX app conforms to.

scitex-dev defines the shape; Django, Gitea, the CLI and every leaf are
adapters. See ``_types`` for who is authoritative over what, and why the test
is "who enforces" rather than "who stores".
"""

from ._types import (
    AppSpec,
    DataLivesAt,
    Member,
    Principal,
    PrincipalKind,
    Project,
    Role,
    Scope,
    ViewKind,
    Visibility,
    effective_role,
)

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
