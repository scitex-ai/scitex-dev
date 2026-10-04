"""Finite literal runner selections, reviewed bytes and fresh main protection.

Branch and SHA selections retain their distinct literal spelling. Only the
eleven protected-main definitions, the explicit transitional SHA profile, or
their exact union are qualified, with an optional finite subset of registered
immutable leaf callers. Local reusable dependencies are read at the defining
commit.
This observer never changes workflow access or infers actual job admission.
"""
from __future__ import annotations

import base64
import hashlib
import re

import yaml

NATIVE_WORKFLOWS = (
    "auto-merge-to-develop.yml", "cla.yml", "import-smoke.yml",
    "promote-develop-to-main-on-tag.yml", "pytest-matrix.yml",
    "quality-audit.yml", "rtd-sphinx-build.yml",
    "ci-sif-matrix.yml", "writer-release-sif.yml", "fd-fclones-integration.yml", "runner-health.yml",
)
# Exact hashes are generated from the reviewed organization source packet.
WORKFLOW_HASHES = {'auto-merge-to-develop.yml': 'a28d9b92576590903290809643f21c93f680a6b2a1a8913d6c6e2fed89993de0',
 'cla.yml': '55b422a674acb918d247b3a025bf413fe751de16b85f5f06f1251331c4d98c06',
 'import-smoke.yml': '3df1f4d4abd9da553b36484e37b8c5588e5684f6618d1b102c698893595fe8d6',
 'promote-develop-to-main-on-tag.yml': '1e3cec556f96612ff987f1bc2969dd145f85ebfff48297a3bf3adccd0b8c0c69',
 'pytest-matrix.yml': 'e822cffc869bde67a19b97755aa5844c2c83ee717c168540562ee0984a72f0ae',
 'quality-audit.yml': 'f44a2e6b5c479c2975d1cedf66738fdbf402a74cf1d8e26340bb9895524e7b4a',
 'rtd-sphinx-build.yml': 'cc680b6ceecac73566b212a0db96ba016b3aa28766700e95b04691981ededaad',
 'runner-admission.yml': 'f2e92f6a50526c2133cd12ae7c5cbd98ce2922354bd85c628ca48aad4acc6d18',
 'ci-sif-matrix.yml': '84aa0118ee9b97b4e1ecd7a81c84ca6455609eebed6412b82873c056f1c88d69',
 'writer-release-sif.yml': '6ba940f2831159a4a3401746d29b8acdfc74fe89e336fe1dd7065bf21b85d1bb',
 'fd-fclones-integration.yml': 'a183e685a397fad2fad66375b0a9a7a87df945d9048d1277d1a605a9ba3a36c5',
 'runner-health.yml': 'e1bbd6cfa7f9c576898ffde263931f5d7ab6ab1c034197b5e03a0607897505d7'}

PREFIX = "scitex-ai/.github/.github/workflows/"
BRANCH = "refs/heads/main"
OLD_REVISION = "8c646081e9f1352077d3d8674052cce7ec75a1b7"
SIF_REVISION = "e09a4f6746c79c7cc64ca6503350a8096411b25d"
NEW_REVISION = "442f4e5dcd938c0297e36a5f07461d809f9416ff"
IMMUTABLE_REVISIONS = {
    name: OLD_REVISION if index < 7 else SIF_REVISION if index == 7 else NEW_REVISION
    for index, name in enumerate(NATIVE_WORKFLOWS[:10])
}
BRANCH_SELECTION = tuple(PREFIX + name + "@" + BRANCH for name in NATIVE_WORKFLOWS)
IMMUTABLE_SELECTION = tuple(PREFIX + name + "@" + revision for name, revision in IMMUTABLE_REVISIONS.items())
TRANSITION_SELECTION = BRANCH_SELECTION + IMMUTABLE_SELECTION
IMMUTABLE_ADMISSION_HASH = "e4eb6c5cc5aedd8a460380f796047c2ea33a446846235001355697350d36c915"
IMMUTABLE_HASHES = {
    OLD_REVISION: {**{name: WORKFLOW_HASHES[name] for name in (*NATIVE_WORKFLOWS[:7], "runner-admission.yml")},
                   "import-smoke.yml": "df8fb3d63e91612353b3fcbfcaf6f0e43d7c0102f799b48e82d8a47e32956f06",
                   "rtd-sphinx-build.yml": "51be02f591beeeb5398b6447a7c26f0959e5487cad5b974bf62d2cf56fd51b5d",
                   "runner-admission.yml": IMMUTABLE_ADMISSION_HASH},
    SIF_REVISION: {"ci-sif-matrix.yml": "f2abf8459abf711beb25355061df43572e506ae1461ffaf62cdaab2b05abcce1",
                   "runner-admission.yml": IMMUTABLE_ADMISSION_HASH},
    NEW_REVISION: {**{name: WORKFLOW_HASHES[name] for name in (*NATIVE_WORKFLOWS[8:10], "runner-admission.yml")},
                   "runner-admission.yml": IMMUTABLE_ADMISSION_HASH},
}


