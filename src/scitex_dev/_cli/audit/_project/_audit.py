"""Project-structure auditor — engine + rules.

Rules cover the automatable items from
`scitex-dev/src/scitex_dev/_skills/general/02_package/01_project-structure-root.md`
(and its sibling `scientific/02_research-project_01_project-structure.md`).

Numbering: ``PS<§><idx>`` (PS = Project Structure), e.g. PS-201 = §2 rule 01.
Mirrors the ``PA<n>`` / ``SK<n>`` / ``M<n>`` pattern of sibling auditors.

This file is the public-API facade for the project-structure auditor.
Implementation was split across sibling modules (issue #103) — pure
refactor, zero behaviour change. Imports below preserve the original
public surface so consumers reading via
``from scitex_dev._cli.audit._project._audit import X`` keep working.
"""

from __future__ import annotations

from pathlib import Path

import click

# Re-exported symbols so internal callers and external tests that read
# `from scitex_dev._cli.audit._project._audit import X` keep working
# after the split.
from ._checks import (
    _check_docs_structure,
    _check_empty_test_dirs,
    _check_loose_top_level_tests,
    _check_mirror,
    _check_placeholder_tests,
    _check_tests_subdir_convention,
    _check_top_level,
    _suggest_test_location,
    _test_has_src_match,
    check_codecov_target,
)
from ._constants import (
    _FORBIDDEN_TOP_DIRS,
    _JUNK_FILE_RE,
    _KNOWN_TEST_SUBDIRS,
    _META_TESTS_AT_ROOT,
    _MIRROR_EXEMPT_CATEGORIES,
    _PRIVATE_TEST_RE,
    _PUBLIC_TEST_RE,
    _WALK_BLACKLIST_RE,
    _is_blacklisted,
)
from ._discovery import (
    _has_py,
    _import_name,
    _is_git_ignored,
    _resolve_repo_root,
    _resolve_repo_root_with_rule,
    _src_pkg_dir,
    _tests_root,
)
from ._registry import RULES, Rule
from ._violation import Violation

