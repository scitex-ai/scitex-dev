#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/_hook_rules.py
"""scitex-dev's OWN agent guardrails, declared as a leaf of the federation.

Registered under the ``scitex_dev.hooks`` entry-point group in pyproject.toml
exactly like any downstream package's provider. scitex-dev holds no privileged
position in the corpus it aggregates.

SCOPE. These are the DEV-WORKFLOW guardrails -- git discipline, test
discipline, search-tool discipline, edit-surface discipline. They are
scitex-dev's domain because scitex-dev is the package that owns the
development workflow. Guardrails about containers, agent lifecycle and HPC
belong to scitex-agent-container; the operator-facing message-format rules
belong to claude-code-telegrammer. Each declares its own.

PROVENANCE. Every rule below was read off the implementation actually
deployed on 2026-08-12, at
``~/.dotfiles/src/.claude/to_claude/hooks/pre-tool-use/`` -- not reconstructed
from documentation, which the inventory found to be wrong in several places
(hooks named ``advise_`` / ``encourage_`` that hard-block, a header promising
"at least one skill read" against code demanding all of them).

Three facts from that inventory that this federation exists to fix:

1. THREE TREES, NOT ONE. The dotfiles-tracked copy, sac's ``to_home``
   materialization baseline, and the live container copy are three different
   trees. 15 scripts had diverged between them; drift ran BOTH ways, so a
   one-directional sync would silently destroy hand-edits.
2. ONLY 33 OF 68 SCRIPTS ARE REGISTERED. The other 35 sit on disk, fully
   written and self-testable, wired into nothing. A rule that is not
   registered is not a rule, and nothing made that visible.
3. EIGHT RULES STATE NO REASON AT ALL. Their ``reason`` below records that
   absence rather than papering over it with an invented rationale -- an
   invented reason would be worse than none, because it would look settled.

``implemented_in`` names the deployed script rather than a repo-relative
``script``: scitex-dev does not ship these files today. Declaring them makes
them enumerable and auditable now; moving the implementations into the package
is the follow-on, and is deliberately not bundled with the declaration.
"""

from __future__ import annotations

from .hooks import HookRule

_PROVIDER = "scitex-dev"
_HOOK_DIR = "dotfiles:src/.claude/to_claude/hooks/pre-tool-use"

#: Recorded verbatim for the rules whose deployed implementation states no
#: rationale. Naming the gap keeps it trackable; inventing one would not.
_NO_REASON = (
    "NO REASON RECORDED in the deployed implementation (measured 2026-08-12). "
    "The rule is enforced fleet-wide but whoever added it left no incident, "
    "directive or doctrine behind it. Declared here so the gap is visible and "
    "can be filled by the rule's owner instead of staying invisible; an "
    "invented rationale would be worse, because it would read as settled."
)


def _rule(**kw) -> HookRule:
    kw.setdefault("provider", _PROVIDER)
    kw.setdefault("event", "pre-tool-use")
    script = kw.pop("script_file")
    kw.setdefault("implemented_in", f"{_HOOK_DIR}/{script}")
    return HookRule(**kw)


