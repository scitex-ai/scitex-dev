"""Static auditor for SciTeX `_skills/<pip-name>/` directories — engine.

Rules cover the automatable items from
`scitex-python/src/scitex/_skills/general/03_interface/04_skills/12_quality-checklist.md`.

Numbering: `SK<§><idx>` (e.g. SK-101 = §1 rule 01). Mirrors the `PA<n>` /
`M<n>` rule-numbering used by the sibling `_cli_audit_api` and
`_cli_audit/_mcp_audit` modules.

The rule corpus, the `Violation` model, tree discovery and the per-file
checks were split into sibling modules (pure extraction, zero behaviour
change) to keep this file within the repo file-size budget. The imports
below preserve the original public surface, so consumers reading
`from ..._skills._audit import X` keep working.
"""

from __future__ import annotations

from pathlib import Path

import click

from .._emit import emit as _emit
from . import _audit_v2 as _v2
from ._checks import (
    _check_frontmatter,
    _check_header_footer,
    _check_import_alias,
    _check_index_links,
    _check_layout,
    _check_leaf_size,
    _check_naming,
    _check_skill_md_size,
)
from ._discovery import _import_name, _locate_skills_dir, _locate_skills_dir_under
from ._registry import RULES, Rule
from ._violation import Violation

__all__ = [
    "RULES",
    "Rule",
    "Violation",
    "audit_skills",
]


def _collect_violations(
    distribution: str,
    canonical_dir: Path,
    inspected: "set[Path] | None" = None,
) -> list[Violation]:
    """Run all per-file rules on a fully-discovered `_skills/<dist>/` dir."""
    violations: list[Violation] = []
    skill_md = canonical_dir / "SKILL.md"

    # SKILL.md checks.
    _check_header_footer(skill_md, violations)
    _check_frontmatter(skill_md, violations, is_skill_md=True)
    _check_skill_md_size(skill_md, violations)
    _check_index_links(skill_md, canonical_dir, violations)
    _check_import_alias(skill_md, violations)
    for code, where, detail in _v2.check_skill_md_frontmatter(skill_md, distribution):
        violations.append(Violation(code, where, detail))

    # File-presence (SK-105–SK-111).
    for code, where, detail in _v2.check_file_presence(canonical_dir, distribution):
        violations.append(Violation(code, where, detail))

    # Naming check covers the whole directory at once.
    _check_naming(canonical_dir, violations)

    # Per-leaf checks.
    for leaf in sorted(canonical_dir.iterdir()):
        if not leaf.is_file() or leaf.suffix != ".md" or leaf.name == "SKILL.md":
            continue
        # The DENOMINATOR, filled in place like `violations`. Recorded HERE —
        # past the skip — so it counts leaves actually CHECKED rather than
        # directory entries encountered. Counting the latter would make an
        # empty run of a directory full of non-skill files look like coverage.
        if inspected is not None:
            inspected.add(leaf)
        _check_header_footer(leaf, violations)
        _check_frontmatter(leaf, violations, is_skill_md=False)
        _check_leaf_size(leaf, violations)
        _check_import_alias(leaf, violations)
        for code, where, detail in _v2.check_leaf_frontmatter(leaf, distribution):
            violations.append(Violation(code, where, detail))

    return violations


_FIXABLE = {"SK-705", "SK-709", "SK-710"}


def _apply_fixes(
    distribution: str, canonical_dir: Path, violations: list[Violation]
) -> dict[str, set[str]]:
    """Apply fixes; return {file_path: {codes_fixed}}."""
    by_file: dict[Path, set[str]] = {}
    for v in violations:
        if v.rule not in _FIXABLE:
            continue
        by_file.setdefault(Path(v.where), set()).add(v.rule)
    fixed_log: dict[str, set[str]] = {}
    skill_md = canonical_dir / "SKILL.md"
    for path, codes in by_file.items():
        if path == skill_md:
            done = _v2.fix_skill_md(path, distribution, codes)
        else:
            done = _v2.fix_leaf(path, distribution, codes)
        if done:
            fixed_log[str(path)] = done
    return fixed_log


