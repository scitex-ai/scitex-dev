"""Classify auditor output lines against declared `audit.skip-rules`.

``audit-all`` captures each sub-auditor's stdout/stderr, so masking is
applied HERE — one place, after the fan-out — rather than teaching six
auditors about deferrals. The exit code is then driven by the UNMASKED
findings only, and the masked ones are re-emitted as a loud inventory.

The visibility rule is the whole point: honouring a skip must never be
silent. A masked violation that nobody sees is green-by-absence, which
is indistinguishable from a gate that never ran.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ...audit._config._skip_rules import SkipRule


INVENTORY_HEADER = "=== MASKED INVENTORY (audit.skip-rules) ==="

# A bracketed token carrying a RULE ID — the thing that makes a finding
# attributable to a rule, and therefore decidable as masked or unmasked.
#
# The discriminator is "contains a digit or §": every rule id in the corpus
# does (`PS-103`, `STX-IO001`, `§10w`, `SK-401`), and the severity markers
# that share the bracket syntax do not (`[E]`, `[W]`). That is a structural
# test, not a list of known prefixes, so a new rule family needs no edit
# here.
_RULE_ID_RE = re.compile(r"\[[^\]]*(?:\d|§)[^\]]*\]")


def is_violation_line(line: str) -> bool:
    """True iff ``line`` is an auditor finding line carrying a rule id.

    Auditors print findings in two shapes::

        `  [E] [PS-139 §2] ...`      (legacy, from audit-summary)
        `  [PS-139 §2] <where>: ...` (canonical, every current auditor)

    Current auditors additionally prefix a coloured level word
    (``ERRO: ``/``WARN: ``), so a leading alphabetic word plus colon is
    stripped before the bracket test.
    """
    stripped = line.lstrip()
    head = stripped.split(":", 1)
    payload = head[1].lstrip() if len(head) == 2 and head[0].isalpha() else stripped
    return payload.startswith("[")


def line_matches_rule(line: str, rule: str) -> bool:
    """True iff ``line`` reports a violation of ``rule``.

    Matches by rule id inside its bracketed token — the surrounding
    marker (severity letter, section suffix) is incidental. ``[PS-139 §2]``
    and ``[PS-139]`` both match ``PS-139``; ``[PS-1390]`` does not.
    """
    return f"[{rule} " in line or f"[{rule}]" in line


def is_error_line(line: str) -> bool:
    """True iff ``line`` is an ERROR-level finding (not a warning/info).

    Auditors mark severity two ways: scitex-logging's `ERRO: ` prefix,
    and the legacy audit-summary `[E]` marker.
    """
    return line.lstrip().startswith("ERRO:") or "[E] " in line


@dataclass(frozen=True)
class MaskReport:
    """Outcome of classifying one run's output against declared skips."""

    #: rule id -> the violation lines it masked (declaration order).
    masked: dict[str, list[str]]
    #: violation lines matching no declared skip — these drive the exit code.
    unmasked: list[str]
    #: the declared skips, carried so the inventory can print rationales.
    skip_rules: tuple[SkipRule, ...]
    #: finding-shaped lines carrying no rule id, so they cannot be attributed
    #: to a rule and cannot be shown to be covered by a declared skip.
    #: UNKNOWN — neither masked nor cleanly unmasked.
    #:
    #: The membership test was originally "carries a level prefix", which
    #: measured the wrong thing: scitex-logging prefixes EVERY console line
    #: with a level, so banners and headlines qualified. Measured 2026-08-05
    #: on this repo's own captured audit output — 17 unreadable of 42
    #: inspected, and all 17 were framing (`INFO: auditing <path>`, `SUCC: no
    #: skills violations`, the per-auditor headlines). Zero true positives.
    #: A signal that is ~100% false positive cannot gate anything, and
    #: printing it next to a clean verdict trains readers to ignore it.
    unreadable: list[str] = field(default_factory=list)
    #: how many non-blank lines were examined. The DENOMINATOR: "0 unmasked
    #: error(s)" means nothing without it, and an inspected count of 0 makes
    #: any verdict impossible to issue honestly.
    inspected: int = 0

    @property
    def masked_count(self) -> int:
        return sum(len(v) for v in self.masked.values())

    @property
    def unmasked_count(self) -> int:
        return len(self.unmasked)

    @property
    def unmasked_error_count(self) -> int:
        """How many unmasked findings are ERROR-level.

        Counting every finding as an "error" would repeat, in the very
        summary meant to end imprecision, the conflation this PR exists
        to fix: a run with 7 warnings and 1 error is not 8 errors.
        Severity is read off the auditor's own prefix (`ERRO:` from
        scitex-logging, `[E]` from the legacy audit-summary shape).
        """
        return sum(1 for line in self.unmasked if is_error_line(line))

    def is_answerable(self) -> bool:
        """False when a line claimed to be a finding and could not be read.

        Named to match :meth:`SurfaceCoverage.is_answerable` in
        ``_cli/audit/_summary/_coverage.py`` — same question ("is a verdict
        licensed at all?"), same refusal, so both are greppable under one
        name. They are deliberately NOT the same object: that one counts
        command paths a walker inspected, this one counts output lines a
        classifier read. Sharing the type would couple two unrelated
        denominators; sharing the name is the part that has to be shared.

        ``unreadable`` is the only input. ``unmasked`` findings are read
        just fine — they are an ANSWER (red), not the absence of one.
        """
        return not self.unreadable

    @property
    def fully_masked(self) -> bool:
        """True iff every finding was masked and at least one was.

        The "at least one" guard matters: without it any non-zero exit
        with no parseable finding lines (a crashed auditor, a warn-only
        run) would be swallowed simply because the repo declared SOME
        skip rules. That is a real visibility bug, not a deferral.

        UNREADABLE lines defeat the claim outright. This property is what
        downgrades a failing package to green in ``_audit_all.py``, and it
        asserts "everything that failed was declared" — which is exactly
        the sentence you cannot say about a line nobody could parse. The
        line may have been an undeclared ERROR; masked and unreadable are
        different answers, and only one of them licenses the downgrade.
        """
        return bool(self.masked) and not self.unmasked and self.is_answerable()


