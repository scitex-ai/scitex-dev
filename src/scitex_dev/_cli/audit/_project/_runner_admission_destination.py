"""Resolve only the reviewed central admission output for PS-224.

This static source door does not establish membership, runner access, image
readiness or an actual job result. It resolves the declared native label set;
the caller still checks it against the unchanged machine-registry floor.
"""

from __future__ import annotations

import json
import re

ADMISSION_SOURCE = (
    "scitex-ai/.github/.github/workflows/runner-admission.yml@"
    "d7d96c34d68cdfbb5503a933591f7748b5aa30ee"
)
ADMISSION_SOURCE_SHA256 = (
    "f2e92f6a50526c2133cd12ae7c5cbd98ce2922354bd85c628ca48aad4acc6d18"
)
DESTINATION_OUTPUT = "${{ fromJSON(needs.runner-admission.outputs.runs_on) }}"
AUTHORIZED_OUTPUT = "${{ needs.runner-admission.outputs.native_authorized }}"
NATIVE_JOB_IF = "${{ needs.runner-admission.outputs.native_authorized == 'true' }}"
_KNOWN_NATIVE = frozenset(
    {
        "self-hosted",
        "Linux",
        "X64",
        "scitex-ci",
        "scitex-org-cpu",
        "scitex-local-cpu",
        "scitex-docker",
        "sac-control-plane",
        "scitex-compute-02",
        "scitex-compute-03",
        "scitex-compute-04",
    }
)
_CAPACITY = frozenset(
    {"scitex-ci", "scitex-org-cpu", "scitex-local-cpu", "scitex-docker"}
)
_FALLBACK = re.compile(r"\$\{\{\s*vars\.CI_RUNS_ON\s*\|\|\s*'([^']+)'\s*\}\}")


def _native_labels(value):
    if not isinstance(value, str):
        return None
    fallback = _FALLBACK.fullmatch(value)
    literal = fallback[1] if fallback else value
    try:
        labels = json.loads(literal)
    except ValueError:
        return None
    if (
        not isinstance(labels, list)
        or not 1 <= len(labels) <= 12
        or any(
            not isinstance(label, str) or label not in _KNOWN_NATIVE for label in labels
        )
        or len(set(labels)) != len(labels)
        or "self-hosted" not in labels
        or not _CAPACITY.intersection(labels)
    ):
        return None
    return labels


def _lines(script):
    if not isinstance(script, str):
        return None
    return [
        line.strip()
        for line in script.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def _guarded(job, labels):
    steps = job.get("steps")
    if not isinstance(steps, list) or not steps or not isinstance(steps[0], dict):
        return False
    first = steps[0]
    # No step condition, error continuation or alternate shell can bypass this
    # first action. GitHub's ordinary Bash run step supplies errexit.
    if set(first) - {"name", "env", "run"}:
        return False
    native_env = {
        "NATIVE_AUTHORIZED": AUTHORIZED_OUTPUT,
        "RUNNER_ENVIRONMENT": "${{ runner.environment }}",
    }
    native_lines = [
        'test "$NATIVE_AUTHORIZED" = "true"',
        'test "$RUNNER_ENVIRONMENT" = "self-hosted"',
    ]
    if (
        first.get("env") == native_env
        and _lines(first.get("run")) == native_lines
        and job.get("if") == NATIVE_JOB_IF
    ):
        return True
    hybrid_env = {
        **native_env,
        "ADMISSION_REASON": "${{ needs.runner-admission.outputs.reason }}",
        "ADMISSION_RUNS_ON": "${{ needs.runner-admission.outputs.runs_on }}",
    }
    destination = json.dumps(
        {"group": "Organization", "labels": labels}, separators=(",", ":")
    )
    hybrid_lines = [
        "set -eu",
        'case "$RUNNER_ENVIRONMENT" in',
        "self-hosted)",
        'test "$NATIVE_AUTHORIZED" = true',
        'test "$ADMISSION_REASON" = confirmed-organization-members',
        f"test \"$ADMISSION_RUNS_ON\" = '{destination}'",
        ";;",
        "github-hosted)",
        ";;",
        "*)",
        "printf '%s\\n' 'Unknown runner environment refused' >&2",
        "exit 1",
        ";;",
        "esac",
    ]
    return first.get("env") == hybrid_env and _lines(first.get("run")) == hybrid_lines


def resolve_admission_destination(doc, job):
    """Return declared labels only for the exact callee and first native fence.

    The established CI_RUNS_ON idiom retains its literal-fallback semantics.
    A variable override's runtime labels remain the admission callee's decision;
    this source audit makes no assertion about a current repository variable.
    """
    if not isinstance(doc, dict) or not isinstance(job, dict):
        return None
    for environment in (doc.get("env", {}), job.get("env", {})):
        if not isinstance(environment, dict) or {
            "BASH_ENV",
            "ENV",
            "SHELLOPTS",
            "BASHOPTS",
        }.intersection(environment):
            return None
    if (
        job.get("runs-on") != DESTINATION_OUTPUT
        or doc.get("defaults")
        or job.get("defaults")
    ):
        return None
    needs = job.get("needs")
    needs = [needs] if isinstance(needs, str) else needs
    if not isinstance(needs, list) or "runner-admission" not in needs:
        return None
    jobs = doc.get("jobs")
    admission = jobs.get("runner-admission") if isinstance(jobs, dict) else None
    if (
        not isinstance(admission, dict)
        or admission.get("uses") != ADMISSION_SOURCE
        or set(admission) - {"name", "uses", "with", "permissions"}
        or not isinstance(admission.get("with"), dict)
        or set(admission["with"]) != {"runs_on"}
    ):
        return None
    labels = _native_labels(admission["with"]["runs_on"])
    return labels if labels is not None and _guarded(job, labels) else None