def audit_skills(
    distribution: str,
    *,
    json_out: bool = False,
    rules: set[str] | None = None,
    fix: bool = False,
    skills_dir: Path | None = None,
    repo_root: Path | None = None,
    resolved_via: str | None = None,
) -> int:
    """Audit `<distribution>` against the skills checklist. Warn-only.

    Parameters
    ----------
    distribution : str
        Distribution name (e.g. ``"scitex-io"``).
    json_out : bool
        Emit machine-readable output on stdout.
    rules : set of str, optional
        If given, only run these rule codes.
    skills_dir : Path, optional
        Explicit skills directory. Highest precedence — bypasses all
        resolution (used by tests operating on a synthetic tree).
    repo_root : Path, optional
        Explicit repo root to audit (from ``--path`` via the shared
        ``resolve_target_tree``). When given, the skills tree is located
        UNDER this root (``src/<import_name>/_skills/<dist>`` or flat)
        instead of the installed / registry location — closing the
        wrong-tree footgun for audit-skills the same way it is closed for
        audit-project/django/python-apis.
    resolved_via : str, optional
        Which rule picked ``repo_root`` (``explicit`` / ``cwd`` /
        ``registry``) — surfaced in the resolved-tree banner.

    Returns
    -------
    int
        Exit code: 0 = no violations, 1 = violations, 2 = could not locate.
    """
    # Category-aware skip — see `should_skip_audit` in _ecosystem._core.
    try:
        from ...._ecosystem import should_skip_audit
    except ImportError:
        should_skip_audit = lambda *_a, **_k: (False, "")  # noqa: E731
    skip, reason = should_skip_audit(distribution, "audit-skills")
    if skip:
        if json_out:
            import json

            click.echo(
                json.dumps(
                    {
                        "distribution": distribution,
                        "skills_dir": None,
                        "skipped": reason,
                        "violations": [],
                    },
                    indent=2,
                )
            )
        else:
            _emit("skip", f"{distribution}: {reason}")
        return 0

    if skills_dir is None:
        if repo_root is not None:
            skills_dir = _locate_skills_dir_under(repo_root, distribution)
        else:
            skills_dir = _locate_skills_dir(distribution)

    # Anti wrong-tree footgun: announce the resolved checkout BEFORE any
    # results whenever a tree was resolved via `--path` / cwd / registry
    # (mirrors audit-project's #392 banner). Human rail only; no-op under
    # --json and when nothing was resolved.
    if repo_root is not None and not fix:
        from .._project._resolved_tree import (
            resolved_context,
            surface_resolved_tree,
        )

        surface_resolved_tree(
            distribution,
            resolved_context(repo_root),
            json_out,
            via=resolved_via,
        )
    violations: list[Violation] = []
    # The DENOMINATOR. Without it "no skills violations" reads identically
    # whether forty leaves were checked or the directory was empty — and the
    # empty case renders as the clean case. Same treatment the CLI auditor has
    # had since 2026-07-29 (`_summary/_coverage.py`) and the API auditor
    # gained in #654; this was the last leg reporting a verdict with no scope.
    inspected: set[Path] = set()

    canonical_dir = _check_layout(skills_dir, distribution, violations)

    if canonical_dir is not None:
        violations.extend(
            _collect_violations(distribution, canonical_dir, inspected)
        )

        # --fix: apply auto-fixable rules and re-collect.
        if fix:
            fixed_log = _apply_fixes(distribution, canonical_dir, violations)
            for path_str, codes in sorted(fixed_log.items()):
                click.echo(f"fixed {path_str}: {', '.join(sorted(codes))}")
            # Re-run checks after fixes.
            violations = []
            # RESET the denominator with the violations. The re-collect is a
            # second full pass, so keeping the first pass's leaves would double
            # every count on a --fix run — a denominator that grows because the
            # tool ran twice is worse than none, since it reads as more coverage.
            inspected.clear()
            canonical_dir2 = _check_layout(skills_dir, distribution, violations)
            if canonical_dir2 is not None:
                violations.extend(
                    _collect_violations(distribution, canonical_dir2, inspected)
                )

    if rules:
        violations = [v for v in violations if v.rule in rules]

    if json_out:
        import json

        click.echo(
            json.dumps(
                {
                    "distribution": distribution,
                    "skills_dir": str(skills_dir) if skills_dir else None,
                    "violations": [
                        {"rule": v.rule, "where": v.where, "detail": v.detail}
                        for v in violations
                    ],
                },
                indent=2,
            )
        )
        return 0 if not violations else 1

    if skills_dir is None:
        # Same as audit-api: not every package ships a `_skills/` directory,
        # and audit-all may run before `pip install -e .`. Skip rather than
        # fail.
        _emit(
            "info",
            f"{distribution}: no `_skills/` directory found — skipped.",
            err=True,
        )
        return 0

    from ...._audit_disclaimer import emit_disclaimer, emit_skill_hints

    if not violations:
        # REFUSE rather than pass when nothing was checked. Zero leaves is not
        # a clean skills tree, it is an unanswered question, and it renders
        # exactly like a package with forty conforming leaves. Same condition
        # as `SurfaceCoverage.is_answerable` and the API auditor's guard, so
        # the three legs cannot disagree about what licenses a verdict.
        if not inspected:
            _emit(
                "error",
                f"{distribution}: not-auditable: the skills walker inspected 0 "
                "leaves, so no verdict is possible (is the skills directory "
                "empty, or did layout resolution pick the wrong tree?)",
                err=True,
            )
            return 1
        # WITH ITS ROOT, not only its count. A count alone cannot be checked by
        # a reader: #654 measured a scan reporting a plausible 311 files from
        # site-packages while claiming the checkout, and only the root made
        # that visible.
        _emit(
            "success",
            f"{distribution}: no skills violations "
            f"({len(inspected)} leaf/leaves inspected under {canonical_dir})",
        )
        emit_disclaimer()
        return 0

    # Category-named failure line — mirrors the clean line's
    # "no skills violations". See the note in _project/_audit.py.
    _emit("warning", f"{distribution}: skills: {len(violations)} violation(s)")
    for v in violations:
        _emit("warning", v.format())
    emit_disclaimer()
    emit_skill_hints()
    return 1
