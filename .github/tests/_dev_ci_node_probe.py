"""Run the CI contract with its original deadline and child-only evidence."""

import json
import subprocess
import threading
import time
from pathlib import Path


def _child_snapshot(pid):
    """Read bounded Linux process fields, never argv, environment or other PIDs."""
    root = Path("/proc") / str(pid)
    result = {"pid": pid, "scope": "direct child only; descendants not inspected"}
    for name in ("stat", "wchan", "syscall"):
        try:
            with (root / name).open() as stream:
                value = stream.read(4096)
            if name == "stat":
                fields = value.rsplit(")", 1)[1].split()
                result.update(
                    state=fields[0],
                    parent_pid=int(fields[1]),
                    user_ticks=int(fields[11]),
                    system_ticks=int(fields[12]),
                    threads=int(fields[17]),
                    start_ticks=int(fields[19]),
                )
            else:
                # The syscall number suffices; do not log memory addresses.
                result[name] = value.split()[0] if value.split() else ""
        except (OSError, IndexError, ValueError) as error:
            result[name + "_unavailable"] = type(error).__name__
    return result


def run_node(source, *, timeout=4):
    """Preserve Node results and TimeoutExpired; never retry or extend its budget.

    A daemon observer samples at three quarters of the deadline. The timeout
    path never waits for that observer or reads procfs: unavailable or incomplete
    evidence is explicit. Sampling is scheduled before the deadline; timestamps show any delay.
    It is not a root-cause verdict.
    """
    command = ["node", "-"]
    done = threading.Event()
    evidence = {}
    with subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ) as child:
        started = time.monotonic()

        def observe():
            if done.wait(timeout * 0.75):
                return
            sampled_at = time.monotonic() - started
            snapshot = _child_snapshot(child.pid)
            evidence["sample"] = {
                "elapsed_seconds": sampled_at,
                "completed_elapsed_seconds": time.monotonic() - started,
                **snapshot,
            }

        observer = threading.Thread(target=observe, daemon=True)
        try:
            observer.start()
            remaining = max(0, timeout - (time.monotonic() - started))
            stdout, stderr = child.communicate(source, timeout=remaining)
        except subprocess.TimeoutExpired as error:
            done.set()
            # Preserve the requested budget in the exception, while actual
            # communication has no more than that budget after Popen returns.
            error.timeout = timeout
            error.add_note(
                json.dumps(
                    {
                        "requested_timeout_seconds": timeout,
                        "elapsed_seconds": time.monotonic() - started,
                        "child_pid": child.pid,
                        "stdout_bytes": len(error.output or b""),
                        "stderr_bytes": len(error.stderr or b""),
                        "output_limit": "captured bytes only; zero does not prove no output was emitted",
                        "sample": evidence.get("sample"),
                        "sample_limit": "scheduled before deadline; inspect timestamps; may be absent; no descendants",
                    },
                    sort_keys=True,
                )
            )
            child.kill()
            child.wait()
            raise
        except BaseException:
            child.kill()
            raise
        finally:
            done.set()
    return subprocess.CompletedProcess(command, child.returncode, stdout, stderr)
