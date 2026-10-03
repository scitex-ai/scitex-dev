"""Verify declared PostgreSQL binaries before resolving a CI environment."""

import argparse
import json
import os
import re
import selectors
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path

TOOLS = ("initdb", "pg_ctl", "postgres", "psql")
VERSION = re.compile(r"[1-9][0-9]*\.[0-9]+")
BIN_DIRECTORY = re.compile(r"/usr/lib/postgresql/([1-9][0-9]*)/bin")


class CapabilityError(RuntimeError):
    """The declared immutable image capability was not established."""


def check_declared_location(directory, expected_version):
    """Bind a literal image path to the declared server major version."""
    match = BIN_DIRECTORY.fullmatch(str(directory))
    if (
        VERSION.fullmatch(expected_version) is None
        or match is None
        or match.group(1) != expected_version.split(".")[0]
    ):
        raise CapabilityError("invalid declared PostgreSQL image capability")


def executable_files(directory):
    """Refuse missing, foreign or symlinked binaries before invoking any."""
    directory = Path(directory)
    if not directory.is_absolute():
        raise CapabilityError("PostgreSQL directory must be absolute")
    for parent in (directory, *directory.parents):
        if stat.S_ISLNK(parent.lstat().st_mode):
            raise CapabilityError("PostgreSQL capability path is symlinked")
    result = {}
    for tool in TOOLS:
        binary = directory / tool
        try:
            mode = binary.lstat().st_mode
        except FileNotFoundError as error:
            raise CapabilityError("declared PostgreSQL binary is missing") from error
        if not stat.S_ISREG(mode) or not os.access(binary, os.X_OK):
            raise CapabilityError("declared PostgreSQL binary is not executable")
        result[tool] = binary
    return result


def version_output(binary, timeout_s=2):
    """Read at most 1024 bytes and reap the exact bounded version process."""
    child = subprocess.Popen(
        [str(binary), "--version"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
        start_new_session=True,
    )
    deadline = time.monotonic() + timeout_s
    output = bytearray()
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(child.stdout, selectors.EVENT_READ)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    raise CapabilityError("PostgreSQL version command timed out")
                chunk = os.read(child.stdout.fileno(), 1025 - len(output))
                if not chunk:
                    selector.unregister(child.stdout)
                    break
                output.extend(chunk)
                if len(output) > 1024:
                    raise CapabilityError("PostgreSQL version output is oversized")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise CapabilityError("PostgreSQL version command timed out")
        try:
            code = child.wait(timeout=remaining)
        except subprocess.TimeoutExpired as error:
            raise CapabilityError("PostgreSQL version command timed out") from error
        if code:
            raise CapabilityError("PostgreSQL version command failed")
        return bytes(output)
    finally:
        if child.poll() is None:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait(timeout=2)
        child.stdout.close()


def verify_capability(directory, expected_version):
    """Require every exact binary to report the same declared version."""
    if VERSION.fullmatch(expected_version) is None:
        raise CapabilityError("invalid declared PostgreSQL version")
    binaries = executable_files(directory)
    versions = {}
    for tool, binary in binaries.items():
        output = version_output(binary)
        pattern = (
            re.escape(tool).encode()
            + rb" \(PostgreSQL\) ([1-9][0-9]*\.[0-9]+)"
            + rb"(?: \([^\r\n]*\))?\n?"
        )
        match = re.fullmatch(pattern, output)
        if match is None or match.group(1).decode("ascii") != expected_version:
            raise CapabilityError("declared PostgreSQL version differs")
        versions[tool] = expected_version
    return {"bin_dir": str(directory), "version": expected_version, "tools": versions}


def main():
    """Check only an explicitly declared, supported immutable image path."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bin-dir", required=True)
    parser.add_argument("--expected-version", required=True)
    args = parser.parse_args()
    try:
        check_declared_location(args.bin_dir, args.expected_version)
        result = verify_capability(args.bin_dir, args.expected_version)
    except (CapabilityError, OSError) as error:
        # Error bodies cannot expose inherited credentials or child output.
        print(
            "CI PostgreSQL capability refused: " + type(error).__name__, file=sys.stderr
        )
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
