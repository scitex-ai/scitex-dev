"""PS-169 — GitHub-hosted runners are forbidden. No exceptions.

Operator mandate (2026-07-14):

    「PR用のテストとgithub側のランナーというのは本当にもう一切使わないでください」
    — never use GitHub-hosted runners, at all, including PR tests.
    「もし使っているパッケージがあれば…リンター、フックでエラーにしてください。
      強制です、例外なしです」
    — any package still using one must be a hard ERROR. Mandatory, no exceptions.

Every SciTeX job runs on the self-hosted Spartan runners. If Spartan cannot
run something, we fix Spartan — falling back to a GitHub-hosted runner is
forbidden.

**This rule is the only enforcement that exists.** GitHub cannot help us
here: blocking hosted runners at the org level is an Enterprise Cloud
policy, and the `scitex-ai` org is on the Free plan. There is no backstop
behind this check, which is why it is severity **E** and why it is wired
into both the pre-commit hook and CI.

Why this cannot be a `grep ubuntu-latest`
-----------------------------------------
The runner is frequently *indirect*. All of these are violations, and only
the first is greppable on the ``runs-on:`` line::

    runs-on: ubuntu-latest                    # (1) direct scalar
    runs-on: [ubuntu-latest]                  # (2) list form
    runs-on: ${{ matrix.os }}                 # (3) resolves via strategy.matrix.os
      strategy: {matrix: {os: [ubuntu-latest, macos-14]}}
    runs-on: ${{ inputs.runner }}             # (4) resolves via a workflow_call input default

So the check resolves the **effective** runner: it follows ``matrix.*`` and
``inputs.*`` expressions back to their declared values before judging. A rule
that only pattern-matched the literal line would pass a workflow that runs
every job on ``ubuntu-latest`` via a matrix — which is precisely how the
violation hides.

Consuming the shared workflow is not, by itself, compliance
-----------------------------------------------------------
A repo can be "unified" (a thin caller of ``scitex-ai/.github``) and still
effectively run on a hosted runner if the *callee* is dirty. That is closed
structurally rather than by network lookup: the SSOT repo's own workflows
declare their ``runs-on`` inline, so this same rule, run against
``scitex-ai/.github``, fires on a dirty shared workflow at its source. The
callee is audited where it lives; the caller inherits a runner that is
already known-good.

A caller of a reusable workflow from an **unrecognised** owner is flagged
(``unverifiable``): we cannot vouch for a third party's runner, and silently
trusting it would reopen the hole.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

#: Runner-image prefixes GitHub hosts. Anything matching these is a violation.
#: Covers `ubuntu-latest`, `ubuntu-24.04`, `macos-14`, `windows-2022`, and the
#: large/arm variants (`ubuntu-22.04-arm`, `macos-13-xlarge`, ...).
_HOSTED_RE = re.compile(r"^(ubuntu|macos|windows)-", re.IGNORECASE)

#: Owners whose reusable workflows we vouch for. Their `runs-on` is audited by
#: this same rule in their own repo, so a caller inherits a verified runner.
_TRUSTED_REUSABLE_OWNERS = frozenset({"scitex-ai"})

#: `${{ matrix.os }}` / `${{ inputs.runner }}` / `${{ vars.RUNNER }}`
_RE_EXPR = re.compile(r"\$\{\{\s*([a-zA-Z_][\w.-]*)\s*\}\}")

#: Fallback scan when YAML will not parse — better a crude finding than none.
_RE_RUNS_ON_LINE = re.compile(r"^\s*runs-on:\s*(.+?)\s*$", re.MULTILINE)


def _is_hosted(label: object) -> bool:
    """True iff ``label`` names a GitHub-hosted runner image."""
    return isinstance(label, str) and bool(_HOSTED_RE.match(label.strip()))


def _as_labels(value: Any) -> list[str]:
    """Flatten a ``runs-on`` value into a list of candidate label strings.

    Handles the scalar (``ubuntu-latest``), sequence (``[self-hosted, X64]``)
    and ``group:``/``labels:`` mapping forms.
    """
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [v for v in value if isinstance(v, str)]
    if isinstance(value, dict):
        out: list[str] = []
        for key in ("labels", "group"):
            got = value.get(key)
            if isinstance(got, str):
                out.append(got)
            elif isinstance(got, list):
                out.extend(v for v in got if isinstance(v, str))
        return out
    return []


def _resolve_expr(expr_path: str, job: dict, workflow: dict) -> list[str]:
    """Resolve a `${{ ... }}` reference to the values it can take.

    Follows the two indirections that actually occur in our workflows:

    * ``matrix.<key>``  -> ``job.strategy.matrix.<key>`` (a list of images)
    * ``inputs.<key>``  -> ``on.workflow_call.inputs.<key>.default``

    Anything else resolves to ``[]`` (unknown), which is reported separately
    rather than assumed innocent — an unresolvable runner is not a pass.
    """
    parts = expr_path.split(".")
    if len(parts) != 2:
        return []
    scope, key = parts

    if scope == "matrix":
        matrix = (job.get("strategy") or {}).get("matrix") or {}
        if isinstance(matrix, dict):
            got = matrix.get(key)
            if isinstance(got, list):
                return [v for v in got if isinstance(v, str)]
            if isinstance(got, str):
                return [got]
            # `matrix.include` entries can also carry the key
            include = matrix.get("include")
            if isinstance(include, list):
                return [
                    e[key]
                    for e in include
                    if isinstance(e, dict) and isinstance(e.get(key), str)
                ]
        return []

    if scope == "inputs":
        # `on:` is parsed by YAML as the boolean True — check both spellings.
        on_block = workflow.get("on") or workflow.get(True) or {}
        if isinstance(on_block, dict):
            call = on_block.get("workflow_call") or {}
            if isinstance(call, dict):
                inputs = call.get("inputs") or {}
                if isinstance(inputs, dict):
                    spec = inputs.get(key) or {}
                    if isinstance(spec, dict) and isinstance(spec.get("default"), str):
                        return [spec["default"]]
        return []

    return []


def _effective_labels(
    runs_on: Any, job: dict, workflow: dict
) -> tuple[list[str], list[str]]:
    """Return ``(concrete_labels, unresolved_exprs)`` for one job's ``runs-on``."""
    concrete: list[str] = []
    unresolved: list[str] = []
    for label in _as_labels(runs_on):
        m = _RE_EXPR.search(label)
        if not m:
            concrete.append(label)
            continue
        resolved = _resolve_expr(m.group(1), job, workflow)
        if resolved:
            concrete.extend(resolved)
        else:
            unresolved.append(label)
    return concrete, unresolved


