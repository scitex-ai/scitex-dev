#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Active-project selection primitive for the SciTeX ecosystem.

The project selector must work at CUI level for every package, so the
selection state lives here in scitex-dev — not in the hub, not in a leaf.
The SDK (`scitex_sdk.project`) and every leaf CLI resolve through
:func:`resolve_project`; the hub's web selector writes the same
``$SCITEX_PROJECT`` contract from the server side.

Precedence (first hit wins):
  1. explicit argument (``--project`` / API ``explicit=``)
  2. ``$SCITEX_PROJECT`` environment variable
  3. ``~/.scitex/scitex-dev/active_project`` selection file (user state,
     never git-tracked — the managed-``~/.scitex`` block default-denies it)

Accepted refs: ``owner/name`` (validated by the scope contract) or the
literal ``all`` for user-level scope. Anything else is rejected loudly —
a caller who can name a project can name it exactly.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final, Optional

ACTIVE_PROJECT_ENV: Final[str] = "SCITEX_PROJECT"

#: Literal ref selecting user-level scope (all projects).
ALL_PROJECTS: Final[str] = "all"

#: File holding the persisted selection. Platform state owned by scitex-dev
#: under the ``~/.scitex/<pkg>/`` contract; user state, never tracked.
ACTIVE_PROJECT_FILENAME: Final[str] = "active_project"


def _dotscitex_dev_dir() -> Path:
    return Path(os.path.expanduser("~")) / ".scitex" / "scitex-dev"


def active_project_file() -> Path:
    """Path of the persisted selection file (created on ``use``)."""
    return _dotscitex_dev_dir() / ACTIVE_PROJECT_FILENAME


def validate_ref(ref: str) -> str:
    """Validate a project ref; return it unchanged or raise ValueError."""
    from scitex_dev.scope._types import _check_id

    if ref == ALL_PROJECTS:
        return ref
    if "/" not in ref:
        raise ValueError(
            f"unusable project ref {ref!r}: expected 'owner/name' or "
            f"'{ALL_PROJECTS}'. A bare name hides the owner; name it exactly."
        )
    owner, name = ref.split("/", 1)
    _check_id("project owner", owner)
    _check_id("project name", name)
    return ref


def resolve_project(explicit: Optional[str] = None) -> Optional[str]:
    """Resolve the active project ref, or None when nothing is selected."""
    if explicit is not None:
        return validate_ref(explicit.strip())
    env = os.environ.get(ACTIVE_PROJECT_ENV, "").strip()
    if env:
        return validate_ref(env)
    try:
        stored = active_project_file().read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return None
    if not stored:
        return None
    return validate_ref(stored)


def set_active_project(ref: str) -> str:
    """Persist ``ref`` as the active project; returns the validated ref."""
    validated = validate_ref(ref.strip())
    path = active_project_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(validated + "\n", encoding="utf-8")
    return validated


def clear_active_project() -> bool:
    """Remove the persisted selection; True when something was cleared."""
    try:
        active_project_file().unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError as e:
        raise OSError(f"cannot clear active project: {e}") from e
