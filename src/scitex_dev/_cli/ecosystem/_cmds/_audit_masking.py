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

from dataclasses import dataclass

from ...audit._config._skip_rules import SkipRule


INVENTORY_HEADER = "=== MASKED INVENTORY (audit.skip-rules) ==="


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
    """Split ``text``'s violation lines into masked / unmasked buckets."""
    rules = tuple(skip_rules)
    masked: dict[str, list[str]] = {r.rule: [] for r in rules}
    unmasked: list[str] = []
    for line in text.splitlines():
        if not is_violation_line(line):
            continue
        hit = next((r.rule for r in rules if line_matches_rule(line, r.rule)), None)
        if hit is not None:
            masked[hit].append(line.strip())
        else:
            unmasked.append(line)
    return MaskReport(
        masked={k: v for k, v in masked.items() if v},
        unmasked=unmasked,
        skip_rules=rules,
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
    unmasked_total: int | None = None,
) -> str:
    """One summary line stating BOTH numbers.

    A summary reporting only "0 errors" while 150 are masked is a lie of
    omission, so the masked count is never conditional on being non-zero.
    Warning-level findings are reported separately from errors rather
    than folded into the error count — only errors drive the exit code.
    """
    line = f"summary: {distribution}: {unmasked_errors} unmasked error(s)"
    if unmasked_total is not None and unmasked_total > unmasked_errors:
        line += f" (+{unmasked_total - unmasked_errors} warning/info finding(s))"
    return line + f", {masked} masked by skip-rules ({declared} declared)"


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