def classify_output(text: str, skip_rules) -> MaskReport:
    """Split ``text``'s violation lines into masked / unmasked buckets.

    Also records what it COULD NOT CLASSIFY. The old loop did a bare
    ``continue`` on any line ``is_violation_line`` rejected, so the summary
    downstream was computed over a silently-narrowed set: it could report
    "0 unmasked error(s)" while the run exited non-zero, because the exit
    code comes from the sub-auditors' return codes and the count came from
    whatever survived this filter. Two inputs, one verdict, and no way for
    either side to notice the disagreement.

    A finding-shaped line (payload starts with ``[``) that carries no rule
    id is kept in ``unreadable`` — an UNKNOWN, not a silent zero. It cannot
    be attributed to a rule, so it cannot be shown to be masked. Genuine
    non-findings (banners, headlines, blank lines, prose that never claimed
    to be a finding) are skipped and counted only in ``inspected``.

    THE THREE BUCKETS ARE ORDERED BY HOW MUCH IS KNOWN::

        masked      attributable, and the rule is declared    -> suppressed
        unmasked    attributable, no declared rule            -> red
        unreadable  finding-shaped, NOT attributable          -> unknown

    ``unmasked`` is deliberately the default for anything attributable: a
    finding nobody deferred stays red without needing a rule to say so.
    """
    rules = tuple(skip_rules)
    masked: dict[str, list[str]] = {r.rule: [] for r in rules}
    unmasked: list[str] = []
    unreadable: list[str] = []
    inspected = 0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        inspected += 1
        if not is_violation_line(line):
            # Framing: banners, headlines, per-audit progress. Counted in
            # `inspected` and nowhere else.
            continue
        hit = next((r.rule for r in rules if line_matches_rule(line, r.rule)), None)
        if hit is not None:
            masked[hit].append(stripped)
        elif _RULE_ID_RE.search(stripped):
            # Finding-shaped, attributable, matched no declared skip. A
            # clean ANSWER: red.
            unmasked.append(line)
        else:
            # Finding-shaped but carrying no rule id, so it cannot be
            # attributed and therefore cannot be shown to be covered by a
            # declared skip. The genuine UNKNOWN.
            unreadable.append(stripped)
    return MaskReport(
        masked={k: v for k, v in masked.items() if v},
        unmasked=unmasked,
        skip_rules=rules,
        unreadable=unreadable,
        inspected=inspected,
    )


#: Prefix stamped on a finding that a declared skip rule has MASKED.
#:
#: Chosen to be the same width as the auditor's own `ERRO: ` / `WARN: `
#: so the findings stay column-aligned when a run mixes both.
MASKED_PREFIX = "MASK: "


def label_masked_lines(text: str, report: MaskReport | None) -> str:
    """Re-stamp the auditor's own output so MASKED findings say so.

    The sub-auditor prints its findings with its own `ERRO: ` prefix and
    that text is echoed verbatim. Masking is applied afterwards and shows
    up only as a COUNT in the inventory, so a masked finding reaches the
    reader still labelled ERRO — a line that says ERROR while provably
    unable to fail the gate (only `unmasked` findings drive the exit
    code; see `MaskReport.unmasked`).

    Reported by scitex-storage 2026-08-11, who read a CI log showing
    `[PS-221] 25 violation(s) masked` above a still-red run and could not
    tell from the output whether masking was inert. It was not — the run
    was red on 29 unrelated unmasked errors — but nothing in the text
    distinguished "this is why you are red" from "this is inventory".

    Loud is correct: the inventory must never be silent. Loud and
    MISLABELLED is worse than either, because the reader then has to
    reconcile an ERRO count that disagrees with the exit code.

    Membership is an exact-line lookup against `report.masked`, which
    `classify_output` already built — no re-parsing, so the label cannot
    drift from the classification that drove the exit code. Lines the
    report does not know are returned untouched.
    """
    if report is None or not text:
        return text
    masked_lines = {line for hits in report.masked.values() for line in hits}
    if not masked_lines:
        return text
    out = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped and stripped in masked_lines:
            indent = raw[: len(raw) - len(raw.lstrip())]
            out.append(f"{indent}{MASKED_PREFIX}{stripped}")
        else:
            out.append(raw)
    return "\n".join(out)


