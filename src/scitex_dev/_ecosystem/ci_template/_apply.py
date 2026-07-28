#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex-dev ecosystem ci-template apply`` — programmatic core.

THE single canonical CI mechanism for the scitex fleet (operator decision,
2026-07-21): every repo ships ONE thin ``ci.yml`` that delegates its job
bodies to the org-level reusable workflows in ``scitex-ai/.github@main``.
A shared workflow cannot drift per-repo — the dual-canonical era
(consolidated ``pr-ci.yml``/``release-ci.yml`` templates here vs. the
``ci runner register`` in-SIF ``ci.yml.template``) is over; both losers
now route through this module or are deleted.

Behavioural contract:

1. **Detect target repo state** — parse ``pyproject.toml`` to derive
   ``PKG_NAME`` (``[project].name``) and ``PKG_MODULE`` (``-`` → ``_``).
   List existing ``.github/workflows/`` files.

2. **Branch-protection compatibility gate** — query the target's
   ``required_status_checks`` for ``develop`` and ``main`` via ``gh api``.
   If any required context is NOT in the caller's emitted check-run names
   (``"<caller-job-id> / <reusable job name>"``), refuse to apply and print
   the old→new context worksheet (see ``_gate``).
   ``skip_required_check_gate=True`` bypasses (operator-debug only).

3. **Substitute template** — read the vendored ``ci.yml.tmpl`` and replace
   ``<PKG_NAME>`` / ``<PKG_MODULE>`` (provenance header only — the org
   reusable workflows self-derive the package from the checkout).

4. **Apply changes** — write ``ci.yml``; delete superseded workflows by
   HARDCODED PREFIX LIST (no heuristic content-matching), plus any
   protected-prefix file the emitted ci.yml genuinely supersedes. The
   policy and the per-file reasoning live in ``_workflows``.

5. **--dry-run** — skip writes; return the intended diff for the caller
   to print. The returned buckets (``written``/``deleted``/``protected``/
   ``skipped``) PARTITION ``.github/workflows/``: a dry-run that stays
   silent about a file is indistinguishable from one that never looked at
   it, and that silence is how a PS-224-violating leftover survived a
   "successful" apply (measured 2026-07-28).

Failure modes use distinct exception types so the CLI can render
operator-friendly errors instead of tracebacks.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from ._errors import ApplyError
from ._gate import BranchProtectionGateError
from ._workflows import (
    CANONICAL_WORKFLOW,
    list_workflows as _list_workflows,
    plan_workflow_changes,
    superseded_protected_prefixes,
)

if sys.version_info >= (3, 11):
    import tomllib  # type: ignore[no-redef]
else:  # pragma: no cover - exercised on py3.10 only
    import tomli as tomllib  # type: ignore[no-redef]


__all__ = [
    "ApplyError",
    "ApplyResult",
    "BranchProtectionGateError",
    "apply",
    "emitted_job_names",
    "render",
]


# --------------------------------------------------------------------------- #
# Result type — caller (CLI) decides how to render
# --------------------------------------------------------------------------- #


@dataclass
class ApplyResult:
    """Outcome of ``apply``. ``dry_run`` callers print; live callers see the
    same fields but ``written_paths`` and ``deleted_paths`` reflect the FS.

    ``written_paths`` / ``deleted_paths`` / ``protected_paths`` /
    ``skipped_delete_paths`` are DISJOINT and together cover every file in
    ``.github/workflows/``. ``kept_reasons`` maps ``str(path)`` to the reason
    each KEPT file (protected or skipped) was not deleted — so "deliberately
    preserved" is never rendered as the same silence as "never considered".
    """

    repo_dir: Path
    pkg_name: str
    pkg_module: str
    python_versions: List[str]
    emitted_jobs: List[str]
    required_contexts: Dict[str, List[str]] = field(default_factory=dict)
    rendered: Dict[str, str] = field(default_factory=dict)  # path-rel → content
    written_paths: List[Path] = field(default_factory=list)
    deleted_paths: List[Path] = field(default_factory=list)
    protected_paths: List[Path] = field(default_factory=list)
    skipped_delete_paths: List[Path] = field(default_factory=list)
    kept_reasons: Dict[str, str] = field(default_factory=dict)
    superseded_prefixes: List[str] = field(default_factory=list)
    dry_run: bool = False
    gate_skipped: bool = False

    @property
    def kept_paths(self) -> List[Path]:
        """Every file apply considered and deliberately KEPT (protected or
        merely not eligible), in one list for callers that do not care which."""
        return sorted(set(self.protected_paths) | set(self.skipped_delete_paths))


# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #


# The org-side pytest-matrix.yml currently pins this matrix itself
# (``workflow_call: {}`` — no inputs). Kept here ONLY to compute the gate's
# expected check-run names; changing it does not change what actually runs.
DEFAULT_PYTHON_VERSIONS: List[str] = ["3.11", "3.12", "3.13"]


# --------------------------------------------------------------------------- #
# Template loading + rendering
# --------------------------------------------------------------------------- #


def _templates_dir() -> Path:
    return Path(__file__).parent / "templates"


def _load_template(name: str) -> str:
    path = _templates_dir() / name
    if not path.is_file():
        raise ApplyError(f"vendored template missing: {path}")
    return path.read_text(encoding="utf-8")


def render(
    template_name: str,
    *,
    pkg_name: str,
    pkg_module: str,
) -> str:
    """Pure substitution. Exposed for tests + manual diffing.

    The thin caller is package-agnostic at the job level (org reusable
    workflows self-derive the package from the checkout), so substitution
    only stamps the provenance header. No other placeholder may survive.
    """
    body = _load_template(template_name)
    body = body.replace("<PKG_NAME>", pkg_name)
    body = body.replace("<PKG_MODULE>", pkg_module)
    return body


# --------------------------------------------------------------------------- #
# Deterministic emitted-jobs set (gate input)
# --------------------------------------------------------------------------- #


def emitted_job_names(
    python_versions: Sequence[str], *, include_preserved: bool = True
) -> List[str]:
    """Return the sorted set of GitHub check-run names the rendered caller
    publishes, given the org-side python-versions matrix.

    Under ``workflow_call`` GitHub renders each check-run context as
    ``"<caller-job-id> / <reusable job name>"`` — the caller-job ids in
    ``ci.yml.tmpl`` and the job names inside ``scitex-ai/.github@main``
    MUST stay in lock-step with this list; tests pin the caller side.

    When ``include_preserved`` is True (default), also include the
    well-known check-run names emitted by *preserved* workflows that the
    apply step never removes (cla.yml → ``CLAssistant``). Pass
    ``include_preserved=False`` for tests that need the pure-caller set.
    """
    names = {
        "import-smoke / import-smoke-on-ubuntu-py3-12",
        "quality-audit / audit",
        "rtd-sphinx-build / docs-sphinx",
    }
    for pv in python_versions:
        names.add(f"pytest-matrix / pytest-matrix-on-ubuntu-py{pv}")
    if include_preserved:
        names.update(_preserved_workflow_job_names())
    return sorted(names)


# Well-known check-run names from preserved workflows. These files are
# intentionally never removed by ci-template apply (see ``_workflows``) and
# they publish these standard names. Kept here as a small static set so the
# gate logic never has to read or parse YAML at apply time.
#
# ``sphinx`` / ``docs`` USED to be listed here, on the premise that
# ``rtd-sphinx-*.yml`` was preserved. It no longer is — the emitted ci.yml
# carries a superseding ``rtd-sphinx-build`` job and apply now deletes the
# standalone file, so those bare contexts will NOT be published after this
# migration. Claiming otherwise would let the gate wave through exactly the
# deadlock it exists to prevent; a repo still requiring them is now correctly
# refused, with the old→new worksheet telling the operator what to change.
def _preserved_workflow_job_names() -> set:
    return {
        "CLAssistant",   # from cla.yml
    }


