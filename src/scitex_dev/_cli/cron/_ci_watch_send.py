"""Inspect the installed SAC send interface before an authorized CI fix turn."""

from __future__ import annotations

import re
import subprocess
from typing import Callable


def send_fix_turn(
    agent: str,
    prompt: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess],
) -> subprocess.CompletedProcess:
    """Supply approval when advertised; never retry a possibly submitted turn.

    Older SAC versions lack --yes. Discover the actual command, rather than
    guessing from package versions or retrying a refused message without it.
    Discovery failure leaves the turn unsent. The caller owns the send verdict.
    """
    probe = runner(["agents", "send", "--help"], input_text="")
    if probe.returncode != 0:
        raise RuntimeError(
            f"cannot inspect SAC send help (rc={probe.returncode}); no turn sent"
        )
    help_text = probe.stdout or ""
    if not re.search(r"(?m)^Usage: .+\bsend \[OPTIONS\]", help_text):
        raise RuntimeError("SAC send help did not identify the command; no turn sent")
    _, separator, options = help_text.partition("\nOptions:\n")
    if not separator:
        raise RuntimeError("SAC send help omitted its options; no turn sent")
    approved = re.search(r"(?m)^\s*(?:-y,\s*)?--yes(?:[,\s]|$)", options)
    args = ["agents", "send"]
    if approved:
        args.append("--yes")
    return runner([*args, "--", agent, prompt], input_text="")
