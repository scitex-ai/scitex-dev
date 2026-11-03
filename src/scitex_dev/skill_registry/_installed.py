"""Adapt installed leaf resources into the existing harness-neutral registry."""

from __future__ import annotations

from ._model import RegistryReport

__all__ = ["discover_installed_skills"]


def discover_installed_skills(*, package: str | None = None) -> RegistryReport:
    """Read enabled installed skill resources with real distribution ownership.

    Duplicate ownership raises SkillRegistryError before selecting any source.
    An empty enabled inventory is a valid empty read result, not evidence of a
    successful installation. Consumers decide their required coverage. No
    consumer modules are imported and no harness directory is changed.
    """
    from .._ecosystem._skills.projection_install import registry_from_listing
    from .._ecosystem._skills.skills import list_skills

    listed = list_skills(package=package)
    if not listed:
        return RegistryReport((), ())
    return registry_from_listing(listed)
