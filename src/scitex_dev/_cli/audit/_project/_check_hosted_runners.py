# -*- coding: utf-8 -*-
"""PS-169 — GitHub-hosted runners are forbidden (operator mandate 2026-07-14).

Operator mandate (2026-07-14):

    「PR用のテストとgithub側のランナーというのは本当にもう一切使わないでください」
    — never use GitHub-hosted runners, at all, including PR tests.
    「もし使っているパッケージがあれば…リンター、フックでエラーにしてください。
      強制です、例外なしです」
    — any package still using one must be a hard ERROR. Mandatory, no exceptions.

Every SciTeX job runs on the self-hosted `scitex-ci` runners. If the
self-hosted pool cannot run something, we fix the pool — falling back to a
GitHub-hosted runner is forbidden. This rule is the ONLY enforcement that
exists: blocking hosted runners at the org level is an Enterprise Cloud
policy and the `scitex-ai` org is on the Free plan, so there is no backstop
behind this check.

This is a **reland** of the check that shipped on the closed PR #344
(`ci/ps169-forbid-hosted-runners`), rewritten fresh against current
`develop`. Two deliberate design changes vs. that version, both to avoid
false positives on the live fleet:

1. An **unresolvable** ``runs-on`` (an expression we cannot statically
   resolve, e.g. ``${{ vars.RUNNER }}`` with no in-workflow default) is NOT
   flagged. The mandate is enforced on what we can PROVE is hosted; an
   unprovable runner is left to the human, never guessed as a violation.
2. The scitex idiom
   ``runs-on: ${{ fromJSON(vars.CI_RUNS_ON || '["self-hosted","Linux","X64","scitex-ci"]') }}``
   resolves (via its ``|| '<json-array>'`` default) to a self-hosted label
   set and is therefore NOT flagged. This is the fleet's canonical form.

What IS flagged
---------------
The **effective** runner is resolved before judging, so all of these fire —
only the first is greppable on the ``runs-on:`` line::

    runs-on: ubuntu-latest                    # (1) direct scalar literal
    runs-on: [ubuntu-latest]                  # (2) list form
    runs-on: ${{ matrix.os }}                 # (3) resolves via strategy.matrix.os
      strategy: {matrix: {os: [ubuntu-latest, macos-14]}}
    runs-on: ${{ inputs.runner }}             # (4) workflow_call input default
      on: {workflow_call: {inputs: {runner: {default: ubuntu-latest}}}}

A literal that only pattern-matched the ``runs-on:`` line would pass a
workflow that runs every job on ``ubuntu-latest`` via a matrix — which is
exactly how the violation hides. So the check follows ``matrix.*`` /
``inputs.*`` / ``fromJSON(... || '<default>')`` indirection back to concrete
labels, and flags a job only when a concrete effective label is a
GitHub-hosted image (``ubuntu-*`` / ``macos-*`` / ``windows-*``).

Severity: WARN + baseline-ratchet (bake-in)
-------------------------------------------
Per this fleet's convention, a new rule bakes in as **W** (warn,
non-blocking) and is promoted to **E** (error) once the fleet is confirmed
clean. So this check ships at W in ``_registry`` and additionally
new-vs-baseline-ratchets: a violation genuinely NEW relative to the git
baseline (default ``develop``) is escalated to E (blocking the change that
introduced it), while a pre-existing violation stays at the rule default W
(reported, non-blocking) so an already-red repo is not newly wedged the
moment the rule lands. When no baseline resolves (no ``.git`` / shallow
clone), everything stays at W — see
``_new_vs_baseline.escalate_new_violations``.

OPERATOR MANDATE — this rule is intended for promotion to ``error`` (flip
``_HOSTED_SEVERITY`` below to ``"E"``) once the fleet is confirmed clean.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from ._new_vs_baseline import DEFAULT_BASELINE_REF, escalate_new_violations

#: Runner-image prefixes GitHub hosts. Any concrete label matching these is a
#: violation — covers `ubuntu-latest`, `ubuntu-24.04`, `macos-14`,
#: `windows-2022`, and the large/arm variants (`ubuntu-22.04-arm`,
#: `macos-13-xlarge`, ...).
_HOSTED_RE = re.compile(r"^(ubuntu|macos|windows)-", re.IGNORECASE)

#: A `${{ ... }}` expression block (contents captured).
_RE_EXPR_BLOCK = re.compile(r"\$\{\{\s*(.+?)\s*\}\}", re.DOTALL)

#: A bare `matrix.os` / `inputs.runner` style reference (whole expr body).
_RE_SIMPLE_REF = re.compile(r"^([a-zA-Z_][\w.]*)$")

#: `fromJSON( ... )` — the scitex CI idiom; args captured for default mining.
_RE_FROMJSON = re.compile(r"fromJSON\s*\((.*)\)", re.IGNORECASE | re.DOTALL)

#: A single-level JSON array literal, e.g. `["self-hosted","Linux"]`.
_RE_JSON_ARRAY = re.compile(r"(\[[^\[\]]*\])")

#: Fallback literal scan for a file that will not parse as YAML — only ever
#: matches an OUTRIGHT hosted literal on a `runs-on:` line, which cannot be a
#: false positive.
_RE_RUNS_ON_LINE = re.compile(r"^\s*runs-on:\s*(.+?)\s*$", re.MULTILINE)

# The PS-169 rule DEFINITION (code/section/message/severity/slug) is
# registered as a literal tuple in `_extra_rules.py`, NOT here — this module
# imports `_new_vs_baseline` (→ `_violation` → `_registry`), so exporting the
# rule tuple for `_registry` to import back would close an import cycle. The
# baseline-escalating siblings PS-214/PS-215 are registered the same way. The
# rule ships at severity **W** (bake-in); see `_extra_rules.py` and the module
# docstring for the promote-to-E mandate.


def _is_hosted(label: object) -> bool:
    """True iff ``label`` names a GitHub-hosted runner image."""
    return isinstance(label, str) and bool(_HOSTED_RE.match(label.strip()))


def _as_labels(value: Any) -> list[str]:
    """Flatten a ``runs-on`` value into candidate label strings.

    Handles the scalar (``ubuntu-latest``), sequence
    (``[self-hosted, X64]``) and ``group:``/``labels:`` mapping forms.
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


