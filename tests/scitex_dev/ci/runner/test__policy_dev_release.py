"""Replay complete actual Git bodies under an explicitly hypothetical promotion."""
import base64
import copy
import gzip
import json
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from scitex_dev.ci.runner import _policy_callers as callers
from scitex_dev.ci.runner import _policy_contract as contract
from scitex_dev.ci.runner import _policy_dev_release as release


def report():
    return {"expected": [], "unknown": [], "violations": [], "source": []}


def source_case():
    fixture = json.loads(gzip.decompress((Path(__file__).parent / "fixtures" /
        "dev-protected-release-publisher.json.gz").read_bytes()))
    requests = []

    def api(endpoint):
        requests.append(endpoint)
        return copy.deepcopy(fixture["responses"].get(endpoint))

    return fixture, api, requests


def caller():
    return callers.REGISTERED_CALLERS[release.DEV_SELECTION]


def test_one_literal_dev_selection_preserves_provisional_storage_refusal():
    # Arrange
    # Act
    selected = callers.REGISTERED_SELECTION
    # Assert
    assert selected == (release.DEV_SELECTION,) and callers.STORAGE_SELECTION not in selected


def test_complete_actual_git_bodies_and_protected_main_replay_qualify_without_access_effect():
    # Arrange
    _fixture, api, requests = source_case()
    result = report()
    # Act
    release.qualify_dev_release(caller(), api, result)
    # Assert
    assert (result["unknown"], result["violations"], result["expected"],
            len(result["source"]), len(requests)) == ([], [], [], 11, 19)


@pytest.mark.parametrize("index", range(11))
def test_each_whole_workflow_helper_and_admission_change_refuses(index):
    # Arrange
    fixture, api, _requests = source_case()
    key = [key for key in fixture["responses"] if "/contents/" in key][index]
    row = fixture["responses"][key]
    row["content"] = base64.b64encode(base64.b64decode(row["content"]) + b"\n# changed\n").decode()
    result = report()
    # Act
    release.qualify_dev_release(caller(), api, result)
    # Assert
    assert (len(result["violations"]), result["expected"], result["unknown"]) == (1, [], [])


@pytest.mark.parametrize("repository", ["scitex-ai/scitex-dev", "scitex-ai/.github"])
def test_unprotected_defining_or_callee_main_refuses(repository):
    # Arrange
    fixture, api, _requests = source_case()
    fixture["responses"][f"repos/{repository}/branches/main"]["protected"] = False
    result = report()
    # Act
    release.qualify_dev_release(caller(), api, result)
    # Assert
    assert result["violations"] and result["source"] == [] and result["expected"] == []


@pytest.mark.parametrize("key", ["allow_force_pushes", "allow_deletions"])
def test_dev_force_or_deletion_permission_refuses(key):
    # Arrange
    fixture, api, _requests = source_case()
    fixture["responses"]["repos/scitex-ai/scitex-dev/branches/main/protection"][key]["enabled"] = True
    result = report()
    # Act
    release.qualify_dev_release(caller(), api, result)
    # Assert
    assert result["violations"] == ["Dev publisher main protection weakened"]


def test_missing_required_pr_protection_refuses():
    # Arrange
    fixture, api, _requests = source_case()
    fixture["responses"]["repos/scitex-ai/scitex-dev/branches/main/protection"]["required_pull_request_reviews"] = None
    result = report()
    # Act
    release.qualify_dev_release(caller(), api, result)
    # Assert
    assert result["violations"] == ["Dev publisher main protection weakened"]


def test_missing_github_owned_minor_check_refuses():
    # Arrange
    fixture, api, _requests = source_case()
    fixture["responses"]["repos/scitex-ai/scitex-dev/branches/main/protection"]["required_status_checks"]["checks"][0]["app_id"] = 1
    result = report()
    # Act
    release.qualify_dev_release(caller(), api, result)
    # Assert
    assert result["violations"] == ["Dev publisher main protection weakened"]


@pytest.mark.parametrize("repository", ["scitex-ai/scitex-dev", "scitex-ai/.github"])
def test_moving_main_during_whole_source_read_is_unknown(repository):
    # Arrange
    _fixture, original_api, _requests = source_case()
    reads = 0

    def api(endpoint):
        nonlocal reads
        result = original_api(endpoint)
        if endpoint == f"repos/{repository}/branches/main":
            reads += 1
            if reads == 2:
                result["commit"]["sha"] = "a" * 40
        return result

    result = report()
    # Act
    release.qualify_dev_release(caller(), api, result)
    # Assert
    assert result["unknown"] == ["Dev publisher protected source changed during qualification"]


@pytest.mark.parametrize("value", [None, {}, "PRIVATE_RESPONSE_DO_NOT_EMIT"])
def test_missing_or_malformed_protection_remains_unknown_without_reflection(value):
    # Arrange
    fixture, api, _requests = source_case()
    fixture["responses"]["repos/scitex-ai/scitex-dev/branches/main/protection"] = value
    result = report()
    # Act
    release.qualify_dev_release(caller(), api, result)
    # Assert
    assert result["unknown"] and not result["violations"] and "PRIVATE_RESPONSE" not in json.dumps(result)


@pytest.mark.parametrize("selection", [release.DEV_SELECTION.replace("refs/heads/main", "main"),
    release.DEV_SELECTION.replace("scitex-dev", "other"),
    release.DEV_SELECTION.replace("refs/heads/main", "a" * 40)])
