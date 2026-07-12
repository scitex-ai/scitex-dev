#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scitex_dev.gui_runtime — shared lifecycle primitive for `<pkg> gui {open,serve,status,stop}`.

Every SciTeX package's `gui serve/open/status/stop` group needs the
same ~140-line pattern: state-file bookkeeping, pid liveness that
survives zombies, and an idempotent stop. Two independent
reimplementations (scitex-writer, figrecipe) were the exact signal
that this belongs here as a shared primitive — see the doctrine at
`_skills/general/03_interface/02_cli/19_gui-commands.md`.

Public surface
--------------
* :class:`GuiRuntime` — one instance per `<pkg> gui` state file. Owns
  `write_state` / `read_state` / `clear_state` / `status` / `stop`.
* :func:`pid_alive` — the standalone liveness check (invalid / gone /
  zombie / owned-by-another-user pid handling), reusable on its own.

Stable import path for consumers::

    from scitex_dev.gui_runtime import GuiRuntime, pid_alive

Importing this package has no side effects.
"""

from __future__ import annotations

from ._runtime import GuiRuntime, pid_alive

__all__ = ["GuiRuntime", "pid_alive"]


# EOF
