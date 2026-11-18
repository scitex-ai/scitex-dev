"""Resolve only the contributor dev group, without importing project code."""

from __future__ import annotations

import re

from packaging.requirements import InvalidRequirement, Requirement


def dev_group_requirements(meta: dict) -> list[Requirement] | None:
    """Return applicable dev requirements, or None for a legacy-only project.

    Includes normalize names, reject cycles/invalid reachable entries, and
    stop at 32 levels or 4096 expanded entries. Unrelated group contents are
    not evaluated. Group installation does not activate an extra named dev.
    """
    if "dependency-groups" not in meta:
        return None
    raw = meta["dependency-groups"]
    if not isinstance(raw, dict):
        raise TypeError("dependency-groups must be a table")
    groups = {}
    for name, value in raw.items():
        if not isinstance(name, str) or not re.fullmatch(
            r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?", name
        ):
            raise ValueError("Invalid dependency group name")
        key = re.sub(r"[-_.]+", "-", name).lower()
        if key in groups:
            raise ValueError("Duplicate normalized dependency group name")
        groups[key] = value
    if "dev" not in groups:
        return None
    result = []
    steps = 0

    def visit(name: str, chain: tuple[str, ...]) -> None:
        nonlocal steps
        if name in chain or len(chain) >= 32:
            raise ValueError("Cyclic or over-depth dev group includes")
        if name not in groups or not isinstance(groups[name], list):
            raise ValueError("Missing or non-list dev group include")
        for item in groups[name]:
            steps += 1
            if steps > 4096:
                raise ValueError("Dev group expansion exceeds 4096 entries")
            if isinstance(item, str):
                try:
                    requirement = Requirement(item)
                except InvalidRequirement as error:
                    raise ValueError("Invalid dev group requirement") from error
                try:
                    applicable = (
                        requirement.marker is None
                        or requirement.marker.evaluate({"extra": ""})
                    )
                except (LookupError, ValueError) as error:
                    raise ValueError("Cannot evaluate dev group marker") from error
                if applicable:
                    result.append(requirement)
            elif (
                isinstance(item, dict)
                and set(item) == {"include-group"}
                and isinstance(item["include-group"], str)
            ):
                visit(
                    re.sub(r"[-_.]+", "-", item["include-group"]).lower(),
                    chain + (name,),
                )
            else:
                raise ValueError("Invalid dev group include entry")

    visit("dev", ())
    return result
