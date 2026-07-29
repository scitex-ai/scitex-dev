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

# A line that CLAIMS to be a finding by carrying an auditor level prefix.
# Deliberately NOT a finding test — `is_violation_line` is that. This only
# separates "prose the auditor printed as framing" from "something that
# presented itself as a finding and could not be read", so the second can
# be reported as UNKNOWN instead of vanishing.
_LEVEL_PREFIX_RE = re.compile(r"^(ERRO|WARN|INFO|SUCC):\s")


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
    #: lines that CLAIM to be findings (level prefix) but that the classifier
    #: could not read. UNKNOWN — neither masked nor cleanly unmasked. Carried
    #: so a summary can say so instead of implying zero.
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

    @property
    def fully_masked(self) -> bool:
        """True iff every finding was masked and at least one was.

        The "at least one" guard matters: without it any non-zero exit
        with no parseable finding lines (a crashed auditor, a warn-only
        run) would be swallowed simply because the repo declared SOME
        skip rules. That is a real visibility bug, not a deferral.
        """
        return bool(self.masked) and not self.unmasked


def classify_output(text: str, skip_rules) -> MaskReport:
    """Split ``text``'s violation lines into masked / unmasked buckets.

    Also records what it COULD NOT CLASSIFY. The old loop did a bare
    ``continue`` on any line ``is_violation_line`` rejected, so the summary
    downstream was computed over a silently-narrowed set: it could report
    "0 unmasked error(s)" while the run exited non-zero, because the exit
    code comes from the sub-auditors' return codes and the count came from
    whatever survived this filter. Two inputs, one verdict, and no way for
    either side to notice the disagreement.

    A line that LOOKS like a finding (carries a level prefix) but that the
    classifier cannot read is now kept in ``unreadable`` — an UNKNOWN, not
    a silent zero. Genuine non-findings (banners, blank lines, prose that
    never claimed to be a finding) are still skipped, and are counted only
    in ``inspected``.
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
            # Not a violation the classifier can read. If it CLAIMS to be a
            # finding by carrying a level prefix, that is an unknown worth
            # surfacing; anything else is framing.
            if _LEVEL_PREFIX_RE.match(stripped):
                unreadable.append(stripped)
            continue
        hit = next((r.rule for r in rules if line_matches_rule(line, r.rule)), None)
        if hit is not None:
            masked[hit].append(stripped)
        else:
            unmasked.append(line)
    return MaskReport(
        masked={k: v for k, v in masked.items() if v},
        unmasked=unmasked,
        skip_rules=rules,
        unreadable=unreadable,
        inspected=inspected,
    )


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
