"""Finite literal runner selections, reviewed bytes and fresh main protection.

Branch and SHA selections retain their distinct literal spelling. Only the
eleven protected-main definitions, the explicit transitional SHA profile, or
their exact union are qualified, with an optional finite subset of registered
leaf callers, including the one protected-main Dev publisher. Local reusable dependencies are read at the defining
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
 'cla.yml': 'd39672edd41d5689c4d3f203bd94b7fb7ecfd1dce589e07f40ccff8b494d1732',
 'import-smoke.yml': '3df1f4d4abd9da553b36484e37b8c5588e5684f6618d1b102c698893595fe8d6',
 'promote-develop-to-main-on-tag.yml': '1e3cec556f96612ff987f1bc2969dd145f85ebfff48297a3bf3adccd0b8c0c69',
 'pytest-matrix.yml': 'e822cffc869bde67a19b97755aa5844c2c83ee717c168540562ee0984a72f0ae',
 'quality-audit.yml': 'f44a2e6b5c479c2975d1cedf66738fdbf402a74cf1d8e26340bb9895524e7b4a',
 'rtd-sphinx-build.yml': 'cc680b6ceecac73566b212a0db96ba016b3aa28766700e95b04691981ededaad',
 'runner-admission.yml': 'f2e92f6a50526c2133cd12ae7c5cbd98ce2922354bd85c628ca48aad4acc6d18',
 'ci-sif-matrix.yml': 'bba67919d4c8f82644a18e9e0ab9cea8b78cbdd241a8680b5dbda78e655bb6d4',
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
# Additive defining-source selection; neither SDK caller titles nor arbitrary
# central workflows gain authority. The existing three profiles stay exact.
SDK_WORKFLOWS = ("sdk-python-package.yml", "sdk-frontend.yml")
SDK_SELECTION = tuple(PREFIX + name + "@" + BRANCH for name in SDK_WORKFLOWS)
SDK_HASHES = {
    "sdk-python-package.yml":
        "d1ba783f1bb54f7a9fc54f9c363e114d1bc9aa885955a0cd733dabe3089e3c94",
    "sdk-frontend.yml":
        "312fcfa2e0078574ca9ab0c838103b17045c84e78dc96c26df8920a1b651bd09",
    "runner-admission.yml": WORKFLOW_HASHES["runner-admission.yml"],
}
# Hub source is one exact optional seven-definition bundle. Public callers
# and arbitrary subsets do not acquire native defining-source authority.
HUB_WORKFLOWS = (
    "hub-pytest-matrix.yml", "hub-quality-audit.yml", "hub-command-v-guard.yml",
    "hub-symlink-guard.yml", "hub-cli-import-smoke.yml", "hub-sphinx-build.yml",
    "hub-custom-tests.yml",
)
HUB_SELECTION = tuple(PREFIX + name + "@" + BRANCH for name in HUB_WORKFLOWS)
HUB_HASHES = {
    "hub-pytest-matrix.yml":
        "8017f280cc860fba9983835c8599284de44ecf3f094ca4446556e158c83980a8",
    "hub-quality-audit.yml":
        "89a8e8b79b6209dbca477b63316cdff4c619fa328c90ab476792a478625dd26e",
    "hub-command-v-guard.yml":
        "22e310f093cd15796b6f109a92c322162856f8d035700639d2f29623178b734f",
    "hub-symlink-guard.yml":
        "747e9b26448068ac6ade43405d56c065232932fc2b3b1ec2fc7a80070550bd4e",
    "hub-cli-import-smoke.yml":
        "42f3abdd3931cbcdb47554c92a05d3c34c860f19c9f65381508041aaef6b1765",
    "hub-sphinx-build.yml":
        "f61672078b0fc8a7a52a95db114a8f0d1cecc808213fc2a63e4fa4f4eb9b7969",
    "hub-custom-tests.yml":
        "80fecd20a5a46304e5d00ab25b5fff630bd99689e94dff364f548e5ad06a65e8",
    "runner-admission.yml": WORKFLOW_HASHES["runner-admission.yml"],
}
# CodeQL is independently optional; it never turns the seven Hub tests into
# a partial eight-definition bundle or invalidates the admitted 31-profile.
HUB_CODEQL_WORKFLOWS = ("hub-codeql-security-analysis.yml",)
HUB_CODEQL_SELECTION = tuple(
    PREFIX + name + "@" + BRANCH for name in HUB_CODEQL_WORKFLOWS
)
HUB_CODEQL_HASHES = {
    "hub-codeql-security-analysis.yml":
        "9e2d0d823ec528d2aae9c99a6b3858c367846970bd7b3f3b086fec8a7276c784",
    "runner-admission.yml": WORKFLOW_HASHES["runner-admission.yml"],
}
CLA_HELPER_SOURCE = (
    "scitex-ai/.github", "10ee482c6f70a4cb10799c407cd88c64afc5458b",
    ".github/cla/baseline-transports.js", 10003,
    "01d63df199614ff1ee63a116c21f964daf8534424a560427793a90ac1b6bc340",
    "e09aa444b4a0f2e6fef062d8ba85bdb3758f060b",
)
IMMUTABLE_ADMISSION_HASH = "e4eb6c5cc5aedd8a460380f796047c2ea33a446846235001355697350d36c915"
IMMUTABLE_HASHES = {
    OLD_REVISION: {**{name: WORKFLOW_HASHES[name] for name in (*NATIVE_WORKFLOWS[:7], "runner-admission.yml")},
                   "cla.yml":
                   "55b422a674acb918d247b3a025bf413fe751de16b85f5f06f1251331c4d98c06",
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
        if name == "cla.yml" and actual == WORKFLOW_HASHES["cla.yml"]:
            from ._policy_callers import SourcePin, _source
            _source(SourcePin(*CLA_HELPER_SOURCE), api, result)
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
                or set(refs).intersection(SDK_SELECTION) not in
                (set(), set(SDK_SELECTION))
                or set(refs).intersection(HUB_SELECTION) not in
                (set(), set(HUB_SELECTION))
                or set(refs) - set(REGISTERED_SELECTION) - set(SDK_SELECTION)
                - set(HUB_SELECTION) - set(HUB_CODEQL_SELECTION) not in
                (set(BRANCH_SELECTION), set(IMMUTABLE_SELECTION), set(TRANSITION_SELECTION))):
            result["violations"].append("selected workflows differ from the finite literal organization profiles")
            continue
        if set(refs).intersection(REGISTERED_SELECTION):
            if type(group.get("id")) is not int or not isinstance(group.get("name"), str):
                result["unknown"].append("registered publisher group identity unavailable")
                continue
            if group["id"] != 6 or group["name"] != "Organization":
                result["violations"].append("registered publisher requires exact Organization group6")
                continue
        selections.append(set(refs))
    if result["violations"] or result["unknown"]:
        return result
    if any(refs != selections[0] for refs in selections):
        result["violations"].append("organization groups select different reviewed profiles")
        return result
    selected = selections[0]
    branch_selected = bool(selected.intersection(BRANCH_SELECTION))
    immutable_selected = bool(selected.intersection(IMMUTABLE_SELECTION))
    sdk_selected = bool(selected.intersection(SDK_SELECTION))
    hub_selected = bool(selected.intersection(HUB_SELECTION))
    codeql_selected = bool(selected.intersection(HUB_CODEQL_SELECTION))
    revision = None
    if branch_selected or sdk_selected or hub_selected or codeql_selected:
        revision = _main(api, result)
        _protection(api, result)
        if revision is None or result["unknown"] or result["violations"]:
            return result
        if branch_selected:
            _source_closure(api, NATIVE_WORKFLOWS, revision, WORKFLOW_HASHES, result)
        if sdk_selected:
            _source_closure(api, SDK_WORKFLOWS, revision, SDK_HASHES, result)
        if hub_selected:
            _source_closure(api, HUB_WORKFLOWS, revision, HUB_HASHES, result)
        if codeql_selected:
            _source_closure(api, HUB_CODEQL_WORKFLOWS, revision,
                            HUB_CODEQL_HASHES, result)
    if immutable_selected:
        for fixed_revision, hashes in IMMUTABLE_HASHES.items():
            names = [name for name, selected_revision in IMMUTABLE_REVISIONS.items()
                     if selected_revision == fixed_revision]
            _source_closure(api, names, fixed_revision, hashes, result)
    qualify_registered_callers(selected, api, result)
    if branch_selected or sdk_selected or hub_selected or codeql_selected:
        _protection(api, result)
        after = _main(api, result)
        if after is not None and after != revision:
            result["unknown"].append("central main revision changed during source qualification")
    expected = (TRANSITION_SELECTION if branch_selected and immutable_selected
                else BRANCH_SELECTION if branch_selected else IMMUTABLE_SELECTION)
    if not result["unknown"] and not result["violations"]:
        registered = [ref for ref in REGISTERED_SELECTION if ref in selected]
        result["expected"] = (list(expected)
                              + [ref for ref in SDK_SELECTION if ref in selected]
                              + [ref for ref in HUB_SELECTION if ref in selected]
                              + [ref for ref in HUB_CODEQL_SELECTION if ref in selected]
                              + registered)
    return result
