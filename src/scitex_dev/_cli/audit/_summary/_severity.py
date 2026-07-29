"""audit-cli severity registry, per-severity tallies and rule filtering.

Extracted from `_run.py` (which had reached the 512-line cap) when the
per-severity renderer landed. `_run.py` re-exports every public name, so
`from ._run import RULE_SEVERITY` and the `_audit.py` PEP 562 forwarder
keep working unchanged.

Why this is its own module
--------------------------
Severity is consulted from four places — the human renderer, the JSON
record, the `--severity` filter and the exit code. When each of those
derived severity for itself, they drifted: the human renderer collapsed
every finding onto the run's MAXIMUM severity, so one §10 error
relabelled six standing §12/§13 warnings as `ERRO:` and printed
"7 error(s)" for 1 error + 6 warnings (measured on CI, PR #447). The
downstream masking layer reads severity off that very prefix
(`_audit_masking.is_error_line`), so a renderer bug became a wrong
error COUNT in the audit-all summary — a layer whose own docstring
already said "a run with 7 warnings and 1 error is not 8 errors".

One function (`severity_of`) is now the only place a violation's
severity is decided.
"""

from __future__ import annotations

__all__ = [
    "RULE_SEVERITY",
    "SEVERITY_ORDER",
    "EMIT_LEVEL",
    "severity_of",
    "severity_counts",
    "format_severity_counts",
]

# Severity tiers — used by --severity to gate which findings are reported.
#
# Per 2026-05-06 directive: any rule that has been live long enough to ship a
# documented spec is `error` (CI must fail). Demote a rule back to `warn` only
# after a concrete false-positive lands on develop. `info` is reserved for
# purely advisory categorizations (pass-through entry-points) that cannot
# describe a violation.
RULE_SEVERITY: dict[str, str] = {
    "§1": "error",
    "§1a": "error",
    "§1b": "error",
    "§1c": "info",
    "§1d": "error",
    "§1e": "info",
    # §1f — non-canonical verb synonym (slice 4). WARN while the fleet
    # migrates via the deprecation ladder; the baseline ratchet keeps
    # the drift from growing.
    "§1f": "warn",
    "§2": "error",
    "§3": "error",
    "§4": "error",
    # §4b — help not built from a CliHelp spec (slice 4). WARN: spec-built
    # help is the enforced construction method going forward, but the
    # existing free-form fleet migrates incrementally.
    "§4b": "warn",
    "§5": "error",
    # §6 (Python API ↔ MCP tool parity). Promoted back to error 2026-05-08
    # at user direction: severity must match the rule corpus's intent —
    # if it's a real violation, label it as one. False-positives on
    # utility-heavy packages should be addressed via per-package
    # allowlists (skip_rules in test_audit.py) or a tightened threshold,
    # not by globally demoting the rule to warn.
    "§6": "error",
    "§6a": "error",
    "§6b": "error",
    "§7": "error",
    "§8": "error",
    "§10": "error",
    # §10w — warn-tier sibling of §10, meaning "COULD NOT MEASURE
    # RELIABLY". Emitted when the runner cannot resolve the import budget
    # (see `_startup_speed_violation`). WARN, not error, so `audit-all`
    # exit stays 0 — but it is always PRINTED and always counted in the
    # warning tally, so an unmeasurable run never looks like a clean one.
    "§10w": "warn",
    "§11": "error",
    # §12 — canonical `gui {open,serve,status,stop}` command group.
    # WARN during ecosystem migration (figrecipe/writer/scholar/todo are
    # adopting incrementally as of 2026-07); promote once the fleet has
    # converged, same bake-in pattern as §1f / §4b.
    "§12": "warn",
    # §13 — self-maintenance commands must nest under a `dev` group.
    # WARN during the fleet migration to `<pkg> dev {daemon,cron,systemd,
    # hooks,skills,shell}`; promote to error once the fleet has converged,
    # same bake-in pattern as §1f / §4b / §12. The baseline ratchet
    # contains the existing drift so only NEW top-level self-maintenance
    # commands break CI.
    "§13": "warn",
    # PA-304: umbrella imports (scitex.X / import scitex) inside standalone
    # source. Drags umbrella __init__ + lazy re-export setup into every call
    # — measurable on NFS-mounted homes (HPC). Codified 2026-05-06 after the
    # scitex-scholar 2.7s cold-import surfaced on Spartan.
    "PA-304": "error",
    # PA-305: playwright.async_api imported without capture_debug_artifacts_async
    # call. Codified 2026-05-06 — every browser-automation decision point must
    # capture screenshot+HTML so selector regressions are diagnosable
    # post-mortem. See _skills/general/02_package/09_browser-automation-debugging.md.
    "PA-305": "error",
}

SEVERITY_ORDER = {"info": 0, "warn": 1, "error": 2}

# Registry severity -> the level word `_emit` renders. Every violation is
# emitted at ITS OWN level; nothing is promoted to the run's maximum.
EMIT_LEVEL = {"error": "error", "warn": "warning", "info": "info"}

# Unregistered rules default to `warn`: a rule whose severity nobody
# declared must not silently become an error, and must not silently
# vanish below the default `info` floor either.
_DEFAULT_SEVERITY = "warn"


def severity_of(violation) -> str:
    """The registered severity of one violation: 'error' / 'warn' / 'info'.

    THE single place a violation's severity is decided. Rendering,
    counting, filtering and the exit code all call this, so a finding
    can no longer be printed at one severity and tallied at another.
    """
    return RULE_SEVERITY.get(violation.rule, _DEFAULT_SEVERITY)


def max_severity(violations: list) -> str:
    """Highest severity present among violations; 'info' if list is empty.

    Drives the EXIT CODE (error -> 1) and the headline level. It must
    never drive how an individual finding is LABELLED — that is
    `severity_of`.
    """
    best = "info"
    for v in violations:
        sev = severity_of(v)
        if SEVERITY_ORDER[sev] > SEVERITY_ORDER[best]:
            best = sev
    return best


def severity_counts(violations: list) -> dict[str, int]:
    """Per-severity tally ``{'error': n, 'warn': n, 'info': n}``.

    All three keys are always present, at zero when empty. A tally that
    drops an empty band makes "zero errors" and "errors were not
    counted" indistinguishable to both a reader and a grep.
    """
    counts = {"error": 0, "warn": 0, "info": 0}
    for v in violations:
        counts[severity_of(v)] += 1
    return counts


def format_severity_counts(violations: list) -> str:
    """Render the tally as ``"1 error(s), 6 warning(s)"``.

    Error and warning counts are ALWAYS printed, even at zero, so the
    headline has one fixed shape — same contract as audit-project's
    summary line. `info` stays conditional; it is a much rarer band.
    """
    counts = severity_counts(violations)
    text = f"{counts['error']} error(s), {counts['warn']} warning(s)"
    if counts["info"]:
        text += f", {counts['info']} info"
    return text


def filter_violations(
    violations: list,
    rules: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    min_severity: str | None = None,
) -> list:
    """Apply --rule / --exclude / --severity gating to a violation list."""
    out: list = []
    threshold = SEVERITY_ORDER.get(min_severity or "info", 0)
    rules_set = {r.lstrip("§") for r in rules}
    excl_set = {r.lstrip("§") for r in exclude}
    for v in violations:
        rule_key = v.rule.lstrip("§")
        if rules_set and rule_key not in rules_set:
            continue
        if rule_key in excl_set:
            continue
        if SEVERITY_ORDER[severity_of(v)] < threshold:
            continue
        out.append(v)
    return out