def _reusable_owner(uses: str) -> str | None:
    """Owner of a reusable-workflow ``uses:`` ref, or None if it is local."""
    if not isinstance(uses, str) or uses.startswith("./"):
        return None
    return uses.split("/", 1)[0] if "/" in uses else None


def check_ps169_hosted_runners(repo: Path, violation_cls: type, out: list) -> None:
    """Append PS-169 violations for any GitHub-hosted runner under `.github/`."""
    wf_dir = repo / ".github" / "workflows"
    if not wf_dir.is_dir():
        return

    for path in sorted(wf_dir.iterdir()):
        if not path.is_file() or path.suffix not in {".yml", ".yaml"}:
            continue
        rel = str(path.relative_to(repo))
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        try:
            doc = yaml.safe_load(text)
        except yaml.YAMLError:
            doc = None

        # Fallback: unparseable YAML still gets a literal scan, so a broken
        # file cannot smuggle a hosted runner past the gate.
        if not isinstance(doc, dict):
            for raw in _RE_RUNS_ON_LINE.findall(text):
                if _HOSTED_RE.search(raw.strip().lstrip("[").strip()):
                    out.append(
                        violation_cls(
                            "PS-169",
                            rel,
                            f"GitHub-hosted runner `{raw.strip()}` (file does not "
                            "parse as YAML; scanned literally). Use the Spartan "
                            "pool: `runs-on: [self-hosted, Linux, X64, spartan-cpu]`.",
                        )
                    )
            continue

        jobs = doc.get("jobs") or {}
        if not isinstance(jobs, dict):
            continue

        for job_id, job in jobs.items():
            if not isinstance(job, dict):
                continue

            # A caller stub has no `runs-on` — its runner comes from the callee.
            uses = job.get("uses")
            if uses and "runs-on" not in job:
                owner = _reusable_owner(uses)
                if owner is not None and owner not in _TRUSTED_REUSABLE_OWNERS:
                    out.append(
                        violation_cls(
                            "PS-169",
                            rel,
                            f"job `{job_id}` calls reusable workflow `{uses}` from "
                            f"untrusted owner `{owner}` — its effective runner "
                            "cannot be verified. Call a `scitex-ai/.github` "
                            "reusable workflow, or declare a Spartan `runs-on`.",
                        )
                    )
                continue

            if "runs-on" not in job:
                continue

            concrete, unresolved = _effective_labels(job["runs-on"], job, doc)

            for label in concrete:
                if _is_hosted(label):
                    via = ""
                    if _RE_EXPR.search(str(job["runs-on"])):
                        via = f" (via `{job['runs-on']}`)"
                    out.append(
                        violation_cls(
                            "PS-169",
                            rel,
                            f"job `{job_id}` runs on GitHub-hosted runner "
                            f"`{label}`{via} — forbidden without exception. Use "
                            "the Spartan pool: `runs-on: [self-hosted, Linux, "
                            "X64, spartan-cpu]`. If Spartan cannot run this "
                            "job, fix Spartan (scitex-hpc) — never fall back.",
                        )
                    )

            for expr in unresolved:
                out.append(
                    violation_cls(
                        "PS-169",
                        rel,
                        f"job `{job_id}` has an unresolvable runner `{expr}` — "
                        "its effective runner cannot be verified, so it cannot "
                        "be proven Spartan-only. Declare `runs-on: [self-hosted, "
                        "Linux, X64, spartan-cpu]` explicitly.",
                    )
                )