__all__ = [
    "RULES",
    "Rule",
    "Violation",
    "audit_project",
    "check_codecov_target",
]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def audit_project(
    distribution: str,
    *,
    repo: Path | None = None,
    json_out: bool = False,
    rules: set[str] | None = None,
    severity: str = "error",
    resolved_via: str | None = None,
) -> int:
    """Audit `<distribution>` against the project-structure checklist.

    Parameters
    ----------
    distribution : str
        Distribution name (e.g. ``"scitex-io"``).
    repo : Path, optional
        Repo root. Defaults to the result of locating the installed package.
    json_out : bool
        Emit machine-readable output on stdout.
    rules : set of str, optional
        If given, only run these rule codes.
    severity : {"error","warning","info"}
        Minimum severity to print AND to drive the exit code.
        - ``"error"``  (default): print E findings only; exit 1 iff ≥1 E.
        - ``"warning"``: print E + W findings; exit 1 iff ≥1 E.
        - ``"info"``: print everything; exit 1 iff ≥1 E.
        W and I findings never fail CI on their own.
    resolved_via : str, optional
        Which resolution rule produced ``repo`` when the CALLER already
        resolved it (``"explicit"`` / ``"cwd"`` / ``"registry"`` — see
        ``.._target_tree.resolve_target_tree``). Overrides the label this
        function would infer, so the resolved-tree banner reports the
        rule that actually picked the tree. When omitted, the label
        comes from the internal resolution (``explicit`` for a passed
        ``repo``, else ``cwd`` / ``import`` / ``proj-guess``).

    Returns
    -------
    int
        Exit code: 0 = no E-level violations, 1 = ≥1 E violation, 2 = could not locate.
    """
    repo_root, _rule = _resolve_repo_root_with_rule(distribution, repo)
    via = resolved_via or _rule
    violations: list[Violation] = []

    from ._resolved_tree import resolved_context, surface_resolved_tree
    resolved_ctx = resolved_context(repo_root)
    if repo_root is None:
        if json_out:
            import json as _json

            click.echo(
                _json.dumps(
                    {
                        "distribution": distribution,
                        "repo": None,
                        **resolved_ctx,
                        "resolved_via": via,
                        "violations": [],
                    },
                    indent=2,
                )
            )
            return 2
        click.echo(
            f"audit-project: cannot locate repo root for '{distribution}' "
            "(is it installed in editable mode, or pass --repo PATH?)",
            err=True,
        )
        return 2

    surface_resolved_tree(distribution, resolved_ctx, json_out, via=via)

    # Category-aware skip — see `should_skip_audit` in _ecosystem._core.
    try:
        from ...._ecosystem import ECOSYSTEM, should_skip_audit
    except ImportError:
        ECOSYSTEM = {}
        should_skip_audit = lambda *_a, **_k: (False, "")  # noqa: E731
    skip, reason = should_skip_audit(distribution, "audit-project")
    if skip:
        if not json_out:
            from .._emit import emit as _emit_skip

            _emit_skip("skip", f"{distribution}: {reason}")
        return 0
    info = ECOSYSTEM.get(distribution, {})
    category = info.get("category", "library")
    skip_mirror = category in _MIRROR_EXEMPT_CATEGORIES

    from ._run_checks import run_checks

    run_checks(repo_root, distribution, violations, skip_mirror=skip_mirror)

    if rules:
        violations = [v for v in violations if v.rule in rules]

    # Project-type dispatch: drop findings for rule families that don't
    # apply to this project (PS rules only fire for `pip` projects, RP
    # rules only for `research`). Honours the user's `audit.skip` list too.
    from .._config import load_config

    cfg = load_config(repo_root)
    # Track findings that the project-type filter would have dropped —
    # specifically PS-103 violations on `deferred`-type projects. The
    # auditor doesn't fire them (deferred opts out) but we surface a
    # one-line warning so the operator has a visible TODO list when
    # revisiting cleanup.
    deferred_dropped: list[Violation] = (
        [v for v in violations if v.rule == "PS-103"]
        if "deferred" in cfg.project_types
        else []
    )

    # Leaf-side package-type CAPABILITY knob (operator directive 2026-06-22):
    # a declared `audit.capabilities` entry (e.g. `no-umbrella`) skips the
    # rules that do not fit the package TYPE — with a VISIBLE
    # "skipped (declared capability: X)" notice, NOT a silent pass and NOT a
    # blanket `audit.skip`. Each capability gates a FIXED rule set
    # (CAPABILITY_RULES), so this can never silence an unrelated rule. We
    # compute the skip BEFORE the project-type/skip filter so the notice
    # reflects exactly what the capability dropped.
    from .._config import capability_for_rule

    capability_skipped: list[tuple[str, str]] = []  # (rule, capability)
    if cfg.capabilities:
        kept: list[Violation] = []
        seen: set[tuple[str, str]] = set()
        for v in violations:
            cap = capability_for_rule(v.rule)
            if cap is not None and cfg.has_capability(cap):
                key = (v.rule, cap)
                if key not in seen:
                    seen.add(key)
                    capability_skipped.append(key)
                continue
            kept.append(v)
        violations = kept

    violations = [
        v for v in violations if cfg.applies(v.rule) and v.rule not in cfg.skip
    ]

    # Severity filtering: print everything ≥ the requested floor.
    _floor = {"error": {"E"}, "warning": {"E", "W"}, "info": {"E", "W", "I"}}
    visible_set = _floor.get(severity, _floor["error"])
    visible = [v for v in violations if v.severity in visible_set]
    n_errors = sum(1 for v in violations if v.severity == "E")
    exit_code = 1 if n_errors > 0 else 0

    if json_out:
        import json as _json

        click.echo(
            _json.dumps(
                {
                    "distribution": distribution,
                    "repo": str(repo_root),
                    **resolved_ctx,
                    "resolved_via": via,
                    "violations": [
                        {
                            "rule": v.rule,
                            "where": v.where,
                            "detail": v.detail,
                            "severity": v.severity,
                        }
                        for v in visible
                    ],
                    "capability_skips": [
                        {"rule": rule, "capability": cap}
                        for rule, cap in capability_skipped
                    ],
                    "exit_code": exit_code,
                    "errors": n_errors,
                },
                indent=2,
            )
        )
        return exit_code

    from ...._audit_disclaimer import emit_disclaimer, emit_skill_hints

    def _emit_deferred_reminder() -> None:
        if not deferred_dropped:
            return
        click.echo(
            f"  [defer] {distribution}: {len(deferred_dropped)} PS-103 "
            f"finding(s) suppressed by `project-type: deferred`. "
            f"Re-review when time permits — entries currently at root "
            f"that the strict baseline would flag:",
            err=True,
        )
        for v in deferred_dropped[:10]:
            basename = Path(v.where).name
            click.echo(f"    - {basename}", err=True)
        if len(deferred_dropped) > 10:
            click.echo(
                f"    … +{len(deferred_dropped) - 10} more (run with "
                f"`--severity warning` against a non-deferred config to see all)",
                err=True,
            )

    from .._emit import emit as _emit

    def _emit_capability_skips() -> None:
        # Route via click.echo(err=True) — NOT _emit("info", ...) — so the
        # notice is ALWAYS visible: the audit logger's default level is
        # WARNING, which would swallow an info/skip headline. The operator
        # requires this skip to be visible, not silent. Mirrors the
        # always-printed `_emit_deferred_reminder` precedent.
        for rule, cap in capability_skipped:
            click.echo(
                f"  [capability] {distribution}: {rule} skipped "
                f"(declared capability: {cap})",
                err=True,
            )

    if not visible:
        # No findings at the requested severity floor. Name the tree we
        # graded, exactly as the violation headline below does: a CLEAN
        # result is precisely the one nobody double-checks, so it is the
        # one that must say what it read. Resolution can land on a tree
        # that isn't the commit under test (an editable install or the
        # `~/proj/<name>` guess — see `_resolve_repo_root`), and a green
        # "no violations" for the WRONG tree is a confident lie. Printing
        # the root makes that self-evident instead of silent.
        # `_emit("info", ...)` would NOT do: the audit logger's default
        # level is WARNING and swallows info (see `_emit_capability_skips`).
        _emit(
            "success",
            f"{distribution} ({repo_root}): no project-structure violations",
        )
        _emit_capability_skips()
        _emit_deferred_reminder()
        emit_disclaimer()
        return exit_code

    n_w = sum(1 for v in visible if v.severity == "W")
    n_i = sum(1 for v in visible if v.severity == "I")
    headline_level = "error" if exit_code else "warning"
    summary = f"{distribution} ({repo_root}): {n_errors} error(s)"
    if n_w:
        summary += f", {n_w} warning(s)"
    if n_i:
        summary += f", {n_i} info"
    _emit(headline_level, summary)
    for v in visible:
        sev = (
            "error"
            if getattr(v, "severity", "W") == "E"
            else ("warning" if getattr(v, "severity", "W") == "W" else "info")
        )
        _emit(sev, v.format())
    _emit_capability_skips()
    _emit_deferred_reminder()
    emit_disclaimer()
    emit_skill_hints()
    return exit_code
