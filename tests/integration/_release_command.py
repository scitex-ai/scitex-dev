"""Bounded failure evidence for disposable release-identity commands."""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from ._release_child_observation import OwnedChildObservation

_LIMIT = 8192
_NOTE_PREFIX = "release-command-timeout: "


def _read_bounded(path, *, tail=False):
    """Read bounded data; only regular trace files need a seek to their tail."""
    try:
        with Path(path).open("rb") as stream:
            if tail:
                stream.seek(0, 2)
                stream.seek(max(0, stream.tell() - _LIMIT))
            return stream.read(_LIMIT).decode("utf-8", errors="replace")
    except OSError as error:
        return "unavailable: " + type(error).__name__


def run_release_command(command, root, environment, **options):
    """Keep the original five-second deadline and re-raise its failure."""
    observation = OwnedChildObservation(root)
    observation.start()
    try:
        return subprocess.run(
            command, cwd=root, env=environment, capture_output=True, timeout=5,
            **options,
        )
    except subprocess.TimeoutExpired as error:
        observation.close()
        # Only owned fixture commands and bounded local diagnostics are recorded.
        # Never dump the environment or inspect another process's credentials.
        evidence = {
            "observed_utc": datetime.now(timezone.utc).isoformat(),
            "timeout_seconds": error.timeout,
            "command": command,
            "git_trace_tail": _read_bounded(root.parent / "git-trace.jsonl", tail=True),
            "loadavg": _read_bounded("/proc/loadavg"),
            "io_pressure": _read_bounded("/proc/pressure/io"),
            "memory": _read_bounded("/proc/meminfo"),
            "owned_child_observation": observation.snapshot(),
        }
        note = _NOTE_PREFIX + json.dumps(evidence, sort_keys=True)
        if hasattr(error, "add_note"):
            error.add_note(note)
        else:  # Python < 3.11 has no exception notes.
            print(note, file=sys.stderr)
        raise
    finally:
        observation.close()