def _body(api, name, revision, result):
    payload = api(f"repos/scitex-ai/.github/contents/.github/workflows/{name}?ref={revision}")
    try:
        if payload.get("type") != "file" or payload.get("encoding") != "base64":
            raise ValueError
        encoded = payload["content"]
        if not isinstance(encoded, str) or len(encoded) > 256 * 1024:
            raise ValueError
        return base64.b64decode("".join(encoded.split()), validate=True)
    except (AttributeError, KeyError, TypeError, ValueError):
        result["unknown"].append(f"reviewed workflow bytes unavailable: {name}")
        return None


def _main(api, result):
    branch = api("repos/scitex-ai/.github/branches/main")
    try:
        revision = branch["commit"]["sha"]
        if branch["name"] != "main" or not isinstance(revision, str) or not re.fullmatch(r"[a-f0-9]{40}", revision):
            raise ValueError
        if type(branch["protected"]) is not bool:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        result["unknown"].append("central main revision/protection unavailable")
        return None
    if not branch["protected"]:
        result["violations"].append("central main is not protected")
    return revision


def _protection(api, result):
    data = api("repos/scitex-ai/.github/branches/main/protection")
    if not isinstance(data, dict):
        result["unknown"].append("central main protection unavailable")
        return
    for key, expected in (("enforce_admins", True), ("allow_force_pushes", False), ("allow_deletions", False)):
        row = data.get(key)
        value = row.get("enabled") if isinstance(row, dict) else None
        if type(value) is not bool:
            result["unknown"].append(f"central main protection field unavailable: {key}")
        elif value is not expected:
            result["violations"].append(f"central main protection weakened: {key}")
    if "required_pull_request_reviews" not in data:
        result["unknown"].append("central main pull request protection unavailable")
    elif data["required_pull_request_reviews"] is None:
        result["violations"].append("central main mandatory pull request protection absent")
    elif not isinstance(data["required_pull_request_reviews"], dict):
        result["unknown"].append("central main pull request protection malformed")
    checks = data.get("required_status_checks")
    if checks is None and "required_status_checks" in data:
        result["violations"].append("central main mandatory status protection absent")
    elif not isinstance(checks, dict) or type(checks.get("strict")) is not bool or not isinstance(checks.get("checks"), list):
        result["unknown"].append("central main strict pytest protection unavailable")
    elif any(not isinstance(check, dict) or not isinstance(check.get("context"), str)
             or (check.get("app_id") is not None and type(check.get("app_id")) is not int)
             for check in checks["checks"]):
        result["unknown"].append("central main status check identity malformed")
    elif not checks["strict"] or not any(isinstance(check, dict) and check.get("context") == "pytest"
                                         and type(check.get("app_id")) is int and check["app_id"] == 15368
                                         for check in checks["checks"]):
        result["violations"].append("central main strict GitHub pytest protection weakened")


def _source_closure(api, names, revision, hashes, result):
    pending = list(names)
    visited = set()
    while pending:
        name = pending.pop(0)
        if name in visited:
            continue
        visited.add(name)
        if name not in hashes:
            result["violations"].append("local reusable dependency outside reviewed byte contract")
            continue
        body = _body(api, name, revision, result)
        if body is None:
            continue
        actual = hashlib.sha256(body).hexdigest()
        result["source"].append({"workflow": name, "revision": revision, "sha256": actual})
        if actual != hashes[name]:
            result["violations"].append(f"reviewed workflow bytes changed: {name}")
            continue
        try:
            workflow = yaml.safe_load(body)
            events = workflow.get("on", workflow.get(True))
            if not isinstance(events, dict) or "workflow_call" not in events or not isinstance(workflow.get("jobs"), dict):
                raise ValueError
            for job in workflow["jobs"].values():
                if not isinstance(job, dict):
                    raise TypeError
                uses = job.get("uses")
                if isinstance(uses, str) and uses.startswith("./"):
                    match = re.fullmatch(r"\./\.github/workflows/([A-Za-z0-9_-]+\.yml)", uses)
                    if not match:
                        raise ValueError
                    pending.append(match[1])
        except (AttributeError, TypeError, ValueError, yaml.YAMLError):
            result["unknown"].append(f"reviewed reusable workflow shape unavailable: {name}")


