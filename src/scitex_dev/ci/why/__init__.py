"""``scitex_dev.ci.why`` — the ecosystem CI-failure-reading primitive.

Reading CI *status* is one word (``failure``); reading *why* has been
tens of thousands of lines, so a bounded-context agent is steered to the
cheap word and the word replaces the reason instead of summarising it.
This primitive inverts that price: it fetches a failing run's log ONCE
and distils it to a few hundred bytes — failing test ids, assertion
lines, or a setup failure's ``##[error]``.

The reusable SSOT any SciTeX project (sac, the umbrella, …) consumes via
a thin ``ci why`` verb. Everything except the injectable :func:`run_gh`
gh-seam is pure/string-based (unit-tested, no network); a target that
cannot be read raises :class:`CIWhyError` (UNKNOWN, never a silent
"green").

Public entry::

    from scitex_dev.ci.why import explain_ci_run, render_text

    for run in explain_ci_run("712"):          # PR#, run id, or branch
        print(render_text(run))
"""

from __future__ import annotations

from ._model import CIWhyError, GhRunner, JobFailure, RunFailures
from ._parse import (
    clean_log_line,
    parse_failed_log,
    parse_job_context,
    split_log_by_job,
)
from ._resolve import (
    explain_ci_run,
    explain_run,
    render_text,
    resolve_run_ids,
    run_gh,
)

__all__ = [
    "CIWhyError",
    "GhRunner",
    "JobFailure",
    "RunFailures",
    "clean_log_line",
    "split_log_by_job",
    "parse_job_context",
    "parse_failed_log",
    "run_gh",
    "resolve_run_ids",
    "explain_run",
    "explain_ci_run",
    "render_text",
]
