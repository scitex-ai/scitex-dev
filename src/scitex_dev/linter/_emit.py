"""The ONE emission gate every finding passes through — engine and plugins.

``SciTeXChecker._add`` used to own these gates privately: a leaf plugin that
emitted the same rule had to re-implement them and could drift. A rule that
moves from the engine to its owning leaf (``_rules/_handover.py``) must keep
EXACTLY the same per-rule behaviour, so the gates live here and both sides
call :func:`add_issue` (exported as ``scitex_dev.linter.spi.add_issue``).

Gates, in order:

1. ``requires`` — the rule's runtime package must be importable, else the
   finding is dropped and the skip is tallied for the fail-loud health notice.
2. ``config.disable`` — project-level disable list.
3. ``# stx-allow[: ids]`` on the source line.
4. Severity — ``config.per_rule_severity`` pin, else the
   ``config.category_severity_override`` floor (e.g. research projects).
"""

from __future__ import annotations

from dataclasses import replace

from ._issue import Issue
from ._source_helpers import _is_allowed_by_comment

__all__ = ["add_issue"]


def add_issue(
    issues: list, rule, line: int, col: int, source_line: str, config, available=None
) -> None:
    """Append an ``Issue`` for *rule* to *issues* unless a gate drops it.

    Args:
        issues: the list to append to (a checker's ``.issues``).
        rule: the ``Rule``; ``None`` is a no-op (an optional rule missing
            from a lean environment).
        line, col: 1-based line, 0-based column of the finding.
        source_line: the source text of *line* (used by ``# stx-allow``).
        config: the resolved ``LinterConfig``.
        available: package-availability map (``_packages.detect()``);
            computed when omitted.
    """
    if rule is None:
        return
    if available is None:
        from ._packages import detect

        available = detect()
    if rule.requires and not available.get(rule.requires, False):
        # Pillar-0 fail-loud: tally the silent skip so the health module can
        # report it — otherwise the `requires=` gate evaporates coverage
        # with zero indication (the 2026-06-12 ripple-wm class).
        try:
            from ._health import record_rule_skip

            record_rule_skip(rule.requires)
        except Exception:  # pragma: no cover
            pass
        return
    if rule.id in config.disable:
        return
    if _is_allowed_by_comment(source_line, rule.id):
        return
    sev = config.per_rule_severity.get(rule.id)
    if not sev:
        # Category-wide floor (research project-type flips io/path to
        # error). The per-rule pin above still wins.
        cat_override = getattr(config, "category_severity_override", {}) or {}
        sev = cat_override.get(rule.category)
    if sev:
        rule = replace(rule, severity=sev)
    issues.append(Issue(rule=rule, line=line, col=col, source_line=source_line))


# EOF