def test_no_branch_alias_foreign_repo_or_immutable_equivalence(selection):
    # Arrange
    _fixture, api, requests = source_case()
    result = report()
    altered = replace(caller(), selection=selection)
    # Act
    release.qualify_dev_release(altered, api, result)
    # Assert
    assert result["violations"] == ["Dev publisher outside exact registered source"] and requests == []


def changed_release_bodies(mutation):
    fixture, _api, _requests = source_case()
    bodies = []
    for repository, revision, path, _size, _sha, _oid in fixture["source_rows"]:
        commit = fixture["source_revisions"][repository] if revision == "refs/heads/main" else revision
        value = fixture["responses"][f"repos/{repository}/contents/{path}?ref={commit}"]
        bodies.append(base64.b64decode(value["content"]))
    workflow = yaml.safe_load(bodies[0])
    if mutation == "guard":
        workflow["jobs"]["publish"]["steps"][1]["run"] = "true\n"
    elif mutation == "tag-publish":
        workflow["jobs"]["publish"]["if"] = "github.event_name == 'push'"
    elif mutation == "wrong-callee":
        workflow["jobs"]["test-and-build"]["uses"] = "other/workflow@main"
    else:
        workflow["jobs"]["publish"]["steps"][2]["with"]["ref"] = "main"
    bodies[0] = yaml.safe_dump(workflow).encode()
    return bodies


@pytest.mark.parametrize("mutation", ["guard", "tag-publish", "wrong-callee", "wrong-checkout"])
def test_actual_yaml_shape_rejects_native_or_source_bypass(mutation):
    # Arrange
    bodies = changed_release_bodies(mutation)
    # Act
    # Assert
    with pytest.raises(ValueError, match="^$"):
        release._release_shape(bodies)


def test_registered_publisher_requires_a_complete_original_base_profile():
    # Arrange
    requests = []
    # Act
    result = contract.qualify_workflows([{"restricted_to_workflows": True,
        "selected_workflows": [release.DEV_SELECTION]}], requests.append)
    # Assert
    assert len(result["violations"]) == 1 and result["expected"] == [] and requests == []


def proposed_group_source_case(extra):
    directory = Path(__file__).parent / "fixtures"
    original = json.loads((directory / "group6-original21-readonly-projection.json").read_text())
    central = json.loads(gzip.decompress((directory /
        "organization-workflow-source-contract.json.gz").read_bytes()))
    fixture, _api, _requests = source_case()
    responses = {**central["responses"], **fixture["responses"]}
    original["selected_workflows"] += extra

    def combined_api(endpoint):
        return copy.deepcopy(responses.get(endpoint))

    return original, combined_api


def test_original_exact21_plus_only_registered_publisher_has_complete_source_contract():
    # Arrange
    group, api = proposed_group_source_case([release.DEV_SELECTION])
    # Act
    result = contract.qualify_workflows([group], api)
    # Assert
    assert (set(result["expected"]) == set(contract.TRANSITION_SELECTION) | {release.DEV_SELECTION}
            and len(result["expected"]) == 22 and len(result["source"]) == 36
            and result["unknown"] == [] and result["violations"] == [])


@pytest.mark.parametrize("extra", [[release.DEV_SELECTION, release.DEV_SELECTION],
    [release.DEV_SELECTION, release.DEV_SELECTION.replace("refs/heads/main", "main")]])
def test_duplicate_or_unregistered23rd_selection_refuses(extra):
    # Arrange
    group, api = proposed_group_source_case(extra)
    # Act
    result = contract.qualify_workflows([group], api)
    # Assert
    assert (result["expected"], result["violations"], result["source"]) == (
        [], ["selected workflows differ from the finite literal organization profiles"], [])


@pytest.mark.parametrize("identity,expected", [(None, "unknown"), (8, "violations")])
def test_registered_publisher_without_exact_group6_never_reads_source(identity, expected):
    # Arrange
    group, _api = proposed_group_source_case([release.DEV_SELECTION])
    group["id"] = identity
    requests = []
    # Act
    result = contract.qualify_workflows([group], requests.append)
    # Assert
    assert result[expected] and result["expected"] == [] and requests == []


def pool_source_case(extra):
    from scitex_dev.ci.runner import _policy

    group, api = proposed_group_source_case(extra)
    group["default"] = False
    runners = [{"id": index, "name": name, "status": "online", "busy": False}
               for index, name in enumerate(_policy.COMPANY_RUNNERS, 1)]
    return group, api, runners


def test_real_policy_projection_accepts_only_source_qualified22ref_company_pool():
    # Arrange
    from scitex_dev.ci.runner import _policy

    group, api, runners = pool_source_case([release.DEV_SELECTION])
    qualified = contract.qualify_workflows([group], api)
    # Act
    result = _policy.assess_pool(runners, [group], {6: [1, 2, 3, 4, 5]},
                                 expected_workflows=qualified["expected"])
    # Assert
    assert (qualified["unknown"], qualified["violations"], result["state"]) == ([], [], "conformant")


def test_real_pool_projection_never_accepts_other_leaf_title_or_repo():
    # Arrange
    from scitex_dev.ci.runner import _policy

    group, _api, runners = pool_source_case([release.DEV_SELECTION.replace("scitex-dev", "other")])
    # Act
    result = _policy.assess_pool(runners, [group], {6: [1, 2, 3, 4, 5]},
                                 expected_workflows=group["selected_workflows"])
    # Assert
    assert result["state"] == "violation"
