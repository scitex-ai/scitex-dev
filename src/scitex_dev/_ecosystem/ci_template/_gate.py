#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Branch-protection compatibility gate — the refusal and its remedy.

The gate itself is one comparison (are the LIVE required status-check
contexts a subset of what the new ``ci.yml`` will publish?) and refusing on
a mismatch is unambiguously right: deleting the legacy workflows without
reconciling protection leaves every PR in that repo waiting forever on a
context nothing will ever emit. GitHub does not surface that as an error —
the merge button simply never turns green.

What was WRONG was the message. Measured on scitex-hub, 2026-07-28:
protection required the BARE names (``pytest-matrix-on-ubuntu-py3.11``,
``audit``) because they were emitted by standalone workflows, while the
``workflow_call`` caller emits the PREFIXED form
(``pytest-matrix / pytest-matrix-on-ubuntu-py3.11``). The old message said
"update branch protection alongside this migration" and left the operator
to derive the mapping by hand, per branch, from a repr'd list.

This module renders the refusal as a WORKSHEET: the exact old names, the
exact new names, the old→new correspondence where one exists, which
branches are affected, and the ``gh`` call that fixes it. No bypass is
added — ``--skip-required-check-gate`` already exists, is documented as
dangerous, and does not fix anything the message asks for.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence

from ._errors import ApplyError

#: Separator GitHub renders between a caller job id and the reusable job
#: name when a workflow is invoked via ``workflow_call``.
CALLER_SEPARATOR = " / "


def suggest_new_context(old_context: str, emitted: Sequence[str]) -> Optional[str]:
    """The emitted context that REPLACES *old_context*, if any.

    The migration's whole shape is bare-name -> ``"<caller-job-id> / <name>"``,
    so a live required context is matched against the suffix of each emitted
    context. Returns ``None`` when nothing emitted corresponds — a genuinely
    retired check, which must be REMOVED from protection rather than renamed.
    """
    for candidate in emitted:
        if CALLER_SEPARATOR not in candidate:
            continue
        if candidate.split(CALLER_SEPARATOR, 1)[1] == old_context:
            return candidate
    return None


def _mapping_lines(
    missing: Dict[str, List[str]], emitted: Sequence[str]
) -> List[str]:
    """The old->new worksheet rows, de-duplicated across branches."""
    seen: List[str] = []
    for _branch, contexts in sorted(missing.items()):
        for ctx in contexts:
            if ctx not in seen:
                seen.append(ctx)
    rows: List[str] = []
    for old in seen:
        new = suggest_new_context(old, emitted)
        if new is None:
            rows.append(
                f"    {old!r}  ->  (nothing emitted matches; this check is "
                "RETIRED — remove it from branch protection)"
            )
        else:
            rows.append(f"    {old!r}  ->  {new!r}")
    return rows


def render_gate_failure(
    missing: Dict[str, List[str]],
    emitted: Sequence[str] = (),
    owner_repo: Optional[str] = None,
) -> str:
    """Full operator-facing refusal text. Pure function — tests read it."""
    branches = sorted(missing)
    branch_word = "branches" if len(branches) > 1 else "branch"
    slug = owner_repo or "<owner>/<repo>"

    lines: List[str] = [
        "branch-protection gate failure — required contexts not in emitted set:"
    ]
    for branch in branches:
        lines.append(f"  {branch}: missing {sorted(missing[branch])!r}")
    lines += [
        "",
        f"AFFECTED {branch_word.upper()}: {', '.join(branches)}",
        "",
        "REFUSING TO APPLY. Deleting the legacy workflows without reconciling",
        "branch protection permanently deadlocks EVERY PR in this repo: GitHub",
        "keeps waiting for a required context that nothing will ever publish,",
        "and reports it as 'expected' rather than as a failure.",
        "",
        "WHY THE NAMES CHANGED: the new ci.yml calls the org-level reusable",
        "workflows via `workflow_call`, and GitHub renders each check-run",
        f"context as '<caller-job-id>{CALLER_SEPARATOR}<reusable job name>'. The",
        "BARE names your protection requires today were published by the",
        "standalone workflows this migration removes.",
        "",
        "OLD (required now)  ->  NEW (emitted by the new ci.yml):",
    ]
    lines += _mapping_lines(missing, emitted)
    lines += [
        "",
        "FULL set of contexts the new ci.yml will emit:",
    ]
    lines += [f"    {name!r}" for name in emitted] or ["    (none)"]
    lines += [
        "",
        "FIX: update branch protection to the NEW names BEFORE (or in the same",
        f"change as) this migration, on {'each of ' if len(branches) > 1 else ''}"
        f"{', '.join(branches)}:",
    ]
    for branch in branches:
        lines.append(
            f"    gh api -X PATCH "
            f"repos/{slug}/branches/{branch}/protection/required_status_checks "
            "\\"
        )
        lines.append("         -f strict=false " + " ".join(
            f"-f 'contexts[]={_new_name_for(ctx, emitted)}'"
            for ctx in sorted(missing[branch])
        ))
    lines += [
        "",
        "Then re-run this apply. `--skip-required-check-gate` is NOT the fix:",
        "it does not touch protection, it only moves the deadlock to after the",
        "workflows are already gone.",
    ]
    return "\n".join(lines)


def _new_name_for(old: str, emitted: Sequence[str]) -> str:
    new = suggest_new_context(old, emitted)
    return new if new is not None else f"<DROP {old}>"


class BranchProtectionGateError(ApplyError):
    """The gate found required contexts the new caller won't publish.

    Carries the structured data (``missing`` / ``emitted`` / ``owner_repo``)
    alongside the rendered message so a caller can re-render it differently
    without re-deriving the mapping.
    """

    def __init__(
        self,
        missing: Dict[str, List[str]],
        emitted: Optional[Iterable[str]] = None,
        owner_repo: Optional[str] = None,
    ):
        self.missing = missing  # {branch: [missing_context, ...]}
        self.emitted: List[str] = sorted(emitted or [])
        self.owner_repo = owner_repo
        super().__init__(render_gate_failure(missing, self.emitted, owner_repo))


# EOF
