"""Pure, network-free parsing of ``gh run view --log-failed`` output.

Everything here is string in, structured out — no subprocess, no gh, no
network — so it is exhaustively unit-testable on real-shaped log strings.
:func:`parse_failed_log` is the core: it distils one job's log into a
:class:`~scitex_dev.ci.why._model.JobFailure` by four priority tiers —
pytest ``short test summary info`` FAILED ids, the ``FAILURES`` block's
``E`` assertion lines, ``##[error]`` annotations, then a tail fallback.
"""

from __future__ import annotations

import re
from collections import OrderedDict
from typing import Optional

from ._model import JobFailure

# The ISO-8601 runner timestamp that prefixes every raw actions log line
# (after gh's optional "<job>\t<step>\t" prefix). Everything up to and
# including it is scaffolding.
_TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z ?")
_BOM = "﻿"
_ERROR_ANNOT = "##[error]"

_SUMMARY_RE = re.compile(r"={3,}\s*short test summary info\s*={3,}", re.IGNORECASE)
_FAILURES_HDR_RE = re.compile(r"={3,}\s*(FAILURES|ERRORS)\s*={3,}")
_SUMMARY_END_RE = re.compile(
    r"={3,}.*\b(passed|failed|error|errors|skipped|deselected|"
    r"xfailed|xpassed|warning|warnings|no tests ran)\b.*={3,}",
    re.IGNORECASE,
)
_FAILED_LINE_RE = re.compile(r"^(FAILED|ERROR)\s+\S")
_E_LINE_RE = re.compile(r"^E(?:\s|$)")

# Matrix legs encode context in the job name (py version, runner OS).
_PY_RE = re.compile(r"(?:py[ -]?)?3[.\-](\d{1,2})\b", re.IGNORECASE)
_OS_RE = re.compile(
    r"(ubuntu-latest|ubuntu-\d[\w.]*|ubuntu|macos-[\w.]+|macos|"
    r"windows-[\w.]+|windows|self-hosted)",
    re.IGNORECASE,
)


def clean_log_line(raw: str) -> Optional[str]:
    r"""Strip GitHub-Actions scaffolding from one raw log line.

    Removes the optional ``<job>\t<step>\t`` prefix that
    ``gh run view --log-failed`` prepends, the ISO-8601 runner timestamp,
    and the UTF-8 BOM. ``##[group]`` / ``##[endgroup]`` fold markers are
    dropped entirely (return ``None``). Everything else — including
    ``##[error]`` — is returned as bare content.
    """
    line = raw.rstrip("\n").replace(_BOM, "")
    m = _TS_RE.search(line)
    content = line[m.end() :] if m else line
    stripped = content.strip()
    if stripped.startswith("##[group]") or stripped.startswith("##[endgroup]"):
        return None
    return content


def split_log_by_job(log_text: str) -> "OrderedDict[str, str]":
    r"""Group ``gh run view --log-failed`` lines by job name (first column).

    ``--log-failed`` prefixes each line ``<job>\t<step>\t<ts> <content>``.
    Lines with no such prefix (a plain single-job log, as in a fixture)
    group under the empty-string key.
    """
    groups: "OrderedDict[str, list[str]]" = OrderedDict()
    for raw in log_text.splitlines():
        line = raw.replace(_BOM, "")
        parts = line.split("\t", 2)
        if len(parts) == 3 and _TS_RE.match(parts[2]):
            job = parts[0]
        else:
            job = ""
        groups.setdefault(job, []).append(raw)
    return OrderedDict((job, "\n".join(lines)) for job, lines in groups.items())


def parse_job_context(job_name: str) -> tuple[Optional[str], Optional[str]]:
    """Best-effort ``(python_version, runner_os)`` from a job name.

    Matrix legs encode context in the name, e.g.
    ``pytest-matrix-on-ubuntu-py3.11``  -> ('3.11', 'ubuntu'),
    ``import-smoke-on-ubuntu-py3-12``   -> ('3.12', 'ubuntu'),
    ``...guard-on-self-hosted``         -> (None, 'self-hosted').
    """
    py = None
    m = _PY_RE.search(job_name)
    if m:
        py = f"3.{m.group(1)}"
    os_ = None
    mo = _OS_RE.search(job_name)
    if mo:
        os_ = mo.group(1).lower()
    return py, os_


def parse_failed_log(
    log_text: str,
    *,
    job_name: str = "",
    url: str = "",
    tail_lines: int = 8,
) -> JobFailure:
    """Parse ONE job's ``--log-failed`` text into a :class:`JobFailure`.

    Priority of signals: (1) the ``short test summary info`` ``FAILED``
    lines; (2) the ``FAILURES`` block ``E`` assertion lines; (3)
    ``##[error]`` annotations (setup/infra failures); (4) fallback to the
    last ``tail_lines`` non-blank cleaned lines.
    """
    py, os_ = parse_job_context(job_name)
    fail = JobFailure(job=job_name, py=py, os=os_, url=url)

    clean: list[str] = []
    for raw in log_text.splitlines():
        c = clean_log_line(raw)
        if c is None:
            continue
        clean.append(c)
        if c.lstrip().startswith(_ERROR_ANNOT):
            annot = c.lstrip()[len(_ERROR_ANNOT) :].strip()
            if annot:
                fail.errors.append(annot)

    # (1) pytest short test summary — the cheapest, richest signal.
    in_summary = False
    for c in clean:
        s = c.strip()
        if _SUMMARY_RE.search(s):
            in_summary = True
            continue
        if in_summary:
            if _SUMMARY_END_RE.search(s):
                break
            if _FAILED_LINE_RE.match(s):
                fail.failed_tests.append(s)

    # (2) assertion detail from the FAILURES / ERRORS block.
    in_failures = False
    for c in clean:
        st = c.strip()
        if _FAILURES_HDR_RE.search(st):
            in_failures = True
            continue
        if in_failures:
            if _SUMMARY_RE.search(st):
                break
            if _E_LINE_RE.match(c):
                fail.assertions.append(st)

    # (4) fallback tail when nothing structured was found.
    if not (fail.failed_tests or fail.assertions or fail.errors):
        nonblank = [c for c in clean if c.strip()]
        fail.tail = nonblank[-tail_lines:]
    return fail


__all__ = [
    "clean_log_line",
    "split_log_by_job",
    "parse_job_context",
    "parse_failed_log",
]
