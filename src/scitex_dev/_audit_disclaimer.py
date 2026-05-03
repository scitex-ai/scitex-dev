"""Sufficiency disclaimer printed at the end of every audit-* run.

Auditors check necessity (codified rules pass) but cannot judge
sufficiency (whether the package is genuinely well-organized,
documented, and useful). Surfacing this on every run keeps consumers
honest about the audit's limits.
"""

from __future__ import annotations

import os as _os

import click

DISCLAIMER = (
    "note: passing this audit is necessary but not sufficient for "
    "SciTeX standards — see _skills/general/ for the full quality "
    "checklist (content accuracy, prose clarity, naming taste, etc.)."
)


def emit_disclaimer() -> None:
    """Print the sufficiency disclaimer to stderr (suppress with SCITEX_DEV_NO_AUDIT_DISCLAIMER=1)."""
    if _os.environ.get("SCITEX_DEV_NO_AUDIT_DISCLAIMER"):
        return
    click.echo(DISCLAIMER, err=True)
