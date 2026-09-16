#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Resource-kind registration through the ``scitex_dev.access.kinds`` entry point.

A package publishes a callable returning ``list[KindSpec]``::

    [project.entry-points."scitex_dev.access.kinds"]
    scitex-cards = "scitex_cards._access_kinds:provide"

Registration is the single extension point: the command surface and the
decision rules never grow per app.
"""

from __future__ import annotations

import warnings
from dataclasses import replace
from typing import Callable, Iterable, Iterator, Mapping, Optional

from ._errors import AccessConfigError
from ._types import KindSpec

ENTRY_POINT_GROUP = "scitex_dev.access.kinds"

KindProvider = Callable[[], Iterable[KindSpec]]


class KindRegistry(Mapping[str, KindSpec]):
    """Kind name to spec. Two different specs under one name is refused."""

    def __init__(self, specs: Iterable[KindSpec] = ()) -> None:
        by_name: dict[str, KindSpec] = {}
        for spec in specs:
            if not isinstance(spec, KindSpec):
                raise AccessConfigError(
                    f"a kind provider returned {spec!r}; expected KindSpec instances"
                )
            existing = by_name.get(spec.name)
            if existing is not None and existing.to_dict() != spec.to_dict():
                raise AccessConfigError(
                    f"kind {spec.name!r} is registered twice with different rules "
                    f"({existing.package or '?'} and {spec.package or '?'}); "
                    "which one applies would depend on install order"
                )
            by_name[spec.name] = spec
        self._by_name = dict(sorted(by_name.items()))

    def __getitem__(self, name: str) -> KindSpec:
        return self._by_name[name]

    def __iter__(self) -> Iterator[str]:
        return iter(self._by_name)

    def __len__(self) -> int:
        return len(self._by_name)


def _entry_point_providers() -> list[tuple[str, KindProvider]]:
    from importlib.metadata import entry_points

    providers: list[tuple[str, KindProvider]] = []
    for entry_point in entry_points(group=ENTRY_POINT_GROUP):
        try:
            providers.append((entry_point.name, entry_point.load()))
        except Exception as error:  # a broken leaf leaves its kinds unregistered, which fails closed
            warnings.warn(
                f"access kind provider {entry_point.name!r} failed to load: {error!r}; "
                "its kinds are unregistered and every check on them is unresolved",
                RuntimeWarning,
                stacklevel=2,
            )
    return providers


def discover_kinds(
    *,
    extra_providers: Optional[Iterable[KindProvider]] = None,
    include_entry_points: bool = True,
) -> KindRegistry:
    """Every registered kind. ``extra_providers`` / ``include_entry_points`` are the test seams."""
    named: list[tuple[str, KindProvider]] = []
    if include_entry_points:
        named.extend(_entry_point_providers())
    for provider in extra_providers or ():
        named.append((getattr(provider, "__name__", "extra"), provider))

    specs: list[KindSpec] = []
    for name, provider in named:
        try:
            provided = list(provider())
        except Exception as error:  # same fail-closed rule as a load failure
            warnings.warn(
                f"access kind provider {name!r} raised {error!r}; its kinds are unregistered",
                RuntimeWarning,
                stacklevel=2,
            )
            continue
        specs.extend(
            spec if not isinstance(spec, KindSpec) or spec.package else replace(spec, package=name)
            for spec in provided
        )
    return KindRegistry(specs)


__all__ = ["ENTRY_POINT_GROUP", "KindProvider", "KindRegistry", "discover_kinds"]

# EOF
