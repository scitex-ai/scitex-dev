"""Engine package for ``scitex-dev registry-normalize`` (and the PS-181
audit rule, which shares the same detection logic via ``scan.py``).

Public surface:

* ``scan_pkg_dir(pkg_dir) -> list[DriftItem]`` — drift in one
  ``~/.scitex/<pkg>/`` directory.
* ``scan_registry(scitex_dir) -> dict[str, list[DriftItem]]`` — drift
  across every package under ``$SCITEX_DIR``.
* ``build_plan(pkg_dir) -> list[MoveResult]`` — the moves drift implies
  (pure planning, no disk writes).
* ``run_registry_normalize(pkg, *, confirm, scitex_dir) -> NormalizeReport``
  — the CLI's entry point (dry-run unless ``confirm=True``).
"""

from .normalize import (
    MoveResult,
    NormalizeReport,
    build_plan,
    execute_plan,
    run_registry_normalize,
)
from .scan import MOVABLE_KINDS, DriftItem, scan_pkg_dir, scan_registry

__all__ = [
    "MOVABLE_KINDS",
    "DriftItem",
    "MoveResult",
    "NormalizeReport",
    "build_plan",
    "execute_plan",
    "run_registry_normalize",
    "scan_pkg_dir",
    "scan_registry",
]