# --------------------------------------------------------------------------- #
# Target-repo inspection
# --------------------------------------------------------------------------- #


def _read_pyproject(repo_dir: Path) -> dict:
    p = repo_dir / "pyproject.toml"
    if not p.is_file():
        raise ApplyError(f"no pyproject.toml at {repo_dir}")
    return tomllib.loads(p.read_text(encoding="utf-8"))


def _derive_pkg(meta: dict) -> Tuple[str, str]:
    project = meta.get("project", {})
    name = project.get("name")
    if not name:
        raise ApplyError("pyproject.toml [project].name missing")
    module = name.replace("-", "_")
    return name, module


def _detect_owner_repo(repo_dir: Path) -> Optional[str]:
    """Return ``owner/repo`` from ``origin`` remote, or None if not a git repo
    or no origin configured. We never raise — the gate just degrades to
    "no required contexts found", which is safe.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_dir), "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=7,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    if out.returncode != 0:
        return None
    url = out.stdout.strip()
    # SSH: git@github.com:owner/repo.git ; HTTPS: https://github.com/owner/repo(.git)
    if "github.com" not in url:
        return None
    rest = url.split("github.com", 1)[1].lstrip(":/")
    if rest.endswith(".git"):
        rest = rest[: -len(".git")]
    parts = rest.split("/")
    if len(parts) < 2:
        return None
    return f"{parts[0]}/{parts[1]}"


def _gh_api_get(endpoint: str) -> Tuple[int, str]:
    """Plain ``gh api GET`` shim; returns (rc, stdout|stderr)."""
    if shutil.which("gh") is None:
        return 127, "gh CLI not on PATH"
    proc = subprocess.run(
        ["gh", "api", endpoint],
        capture_output=True, text=True, timeout=30,
    )
    return proc.returncode, (proc.stdout if proc.returncode == 0 else proc.stderr)


def _is_poisoned_context(ctx: str) -> bool:
    """Detect a context string that is actually a serialised GitHub API
    error body (e.g. ``'{"message":"Branch not protected", …,"status":"404"}'``).

    Historical: in some scitex-* repos the ``required_status_checks.contexts``
    array contains a single literal JSON error-body string from a setup-time
    misstep (a 404 response captured as a context name). Such "contexts" can
    never be satisfied by any real CI job, so they would deadlock the gate
    forever. We filter them here with a warning logged at the callsite.
    """
    s = (ctx or "").strip()
    if not (s.startswith("{") and s.endswith("}")):
        return False
    try:
        obj = json.loads(s)
    except json.JSONDecodeError:
        return False
    return isinstance(obj, dict) and (
        "message" in obj or "status" in obj or "documentation_url" in obj
    )


def _read_required_contexts(owner_repo: str, branch: str) -> List[str]:
    """Query branch-protection required_status_checks for one branch.

    Silently returns [] for 404 (branch not protected) so callers can
    union the result across branches without special-casing.

    Also filters out *poisoned* contexts — entries whose name is a literal
    JSON error body (see ``_is_poisoned_context``). Such contexts are real in
    a handful of legacy scitex-* repos; treating them as required would
    permanently block the gate because no CI job can ever emit such a name.
    """
    rc, out = _gh_api_get(
        f"repos/{owner_repo}/branches/{branch}/protection/required_status_checks"
    )
    if rc != 0:
        return []
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return []
    raw = list(data.get("contexts") or [])
    return [c for c in raw if not _is_poisoned_context(c)]


# --------------------------------------------------------------------------- #
# Public entry-point
# --------------------------------------------------------------------------- #


def apply(
    repo_dir: os.PathLike[str] | str,
    *,
    dry_run: bool = False,
    branch: str = "chore/ci-speedup",  # reserved for future PR-flow extension
    python_versions: Optional[Sequence[str]] = None,
    skip_required_check_gate: bool = False,
    # Injection seams (tests pass these; CLI does not).
    required_contexts_lookup=None,
    owner_repo_lookup=None,
) -> ApplyResult:
    """Apply the canonical thin-caller CI workflow to *repo_dir*.

    Parameters
    ----------
    repo_dir
        Path to the target scitex-* repo (must contain pyproject.toml).
    dry_run
        If True, compute everything but write nothing.
    branch
        Reserved: future PR-flow extension will create this branch and
        commit. Today, ``apply`` writes to the working tree; the operator
        commits.
    python_versions
        Override the matrix the GATE expects (informational — the actual
        matrix is pinned org-side in scitex-ai/.github@main).
    skip_required_check_gate
        Skip the gate. DANGEROUS — never use in batch.
    required_contexts_lookup
        ``(owner_repo, branch) -> List[str]`` callable; defaults to live
        ``gh api`` call. Tests pass a stub.
    owner_repo_lookup
        ``(repo_dir) -> Optional[str]`` callable; defaults to live
        ``git remote get-url origin`` parse. Tests pass a stub.
    """
    repo_dir = Path(repo_dir).resolve()
    if not (repo_dir / ".git").exists():
        raise ApplyError(f"not a git repo: {repo_dir}")
    meta = _read_pyproject(repo_dir)
    pkg_name, pkg_module = _derive_pkg(meta)

    pvs = list(python_versions or DEFAULT_PYTHON_VERSIONS)
    emitted = emitted_job_names(pvs)

    # Gate
    or_lookup = owner_repo_lookup or _detect_owner_repo
    owner_repo = or_lookup(repo_dir)
    rc_lookup = required_contexts_lookup or _read_required_contexts
    required: Dict[str, List[str]] = {}
    if owner_repo is not None:
        for br in ("develop", "main"):
            ctxs = rc_lookup(owner_repo, br)
            if ctxs:
                required[br] = ctxs

    if not skip_required_check_gate and required:
        emitted_set = set(emitted)
        missing: Dict[str, List[str]] = {}
        for br, ctxs in required.items():
            gap = [c for c in ctxs if c not in emitted_set]
            if gap:
                missing[br] = gap
        if missing:
            raise BranchProtectionGateError(missing, emitted, owner_repo)

    # Render — ONE canonical workflow.
    rendered = {
        f".github/workflows/{CANONICAL_WORKFLOW}": render(
            "ci.yml.tmpl",
            pkg_name=pkg_name,
            pkg_module=pkg_module,
        ),
    }

    # Plan deletes. Protection for a prefix is lifted ONLY when the body we
    # are about to write genuinely carries the superseding caller job — so a
    # template that drops the job re-protects those files automatically.
    superseded = superseded_protected_prefixes(rendered)
    plan = plan_workflow_changes(
        _list_workflows(repo_dir),
        rendered_paths=[repo_dir / rel for rel in rendered],
        superseded_prefixes=superseded,
    )

    result = ApplyResult(
        repo_dir=repo_dir,
        pkg_name=pkg_name,
        pkg_module=pkg_module,
        python_versions=pvs,
        emitted_jobs=emitted,
        required_contexts=required,
        rendered=rendered,
        protected_paths=plan.protected,
        skipped_delete_paths=plan.skipped,
        kept_reasons=plan.reasons,
        superseded_prefixes=list(superseded),
        dry_run=dry_run,
        gate_skipped=skip_required_check_gate,
    )

    if dry_run:
        # Annotate would-be writes/deletes; do not touch FS.
        result.written_paths = [repo_dir / r for r in rendered]
        result.deleted_paths = list(plan.to_delete)
        return result

    # Write
    wf_dir = repo_dir / ".github" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    for rel, content in rendered.items():
        out = repo_dir / rel
        out.write_text(content, encoding="utf-8")
        result.written_paths.append(out)

    for d in plan.to_delete:
        d.unlink()
        result.deleted_paths.append(d)

    return result


# EOF
