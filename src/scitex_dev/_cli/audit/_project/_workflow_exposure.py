"""Workflow EXPOSURE: which jobs an attacker can trigger, and what they hold.

Sixteen rule modules in this corpus read ``.github/workflows/``. Before this
module, ZERO of them modelled the workflow's TRIGGER. They read two axes:

* PS-168 — how a secret is NAMED (``GH_PERSONAL_ACCESS_TOKEN`` is canonical).
* PS-224 — where the job RUNS (must be a registered destination).

Trigger is the axis that decides whether the other two matter. Reading a
secret's name and a job's destination while ignoring who can start it
produced a rule pair whose combined advice was: *"that correctly-named
fleet PAT — please run it on the shared box."*

Why the trigger is the security-relevant axis
---------------------------------------------
``pull_request_target``, ``issue_comment`` and ``workflow_run`` run against
the BASE repository with access to its secrets, and they can be started by
someone with no write access — opening a PR or typing a comment is enough.
``pull_request``, by contrast, runs in a fork context without base secrets.
So the dangerous combination is not "has a secret" and not "runs on a
hosted runner"; it is::

    attacker can start it  AND  it holds a credential

For that combination a GitHub-hosted ephemeral VM is the CORRECT
destination. The VM is destroyed after the run, so a compromise costs an
attacker one job. Relocating the same job to a persistent self-hosted
runner — which is what an unqualified "use a registered destination" rule
asks for — puts attacker-triggerable code on the machine that stores the
credential and serves every other repository's CI.

This module reports exposure. It does NOT decide policy: whether a hosted
destination is PERMITTED is a fleet directive, not a property of the YAML.
Callers combine this answer with the directive; see PS-224's use of it.
"""

from __future__ import annotations

import re
from typing import Any

__all__ = [
    "ATTACKER_TRIGGERABLE_EVENTS",
    "attacker_triggerable_events",
    "job_secret_refs",
    "is_exposed_credential_job",
    "destination_detail",
]

#: Events startable by someone WITHOUT write access, that still run against
#: the base repo with its secrets. `pull_request` is deliberately absent: a
#: fork PR runs without base secrets, so it does not carry this exposure.
#: `workflow_run` is included because it inherits the base context from a
#: workflow that may itself have been fork-triggered.
ATTACKER_TRIGGERABLE_EVENTS = frozenset(
    {
        "pull_request_target",
        "issue_comment",
        "issues",
        "workflow_run",
        "discussion_comment",
        "pull_request_review_comment",
        "pull_request_review",
    }
)

#: `${{ secrets.FOO }}` anywhere in a job's serialized body. Deliberately a
#: TEXT scan rather than a walk of known secret-bearing keys: a secret can
#: reach a step through `env:`, `with:`, an inline `run:` string, or a
#: `uses:` input, and enumerating those sites is exactly the kind of
#: incomplete list this module exists to stop relying on. Over-matching here
#: is safe — it can only make the rule MORE cautious about relocation.
_SECRET_REF_RE = re.compile(r"\$\{\{\s*secrets\.([A-Za-z_][A-Za-z0-9_-]*)")


def attacker_triggerable_events(doc: dict) -> frozenset[str]:
    """Return the workflow's declared events that an attacker can start.

    Handles the YAML gotcha that bites every naive reader of a workflow:
    the bare key ``on:`` parses as the BOOLEAN ``True``, not the string
    ``"on"``, so ``doc.get("on")`` alone silently returns nothing for most
    real workflows. This is the same both-spellings lookup
    ``_check_hosted_runners`` already performs.
    """
    block: Any = doc.get("on")
    if block is None:
        block = doc.get(True)

    if isinstance(block, str):
        names: set[str] = {block}
    elif isinstance(block, dict):
        names = {str(k) for k in block}
    elif isinstance(block, list):
        names = {str(k) for k in block}
    else:
        names = set()

    return frozenset(names & ATTACKER_TRIGGERABLE_EVENTS)


