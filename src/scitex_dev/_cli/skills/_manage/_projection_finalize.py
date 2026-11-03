"""Compatibility imports for the shared skill projection implementation."""

from ...._ecosystem._skills.projection_install import (
    ProjectionFinalizeResult,
    finalize_projection,
    install_result_dict,
    registry_from_listing,
    registry_from_projection,
)

__all__ = [
    "ProjectionFinalizeResult",
    "finalize_projection",
    "install_result_dict",
    "registry_from_listing",
    "registry_from_projection",
]
