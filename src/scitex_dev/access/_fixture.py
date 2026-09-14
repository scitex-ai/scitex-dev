#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A JSON fixture of kinds, resources, grants and memberships.

v1 has no persistence, so the CLI and the conformance suite both read their
world from this shape::

    {"kinds": [{"name": "demo.doc", "path_prefix": "/users/",
                "actions": {"view": "read", "edit": "write"}}],
     "resources": [{"kind": "demo.doc", "path": "/users/alice/d1",
                    "owner": "user:alice", "visibility": "private",
                    "parent": "demo.project:/users/alice/p1"}],
     "grants": [{"principal": "user:bob", "role": "write",
                 "resource": "demo.doc:/users/alice/d1", "default": false}],
     "memberships": [{"principal": "user:carol", "org": "org:lab", "role": "write"}]}
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional

from ._errors import AccessConfigError
from ._kinds import KindRegistry
from ._types import Grant, KindSpec, Membership, Principal, Resource

_TOP_LEVEL_KEYS = {"kinds", "resources", "grants", "memberships"}


def _field(record: Mapping[str, Any], key: str, where: str) -> Any:
    if key not in record:
        raise AccessConfigError(f"{where} is missing {key!r}: {dict(record)!r}")
    return record[key]


@dataclass(frozen=True)
class AccessFixture:
    kinds: KindRegistry
    resources: tuple[Resource, ...]
    grants: tuple[Grant, ...]
    memberships: tuple[Membership, ...]

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AccessFixture":
        unknown = set(payload) - _TOP_LEVEL_KEYS
        if unknown:
            raise AccessConfigError(
                f"unknown fixture key(s) {sorted(unknown)}; expected {sorted(_TOP_LEVEL_KEYS)}"
            )
        kinds = KindRegistry(
            KindSpec(
                name=_field(row, "name", "kind"),
                path_prefix=_field(row, "path_prefix", "kind"),
                actions=_field(row, "actions", "kind"),
                package=row.get("package", "fixture"),
            )
            for row in payload.get("kinds", ())
        )
        resources = tuple(
            Resource(
                kind=_field(row, "kind", "resource"),
                path=_field(row, "path", "resource"),
                owner=Principal.parse(_field(row, "owner", "resource")),
                visibility=row.get("visibility", "private"),
                parent=row.get("parent"),
            )
            for row in payload.get("resources", ())
        )
        grants = tuple(
            Grant(
                principal=Principal.parse(_field(row, "principal", "grant")),
                role=_field(row, "role", "grant"),
                target=_field(row, "resource", "grant"),
                default=bool(row.get("default", False)),
            )
            for row in payload.get("grants", ())
        )
        memberships = tuple(
            Membership(
                principal=Principal.parse(_field(row, "principal", "membership")),
                org=Principal.parse(_field(row, "org", "membership")),
                role=_field(row, "role", "membership"),
            )
            for row in payload.get("memberships", ())
        )
        return cls(kinds=kinds, resources=resources, grants=grants, memberships=memberships)

    @classmethod
    def load(cls, path: Path) -> "AccessFixture":
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise AccessConfigError(f"cannot read access fixture {path}: {error}") from error
        if not isinstance(payload, dict):
            raise AccessConfigError(f"access fixture {path} must hold a JSON object")
        return cls.from_dict(payload)

    def find(self, ref: str) -> Optional[Resource]:
        return next((resource for resource in self.resources if resource.ref == ref), None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kinds": [spec.to_dict() for spec in self.kinds.values()],
            "resources": [
                {
                    "kind": resource.kind,
                    "path": resource.path,
                    "owner": str(resource.owner),
                    "visibility": resource.visibility,
                    "parent": resource.parent,
                }
                for resource in self.resources
            ],
            "grants": [
                {
                    "principal": str(grant.principal),
                    "role": grant.role,
                    "resource": grant.target,
                    "default": grant.default,
                }
                for grant in self.grants
            ],
            "memberships": [
                {
                    "principal": str(membership.principal),
                    "org": str(membership.org),
                    "role": membership.role,
                }
                for membership in self.memberships
            ],
        }


__all__ = ["AccessFixture"]

# EOF
