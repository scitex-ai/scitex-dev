"""Exact protected-main Dev publisher source; observation grants no access.

The source pins bind the reviewed release proposal, not an assertion that it
has reached main. The original finite central profiles remain unchanged.
"""
from __future__ import annotations

import re
from dataclasses import replace

import yaml

DEV_SELECTION = (
    "scitex-ai/scitex-dev/.github/workflows/"
    "pypi-publish-and-github-release-on-tag.yml@refs/heads/main"
)
DEV_SOURCE_ROWS = (('scitex-ai/scitex-dev',
  'refs/heads/main',
  '.github/workflows/pypi-publish-and-github-release-on-tag.yml',
  23338,
  '8628ecdb6dbfebebc791f26fbb9db22cd9289f6834935a3f9ece1934643b66f7',
  '6db7b25d8563a2e592b810d560f765e128656e39'),
 ('scitex-ai/scitex-dev',
  'refs/heads/main',
  '.github/ci/exec-in-sif.sh',
  7590,
  'dffc356c99c0deb8c031580ea667f6e4ea695dd1ce000d19a1a127442b8c9cf0',
  '7534bc585618959178ce23e310af51e268b32f9c'),
 ('scitex-ai/scitex-dev',
  'refs/heads/main',
  '.github/ci/run-in-sif.sh',
  10126,
  'cc690aeca6770e980652f499d50571e0e2fc759abbf2b870c650fcc3dd493786',
  '8f99e991073111953f7ea14b9ef9dba19040e913'),
 ('scitex-ai/scitex-dev',
  'refs/heads/main',
  '.github/ci/build-in-sif.sh',
  3997,
  '30961623dc2d790adaa43356ff236e5f5ace27f708caaf096d4019660c569c08',
  '1ec3dce49e682670af82319746aec785dd5cc068'),
 ('scitex-ai/scitex-dev',
  'refs/heads/main',
  '.github/ci/publish-in-sif.sh',
  5382,
  '8c1aee030d76b05f650dba88c9508e6241e8fa6c779df6df9aa3c629254dac02',
  'a82d3d62dd044eebdfd96d92e6e8f9cd017314cc'),
 ('scitex-ai/scitex-dev',
  'refs/heads/main',
  '.github/ci/release-context.sh',
  2419,
  'd7433cacdd9098bdbe77994ba7a78d91b90edc7164a00a40450db19978ac57f8',
  'c5846e29e1a95524259438794b9df0563413bf16'),
 ('scitex-ai/scitex-dev',
  'refs/heads/main',
  '.github/ci/release-identity.py',
  7861,
  '0c80f6631f00190ccb24833d95a800af3d979e69c720aa66bb2b5ae0c61f220a',
  'fee36c50a50f43d5a9c6a04df569480d331c3f0c'),
 ('scitex-ai/scitex-dev',
  'refs/heads/main',
  '.github/ci/verify-postgres-capability.py',
  5391,
  'af610a811b19f746c9a717fbebbc67639b16df962544acac9b51a3dd38a43455',
  'df3dc0911f2fb5f69b6cb042f11e5e804ffc69ed'),
 ('scitex-ai/.github',
  'refs/heads/main',
  '.github/workflows/ci-sif-matrix.yml',
  67246,
  'bba67919d4c8f82644a18e9e0ab9cea8b78cbdd241a8680b5dbda78e655bb6d4',
  'bf437bb375fce251b4dc38488808b8772efc3789'),
 ('scitex-ai/.github',
  'refs/heads/main',
  '.github/workflows/runner-admission.yml',
  4642,
  'f2e92f6a50526c2133cd12ae7c5cbd98ce2922354bd85c628ca48aad4acc6d18',
  '3e988cf244f5ec84c703619491707012095cdcaf'),
 ('scitex-ai/.github',
  'd7d96c34d68cdfbb5503a933591f7748b5aa30ee',
  '.github/workflows/runner-admission.yml',
  4642,
  'f2e92f6a50526c2133cd12ae7c5cbd98ce2922354bd85c628ca48aad4acc6d18',
  '3e988cf244f5ec84c703619491707012095cdcaf'))

DEV_CHECKS = frozenset("pytest-matrix-on-ubuntu-py" + minor for minor in ("3.11", "3.12", "3.13"))


def _main(repository, api, result):
    row = api(f"repos/{repository}/branches/main")
    try:
        revision = row["commit"]["sha"]
        if (row["name"] != "main" or type(row["protected"]) is not bool
                or not isinstance(revision, str) or not re.fullmatch(r"[a-f0-9]{40}", revision)):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        result["unknown"].append(f"publisher source main unavailable: {repository}")
        return None
    if not row["protected"]:
        result["violations"].append(f"publisher source main unprotected: {repository}")
        return None
    return revision


