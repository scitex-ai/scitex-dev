"""CI-template applier — THE single canonical CI mechanism for scitex-* repos.

Renders/deploys the one per-repo workflow ``ci.yml``: a thin caller that
delegates every job body to the org-level reusable workflows in
``scitex-ai/.github@main`` (operator decision, 2026-07-21 — a shared
workflow cannot drift per-repo). ``scitex-dev ci runner register`` is a
thin alias over this module; no second template body exists to drift.

Lives under the underscore-private ``scitex_dev._ecosystem`` namespace
because the existing public ``scitex_dev.ecosystem`` (no underscore) is
a flat re-export module, not a package. The Click wiring at
``scitex_dev._cli.ecosystem._cmds._ci_template`` imports from here.

Internal surface
----------------
``apply(repo_dir, ...) -> ApplyResult``
    Programmatic entry-point used by the Click wiring and by tests.

``emitted_job_names(python_versions)``
    Deterministic set of branch-protection-context strings the rendered
    caller publishes. Lives next to ``apply`` so the gate's intent and
    the template's content cannot drift.

``render(template_name, ...)``
    Pure substitution helper, exposed for tests.

Policy that used to live inline in ``_apply`` now has its own modules:
``_workflows`` (which files apply deletes / protects / skips, and WHY —
including the conditional protection lifted by a superseding caller job)
and ``_gate`` (the branch-protection refusal and its old→new remediation
worksheet).

The vendored template lives under ``ci_template/templates/``. The
directory ships as package-data via ``pyproject.toml`` so the installed
wheel can read it without a source checkout.
"""

from __future__ import annotations

from ._apply import (
    ApplyError,
    ApplyResult,
    BranchProtectionGateError,
    apply,
    emitted_job_names,
    render,
)
from ._gate import render_gate_failure, suggest_new_context
from ._workflows import (
    WorkflowPlan,
    eligible_for_delete,
    plan_workflow_changes,
    superseded_protected_prefixes,
)

__all__ = [
    "apply",
    "ApplyError",
    "ApplyResult",
    "BranchProtectionGateError",
    "eligible_for_delete",
    "emitted_job_names",
    "plan_workflow_changes",
    "render",
    "render_gate_failure",
    "suggest_new_context",
    "superseded_protected_prefixes",
    "WorkflowPlan",
]
