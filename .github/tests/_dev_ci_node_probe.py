"""Run CI with its original deadline, child evidence and host IO context."""

import json
import math
import subprocess
import threading
import time
from pathlib import Path


def _numeric_proc_snapshot(name, value):
    """Return only documented nonnegative counters, never arbitrary procfs text."""
    try:
        if name == "schedstat":
            names = ("runtime_ns", "runqueue_wait_ns", "timeslices")
            values = value.split()
            if len(values) != len(names):
                raise ValueError
            result = dict(zip(names, map(int, values)))
        elif name == "io":
            names = {
                "rchar",
                "wchar",
                "syscr",
                "syscw",
                "read_bytes",
                "write_bytes",
                "cancelled_write_bytes",
            }
            result = {}
            for line in value.splitlines():
                key, separator, number = line.partition(":")
                if separator and key in names:
                    if key in result:
                        raise ValueError
                    result[key] = int(number)
            if set(result) != names:
                raise ValueError
        else:
            raise ValueError
        if any(number < 0 for number in result.values()):
            raise ValueError
        return result
    except ValueError:
        # Do not copy malformed fields into a diagnostic exception.
        raise ValueError("procfs counters unavailable") from None


def _child_snapshot(pid):
    """Read bounded Linux process fields, never argv, environment or other PIDs."""
    root = Path("/proc") / str(pid)
    result = {"pid": pid, "scope": "direct child only; descendants not inspected"}
    for name in ("stat", "wchan", "syscall", "schedstat", "io"):
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
            elif name in ("schedstat", "io"):
                result[name] = _numeric_proc_snapshot(name, value)
            else:
                # The syscall number suffices; do not log memory addresses.
                result[name] = value.split()[0] if value.split() else ""
        except (OSError, IndexError, ValueError) as error:
            result[name + "_unavailable"] = type(error).__name__
    result["counter_limit"] = (
        "cumulative direct-child counters; reads are not atomic; "
        "no baseline delta, descendants, paths or root-cause verdict"
    )
    return result



def _numeric_io_pressure(value):
    """Parse only numeric IO PSI rows; averages are percent, totals microseconds.

    Format: https://docs.kernel.org/accounting/psi.html
    Unknown fields are never copied into diagnostic exceptions.
    """
    expected = {"avg10", "avg60", "avg300", "total"}
    result = {}
    try:
        for line in value.splitlines():
            fields = line.split()
            if not fields or fields[0] not in {"some", "full"}:
                continue
            kind = fields[0]
            if kind in result:
                raise ValueError
            row = {}
            for field in fields[1:]:
                key, separator, number = field.partition("=")
                if key not in expected:
                    continue
                if not separator or key in row:
                    raise ValueError
                if key == "total":
                    row[key] = int(number)
                    if row[key] < 0:
                        raise ValueError
                else:
                    row[key] = float(number)
                    if not math.isfinite(row[key]) or not 0 <= row[key] <= 100:
                        raise ValueError
            if set(row) != expected:
                raise ValueError
            result[kind] = row
        if set(result) != {"some", "full"}:
            raise ValueError
        return result
    except ValueError:
        raise ValueError("IO pressure counters unavailable") from None


def _host_io_pressure_snapshot(path=Path("/proc/pressure/io")):
    """Read bounded, host-wide pressure context, without causal attribution."""
    result = {
        "scope": "host-wide IO PSI; not per-child or a root-cause verdict",
        "units": "avg10/avg60/avg300 percent; cumulative total microseconds",
    }
    try:
        with path.open(encoding="ascii") as stream:
            value = stream.read(4097)
        if len(value) > 4096:
            raise ValueError("pressure sample exceeds bound")
        result["counters"] = _numeric_io_pressure(value)
    except (OSError, ValueError) as error:
        result["unavailable"] = type(error).__name__
    return result

def run_node(source, *, timeout=4):
    """Preserve Node results and TimeoutExpired; never retry or extend its budget.

    A daemon observer samples at three quarters of the deadline. The timeout
    path never waits for that observer or reads procfs: unavailable or incomplete
    evidence is explicit. Sampling is scheduled before the deadline; timestamps show any delay.
    Host IO pressure is separate context, not per-child evidence or a cause.
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
            host_io_pressure = _host_io_pressure_snapshot()
            evidence["sample"] = {
                "elapsed_seconds": sampled_at,
                "completed_elapsed_seconds": time.monotonic() - started,
                **snapshot,
                "host_io_pressure": host_io_pressure,
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