def _dev_protection(api, result):
    data = api("repos/scitex-ai/scitex-dev/branches/main/protection")
    try:
        flags = {key: data[key]["enabled"] for key in (
            "enforce_admins", "allow_force_pushes", "allow_deletions", "required_linear_history")}
        checks = data["required_status_checks"]
        reviews = data["required_pull_request_reviews"]
        if (any(type(value) is not bool for value in flags.values())
                or type(checks["strict"]) is not bool or not isinstance(checks["checks"], list)
                or any(not isinstance(row, dict) or not isinstance(row.get("context"), str)
                       or type(row.get("app_id")) is not int for row in checks["checks"])
                or (reviews is not None and not isinstance(reviews, dict))):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        result["unknown"].append("Dev publisher main protection unavailable")
        return None
    actual_checks = {(row["context"], row["app_id"]) for row in checks["checks"]}
    if (flags["allow_force_pushes"] or flags["allow_deletions"]
            or not flags["required_linear_history"] or reviews is None
            or not {(name, 15368) for name in DEV_CHECKS}.issubset(actual_checks)):
        result["violations"].append("Dev publisher main protection weakened")
        return None
    # Preserve the actual existing Dev policy: strict/enforce_admins were false.
    # Their boolean values are observed and CAS-bound, never reported as true.
    return {"flags": flags, "strict": checks["strict"], "checks": sorted(actual_checks),
            "reviews": reviews}


def _release_shape(bodies):
    workflow = yaml.safe_load(bodies[0])
    events = workflow.get("on", workflow.get(True))
    if events != {"push": {"tags": ["v*"]}, "workflow_dispatch": {"inputs": {
        "version": {"description": "Existing promoted release tag (vX.Y.Z)",
                    "required": True, "type": "string"}}}}:
        raise ValueError
    jobs = workflow["jobs"]
    if set(jobs) != {"runner-admission", "test-and-build", "publish", "release"}:
        raise ValueError
    admission = jobs["runner-admission"]
    if admission != {
        "uses": "scitex-ai/.github/.github/workflows/runner-admission.yml@d7d96c34d68cdfbb5503a933591f7748b5aa30ee",
        "with": {"runs_on": '["self-hosted","Linux","X64","scitex-org-cpu"]'}}:
        raise ValueError
    build = jobs["test-and-build"]
    if (build["uses"] != "scitex-ai/.github/.github/workflows/ci-sif-matrix.yml@main"
            or build["with"] != {"suite": "dev-release", "release_tag": "${{ inputs.version || '' }}",
                                  "runs_on": '["self-hosted","Linux","X64","scitex-org-cpu"]'}):
        raise ValueError
    for name in ("publish", "release"):
        job = jobs[name]
        steps = job["steps"]
        if (job["if"] != "github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main'"
                or job["needs"] != ["runner-admission", "test-and-build"] + (["publish"] if name == "release" else [])
                or job["runs-on"] != "${{ fromJSON(needs.runner-admission.outputs.runs_on) }}"
                or steps[2]["uses"] != "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
                or steps[2]["with"]["ref"] != "${{ needs.test-and-build.outputs.source_commit }}"
                or steps[3]["run"] != 'test "$(git rev-parse HEAD)" = "$RELEASE_COMMIT"'
                or steps[1]["run"] != 'set -euo pipefail\ntest "$RUNNER_ENVIRONMENT" = self-hosted\ntest "$NATIVE_AUTHORIZED" = true\n'):
            raise ValueError
    publish = jobs["publish"]
    if (publish["environment"]["name"] != "pypi"
            or publish["permissions"] != {"contents": "read", "id-token": "write"}
            or publish["steps"][-1]["run"] != "bash .github/ci/exec-in-sif.sh publish-in-sif.sh 3.12"):
        raise ValueError
    callee = yaml.safe_load(bodies[8])
    if callee["jobs"]["build-dev-release"]["needs"] != ["runner-admission", "profile", "test-dev"]:
        raise ValueError
    # Whole reviewed bytes also retain the actual three-minor matrix, release
    # source/runtime/image verification, artifact gate and original OIDC code.


def qualify_dev_release(caller, api, result):
    """Observe the one literal publisher and both complete protected source roots."""
    from ._policy_callers import _source
    from ._policy_contract import _protection

    if caller.selection != DEV_SELECTION or tuple(
        (pin.repository, pin.revision, pin.path, pin.bytes, pin.sha256, pin.git_oid)
        for pin in caller.sources
    ) != DEV_SOURCE_ROWS:
        result["violations"].append("Dev publisher outside exact registered source")
        return
    repositories = ("scitex-ai/scitex-dev", "scitex-ai/.github")
    before = {repository: _main(repository, api, result) for repository in repositories}
    protection = _dev_protection(api, result)
    _protection(api, result)
    if None in before.values() or protection is None or result["unknown"] or result["violations"]:
        return
    bodies = []
    for pin in caller.sources:
        resolved = replace(pin, revision=before[pin.repository]) if pin.revision == "refs/heads/main" else pin
        bodies.append(_source(resolved, api, result))
    if any(body is None for body in bodies):
        return
    try:
        _release_shape(bodies)
    except (AttributeError, IndexError, KeyError, TypeError, ValueError, yaml.YAMLError):
        result["violations"].append("Dev publisher admission or full release shape changed")
        return
    after_protection = _dev_protection(api, result)
    _protection(api, result)
    after = {repository: _main(repository, api, result) for repository in repositories}
    if before != after or protection != after_protection:
        result["unknown"].append("Dev publisher protected source changed during qualification")
