"""Project-type config — `.scitex/dev/config.yaml`.

Tells the auditor which rule families apply to a project (pip, research,
or both). Spec: GITIGNORED/RULES_FOR_SCIENTIFIC_PROJECTS.md §"Project-type
config".
"""

from ._loader import (
    PROJECT_TYPES,
    ProjectConfig,
    detect_project_types,
    load_config,
    write_config,
)

__all__ = [
    "PROJECT_TYPES",
    "ProjectConfig",
    "detect_project_types",
    "load_config",
    "write_config",
]
