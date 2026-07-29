"""Central category-severity-override promotion pass (figure-family v1).

``SciTeXChecker._add`` and ``FMChecker._add`` already apply
``LinterConfig.category_severity_override`` at emit time, but EVERY plugin
checker shipped by **figrecipe** honours only ``per_rule_severity`` and
IGNORES the category override — its ``_emit`` reads
``config.per_rule_severity.get(rule.id)`` and nothing else. That is true of
all of them (``FigureMethodChecker``, ``RawMplBypassChecker``,
``StyleKwargChecker``, ``AxisAlignmentChecker``, and the rule-injecting
stat/heatmap/caption checkers), and it stays true of any checker figrecipe
adds later.

Those modules live in figrecipe (read-only here), so we cannot fix them
at the emit site. Instead ``lint_source`` extends every checker's issues
into one list, and ``SciTeXChecker.get_issues`` calls ``finalize_issues``
on that combined list as a final floor — so every rule carrying category
``figure`` or ``plot`` promotes uniformly under ``project-type: research``
regardless of which checker emitted it.

The floor is keyed on ``rule.category``, NOT on a rule-id range. Do not
document it as one: the id enumeration that used to live here and in
``config.py`` ("FM001-FM011 + FIG001") rotted the moment figrecipe added
FM016-FM019, which promoted correctly all along while the comment said
otherwise.

Precedence is preserved exactly: a rule the operator pinned in
``per_rule_severity`` is left untouched (per-rule WINS over the category
floor). The ``# stx-allow: STX-<ID>`` per-line opt-out is honoured upstream
in each checker's ``_add`` / ``_emit`` (an opt-out issue never reaches here).
"""

from __future__ import annotations

from dataclasses import replace


def promote_category_severity(issues, config):
    """Return *issues* with category-severity-override applied as a floor.

    Args:
        issues: list of ``Issue`` (each carries a ``rule`` with ``category``
            and ``severity``).
        config: ``LinterConfig`` — reads ``category_severity_override`` (the
            category→severity floor) and ``per_rule_severity`` (per-rule pins
            that WIN over the floor).

    Returns:
        A new list. Issues whose rule is pinned in ``per_rule_severity`` are
        passed through unchanged; otherwise, if the rule's category has an
        override, the issue's rule severity is replaced with it.
    """
    cat_override = getattr(config, "category_severity_override", {}) or {}
    if not cat_override:
        return issues

    per_rule = getattr(config, "per_rule_severity", {}) or {}
    out = []
    for issue in issues:
        rule = issue.rule
        # Per-rule pin wins over the category floor — leave it as emitted.
        if rule.id in per_rule:
            out.append(issue)
            continue
        sev = cat_override.get(rule.category)
        if sev and sev != rule.severity:
            issue = replace(issue, rule=replace(rule, severity=sev))
        out.append(issue)
    return out


def finalize_issues(issues, config):
    """Apply the category-severity floor, then sort — the ONE finalize step.

    ``SciTeXChecker.get_issues`` has two exit paths (script files, which also
    emit the STX-S00x structural rules, and non-script files, which do not).
    Both must finalize IDENTICALLY. They did not: the non-script early-return
    skipped :func:`promote_category_severity` altogether, so in a
    ``project-type: research`` repo any file under a configured ``script_dirs``
    / ``library_dirs`` entry (``scripts/`` — where a research repo's figure
    code actually lives) reported rules emitted via ``_add`` (FM001-FM009,
    P001-P005) as ERROR while every figrecipe-plugin-emitted rule in the SAME
    file (FM010/FM011/FM016/FM019, P006-P009) stayed WARNING. Reported by
    paper-scitex-clew, 2026-07-29. Keeping the finalize in one function is what
    makes that class of divergence impossible to reintroduce.

    Args:
        issues: the combined issue list (engine + plugin checkers).
        config: ``LinterConfig``.

    Returns:
        The promoted list, sorted errors-first then by line.
    """
    from .rules import SEVERITY_ORDER

    issues = promote_category_severity(issues, config)
    issues.sort(key=lambda i: (-SEVERITY_ORDER[i.rule.severity], i.line))
    return issues


__all__ = ["promote_category_severity", "finalize_issues"]

# EOF
