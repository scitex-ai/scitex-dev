#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Grade one `audit-all` run as PASS / FAIL / UNKNOWN, and say so in words.

THREE ANSWERS, NOT TWO. A gate can say three things and they are not
interchangeable:

  * ``PASS``     — the audit ran and found nothing.
  * ``FAIL``     — the audit ran and FOUND VIOLATIONS.
  * ``UNKNOWN``  — the audit COULD NOT RUN, so it found nothing and also
                   established nothing.

For most of its life :mod:`scitex_dev.testing._audit_conformance` said one
sentence for the last two — *"audit-all reported violations for <pkg>"*.
That sentence is FALSE for UNKNOWN, and falsely SPECIFIC in a way that costs
real time: it sends the reader hunting for a lint violation that does not
exist, while the actual cause (a missing dependency, an auditor that crashed
on import) sits unread further down a several-hundred-line dump. Measured
2026-08-11 on scitex-dev PR #567 — a DOC-ONLY diff whose gate said
"reported violations" and took a full CI-log dive to attribute.

Collapsing UNKNOWN into the failure pole is the same three-valued-signal
error the constitution names, and the same one ``§10w`` (import-budget
"could not measure") and ``MaskReport.unreadable`` already fixed one layer
down. This module is that fix at the pytest-gate layer.

UNKNOWN STILL FAILS. "Could not run" must never be green — that is
green-by-absence. What changes is only what the message CLAIMS.