def _resolve_fromjson_default(args: str) -> list[str] | None:
    """Resolve `fromJSON(... || '<json-array>')` to its default labels.

    Returns the parsed label list from the FIRST JSON-array literal found in
    the fromJSON arguments (the scitex idiom's `|| '[...]'` fallback, or a
    direct `fromJSON('[...]')`). Returns ``None`` when no static array literal
    is present — the runner is then unresolvable and must NOT be flagged.
    """
    for m in _RE_JSON_ARRAY.finditer(args):
        try:
            arr = json.loads(m.group(1))
        except ValueError:
            continue
        if isinstance(arr, list):
            return [str(x) for x in arr if isinstance(x, str)]
    return None


def _resolve_ref(ref: str, job: dict, workflow: dict) -> list[str]:
    """Resolve a `matrix.<key>` / `inputs.<key>` reference to its values.

    * ``matrix.<key>``  -> ``job.strategy.matrix.<key>`` (a list of images),
      also mining ``matrix.include`` entries.
    * ``inputs.<key>``  -> ``on.workflow_call.inputs.<key>.default``.

    Anything else -> ``[]`` (unresolvable; the caller does not flag it).
    """
    parts = ref.split(".")
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
                    if isinstance(spec, dict) and isinstance(
                        spec.get("default"), str
                    ):
                        return [spec["default"]]
        return []

    return []


def _resolve_expr(inner: str, job: dict, workflow: dict) -> list[str]:
    """Resolve one `${{ ... }}` expression body to the labels it can take.

    Returns ``[]`` for anything not statically resolvable — the caller treats
    an empty result as "unprovable, do not flag" (no false positives).
    """
    fj = _RE_FROMJSON.search(inner)
    if fj:
        resolved = _resolve_fromjson_default(fj.group(1))
        return resolved or []
    ref = _RE_SIMPLE_REF.match(inner)
    if ref:
        return _resolve_ref(ref.group(1), job, workflow)
    return []


