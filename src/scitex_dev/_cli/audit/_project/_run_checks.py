"""Check-invocation sequence for the project-structure auditor.

Extracted from ``_audit.py`` (line-limit refactor) — pure move, no
behaviour change. ``audit_project`` stays the orchestrator/facade
(resolution, skip logic, filtering, output rails); this module owns the
single job of invoking every registered PS/RP check against a resolved
repo root, appending findings to ``violations``.
"""

from __future__ import annotations

from pathlib import Path

from ._checks import (
    _check_docs_structure,
    _check_empty_test_dirs,
    _check_mirror,
    _check_placeholder_tests,
    _check_tests_subdir_convention,
    _check_top_level,
    check_codecov_target,
)
from ._discovery import _src_pkg_dir
from ._violation import Violation


def run_checks(
    repo_root: Path,
    distribution: str,
    violations: list[Violation],
    *,
    skip_mirror: bool,
) -> None:
    """Run every project-structure check, appending to ``violations``."""
    _check_top_level(repo_root, violations)
    if not skip_mirror:
        _check_mirror(repo_root, distribution, violations)
        _check_placeholder_tests(repo_root, violations)
        _check_empty_test_dirs(repo_root, distribution, violations)
    _check_tests_subdir_convention(repo_root, distribution, violations)
    # RP-2xx: research projects mirror scripts/ ↔ tests/scripts/ instead of
    # src/<pkg>/ ↔ tests/<pkg>/. Fired only when `research` is in the
    # project-types; the PS package-publish rules drop for pure-research
    # (no `pip` ⇒ applies("PS-*") is False). See _check_research_mirror.
    from .._config import load_config as _load_cfg_for_research

    if "research" in _load_cfg_for_research(repo_root).project_types:
        from ._check_research_mirror import check_research_mirror

        check_research_mirror(repo_root, violations)
    _check_docs_structure(repo_root, violations)
    src_pkg = _src_pkg_dir(repo_root, distribution)
    if src_pkg is not None:
        from ._check_flat_layout import check_flat_layout, check_topical_clutter

        check_flat_layout(src_pkg, Violation, violations)
        check_topical_clutter(src_pkg, Violation, violations)
    from ._check_readme_badges import check_coverage_badge

    check_coverage_badge(repo_root, Violation, violations)
    from ._check_readme_badge_position import check_badge_position

    check_badge_position(repo_root, Violation, violations)
    from ._check_readme_sections import check_readme_sections

    check_readme_sections(repo_root, Violation, violations)
    from ._check_sphinx_html import check_sphinx_html

    check_sphinx_html(repo_root, Violation, violations)
    from ._check_env_example import check_env_example

    check_env_example(repo_root, Violation, violations)
    from ._check_examples import check_examples_conventions

    check_examples_conventions(repo_root, Violation, violations)
    from ._check_readme_structure import check_readme_structure

    check_readme_structure(repo_root, Violation, violations)
    check_codecov_target(repo_root, Violation, violations)
    # PS-HOOK-001: a `language: system` pre-commit hook invoking a Python tool
    # is a $PATH lottery — it resolves to whichever venv is active at commit
    # time. figrecipe's testmon hook ran ZERO tests fleet-wide while blocking
    # every Python commit; davinci-resolve-mcp's took >14 min per commit.
    from ._check_precommit_hooks import check_ps_hook_001_precommit_system_hooks

    check_ps_hook_001_precommit_system_hooks(repo_root, Violation, violations)
    from ._check_dev_extras_complete import check_dev_extras_complete

    check_dev_extras_complete(repo_root, Violation, violations)
    from ._check_optional_deps_guarded import check_ps148_optional_deps_guarded

    check_ps148_optional_deps_guarded(repo_root, distribution, Violation, violations)
    # PS-214/215: all-or-nothing extras + dead install-remedy strings.
    # See scitex-writer PR #322 (reference incident: editor = [] extra +
    # "pip install scitex-writer[editor]" remedy that installs nothing).
    from ._check_empty_extras import check_ps214_empty_extras

    check_ps214_empty_extras(repo_root, Violation, violations)
    from ._check_install_remedy_strings import check_ps215_broken_install_remedy

    check_ps215_broken_install_remedy(repo_root, distribution, Violation, violations)
    # PS-216: direct-URL/VCS deps in publishable metadata. PyPI/twine reject
    # direct references on upload (even inside extras), silently blocking the
    # release of an otherwise-green package.
    from ._check_no_url_deps import check_ps216_no_url_deps

    check_ps216_no_url_deps(repo_root, Violation, violations)
    # PS-220: `print(...)` in package source. SciTeX code must emit messages
    # through scitex-logging (aligned WARN:/ERRO:/SUCC: prefixes), never the
    # builtin print. AST-scans src/<pkg>/**.py; tests/scripts/examples/docs
    # excluded; `# noqa` opts a line out.
    from ._check_no_print import check_ps220_no_print

    check_ps220_no_print(repo_root, Violation, violations)
    # PS-221: [all]-closure on public optional-dependency extras. A public
    # extra must be `[all]` or bare only — every public extra must be a
    # subset of `all`, so `pip install <pkg>[all]` pulls everything public.
    from ._check_extras_all_closure import check_ps221_extras_all_closure

    check_ps221_extras_all_closure(repo_root, Violation, violations)
    # PS-225: extra NAMES restricted to {all, dev, docs}. PS-221 above makes
    # `[all]` complete; PS-225 removes the per-feature menu that made a
    # partial pin possible in the first place. Operator ruling 2026-08-02,
    # after `scitex-cards[mcp]` in container defs cost the fleet its board.
    from ._check_extras_allowlist import check_ps225_extras_allowlist

    check_ps225_extras_allowlist(repo_root, Violation, violations)
    # PS-222: `.scitex/<pkg-short>/` config-layout convention. Everything
    # directly under a package's local-state root is TRACKED except
    # `runtime/`, the one gitignored subdir; the primary config is always
    # named `config.yaml`, never a `<pkg-short>.yaml` alias, and a package
    # scope is always a directory (never a bare `.scitex/<pkg>.yaml` file).
    # W during bake-in; opt out only via `audit.exemptions` with a reason.
    from ._check_config_layout import check_ps222_config_layout

    check_ps222_config_layout(repo_root, Violation, violations)
    # PS-223: non-`runtime/` logs-path string literal in package source.
    # Package logs live under the gitignored `runtime/logs/` layer, never
    # directly under `~/.scitex/<pkg>/logs/` (the pre-#367/#433 location).
    # AST-scans src/<pkg>/**.py for path-token string literals; docstrings,
    # comments and whitespace-bearing description/help strings are spared.
    # W during bake-in; opt out only via `audit.exemptions` with a reason.
    from ._check_logs_path import check_ps223_logs_path

    check_ps223_logs_path(repo_root, Violation, violations)
    # PS-HOOK-010/011/012: agent guardrails must be DECLARED through the
    # `scitex_dev.hooks` federation rather than left implicit in shell.
    # -010 (W) a package ships agent-hook scripts but declares nothing;
    # -011 (E) a HookRule binds script/predicate to a path that is not there,
    #          i.e. a declared gate that cannot fire;
    # -012 (W) a HookRule's `reason` is a placeholder saying nothing.
    # Static AST scan; git-hook trees (`_hooks/`, `.githooks/`) are spared.
    from ._check_hook_rules import check_hook_rules

    check_hook_rules(repo_root, Violation, violations)
    # PS-218/PS-219: CLI-normalization conformance (items 4-5). Health-check
    # verb standardizes on `doctor` (`health` is a deprecated alias); version
    # standardizes on the `--version`/`-V` flag (not a `version` subcommand).
    # Both W during leaf migration. Detection is static (reads source, never
    # imports the leaf) and gated to never false-positive on `--version`.
    from ._check_doctor_health_naming import check_ps218_doctor_health_naming
    from ._check_version_flag import check_ps219_version_flag

    check_ps218_doctor_health_naming(repo_root, Violation, violations)
    check_ps219_version_flag(repo_root, Violation, violations)
    from ._check_console_script_core_deps import (
        check_ps213_console_script_core_deps,
    )

    check_ps213_console_script_core_deps(repo_root, distribution, Violation, violations)
    from ._check_hard_dep_overreach import check_ps149_hard_dep_overreach

    check_ps149_hard_dep_overreach(repo_root, distribution, Violation, violations)
    from ._check_umbrella_dep_and_integration import (
        check_ps139_umbrella_dep,
        check_ps140_integration_gate,
    )

    check_ps139_umbrella_dep(repo_root, Violation, violations)
    check_ps140_integration_gate(repo_root, distribution, Violation, violations)
    from ._check_ecosystem_boundary import check_ps183_ecosystem_boundary

    check_ps183_ecosystem_boundary(repo_root, distribution, Violation, violations)
    from ._check_audit_pin import check_audit_pin

    check_audit_pin(repo_root, Violation, violations)
    from ._check_workflows_naming import check_ps164_workflow_naming

    check_ps164_workflow_naming(repo_root, Violation, violations)
    # PS-169: GitHub-hosted runners forbidden (operator mandate 2026-07-14;
    # reland of closed PR #344). Only flags runners we can PROVE are hosted;
    # the self-hosted `fromJSON(vars.CI_RUNS_ON || '[...]')` idiom is clean.
    from ._check_hosted_runners import check_ps169_hosted_runners

    check_ps169_hosted_runners(repo_root, Violation, violations)
    # PS-224: every `runs-on` must name a destination the scitex-dev MACHINE
    # REGISTRY serves. Static, pre-merge, severity E — GitHub queues an
    # unmatchable job forever instead of rejecting it, so without this the
    # only symptom is a workflow that silently never runs (three scheduled
    # runs sat undispatched from 2026-05-15 while 17 runners idled).
    # Opt out one JOB at a time via `audit.exemptions` with a reason, keyed on
    # the job-qualified site `<workflow-path>::<job-id>` (the check loads the
    # config itself, as PS-222/223 do).
    from ._check_runner_destinations import check_ps224_runner_destinations

    check_ps224_runner_destinations(repo_root, Violation, violations)
    # PS-231: a leaf workflow that RE-IMPLEMENTS a reusable workflow the org
    # already provides. Operator ruling 2026-08-15: "we must stop allowing
    # duplicate workflows written in leaf packages" — hence a rule, not a
    # sweep. A copy silently opts OUT of fixes made org-side: the `scitex-ci`
    # runner-label defect was fixed in the org workflow that morning and all
    # 53 copies across 15 repos kept it. Callers and reusable DEFINITIONS
    # (`on: workflow_call`) are never flagged; a genuinely leaf-specific
    # variant takes a reasoned per-path `audit.exemptions` entry.
    from ._check_workflow_duplication import check_ps231_workflow_duplication

    check_ps231_workflow_duplication(repo_root, Violation, violations)
    from ._check_secret_env_prefix import check_ps168_secret_env_prefix

    check_ps168_secret_env_prefix(repo_root, distribution, Violation, violations)
    # PS-226..PS-229: the fleet-wide JobSpec declaration convention. A job
    # name is the systemd unit FILENAME, derived verbatim, so a dotted name
    # silently installs a second unit beside the hand-written one it was
    # meant to be (`sac.listen.service` vs the live `sac-listen.service`).
    # Static AST scan of src/<pkg>/**.py; the leaf is never imported.
    from ._check_job_naming import check_job_naming

    check_job_naming(repo_root, distribution, Violation, violations)
    # PS-230: retired role vocabulary in package PROSE. The same operator
    # decision as PS-226..229, applied to the words instead of the job ids —
    # credentials `primary/replica`, roles `controller/worker`, DB replication
    # `node/origin`. Scope is docstrings, comments and `src/**/*.md` only;
    # code is never graded, because a sweep cannot tell a live contract
    # (`master_host`, `--master`) from a stale word. W on landing.
    from ._check_naming_vocabulary import check_ps230_naming_vocabulary

    check_ps230_naming_vocabulary(repo_root, Violation, violations)
    from ._check_workflow_presence import check_ps165_workflow_presence
    from ._check_readme_badge_labels import check_ps166_readme_badge_labels

    check_ps165_workflow_presence(repo_root, Violation, violations)
    check_ps166_readme_badge_labels(repo_root, Violation, violations)
    from ._check_readme_badge_layout import check_ps167_readme_badge_layout

    check_ps167_readme_badge_layout(repo_root, Violation, violations)
    from ._check_local_state import (
        check_ps145_cross_package_read,
        check_ps146_pip_install_side_effect,
        check_ps147_eval_form_completion,
    )

    check_ps145_cross_package_read(repo_root, distribution, Violation, violations)
    check_ps146_pip_install_side_effect(repo_root, Violation, violations)
    check_ps147_eval_form_completion(repo_root, Violation, violations)
    # PS-182: rolled-own local-state path resolver (git-root/project-scope
    # precedence re-implemented instead of using scitex_config...local_state).
    from ._check_path_resolver import check_ps182_rolled_own_path_resolver

    check_ps182_rolled_own_path_resolver(repo_root, Violation, violations)
    # PS-PATH / PS-CLEW / PS-AGENT — paper-scitex-clew MVP lint set.
    # Artifact-gated (only fire when PATH.yaml / clew.add_claim /
    # scripts/agent/ are present); safe to run on every project type.
    # See PR #97 and operator directive 2026-06-01.
    from ._check_path_yaml import (
        check_ps_path_001_outer_wrapper,
        check_ps_path_002_bare_string_leaf,
    )
    from ._check_clew_claims import (
        check_ps_agent_001_agent_script_no_claims_json,
        check_ps_clew_001_add_claim_without_self_verify,
    )

    check_ps_path_001_outer_wrapper(repo_root, Violation, violations)
    check_ps_path_002_bare_string_leaf(repo_root, Violation, violations)
    check_ps_clew_001_add_claim_without_self_verify(repo_root, Violation, violations)
    check_ps_agent_001_agent_script_no_claims_json(repo_root, Violation, violations)
    # PS-173: ADR format — only fires when docs/adr/ exists (presence is
    # recommended, not mandated). Scope = all project kinds.
    from ._check_adr import check_ps173_adr_format

    check_ps173_adr_format(repo_root, violations)
    # PS-180: runtime/ separation discipline — only fires when
    # src/<pkg>/runtime/ exists on disk AND no .gitignore covers it.
    # Scope = all project kinds with a src/ layout.
    from ._check_runtime_separation import check_runtime_separation

    check_runtime_separation(repo_root, Violation, violations)
    # PS-217: skills CLI federation — fires when a leaf ships a hand-rolled
    # src/<pkg>/_cli/_skills.py that does NOT import scitex-dev's shared
    # skills_click_group primitive. WARN-only tracking signal for the
    # CLI-normalization fan-out. Scope = all project kinds with a src/ layout.
    from ._check_skills_federation import check_skills_federation

    check_skills_federation(repo_root, Violation, violations)
    if not skip_mirror:
        from ._check_smoke_e2e_layers import (
            check_ps211_smoke_layer,
            check_ps212_e2e_layer,
        )

        check_ps211_smoke_layer(repo_root, Violation, violations)
        check_ps212_e2e_layer(repo_root, Violation, violations)


__all__ = ["run_checks"]