AND THE FAILING CLAIM HAS TO NAME A RULE. Saying FAIL rather than UNKNOWN
fixed the wrong-KIND-of-failure problem; it left every FAIL reading
identically, because the first line — the only line pytest's short summary
shows — was a constant. Seventeen unrelated red PRs then looked like one
outage (scitex-dev#593, measured 2026-08-12). :func:`headline_codes` puts
the rule ids that are ALREADY in the captured output onto that first line.
Nothing is removed: the digest and the full stdout/stderr still follow.

Deliberately free of the `_cli` tree (and therefore of click): this module
is reached from every ecosystem package's test suite, so its import cost and
its dependency surface are everyone's.
"""

from __future__ import annotations

import re


#: The three answers a gate can give. ``UNKNOWN`` is a FAILING verdict — it
#: is separated from ``FAIL`` to fix what the message SAYS, never to let a
#: broken auditor report success.
VERDICT_PASS = "pass"
VERDICT_FAIL = "fail"
VERDICT_UNKNOWN = "unknown"

#: scitex-logging colours its console output, so every membership test below
#: runs on de-escaped text. Without this a ``\x1b[33m``-prefixed line has no
#: parseable level word and slips past the notice guard.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

#: A bracketed token carrying a RULE ID — mirrors
#: ``_cli.ecosystem._cmds._audit_masking._RULE_ID_RE``. The discriminator is
#: "contains a digit or §": every rule id in the corpus does (``PS-103``,
#: ``STX-IO001``, ``§10w``, ``SK-401``) and the bare severity markers
#: (``[E]``, ``[W]``) do not.
_RULE_ID_RE = re.compile(r"\[[^\]]*(?:\d|§)[^\]]*\]")

#: Substrings meaning THE AUDIT DID NOT RUN — an environment/plumbing
#: failure, not a finding about the code under audit.
#:
#: ``Error: No module named 'requests'`` is the measured instance:
#: scitex-hub's CI carried it from 2026-08-05 and it reached every reader
#: through a message that said "reported violations".
_COULD_NOT_RUN_MARKERS: tuple[str, ...] = (
    "no module named",
    "modulenotfounderror",
    "importerror",
    "traceback (most recent call last)",
    "failed to launch",
    "command not found",
    "no such file or directory",
)

#: Words marking a line as a NOTICE rather than the thing that stopped the
#: run. A degraded-but-running auditor announces itself exactly this way, and
#: it is common: scitex-dev's own audit output opens with
#:
#:     [scitex-dev linter] WARNING: failed to load plugin 'io':
#:     ModuleNotFoundError: No module named 'scitex_io._linter'
#:
#: on EVERY invocation, clean runs included (verified 2026-08-11 against
#: `ecosystem audit-skills scitex-dev`). Treating that as could-not-run would
#: relabel every genuine violation report as UNKNOWN — the same collapse as
#: before, pointed the other way.
_NOTICE_TOKENS: tuple[str, ...] = (
    "WARN",
    "WARNING",
    "INFO",
    "NOTE",
    "NOTICE",
    "DEBUG",
    "SUCC",
)


def _looks_like_a_notice(prefix: str) -> bool:
    """Is the text LEADING UP TO a could-not-run marker a warn/info notice?

    Only the prefix is examined, deliberately. Searching the whole line would
    let a crash whose message happens to contain "note" or "warning" disguise
    itself; searching the prefix asks the narrower and correct question —
    *how did the emitter label this line before it said the scary thing?*
    """
    upper = prefix.upper()
    return any(re.search(rf"\b{token}\b", upper) for token in _NOTICE_TOKENS)


def _is_finding_line(line: str) -> bool:
    """Is this an auditor FINDING — a rule id at the START of the payload?

    The rule id must LEAD the payload, not merely appear somewhere on the
    line. Measured while writing this module: the launch-failure line

        error: audit-cli on scitex-io failed to launch: [Errno 2] ...

    carries a trailing ``[Errno 2]``, which satisfies "contains a bracketed
    token with a digit" exactly as well as ``[SK-401]`` does. A whole-line
    search therefore classified the clearest could-not-run signal in the
    codebase as a finding — the very collapse this module removes, restored
    by a lazy regex. Position is what separates a rule id from a bracketed
    aside.
    """
    stripped = _ANSI_RE.sub("", line).lstrip()
    head = stripped.split(":", 1)
    has_level = len(head) == 2 and head[0].isalpha()
    payload = head[1].lstrip() if has_level else stripped
    return payload.startswith("[") and bool(_RULE_ID_RE.search(payload))


def could_not_run_evidence(output: str) -> list[str]:
    """Lines showing the audit COULD NOT RUN, in the order they appeared.

    An empty list means "nothing in this output says the audit was prevented
    from running" — which, paired with a non-zero exit, licenses FAIL.

    Two filters keep this from crying wolf:

    * A line carrying a RULE ID is an attributable FINDING, whatever words it
      contains. An auditor is entitled to report
      ``[STX-NET001] ... requests.get(...)`` without that being a crash.
    * A line whose text BEFORE the marker labels it a warning/info notice is a
      degraded-but-running announcement. See :data:`_NOTICE_TOKENS`.
    """
    hits: list[str] = []
    for raw in output.splitlines():
        line = _ANSI_RE.sub("", raw).strip()
        if not line:
            continue
        lowered = line.lower()
        at = min(
            (
                lowered.find(marker)
                for marker in _COULD_NOT_RUN_MARKERS
                if marker in lowered
            ),
            default=-1,
        )
        if at < 0:
            continue
        if _is_finding_line(line):
            continue
        if _looks_like_a_notice(line[:at]):
            continue
        hits.append(line)
    return hits


def finding_lines(output: str) -> list[str]:
    """The auditor's own finding lines — the ones that drive a FAIL.

    Used to build a DIGEST at the top of the failure message. The full
    stdout+stderr is still printed underneath; this exists because the
    interesting five lines were arriving buried in several hundred, which is
    how a warn-tier finding stayed unread while the reader chased an error
    that the summary line said did not exist.
    """
    return [
        _ANSI_RE.sub("", raw).strip()
        for raw in output.splitlines()
        if _is_finding_line(raw)
    ]


def rule_code(line: str) -> str | None:
    """The rule id one finding line is attributable to, e.g. ``PS-207``.

    The first WORD inside the first bracketed token that carries a rule id.
    Both emitted shapes land on the same answer::

        WARN:   [SK-302 §3 leaf-not-linked-from-skill-md] ...  -> "SK-302"
        ERRO:   [E] [PS-207 §2 empty-test-dir] ...             -> "PS-207"

    The legacy `[E]` marker is stepped over rather than special-cased: it
    carries neither a digit nor a ``§``, so :data:`_RULE_ID_RE` does not
    match it. That is the same structural discriminator the masking
    classifier uses, so a new rule FAMILY needs no edit here — as opposed to
    a list of known prefixes, which is a second place to forget.

    ``None`` when the line is not a finding, or is one whose bracket carries
    no rule id. A finding nobody can attribute is exactly what
    ``MaskReport.unreadable`` calls UNKNOWN, and it must not be rendered as
    though it named a rule.
    """
    stripped = _ANSI_RE.sub("", line).lstrip()
    head = stripped.split(":", 1)
    has_level = len(head) == 2 and head[0].isalpha()
    payload = head[1].lstrip() if has_level else stripped
    if not payload.startswith("["):
        return None
    match = _RULE_ID_RE.search(payload)
    if match is None:
        return None
    words = match.group(0)[1:-1].split()
    return words[0] if words else None


def rule_codes(findings: list[str]) -> list[str]:
    """The DISTINCT rule ids across ``findings``, sorted, de-duplicated.

    SORTED, not first-seen. The entire use for this list is comparing one
    failing run against another at a glance — "are these seventeen red PRs
    the same failure?" — and that comparison only works if two runs that
    tripped the same rules produce the same string. First-seen order does
    not survive: `audit-all` fans its sub-auditors out across a thread pool,
    and a rule's position in the output is a race, not a fact about the
    code.

    De-duplicated for the same reason: ``PS-140`` firing on four modules is
    ONE thing to go fix, and a headline that says it four times crowds out
    the second rule.
    """
    return sorted({code for code in map(rule_code, findings) if code})


def is_error_tier(line: str) -> bool:
    """Did this finding line come in at ERROR tier rather than WARN/INFO?

    Both emitted shapes are covered::

        ERRO:   [E] [PS-207 §2 empty-test-dir] ...   -> True
        WARN:   [SK-302 §3 leaf-not-linked] ...      -> False

    NOT A GATING PREDICATE, and the distinction is the whole reason this
    function is named for the TIER. We run outside the audited process and
    hold exactly two things: its stdout and one exit code. WHICH findings
    drove that exit is not in either. Deriving "did not gate" from "warn
    tier" is refuted by this module's own note below: some sub-auditors
    (audit-skills, audit-project) exit NON-ZERO on WARN-tier findings.

    Reported by figrecipe, 2026-08-18, who read the headline's code census
    as the causal list, concluded their gate could not go green until a rule
    they could not influence stopped firing, and told their product lead the
    repo was structurally blocked — which reached two teams. They proposed
    labelling the split `gating` / `non-gating`. That label would be a
    confident answer to a question this process cannot see, which is the
    defect being fixed rather than a fix for it. So the split ships, and the
    word does not.
    """
    stripped = _ANSI_RE.sub("", line).lstrip()
    head = stripped.split(":", 1)
    if len(head) == 2 and head[0].isalpha():
        level = head[0].upper()
        if level.startswith(("ERR", "CRIT", "FATAL")):
            return True
        if level.startswith(("WARN", "INFO", "NOTIC", "DEBUG")):
            return False
    return "[E]" in stripped


def rule_codes_by_tier(findings: list[str]) -> tuple[list[str], list[str]]:
    """``(error_tier_codes, warn_or_info_only_codes)``, both sorted + distinct.

    A code that appears at BOTH tiers counts as error-tier and is absent from
    the second list: the point of the split is "what should I go fix first",
    and a rule with any error-tier finding belongs in that answer once.
    """
    error: set[str] = set()
    other: set[str] = set()
    for line in findings:
        code = rule_code(line)
        if code is None:
            continue
        (error if is_error_tier(line) else other).add(code)
    return sorted(error), sorted(other - error)


def classify_audit_outcome(returncode: int, output: str) -> tuple[str, list[str]]:
    """Grade one `audit-all` run. Returns ``(verdict, evidence)``.

    ``evidence`` is the could-not-run lines for :data:`VERDICT_UNKNOWN`, the
    finding digest for :data:`VERDICT_FAIL`, and empty for
    :data:`VERDICT_PASS`.

    The rule:

    * exit 0 -> PASS.
    * exit != 0 AND the output says it could not run -> UNKNOWN.
    * exit 2 -> UNKNOWN even with no marker. Exit 2 is `audit-all` declining
      to grade (usage error, unreadable skip-rule config) or a sub-auditor
      reporting "could not locate the tree" — by construction "I did not
      grade", never "I graded and found something".
    * anything else non-zero -> FAIL.

    UNKNOWN is still a FAILING verdict for the caller. It changes the claim,
    not the colour.
    """
    if returncode == 0:
        return VERDICT_PASS, []
    evidence = could_not_run_evidence(output)
    if evidence:
        return VERDICT_UNKNOWN, evidence
    if returncode == 2:
        return VERDICT_UNKNOWN, []
    return VERDICT_FAIL, finding_lines(output)


def _digest(lines: list[str], limit: int = 12) -> str:
    """Render at most ``limit`` evidence lines, saying how many were elided."""
    body = "\n".join(f"    {line}" for line in lines[:limit])
    if len(lines) > limit:
        body += f"\n    ... (+{len(lines) - limit} more)"
    return body


def unknown_message(
    distribution: str,
    cmd: str,
    returncode: int,
    evidence: list[str],
    tail: str,
    *,
    audited_by: str | None = None,
) -> str:
    """The UNKNOWN report — says COULD NOT RUN and quotes the underlying error."""
    quoted = (
        _digest(evidence)
        if evidence
        else "    (none quoted — exit=2 is `audit-all` declining to grade;\n"
        "     see the usage/config error in the output below)"
    )
    return (
        f"audit-all COULD NOT RUN for {distribution!r} — UNKNOWN, not a "
        f"violation report (exit={returncode}).\n"
        f"{_audited_by_line(audited_by)}"
        "  The audit was PREVENTED from grading, so it neither found "
        "violations nor established that there are none.\n"
        "  Do NOT go looking for a lint violation: fix the environment / "
        "dependency / launch failure quoted here, then re-run.\n"
        f"  underlying error(s):\n{quoted}\n"
        f"  $ {cmd}\n{tail}"
    )


#: How many rule codes fit on the headline before it stops being scannable.
#: pytest's short summary is ONE line and terminals truncate it, so the
#: budget is real. Six codes is ~50 characters — measured against a run that
#: produced exactly six.
_MAX_HEADLINE_CODES = 6


def _listed(codes: list[str]) -> str:
    """Comma-joined, truncated, and SAYING how many it dropped.

    Truncation that does not announce itself turns "six rules fired" into
    "four rules fired" for every downstream reader of the one-line summary.
    """
    shown = ", ".join(codes[:_MAX_HEADLINE_CODES])
    if len(codes) > _MAX_HEADLINE_CODES:
        shown += f" (+{len(codes) - _MAX_HEADLINE_CODES} more)"
    return shown


def headline_codes(findings: list[str]) -> str:
    """The `: PS-207, SK-302` suffix for the failure message's FIRST line.

    THE FIRST LINE IS THE WHOLE PRODUCT HERE. pytest's `short test summary
    info` — and every CI notification and `gh pr checks` triage built on it —
    shows that line and nothing else. Without the codes it is a constant
    string: identical for every rule in the corpus, so unrelated failures are
    indistinguishable without downloading each job log.

    Measured 2026-08-12 on scitex-agent-container (scitex-dev#593). Seventeen
    PRs were red, all showing that one sentence, and were escalated as a P1
    fleet-wide CI outage. They were four DIFFERENT rules — ``PS-140`` twice
    for different new modules, ``PS-207``, ``SK-302`` — every one of them
    PR-local and a one-line fix by its own author. There was no outage:
    ``audit-all`` on develop exited 0 throughout. Two wrong root causes were
    published before anyone opened a raw log.

    Over-long lists are truncated rather than dropped: knowing SIX rules
    fired and being shown six of them beats being shown none.
    """
    errors, others = rule_codes_by_tier(findings)
    n_error_lines = sum(1 for line in findings if is_error_tier(line))
    if not errors and not others:
        # Say the words rather than emit a bare `(exit=1)`. An empty suffix
        # is indistinguishable from the old rule-agnostic headline, and this
        # case is not "no information" — it is the specific, reportable
        # shape the `else` digest below explains.
        return ": (no rule-attributable finding line — see below)"
    if not errors:
        # Exit non-zero with nothing at error tier. This is the shape the
        # digest's note describes, and naming it here stops a reader from
        # hunting for an error that the summary line correctly says is not
        # there.
        return f": {_listed(others)} (all at warn/info tier — see note below)"
    # The COUNT travels with the codes deliberately. figrecipe reconstructed
    # the causal set after the fact by noticing that a `summary: 6 unmasked
    # error(s)` line elsewhere in the output was exactly PS-231x5 + PS-140x1
    # — the report already held the answer, in a different sentence and a
    # different unit. Putting both in one line means nobody has to notice.
    lead = f"{_listed(errors)} ({n_error_lines} finding line(s))"
    if not others:
        return f": {lead}"
    return f": {lead} — also reported at warn/info tier: {_listed(others)}"




def _audited_by_line(audited_by: str | None) -> str:
    """The "which ruler measured this" line, or nothing.

    Optional rather than required because call sites outside this
    package construct these messages too, and a KeyError in a failure
    formatter would replace a real finding with a traceback.
    """
    if not audited_by:
        return ""
    return f"  audited by {audited_by}\n"


def violations_message(
    distribution: str,
    cmd: str,
    returncode: int,
    findings: list[str],
    tail: str,
    *,
    audited_by: str | None = None,
) -> str:
    """The FAIL report — names the RULES on line one, then digests the findings."""
    if findings:
        digest = (
            f"  {len(findings)} finding line(s) drove the failure:\n"
            f"{_digest(findings)}\n"
            "  note: `summary: ... 0 unmasked error(s)` WITH exit=1 is a "
            "real and common shape.\n"
            "        It means something OUTSIDE the unmasked-error count "
            "caused the exit. It does NOT\n"
            "        identify what. At least two causes produce it, and the "
            "message cannot tell them apart:\n"
            "          (a) a sub-auditor (audit-skills, audit-project) "
            "exiting non-zero on a WARN-tier\n"
            "              finding, or\n"
            "          (b) an ERROR-tier finding that is not counted as "
            "unmasked — e.g.\n"
            "              `CLI conventions: not-auditable: unknown`, which "
            "appears when the\n"
            "              distribution is not installed where the auditor "
            "can introspect it.\n"
            "        READ THE FINDINGS ABOVE, NOT THE COUNT, AND NOT THIS "
            "NOTE. Measured 2026-08-18:\n"
            "        sac read an earlier version of this note as naming (a) "
            "and concluded warnings\n"
            "        gate. Their cause was (b). They nearly relaxed the "
            "gate for 83 packages on it.\n"
            "        The headline splits codes by TIER, which is what this process can see.\n"
            "        TIER IS NOT GATING: a code listed under `warn/info tier` may still be\n"
            "        what failed the run. Only the sub-auditor that emitted it knows, and\n"
            "        it does not say so in this output.\n"
        )
    else:
        digest = (
            "  No rule-attributable finding line appears in the output, yet "
            "the audit exited non-zero and\n"
            "  did not report being unable to run. Read the full output below "
            "— this shape is itself a defect\n"
            "  in whichever sub-auditor produced it.\n"
        )
    return (
        f"audit-all reported violations for {distribution!r} "
        f"(exit={returncode}){headline_codes(findings)}\n"
        f"{_audited_by_line(audited_by)}"
        f"{digest}"
        f"  $ {cmd}\n{tail}"
    )


__all__ = [
    "VERDICT_FAIL",
    "VERDICT_PASS",
    "VERDICT_UNKNOWN",
    "classify_audit_outcome",
    "could_not_run_evidence",
    "finding_lines",
    "headline_codes",
    "is_error_tier",
    "rule_code",
    "rule_codes",
    "rule_codes_by_tier",
    "unknown_message",
    "violations_message",
]

# EOF
