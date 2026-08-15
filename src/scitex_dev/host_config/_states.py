#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/host_config/_states.py
"""The evaluation vocabulary, in one place both halves can import.

Extracted 2026-08-15 so `_evaluate.py` and `__init__.py` share these
constants without either importing the other. A shared vocabulary defined in
the module that also consumes it is how a circular import starts.
"""

from __future__ import annotations

from typing import Final

#: File present, content byte-identical, mode as declared.
STATE_OK: Final[str] = "ok"
#: No file. Converging this is safe -- nothing is being overwritten.
STATE_ABSENT: Final[str] = "absent"
#: The file exists and differs, OR could not be read/stat'd. Something
#: changed it, or we do not know -- either way it is reported, never
#: silently corrected.
STATE_DRIFT: Final[str] = "drift"
#: ``spec.hosts`` excludes this host.
STATE_NOT_APPLICABLE: Final[str] = "not_applicable"
#: The file could not do its job: its reader is not installed, or its
#: filesystem is RAM-backed so a reboot erases it.
STATE_PRECONDITION_UNMET: Final[str] = "precondition_unmet"

__all__ = [
    "STATE_ABSENT",
    "STATE_DRIFT",
    "STATE_NOT_APPLICABLE",
    "STATE_OK",
    "STATE_PRECONDITION_UNMET",
]

# EOF
