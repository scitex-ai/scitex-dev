# -*- coding: utf-8 -*-
"""Site keys and exemption text for PS-224 runner-destination findings.

A PS-224 finding's LOCATION and the ``path:`` an ``audit.exemptions`` entry
must spell are THE SAME STRING. That identity is the whole point of this
module: the instruction a user reads in the audit output is, literally, the
instruction that works when pasted into config. Split out of
``_check_runner_destinations`` so the contract has one home rather than
living in a corner of the scanner.

Findings are per-JOB, so the key is job-qualified
(``.github/workflows/ci.yml::pytest``). A bare file path would OVER-EXEMPT:
one workflow file routinely holds a job that must stay on a hosted runner AND
a job already migrated to our own hardware, and exempting the file would
silently cover both.
"""

from __future__ import annotations

#: Separator between a workflow path and a job id in an exemption SITE KEY.
#: Human-writable and greppable on purpose.
_SITE_SEP = "::"

#: PS-224 findings are per-JOB, not per-line, so both the emitted site and any
#: ``audit.exemptions`` entry pin line 0 (same contract as PS-222).
_NO_LINE = 0


def _site(rel: str, job_id: str | None = None) -> str:
    """Site key for a finding: ``path`` or ``path::job-id``.

    This exact string is BOTH the finding's reported location AND what an
    ``audit.exemptions`` entry's ``path`` must spell, so the instruction a
    user reads is the instruction that works.
    """
    return rel if job_id is None else f"{rel}{_SITE_SEP}{job_id}"


def _exempt_hint(site: str) -> str:
    """The copy-pasteable exemption recipe for one site (reason MANDATORY)."""
    return (
        " If this job genuinely cannot run on any registered machine, exempt "
        "THIS JOB (never the whole file) in `.scitex/dev/config.yaml` under "
        f"`audit: exemptions: PS-224:` with `path: {site}`, `line: 0` and a "
        "`reason:` saying why — the reason is mandatory (constitution §2), "
        "and a blank one exempts nothing."
    )


__all__ = ["_SITE_SEP", "_NO_LINE", "_site", "_exempt_hint"]

# EOF