def _concrete_labels(runs_on: Any, job: dict, workflow: dict) -> list[str]:
    """Return the concrete (statically resolved) labels for one ``runs-on``.

    Expression labels that cannot be resolved are dropped — the mandate is
    enforced only on runners we can PROVE. So the returned list is exactly the
    set of labels we are willing to judge as hosted-or-not.
    """
    concrete: list[str] = []
    for label in _as_labels(runs_on):
        block = _RE_EXPR_BLOCK.search(label)
        if block:
            concrete.extend(_resolve_expr(block.group(1), job, workflow))
        else:
            concrete.append(label)
    return concrete


def _collect_ps169_violations(repo: Path, violation_cls: type) -> list:
    """Pure collection pass — no severity escalation.

    Split out so the escalation helper can re-run the SAME detection against a
    `worktree_at`-staged baseline checkout without recursing into escalation.
    """
    found: list = []
    wf_dir = repo / ".github" / "workflows"
    if not wf_dir.is_dir():
        return found

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

        # Fallback: an unparseable file still gets a literal scan so a broken
        # workflow cannot smuggle an OUTRIGHT hosted literal past the gate.
        if not isinstance(doc, dict):
            for raw in _RE_RUNS_ON_LINE.findall(text):
                candidate = raw.strip().lstrip("[").split(",")[0].strip().strip("]'\"")
                if _is_hosted(candidate):
                    found.append(
                        violation_cls(
                            "PS-169",
                            rel,
                            f"GitHub-hosted runner `{candidate}` (file does not "
                            "parse as YAML; scanned literally). Use the "
                            "self-hosted pool: `runs-on: [self-hosted, Linux, "
                            "X64, scitex-ci]`.",
                        )
                    )
            continue

        jobs = doc.get("jobs") or {}
        if not isinstance(jobs, dict):
            continue

        for job_id, job in jobs.items():
            if not isinstance(job, dict) or "runs-on" not in job:
                continue

            for label in _concrete_labels(job["runs-on"], job, doc):
                if not _is_hosted(label):
                    continue
                via = ""
                if _RE_EXPR_BLOCK.search(str(job["runs-on"])):
                    via = f" (via `{job['runs-on']}`)"
                found.append(
                    violation_cls(
                        "PS-169",
                        rel,
                        f"job `{job_id}` runs on GitHub-hosted runner "
                        f"`{label}`{via} — forbidden without exception "
                        "(operator mandate 2026-07-14). Use the self-hosted "
                        "pool: `runs-on: ${{ fromJSON(vars.CI_RUNS_ON || "
                        "'[\"self-hosted\",\"Linux\",\"X64\",\"scitex-ci\"]') "
                        "}}` or `runs-on: [self-hosted, Linux, X64, "
                        "scitex-ci]`. If the pool cannot run this job, fix the "
                        "pool — never fall back to a hosted runner.",
                    )
                )
    return found


def check_ps169_hosted_runners(
    repo: Path,
    violation_cls: type,
    out: list,
    *,
    baseline_ref: str = DEFAULT_BASELINE_REF,
) -> None:
    """Append PS-169 violations for GitHub-hosted runners under `.github/`.

    Parameters
    ----------
    repo : Path
        Repository root (the dir containing `.github/workflows/`).
    violation_cls : type
        The auditor's `Violation` dataclass `(rule, where, detail)`.
    out : list
        Violations are appended in place (project-auditor convention).
    baseline_ref : str
        Git ref to diff against for new-vs-existing severity escalation
        (default ``"develop"``; falls back to ``"origin/<baseline_ref>"`` —
        see `_new_vs_baseline.escalate_new_violations`). A NEW hosted-runner
        reference ratchets to "E"; a pre-existing one stays at the rule
        default "W".
    """
    found = _collect_ps169_violations(repo, violation_cls)
    if not found:
        return

    escalate_new_violations(
        repo,
        found,
        ("PS-169",),
        lambda base_repo: _collect_ps169_violations(base_repo, violation_cls),
        baseline_ref=baseline_ref,
    )
    out.extend(found)


# EOF