def render_inventory(report: MaskReport, distribution: str) -> list[str]:
    """Render the always-on masked inventory as a list of output lines.

    Emitted whenever the repo declares ANY skip rule — including rules
    that masked nothing. A declared deferral matching zero violations is
    itself worth seeing: the campaign it was waiting on has landed, and
    the entry is now removable. Silence would hide that too.
    """
    if not report.skip_rules:
        return []
    n_rules = len(report.skip_rules)
    lines = [
        "",
        INVENTORY_HEADER,
        f"{distribution}: {report.masked_count} violation(s) masked "
        f"by {n_rules} declared skip rule(s).",
        "These are DEFERRED, not fixed — the run is green because a "
        "campaign owns them, not because the code is clean.",
    ]
    for entry in report.skip_rules:
        hits = report.masked.get(entry.rule, [])
        count = len(hits)
        suffix = "" if count else "  (no current violations — entry is now removable)"
        lines.append(f"  [{entry.rule}] {count} violation(s) masked{suffix}")
        lines.append(f"      rationale: {entry.reason}")
    lines.append("")
    return lines


def render_summary(
    distribution: str,
    *,
    unmasked_errors: int,
    masked: int,
    declared: int,
    inspected: int,
    unreadable: int,
    unmasked_total: int | None = None,
) -> str:
    """One summary line stating BOTH numbers — AND its denominator.

    A summary reporting only "0 errors" while 150 are masked is a lie of
    omission, so the masked count is never conditional on being non-zero.
    Warning-level findings are reported separately from errors rather
    than folded into the error count — only errors drive the exit code.

    ``inspected`` and ``unreadable`` are REQUIRED and keyword-only, with no
    defaults, on purpose. Every other parameter here is a NUMERATOR; before
    this change the function took four counts and still could not say what
    it had looked at, so "0 unmasked error(s)" read identically whether the
    classifier had read two hundred lines or none. Making them required
    turns the omission into a TypeError at the call site — the only form of
    this rule that survives an author who is tired, which is precisely when
    a denominator gets dropped.

    ``unreadable`` is the three-valued part: lines that claimed to be
    findings and could not be classified are neither errors nor clean. They
    are reported explicitly rather than collapsing into the zero.
    """
    line = f"summary: {distribution}: {unmasked_errors} unmasked error(s)"
    if unmasked_total is not None and unmasked_total > unmasked_errors:
        line += f" (+{unmasked_total - unmasked_errors} warning/info finding(s))"
    line += f", {masked} masked by skip-rules ({declared} declared)"
    line += f"; {inspected} line(s) inspected"
    if unreadable:
        line += (
            f", {unreadable} UNREADABLE (claimed to be findings, could not "
            f"be classified — NOT counted as clean)"
        )
    return line


def resolve_skip_rules(distributions, explicit_path):
    """Load each distribution's declared skips, keyed by distribution.

    Resolution mirrors the auditors': an explicit ``--path`` wins,
    otherwise the target tree is resolved by name. A tree we cannot
    resolve declares nothing (rather than erroring) — but a tree we CAN
    resolve whose config is malformed raises, and the caller exits 2. A
    deferral config we cannot trust must not be graded as if the repo
    had declared no deferrals at all.
    """
    from pathlib import Path

    from ...audit._config._skip_rules import load_skip_rules

    out: dict[str, list] = {}
    for distribution in distributions:
        if explicit_path:
            root = Path(explicit_path)
        else:
            try:
                from ...audit._target_tree import resolve_target_tree

                root, _ = resolve_target_tree(distribution, None)
            except Exception:
                out[distribution] = []
                continue
        out[distribution] = load_skip_rules(Path(root)) if root is not None else []
    return out


def json_payload(mask_reports: dict, distributions) -> dict:
    """Build the ``skip_rules`` block for ``--json`` output.

    Masking affects the exit code in JSON mode too, so omitting this
    would reproduce the exact green-by-absence defect the human-readable
    inventory exists to prevent — just for machine consumers.
    """
    payload: dict = {}
    for d in distributions:
        report = mask_reports.get(d)
        if report is None:
            continue
        payload[d] = {
            "unmasked_errors": report.unmasked_error_count,
            "unmasked_total": report.unmasked_count,
            "masked_total": report.masked_count,
            "declared": [
                {
                    "rule": entry.rule,
                    "reason": entry.reason,
                    "masked": len(report.masked.get(entry.rule, [])),
                }
                for entry in report.skip_rules
            ],
        }
    return payload


__all__ = [
    "INVENTORY_HEADER",
    "MaskReport",
    "classify_output",
    "is_error_line",
    "is_violation_line",
    "json_payload",
    "line_matches_rule",
    "render_inventory",
    "render_summary",
    "resolve_skip_rules",
]
