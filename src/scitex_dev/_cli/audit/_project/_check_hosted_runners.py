# -*- coding: utf-8 -*-
"""PS-169 — GitHub-hosted runners are SLOWER (advisory; hosted is allowed).

SUPERSEDED MANDATE — read this before re-tightening the rule
------------------------------------------------------------
This rule was born as an absolute prohibition. The operator mandate of
2026-07-14 read:

    「PR用のテストとgithub側のランナーというのは本当にもう一切使わないでください」
    — never use GitHub-hosted runners, at all, including PR tests.
    「…リンター、フックでエラーにしてください。強制です、例外なしです」
    — a hard ERROR. Mandatory, no exceptions.

That mandate is **SUPERSEDED by the operator directive of 2026-08-05**:

    「スパルタンのCIは全面的にやめましょう」   — take Spartan OUT of CI entirely.
    「CIのルールを緩めないといけなかったです」  — the CI rules had to be relaxed.
    「しかもスパルタンよりも scitex-compute 使うべきです」
                                              — prefer scitex-compute to Spartan.

The new position is a PREFERENCE, not a prohibition: run CI on fast hardware
we own where that matters, and treat GitHub-hosted runners as a legitimate
fallback — free for public repositories, which most of ours are, just slower.

So this rule no longer forbids anything. It reports, at W, that a job is on a
hosted runner and is therefore slower than our own hardware. That is useful
information; it is not a violation, and it must never fail a build.

Why the ratchet was REMOVED (the important part)
------------------------------------------------
The rule previously shipped at W but escalated a violation that was NEW
relative to the git baseline to E. Under the 2026-08-05 directive that
mechanism is exactly inverted:

* a repo that has run on `ubuntu-latest` for months stays at W — permitted;
* a repo MOVING a job off Spartan onto hosted introduces a NEW violation,
  ratchets to E, and **the compliant PR is the one that gets blocked**.

Not theoretical. Measured on scitex-hub's PR #561, where this rule fired as
``[E] [PS-169 §1 hosted-runner-forbidden] … job `publish` runs on
GitHub-hosted runner `ubuntu-latest``` and blocked the PR — a PR whose fix
commit was titled "run the pack publish on the self-hosted pool". Every PR in
the current migration is new-violation-shaped by definition, so every one of
them would have hit this.

A gate that permits the accumulated mess and blocks its correction is worse
than no gate. The ratchet is gone; PS-169 is now a flat, unconditional W.

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

Severity: flat W, no ratchet, no promotion path
-----------------------------------------------
The rule ships at **W** in ``_extra_rules`` and stays there for every
finding, new or pre-existing. W never affects the exit code
(``_audit.py``: ``exit_code = 1 if n_errors > 0 else 0``), which is the
intent — hosted is permitted, so nothing here may block a merge.

There is deliberately **no promote-to-E path**. If a future directive
re-prohibits hosted runners, that is a new decision and it should be written
as one, not inherited from a TODO left behind by the superseded 2026-07-14
mandate.

What still relies on this check
--------------------------------
Whether a job is on a hosted runner remains a fact worth reporting: it drives
the "why is this repo's CI slow?" question, and the fleet's migration
inventory reads these findings. Detection is unchanged — only the
consequence is.

Not to be confused with PS-224
-------------------------------
PS-224 (``_check_runner_destinations``) is the rule with teeth, and it is
about a different failure: a job whose labels NO machine serves is not slow,
it is UNDELIVERABLE — GitHub queues it forever rather than rejecting it. That
rule stays at E, and it already accepts GitHub-provided images (they are
served by GitHub, so they cannot queue forever). The two rules therefore
agree: a hosted destination is legal, merely slower.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

# `escalate_new_violations` is deliberately NOT imported any more — see
# `check_ps169_hosted_runners`. Only the baseline-ref default is kept, so the
# public signature is unchanged for existing callers.
from ._new_vs_baseline import DEFAULT_BASELINE_REF

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
                            "parse as YAML; scanned literally) — ALLOWED, but "
                            "slower than hardware we own. Advisory only (W).",
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
                        f"`{label}`{via} — ALLOWED, but slower than hardware "
                        "we own. Hosted runners are free for public "
                        "repositories, so this is a legitimate choice where "
                        "turnaround does not matter. Where it does, target a "
                        "machine we own: `runs-on: ${{ fromJSON(vars."
                        "CI_RUNS_ON || '[\"self-hosted\",\"Linux\",\"X64\","
                        "\"scitex-ci\"]') }}`. Advisory only (W) — this never "
                        "fails a build.",
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
    # NO baseline escalation. Every finding stays at the rule default W.
    # The ratchet was removed on 2026-08-05: it left a long-standing
    # `ubuntu-latest` at W (permitted) while escalating a job newly MOVED onto
    # hosted to E — blocking the very PR that complies with the directive to
    # take CI off Spartan. `baseline_ref` is retained in the signature for
    # call-site compatibility and is deliberately unused.
    out.extend(_collect_ps169_violations(repo, violation_cls))


# EOF
