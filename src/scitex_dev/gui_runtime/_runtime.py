#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Package-agnostic lifecycle primitive for `<pkg> gui {open,serve,status,stop}`.

Every SciTeX package that ships a browser-based surface under the
canonical `gui` command group (scitex-dev skill
`_skills/general/03_interface/02_cli/19_gui-commands.md`) needs the
same ~140 lines of state-file bookkeeping: a JSON file recording
{pid, port, host, started_at, ...}, a liveness check that survives
zombies, a self-healing `status()`, and an idempotent `stop()`.
scitex-writer and figrecipe independently reimplemented this exact
pattern — two independent reimplementations of the same primitive is
the signal that it belongs here, generalized, so every consumer
imports instead of reinventing it.

Pure state logic only — no Click, no subprocess spawning, no
`<pkg>`-specific server bootstrap. The consuming package's own
`_cli/commands/gui.py` owns argument parsing, the actual server
start/stop mechanics, and wiring the click group (separation of
concerns: this module never imports anything writer/figrecipe/
scholar/todo-specific).

Usage::

    import os
    from pathlib import Path
    from scitex_dev.gui_runtime import GuiRuntime

    runtime = GuiRuntime(Path("~/.scitex/<pkg>/runtime/gui.json").expanduser())
    runtime.write_state(os.getpid(), port, host, project=str(project_path))
    ...
    runtime.status()   # {"running": True, "url": "...", "pid": ..., ...}
    runtime.stop()     # SIGTERM + poll + clear state; idempotent

Importing this module has no side effects.
"""

from __future__ import annotations

import json
import os
import signal
import time
from pathlib import Path
from typing import Callable, Optional, Union

PathLike = Union[str, Path]
KillFn = Callable[[int, int], None]

__all__ = ["GuiRuntime", "pid_alive"]


def pid_alive(pid: int, *, kill: KillFn = os.kill) -> bool:
    """True when ``pid`` refers to a live process we could signal.

    Three states collapse to False: an invalid pid (``<= 0`` or not an
    ``int``), a pid that no longer exists (``ProcessLookupError``), and
    a zombie — exited but not yet reaped by its parent, which still
    answers signal 0 but is already dead in every sense that matters to
    a GUI-server liveness check. Without the zombie check, ``stop()``
    would poll an exited-but-unreaped server for the full timeout and
    wrongly report ``terminated=False``.

    A pid owned by a different user answers ``PermissionError`` on
    signal 0 — the kernel only raises that for a real target, so such a
    pid counts as alive.

    ``kill`` is an injectable seam (default ``os.kill``) so tests can
    exercise the permission-denied branch with a real hand-rolled fake
    function instead of a mock library (STX-NM policy forbids
    ``unittest.mock``/``monkeypatch``) — a test process cannot portably
    manufacture a real EPERM from the kernel without another uid to
    signal against.
    """
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
        if stat.rpartition(")")[2].split()[0] == "Z":
            return False
    except (OSError, IndexError):
        pass
    return True


class GuiRuntime:
    """Lifecycle primitive for one `<pkg> gui` server instance.

    Fully package-agnostic: the state-file location is supplied by the
    caller — each consuming package resolves its own local-state path
    (its own runtime-path convention, e.g. `~/.scitex/<pkg>/runtime/
    gui.json`) — and any package-specific metadata (writer's
    "project", a future package's "board", ...) travels through
    ``**extra`` on :meth:`write_state` without this module ever naming
    a specific package.
    """

    def __init__(self, state_path: PathLike):
        self._path = Path(state_path)

    @property
    def path(self) -> Path:
        """The state-file path this instance reads/writes."""
        return self._path

    def read_state(self) -> Optional[dict]:
        """Return the persisted state dict, or None when absent/corrupt/malformed."""
        try:
            loaded = json.loads(self._path.read_text())
        except (OSError, ValueError):
            return None
        return loaded if isinstance(loaded, dict) else None

    def write_state(self, pid: int, port: int, host: str, **extra: object) -> Path:
        """Persist the running server's coordinates; returns the state-file path.

        ``extra`` carries any package-specific fields verbatim (e.g.
        ``project=str(project_path)``) — this module doesn't know or
        care what they mean.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        state = {
            "pid": pid,
            "port": port,
            "host": host,
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            **extra,
        }
        self._path.write_text(json.dumps(state, indent=2))
        return self._path

    def clear_state(self) -> None:
        """Remove the state file. Idempotent."""
        try:
            self._path.unlink()
        except OSError:
            pass

    def status(self) -> dict:
        """Report the server's state, self-healing a stale file.

        A state file whose pid is dead (crash, kill -9) or malformed
        (non-integer pid) is removed so the next `open` auto-serves
        instead of pointing the browser at a dead port.
        """
        state = self.read_state()
        if state is None:
            return {"running": False}
        pid = state.get("pid")
        if not isinstance(pid, int) or not pid_alive(pid):
            self.clear_state()
            return {"running": False, "stale_state_cleared": True}
        url = f"http://{state.get('host')}:{state.get('port')}"
        return {"running": True, "url": url, **state}

    def stop(self, timeout: float = 5.0) -> dict:
        """SIGTERM the recorded server and clear the state file. Idempotent."""
        current = self.status()
        if not current.get("running"):
            return {"stopped": False, "running": False}
        pid = current["pid"]
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError as exc:
            return {"stopped": False, "running": True, "pid": pid, "error": str(exc)}
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and pid_alive(pid):
            time.sleep(0.1)
        self.clear_state()
        return {"stopped": True, "pid": pid, "terminated": not pid_alive(pid)}


# EOF