def _qualify_fixed_bytes(groups, api, hashes, names_expected) -> dict:
    """Retain the explicit immutable byte-contract adapter used by callers/tests."""
    result = {"expected": [], "violations": [], "unknown": [], "source": []}
    restricted = [g for g in groups if g.get("restricted_to_workflows") is True]
    if not restricted:
        return result
    revisions = set()
    for group in restricted:
        refs = group.get("selected_workflows")
        if not isinstance(refs, list) or len(refs) != len(names_expected):
            result["violations"].append("reviewed workflow selection count differs from the byte contract")
            continue
        names = set()
        for ref in refs:
            m = re.fullmatch(r"scitex-ai/\.github/\.github/workflows/([A-Za-z0-9_-]+\.yml)@([a-f0-9]{40})", ref) if isinstance(ref, str) else None
            if not m:
                result["violations"].append("reviewed workflow selection has a mutable or foreign revision")
                continue
            names.add(m[1])
            revisions.add(m[2])
        if names != set(names_expected):
            result["violations"].append("reviewed workflow definitions differ from the organization contract")
    if result["violations"] or len(revisions) != 1:
        if len(revisions) != 1:
            result["violations"].append("reviewed workflows must share one immutable revision")
        return result
    revision = next(iter(revisions))
    for name, expected in hashes.items():
        body = _body(api, name, revision, result)
        if body is None:
            continue
        actual = hashlib.sha256(body).hexdigest()
        result["source"].append({"workflow": name, "revision": revision, "sha256": actual})
        if actual != expected:
            result["violations"].append(f"reviewed workflow bytes changed: {name}")
    if not hashes:
        result["unknown"].append("reviewed workflow byte contract absent")
    if not result["unknown"] and not result["violations"]:
        result["expected"] = [f"scitex-ai/.github/.github/workflows/{name}@{revision}" for name in names_expected]
    return result


def qualify_workflows(groups, api, *, workflow_hashes=None, native_workflows=None) -> dict:
    if workflow_hashes is not None or native_workflows is not None:
        return _qualify_fixed_bytes(groups, api,
            WORKFLOW_HASHES if workflow_hashes is None else workflow_hashes,
            NATIVE_WORKFLOWS if native_workflows is None else native_workflows)
    result = {"expected": [], "violations": [], "unknown": [], "source": []}
    from ._policy_callers import REGISTERED_SELECTION, qualify_registered_callers
    restricted = [g for g in groups if g.get("restricted_to_workflows") is True]
    if not restricted:
        return result
    selections = []
    for group in restricted:
        refs = group.get("selected_workflows")
        if (not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs)
                or len(set(refs)) != len(refs)
                or set(refs) - set(REGISTERED_SELECTION) not in
                (set(BRANCH_SELECTION), set(IMMUTABLE_SELECTION), set(TRANSITION_SELECTION))):
            result["violations"].append("selected workflows differ from the finite literal organization profiles")
            continue
        selections.append(set(refs))
    if result["violations"]:
        return result
    if any(refs != selections[0] for refs in selections):
        result["violations"].append("organization groups select different reviewed profiles")
        return result
    selected = selections[0]
    branch_selected = bool(selected.intersection(BRANCH_SELECTION))
    immutable_selected = bool(selected.intersection(IMMUTABLE_SELECTION))
    revision = None
    if branch_selected:
        revision = _main(api, result)
        _protection(api, result)
        if revision is None or result["unknown"] or result["violations"]:
            return result
        _source_closure(api, NATIVE_WORKFLOWS, revision, WORKFLOW_HASHES, result)
    if immutable_selected:
        for fixed_revision, hashes in IMMUTABLE_HASHES.items():
            names = [name for name, selected_revision in IMMUTABLE_REVISIONS.items()
                     if selected_revision == fixed_revision]
            _source_closure(api, names, fixed_revision, hashes, result)
    qualify_registered_callers(selected, api, result)
    if branch_selected:
        _protection(api, result)
        after = _main(api, result)
        if after is not None and after != revision:
            result["unknown"].append("central main revision changed during source qualification")
    expected = (TRANSITION_SELECTION if branch_selected and immutable_selected
                else BRANCH_SELECTION if branch_selected else IMMUTABLE_SELECTION)
    if not result["unknown"] and not result["violations"]:
        result["expected"] = list(expected) + [ref for ref in REGISTERED_SELECTION if ref in selected]
    return result
