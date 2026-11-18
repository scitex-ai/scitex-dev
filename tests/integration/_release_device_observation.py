"""Bounded shared-device context; never per-process I/O or a cause verdict.

Only the kernel's current 17-field block/stat layout is recognized:
https://docs.kernel.org/block/stat.html . One direct backing layer, at most
four devices, is observed; this is not a complete physical storage topology.
"""

import os
import re
import stat
from itertools import islice
from pathlib import Path

_FIELDS = {"reads_completed": 0, "read_ms": 3, "writes_completed": 4,
           "write_ms": 7, "in_flight": 8, "active_ms": 9, "weighted_ms": 10}
_MAX_BACKING = 4


def _unknown(error):
    return {"state": "unknown", "reason": type(error).__name__}


def _read(path, limit):
    flags = os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC | os.O_NOFOLLOW
    with os.fdopen(os.open(path, flags), "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("device attribute must be regular")
        body = stream.read(limit + 1)
    if len(body) > limit:
        raise ValueError("device observation exceeds read bound")
    return body.decode("ascii").strip()


def _identity(path):
    text = _read(path / "dev", 64)
    if re.fullmatch(r"[0-9]{1,10}:[0-9]{1,10}", text) is None:
        raise ValueError("unsupported device identity")
    values = tuple(int(n) for n in text.split(":"))
    if any(n >= 2**32 for n in values):
        raise ValueError("unsupported device identity")
    return values


def _device(path, expected=None):
    before = path.stat()
    identity = _identity(path)
    if expected is not None and identity != expected:
        raise ValueError("device identity mismatch")
    fields = _read(path / "stat", 1024).split()
    if len(fields) != 17 or any(not n.isdecimal() for n in fields):
        raise ValueError("unsupported block statistics")
    numbers = [int(n) for n in fields]
    if any(n >= 2**64 for n in numbers):
        raise ValueError("block statistic exceeds numeric bound")
    after = path.stat()
    if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino) or _identity(path) != identity:
        raise ValueError("device identity changed")
    return {"state": "observed", "major": identity[0], "minor": identity[1],
            "statistics": {name: numbers[index] for name, index in _FIELDS.items()}}


def _backing(path):
    try:
        entries = list(islice((path / "slaves").iterdir(), _MAX_BACKING + 1))
        if len(entries) > _MAX_BACKING:
            raise ValueError("direct backing device count exceeds bound")
        devices = [_device(entry) for entry in entries]
        devices.sort(key=lambda row: (row["major"], row["minor"]))
        return {"state": "observed", "devices": devices}
    except (OSError, ValueError, UnicodeError) as error:
        return _unknown(error)


def observe_fixture_device(device, sys_block_root=Path("/sys/dev/block")):
    """Read fixture-device counters; unsupported or unavailable stays unknown.

    Values are cumulative except in_flight, a gauge. Device/backing snapshots
    are not atomic together, not a baseline/delta and not process attribution.
    No raw sysfs names, identifiers, paths or input text are returned.
    """
    try:
        if type(device) is not int or device < 0:
            raise ValueError("unsupported fixture device")
        identity = (os.major(device), os.minor(device))
        path = sys_block_root / f"{identity[0]}:{identity[1]}"
        before = path.stat()
        result = _device(path, identity)
        result["direct_backing"] = _backing(path)
        after = path.stat()
        if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino) or _identity(path) != identity:
            raise ValueError("device identity changed")
        return result
    except (OSError, ValueError, UnicodeError, OverflowError, AttributeError) as error:
        return _unknown(error)