def provide() -> list[HookRule]:
    """Return scitex-dev's declared guardrails."""
    return [
        # --- git / branch discipline ------------------------------------
        _rule(
            id="dev.git-dash-c",
            rule="Every `git` command must name its repository with "
            "`git -C /absolute/path`.",
            reason="An agent's shell cwd is not reliably where it believes it "
            "is, and a bare `git` silently acts on whatever repo the cwd "
            "happens to sit in. Being explicit removes the ambiguity "
            "entirely.",
            severity="deny",
            matches=("Bash",),
            bypass="hook-bypass: git-dash-C",
            script_file="enforce_git_dash_C.sh",
        ),
        _rule(
            id="dev.no-edit-on-main-checkout",
            rule="Refuse edits to git-TRACKED files in a repository's MAIN "
            "checkout on any branch, and on main/master/release/* "
            "everywhere; untracked files and linked worktrees stay "
            "editable.",
            reason="2026-07-17 operator ruling: the topic-branch exemption in "
            "MAIN checkouts is REVOKED. That exemption is how the shared "
            "checkout collected uncommitted WIP which autosave then swept "
            "(incident ccc55e93). The shared checkout stays on develop and "
            "is not an edit surface.",
            severity="deny",
            matches=("Write", "Edit", "MultiEdit", "NotebookEdit"),
            bypass="CC_ALLOW_MAIN_BRANCH_EDIT",
            script_file="deny_edit_on_main_branch.sh",
        ),
        _rule(
            id="dev.no-commit-push-on-shared-develop",
            rule="Refuse `git commit` / `git push` whose effective target is "
            "the MAIN checkout on branch develop.",
            reason="Incident 2026-06-24 (commit 2d9405e7): a direct commit "
            "onto the shared develop slipped through. The main checkout's "
            "develop is used simultaneously by the operator and other "
            "agents, and origin/develop is often branch-protected.",
            severity="deny",
            matches=("Bash",),
            bypass="CC_ALLOW_DEVELOP_COMMIT",
            script_file="deny_commit_push_on_main_develop.sh",
        ),
        _rule(
            id="dev.no-shared-branch-rewrite",
            rule="Refuse rebase / force-push / `reset --hard` when the target "
            "ref is develop, main or master; feature branches stay free.",
            reason="Rewriting shared history corrupts other clones and "
            "concurrent agents. Feature-branch rebase and force-push are "
            "normal safe workflow, and the operator explicitly required "
            "this guard NOT over-block them.",
            severity="deny",
            matches=("Bash",),
            bypass="CC_ALLOW_SHARED_REWRITE",
            script_file="deny_shared_branch_rewrite.sh",
        ),
        _rule(
            id="dev.no-main-checkout-branch-switch",
            rule="Refuse `git checkout <branch>` / `switch` / `branch -D` / "
            "`reset --hard` against any repository's MAIN checkout; "
            "worktrees and file-restore pass.",
            reason="2026-05-17: a worktree-isolated subagent switched the "
            "LEAD's main checkout to its feature branch and left "
            "uncommitted changes there. Operator: violations must be made "
            "impossible by hook enforcement; widened 2026-05-19 to ALL "
            "repositories.",
            severity="deny",
            matches=("Bash",),
            bypass="CC_ALLOW_MAIN_BRANCH_SWITCH",
            script_file="deny_subagent_main_repo_branch_switch.sh",
        ),
        _rule(
            id="dev.worktree-path",
            rule="`git worktree add` must target <repo-root>/.worktrees/<name>.",
            reason="Operator directive 2026-06-09. Agents created worktrees at "
            "ad-hoc paths, or under .claude/worktrees/ where the Claude "
            "Code harness reaps them (F-CS8), or inside a DIFFERENT "
            "project's tree.",
            severity="deny",
            matches=("Bash",),
            bypass="CC_ALLOW_WORKTREE_PATH",
            doctrine="F-CS8-WORKTREE-BLOAT.md",
            script_file="enforce_worktree_path.sh",
        ),
        _rule(
            id="dev.warn-stale-worktree-base",
            rule="Warn, never block, when `git worktree add` cuts a branch "
            "from a base that is behind its upstream.",
            reason="Measured twice in 24 hours on different repos: scitex-app "
            "2026-07-28 (local develop 49 behind) and sac 2026-07-29 (8 "
            "behind, including that agent's OWN three merges from an hour "
            "earlier, so it baked from the wrong commit). Forking "
            "deliberately from an older base is legitimate, so this warns.",
            severity="warn",
            matches=("Bash",),
            script_file="warn_stale_worktree_base.sh",
        ),
        _rule(
            id="dev.pr-base-never-main",
            rule="Refuse `gh pr create` / `gh pr edit` targeting `--base main`, "
            "and refuse `gh pr create` with no `--base` at all.",
            reason="The scitex repos' GitHub default branch is main "
            "deliberately (main is the stable release face), so a "
            "`gh pr create` without --base silently defaults to it. "
            "Release PRs to main are the lead's job.",
            severity="deny",
            matches=("Bash",),
            bypass="hook-bypass: pr-base-main",
            script_file="block_pr_base_main.sh",
        ),
        _rule(
            id="dev.require-mergeable-verdict",
            rule="Refuse `gh pr merge` unless `scitex-dev ci verify <n> "
            "--repo <owner/repo>` exits 0; refuse it outright without "
            "`--repo`.",
            reason="Three incidents on 2026-08-09: two agents called branches "
            "green from LOCAL runs that CI contradicted; an agent read 7 "
            "SUCCESS checks that were a week old and described a different "
            "commit; and that read came from the WRONG repository, two "
            "repos here each having a #521. Operator: 「なんでプログラムに"
            "できることをエージェントにお願いしてんの?」",
            severity="deny",
            matches=("Bash",),
            bypass="hook-bypass: mergeable-verdict",
            script_file="require_mergeable_verdict.sh",
        ),
        # --- test discipline --------------------------------------------
        _rule(
            id="dev.pytest-fullpath",
            rule="pytest must be invoked with an absolute path, never a "
            "relative one and never via `cd dir && pytest`.",
            reason="An agent's shell cwd is not reliably where it believes it "
            "is, so a relative target silently selects a different test "
            "set than intended.",
            severity="deny",
            matches=("Bash",),
            bypass="hook-bypass: pytest-fullpath",
            script_file="enforce_pytest_fullpath.sh",
        ),
        _rule(
            id="dev.pytest-worktree-source",
            rule="A pytest run inside a linked worktree must set PYTHONPATH to "
            "that worktree's src/.",
            reason="Measured by scitex-hpc 2026-08-02 on PR #72: the editable "
            "install's .pth points at the MAIN checkout's src, so pytest "
            "collects the WORKTREE's tests and runs them against the MAIN "
            "checkout's CODE. Their run reported '56 passed' having "
            "exercised none of the refactor -- a change that only moved "
            "internals would go green while testing nothing.",
            severity="deny",
            matches=("Bash",),
            bypass="CC_ALLOW_PYTEST_MAIN_SOURCE",
            script_file="enforce_pytest_worktree_source.sh",
        ),
        # --- search / edit tool discipline -------------------------------
        _rule(
            id="dev.ripgrep-not-grep-r",
            rule="Refuse `grep -r`, naive `find -name` without -prune/-path, "
            "and `rg` on a .dotfiles path without --hidden.",
            reason="grep -r and find -name ignore .gitignore, scan "
            "node_modules/.venv/build artifacts, waste tokens and run "
            "5-10x slower than rg. The --hidden clause is scoped to "
            ".dotfiles on measured evidence (2026-08-12: `rg pat src` "
            "returned 0 hits, `rg pat src --hidden` returned 96).",
            severity="deny",
            matches=("Bash",),
            bypass="CC_ALLOW_GREP_R",
            script_file="enforce_ripgrep.sh",
        ),
        _rule(
            id="dev.fd-not-find",
            rule="Refuse `find <path> -name/-type/-regex` carrying no -prune "
            "and no -path filter.",
            reason="Plain find traverses node_modules, .venv, build artifacts "
            "and .git, ignores .gitignore, and is slow and noisy. fd is "
            "gitignore-aware, parallel and 5-10x faster.",
            severity="deny",
            matches=("Bash",),
            bypass="CC_ALLOW_FIND",
            script_file="enforce_fd.sh",
        ),
        _rule(
            id="dev.scitex-rename-not-sed-inplace",
            rule="Refuse in-place `sed -i` / `awk -i inplace` and "
            "find|xargs sed rewrites.",
            reason="In-place stream edits miss cross-file references, break "
            "import paths, and have no dry-run or undo. "
            "`scitex-dev rename-symbols` understands symbols and supports "
            "--regex, --dry-run, --exclude, and is invertible.",
            severity="deny",
            matches=("Bash",),
            bypass="CC_ALLOW_SED_INPLACE",
            script_file="enforce_scitex_rename.sh",
        ),
        _rule(
            id="dev.uv-not-pip",
            rule="Refuse `pip install/uninstall/download/sync`; use `uv pip`. "
            "Read-only pip subcommands pass.",
            reason="uv pip is a near-drop-in replacement resolving and "
            "installing 10-100x faster. Hook enforcement is stronger than "
            "a CLAUDE.md instruction because the model cannot route "
            "around it.",
            severity="deny",
            matches=("Bash",),
            bypass="CC_ALLOW_PIP",
            script_file="enforce_uv.sh",
        ),
        _rule(
            id="dev.no-redirect-into-dotfiles",
            rule="Refuse shell redirection whose statically-resolvable target "
            "is inside the dotfiles repo or its deployed ~/.scitex alias.",
            reason="On 2026-07-16, 98+ probe dumps had piled up inside the "
            "dotfiles repo. The writer was fixed the same day; this is the "
            "agreed deterministic backstop.",
            severity="deny",
            matches=("Bash",),
            bypass="CC_ALLOW_DOTFILES_REDIRECT",
            script_file="deny_redirect_into_dotfiles.sh",
        ),
        # --- rules deployed with no recorded rationale -------------------
        _rule(
            id="dev.line-limit",
            rule="Refuse a Write/Edit whose resulting file exceeds a "
            "per-extension line limit; tests and CHANGELOG are exempt, and "
            "the limit is suspended when GITIGNORED/REFACTORING.md exists.",
            reason=_NO_REASON,
            severity="deny",
            matches=("Write", "Edit", "MultiEdit", "NotebookEdit"),
            bypass="hook-bypass: line-limit",
            script_file="limit_line_numbers.sh",
        ),
        _rule(
            id="dev.no-project-root-pollution",
            rule="Refuse a Write/Edit creating a file directly in a project "
            "root unless its name is on the allowed list.",
            reason=_NO_REASON,
            severity="deny",
            matches=("Write", "Edit", "MultiEdit", "NotebookEdit"),
            bypass="hook-bypass: root-pollution",
            script_file="inhibit_project_root_pollution.sh",
        ),
        _rule(
            id="dev.force-flag",
            rule="Refuse `rm` and `cp` invoked without a -f flag.",
            reason="Interactive confirmation prompts hang a non-interactive "
            "agent session, which then blocks on input that never comes. "
            "(No incident recorded in the deployed implementation.)",
            severity="deny",
            matches=("Bash",),
            bypass="hook-bypass: force-flag",
            script_file="enforce_force_flag.sh",
        ),
    ]


__all__ = ["provide"]