def job_secret_refs(job: Any) -> frozenset[str]:
    """Return the names of every ``secrets.*`` reference inside one job."""
    if job is None:
        return frozenset()
    return frozenset(_SECRET_REF_RE.findall(_flatten(job)))


def _flatten(node: Any) -> str:
    """Serialize a parsed-YAML subtree to searchable text.

    `repr` would be shorter, but it escapes nothing predictably across
    container types; this walk keeps every scalar intact so the secret
    pattern sees the same characters that were in the file.
    """
    if isinstance(node, dict):
        return " ".join(f"{k} {_flatten(v)}" for k, v in node.items())
    if isinstance(node, (list, tuple)):
        return " ".join(_flatten(v) for v in node)
    return str(node)


def is_exposed_credential_job(doc: dict, job: Any) -> tuple[bool, frozenset[str], frozenset[str]]:
    """Is this job attacker-triggerable AND credential-bearing?

    Returns ``(exposed, events, secrets)`` so a caller can name BOTH halves
    of the reason in its finding. A caller that reports only "exposed" makes
    the human re-derive which trigger and which secret — the omission that
    let this class stay invisible across 16 workflow-reading rules.
    """
    events = attacker_triggerable_events(doc)
    secrets = job_secret_refs(job)
    return (bool(events) and bool(secrets)), events, secrets


def destination_detail(
    job_id: object,
    labels: list[str],
    registry_file: object,
    legal: object,
    exposed: bool,
    events: frozenset[str],
    secrets: frozenset[str],
) -> str:
    """Build PS-224's finding text, which BRANCHES on exposure.

    The unexposed branch keeps PS-224's original remedy: register the
    machine or re-point the job.

    The exposed branch must NOT say that. "Re-point the job" aimed at an
    attacker-triggerable, credential-bearing workflow means *move the
    attacker's entry point onto the machine that holds the credential* —
    the rule would be issuing, in the fleet's own voice, the exact change
    an attacker wants. Measured across the fleet: 619 workflow files in
    112 repos, 434 carrying a hosted label, of which 70 are also
    attacker-triggerable and secret-bearing.

    So the exposed branch reports the same FACT (this destination is not
    registered) and withholds the remedy, because the safe remedy is not
    the rule's to choose: keeping the job hosted conflicts with the
    fleet's no-hosted-runners directive, and removing the credential
    changes what the workflow can do. Both are decisions for whoever owns
    the directive. A rule that cannot name a safe fix should say so
    plainly rather than name an unsafe one.
    """
    head = (
        f"job `{job_id}` targets `[{', '.join(labels)}]`, NOT in "
        f"the destination registry ({registry_file}). "
    )
    if not exposed:
        return head + (
            "Register the machine under `runner_labels:` or re-point the job. "
            "Checks REGISTRATION, not reachability: a SELF-HOSTED label "
            "no runner advertises queues indefinitely (never fails, never "
            "runs); a GitHub-HOSTED one IS served and DOES run, flagged "
            f"on policy. Confirm a job is idle before re-pointing. {legal}."
        )
    return head + (
        "DO NOT RE-POINT THIS JOB — it is attacker-triggerable "
        f"(`{'`, `'.join(sorted(events))}`) and carries "
        f"`secrets.{'`, `secrets.'.join(sorted(secrets))}`. Those events run "
        "against the BASE repo with its secrets and need no write access to "
        "start, so an ephemeral hosted VM is the correct isolation: a "
        "compromise costs one disposable runner. Moving it to a persistent "
        "self-hosted destination puts attacker-triggerable code on the "
        "machine that stores the credential and serves every other repo's "
        "CI. Resolving this needs a decision, not a re-point: either the "
        "job keeps a hosted destination (an exception to the no-hosted-"
        "runners directive) or it stops needing the credential. Escalate "
        f"rather than silence. Registered destinations: {legal}."
    )


# EOF
