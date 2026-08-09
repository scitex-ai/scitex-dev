#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/ci/_gh.py
"""The only place this package shells out."""

from __future__ import annotations

import json
import subprocess
from typing import Sequence

__all__ = ["gh_json"]


def gh_json(
    args: Sequence[str], timeout: int = 60
) -> "tuple[object | None, str | None]":
    """Run a gh command returning JSON. ``(value, error)`` — never raises.

    An unreachable API is a legitimate CANNOT_DETERMINE input, so the
    failure is returned as data rather than thrown; a traceback here would
    be indistinguishable from a real verdict to a shell caller.
    """
    try:
        completed = subprocess.run(
            list(args), capture_output=True, text=True, timeout=timeout
        )
    except FileNotFoundError:
        return None, "gh is not installed or not on PATH"
    except subprocess.TimeoutExpired:
        return None, f"gh timed out after {timeout}s: {' '.join(args)}"
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip().splitlines()
        first = detail[0] if detail else f"exit {completed.returncode}"
        return None, f"gh failed: {first}"
    try:
        return json.loads(completed.stdout or "null"), None
    except json.JSONDecodeError as exc:
        return None, f"gh returned unparseable JSON: {exc}"


# EOF
