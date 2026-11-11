"""Bounded diagnostics for real Git commands in disposable child fixtures.

Only use this helper with owned fixture paths and synthetic command arguments.
It preserves the caller's command, working directory and operation deadline.
"""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from ._release_child_observation import OwnedChildObservation
from ._release_command import _read_bounded

NOTE_PREFIX = "git-fixture-command-timeout: "


def run_fixture_command(command, root, environment, *, timeout):
    """Re-raise the original timeout with bounded owned-child/Trace2 evidence."""
    root = Path(root)
    trace_directory = None
    trace = None
    trace_problem = None
    selected = dict(environment)
    try:
        trace_directory = Path(
            tempfile.mkdtemp(prefix="git-fixture-trace-", dir=root.parent)
        )
        trace = trace_directory / "git.jsonl"
        selected["GIT_TRACE2_EVENT"] = str(trace)
    except OSError as error:
        trace_problem = type(error).__name__
    observation = OwnedChildObservation(root)
    observation.start()
    completed = False
    try:
        result = subprocess.run(
            command,
            env=selected,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True,
        )
        completed = True
        return result
    except subprocess.TimeoutExpired as error:
        observation.close()
        evidence = {
            "scope": "owned synthetic fixture command; not causal attribution",
            "command": command,
            "timeout_seconds": error.timeout,
            "git_trace_tail": _read_bounded(trace, tail=True)
            if trace
            else {
                "state": "unknown",
                "reason": trace_problem,
            },
            "owned_child_observation": observation.snapshot(),
        }
        note = NOTE_PREFIX + json.dumps(evidence, sort_keys=True)
        if hasattr(error, "add_note"):
            error.add_note(note)
        else:
            print(note, file=sys.stderr)
        raise
    finally:
        observation.close()
        if completed and trace_directory is not None:
            try:
                shutil.rmtree(trace_directory)
            except OSError:
                # Diagnostic cleanup cannot change a successful Git result.
                pass
