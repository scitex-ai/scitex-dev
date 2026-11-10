"""Read-only candidate-child samples in an owned test fixture."""

import os
import sys
import threading
import time
from pathlib import Path


def _unknown(reason):
    return {"state": "unknown", "reason": reason}


def _read(path, limit=8192):
    with path.open("rb") as stream:
        body = stream.read(limit + 1)
    if len(body) > limit:
        raise ValueError("observation exceeds read bound")
    return body.decode("ascii").strip()


class OwnedChildObservation:
    """Samples are fixture-scoped observations, not a diagnosis of the delay."""

    def __init__(self, root, proc_root=Path("/proc")):
        self._proc = proc_root
        self._stop = threading.Event()
        self._thread = None
        self._started = False
        self._samples = []
        self._reason = None
        self._began = time.monotonic()
        self._baseline = set()
        try:
            if not sys.platform.startswith("linux"):
                raise ValueError("Linux proc observations unavailable")
            self._uid = os.getuid()
            self._parent = os.getpid()
            self._children_file = proc_root / str(self._parent) / "task" / str(
                threading.get_native_id()
            ) / "children"
            info = root.stat()
            if info.st_uid != self._uid:
                raise ValueError("fixture directory is not owned")
            self._fixture = (info.st_dev, info.st_ino)
            self._fixture_directory = root
            self._baseline = self._children()
            self._ticks = os.sysconf("SC_CLK_TCK")
        except (OSError, ValueError, UnicodeError) as error:
            self._reason = type(error).__name__

    def _children(self):
        values = _read(self._children_file).split()
        if len(values) > 128 or any(not value.isdecimal() for value in values):
            raise ValueError("caller child list is not bounded numeric data")
        return {int(value) for value in values}

    def _child(self, pid):
        directory = self._proc / str(pid)
        if directory.stat().st_uid != self._uid:
            return None
        fields = _read(directory / "stat").rsplit(") ", 1)[1].split()
        if int(fields[1]) != self._parent:
            return None
        cwd = (directory / "cwd").stat()
        if (cwd.st_dev, cwd.st_ino) != self._fixture:
            return None
        result = {
            "pid": pid, "birth_ticks": int(fields[19]), "uid": self._uid,
            "parent_pid": int(fields[1]), "process_state": fields[0],
            "own_cpu_ticks": int(fields[11]) + int(fields[12]),
        }
        for name, limit in (("wchan", 256), ("syscall", 512)):
            try:
                value = _read(directory / name, limit)
                if name == "syscall":
                    first = value.split()[0]
                    value = "running" if first == "running" else int(first)
                result[name] = {"state": "observed", "value": value}
            except (OSError, ValueError, IndexError, UnicodeError) as error:
                result[name] = _unknown(type(error).__name__)
        # Fence PID reuse across the metadata reads. No args, env, fd contents
        # or memory are read, including when a candidate disappears.
        final = _read(directory / "stat").rsplit(") ", 1)[1].split()
        if final[19] != fields[19] or directory.stat().st_uid != self._uid:
            return None
        return result

    def _fixture_filesystem(self):
        """Observe only the original owned fixture's filesystem, off the caller."""
        try:
            directory = self._fixture_directory
            before = directory.stat()
            if (before.st_dev, before.st_ino) != self._fixture:
                return _unknown("fixture directory identity changed")
            space = os.statvfs(directory)
            after = directory.stat()
            if (after.st_dev, after.st_ino) != self._fixture:
                return _unknown("fixture directory identity changed")
            return {
                "state": "observed",
                "device": before.st_dev,
                "capacity_bytes": space.f_blocks * space.f_frsize,
                "available_bytes": space.f_bavail * space.f_frsize,
                "free_bytes": space.f_bfree * space.f_frsize,
                "available_inodes": space.f_favail,
            }
        except (OSError, AttributeError) as error:
            return _unknown(type(error).__name__)

    def _sample(self):
        try:
            values = []
            for pid in self._children() - self._baseline:
                try:
                    child = self._child(pid)
                    if child is not None:
                        values.append(child)
                except (OSError, ValueError, IndexError, UnicodeError):
                    continue
            if len(values) != 1:
                return _unknown("no unique candidate child in owned fixture")
            return {
                "state": "observed", "child": values[0],
                "fixture_filesystem": self._fixture_filesystem(),
            }
        except (OSError, ValueError, UnicodeError) as error:
            return _unknown(type(error).__name__)

    def _collect(self):
        # Fast commands do not need live samples. Event waits remain immediately
        # interruptible on the command's original completion or failure.
        if self._stop.wait(1):
            return
        for _ in range(24):
            if self._stop.is_set():
                return
            sample = self._sample()
            sample["elapsed_seconds"] = round(time.monotonic() - self._began, 3)
            self._samples.append(sample)
            if self._stop.wait(.25):
                return

    def start(self):
        if self._reason is None:
            self._thread = threading.Thread(target=self._collect, daemon=True)
            try:
                self._thread.start()
                self._started = True
            except RuntimeError:
                self._reason = "observer thread unavailable"

    def close(self):
        self._stop.set()
        if self._started:
            self._thread.join(timeout=.25)

    def snapshot(self):
        samples = list(self._samples)
        observed = any(row["state"] == "observed" for row in samples)
        return {
            "scope": "newly observed caller-thread candidate in owned fixture; not causal attribution",
            "completeness": "sampled only; exiting children can cause omissions",
            "state": "sampled" if observed else "unknown",
            "reason": self._reason or (None if observed else "no candidate sample observed"),
            "clock_ticks_per_second": getattr(self, "_ticks", None),
            "collector_stopped": not self._started or not self._thread.is_alive(),
            "sample_limit": 24,
            "samples": samples,
        }
