"""Bounded diagnostics for the private PostgreSQL bootstrap subprocesses."""

from __future__ import annotations

import subprocess
from typing import Sequence


def _output_tail(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="backslashreplace")
    return str(value)[-2048:]


def _run_bootstrap(
    command: Sequence[str], *, stage: str, timeout: float = 120
) -> subprocess.CompletedProcess:
    """Run once with captured output; log bounded tails before the same error."""
    try:
        return subprocess.run(
            command, check=True, capture_output=True, text=True, timeout=timeout
        )
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as error:
        from scitex_logging import getLogger

        getLogger(__name__).error(
            f"Private PostgreSQL {stage} bootstrap failed "
            f"({type(error).__name__}); "
            f"stdout_tail={_output_tail(error.stdout)!r}; "
            f"stderr_tail={_output_tail(error.stderr)!r}"
        )
        raise
