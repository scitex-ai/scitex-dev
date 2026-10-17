"""Exact public source replay cannot promote a provisional leaf into policy."""

import base64
import copy
import gzip
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from scitex_dev.ci.runner import _policy_callers as callers
from scitex_dev.ci.runner import _policy_contract as contract

FIXTURES = Path(__file__).parent / "fixtures"


def empty_report():
    return {"expected": [], "violations": [], "unknown": [], "source": []}


def source_case():
    """Replay six actually retrieved public blobs, not a live API verdict."""
    fixture = json.loads(
        gzip.decompress(
            (FIXTURES / "storage-immutable-release-caller.json.gz").read_bytes()
        )
    )
    requests = []

    def api(endpoint):
        requests.append(endpoint)
        return copy.deepcopy(fixture["responses"].get(endpoint))

    return fixture, api, requests


def protected_main():
    return {
        "enforce_admins": {"enabled": True},
        "allow_force_pushes": {"enabled": False},
        "allow_deletions": {"enabled": False},
        "required_pull_request_reviews": {},
        "required_status_checks": {
            "strict": True,
            "checks": [{"context": "pytest", "app_id": 15_368}],
        },
    }


def central_case(*, move_main=False, weaken_protection=False):
    fixture = json.loads(
        gzip.decompress(
            (FIXTURES / "organization-workflow-source-contract.json.gz").read_bytes()
        )
    )
    requests = []
    main_reads = 0
    protection_reads = 0

    def api(endpoint):
        nonlocal main_reads, protection_reads
        requests.append(endpoint)
        if endpoint.endswith("branches/main"):
            main_reads += 1
            revision = "a" * 40 if move_main and main_reads > 1 else fixture["main"]
            return {"name": "main", "protected": True, "commit": {"sha": revision}}
        if endpoint.endswith("/protection"):
            protection_reads += 1
            result = protected_main()
            if weaken_protection and protection_reads > 1:
                result["allow_deletions"]["enabled"] = True
            return result
        return copy.deepcopy(fixture["responses"].get(endpoint))

    return api, requests


def group(refs):
    return {"restricted_to_workflows": True, "selected_workflows": list(refs)}


def test_proposed_storage_revision_has_no_registered_selection():
    # Arrange
    proposal = callers.PROVISIONAL_CALLERS[callers.STORAGE_SELECTION]
    # Act
    observed = (
        proposal.selection,
        callers.STORAGE_SELECTION in callers.REGISTERED_CALLERS,
        callers.STORAGE_SELECTION in callers.REGISTERED_SELECTION,
    )
    # Assert
    assert observed == (callers.STORAGE_SELECTION, False, False)


def test_provisional_source_replay_reads_the_complete_pinned_closure():
    # Arrange
    fixture, api, requests = source_case()
    report = empty_report()
    # Act
    callers.qualify_caller_sources(
        callers.PROVISIONAL_CALLERS[callers.STORAGE_SELECTION], api, report
    )
    # Assert
    assert requests == list(fixture["responses"])


def test_provisional_source_replay_never_adds_an_expected_selection():
    # Arrange
    _fixture, api, _requests = source_case()
    report = empty_report()
    # Act
    callers.qualify_caller_sources(
        callers.PROVISIONAL_CALLERS[callers.STORAGE_SELECTION], api, report
    )
    # Assert
    assert (
        report["expected"],
        report["unknown"],
        report["violations"],
        len(report["source"]),
    ) == ([], [], [], 6)


@pytest.mark.parametrize("index", range(6))
def test_changed_workflow_helper_or_admission_blob_is_a_violation(index):
    # Arrange
    fixture, _api, _requests = source_case()
    endpoint = list(fixture["responses"])[index]
    response = fixture["responses"][endpoint]
    body = base64.b64decode(response["content"]) + b"\n# changed source\n"
    response.update(
        content=base64.b64encode(body).decode(),
        size=len(body),
        sha=hashlib.sha1(b"blob " + str(len(body)).encode() + b"\0" + body).hexdigest(),
    )
    report = empty_report()
    # Act
    callers.qualify_caller_sources(
        callers.PROVISIONAL_CALLERS[callers.STORAGE_SELECTION],
        fixture["responses"].get,
        report,
    )
    # Assert
    assert (report["expected"], len(report["violations"]), report["unknown"]) == (
        [],
        1,
        [],
    )


@pytest.mark.parametrize("field,value", [("size", 1), ("sha", "a" * 40)])
def test_actual_body_cannot_override_changed_api_blob_identity(field, value):
    # Arrange
    fixture, _api, _requests = source_case()
    fixture["responses"][next(iter(fixture["responses"]))][field] = value
    report = empty_report()
    # Act
    callers.qualify_caller_sources(
        callers.PROVISIONAL_CALLERS[callers.STORAGE_SELECTION],
        fixture["responses"].get,
        report,
    )
    # Assert
    assert (report["expected"], len(report["violations"]), report["unknown"]) == (
        [],
        1,
        [],
    )


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        "PRIVATE_PAYLOAD_DO_NOT_EMIT",
        {
            "type": "file",
            "encoding": "base64",
            "content": "!",
            "size": 1,
            "sha": "a" * 40,
        },
        {
            "type": "file",
            "encoding": "base64",
            "content": "A" * (256 * 1_024 + 1),
            "size": 1,
            "sha": "a" * 40,
        },
        {
            "type": "file",
            "encoding": "base64",
            "content": "YQ==",
            "size": True,
            "sha": "a" * 40,
        },
    ],
)
def test_unavailable_or_malformed_closure_is_unknown_without_payload_reflection(
    payload,
):
    # Arrange
    report = empty_report()
    proposal = callers.PROVISIONAL_CALLERS[callers.STORAGE_SELECTION]
    # Act
    callers.qualify_caller_sources(proposal, lambda endpoint: payload, report)
    # Assert
    assert (
        report["expected"],
        report["violations"],
        len(report["unknown"]),
        "PRIVATE_PAYLOAD_DO_NOT_EMIT" in json.dumps(report),
    ) == ([], [], 6, False)


@pytest.mark.parametrize(
    "refs",
    [
        contract.BRANCH_SELECTION,
        contract.IMMUTABLE_SELECTION,
        contract.TRANSITION_SELECTION,
    ],
)
def test_existing_finite_profiles_keep_their_complete_original_source_closure(refs):
    # Arrange
    api, requests = central_case()
    expected_source_count = (
        12
        if refs == contract.BRANCH_SELECTION
        else 13
        if refs == contract.IMMUTABLE_SELECTION
        else 25
    )
    expected_protection_reads = 0 if refs == contract.IMMUTABLE_SELECTION else 2
    # Act
    report = contract.qualify_workflows([group(refs)], api)
    # Assert
    assert (
        report["expected"],
        report["unknown"],
        report["violations"],
        len(report["source"]),
        requests.count("repos/scitex-ai/.github/branches/main/protection"),
    ) == (list(refs), [], [], expected_source_count, expected_protection_reads)


@pytest.mark.parametrize(
    "extra",
    [
        callers.STORAGE_SELECTION,
        callers.STORAGE_SELECTION.replace(callers.STORAGE_REVISION, "refs/heads/main"),
        callers.STORAGE_SELECTION.replace(callers.STORAGE_REVISION, "a" * 40),
        callers.STORAGE_SELECTION.replace(
            "scitex-ai/scitex-storage", "attacker/scitex-storage"
        ),
        callers.STORAGE_SELECTION.replace(
            "pypi-publish-and-github-release-on-tag.yml", "other.yml"
        ),
    ],
)
def test_provisional_unknown_mutable_or_foreign_leaf_is_rejected_before_source_requests(
    extra,
):
    # Arrange
    requests = []
    refs = list(contract.TRANSITION_SELECTION) + [extra]
    # Act
    report = contract.qualify_workflows([group(refs)], requests.append)
    # Assert
    assert (report["expected"], report["violations"], requests) == (
        [],
        ["selected workflows differ from the finite literal organization profiles"],
        [],
    )


@pytest.mark.parametrize(
    "refs",
    [
        (callers.STORAGE_SELECTION,),
        contract.TRANSITION_SELECTION + (contract.TRANSITION_SELECTION[0],),
        contract.BRANCH_SELECTION + contract.IMMUTABLE_SELECTION[:-1],
    ],
)
def test_leaf_alone_duplicate_or_partial_base_does_not_gain_authority(refs):
    # Arrange
    requests = []
    # Act
    report = contract.qualify_workflows([group(refs)], requests.append)
    # Assert
    assert (report["expected"], len(report["violations"]), requests) == ([], 1, [])


def test_two_groups_cannot_select_different_profiles():
    # Arrange
    requests = []
    # Act
    report = contract.qualify_workflows(
        [group(contract.BRANCH_SELECTION), group(contract.TRANSITION_SELECTION)],
        requests.append,
    )
    # Assert
    assert (report["expected"], report["violations"], requests) == (
        [],
        ["organization groups select different reviewed profiles"],
        [],
    )


def test_main_revision_race_stays_unknown_with_registry_integration():
    # Arrange
    api, _requests = central_case(move_main=True)
    # Act
    report = contract.qualify_workflows([group(contract.TRANSITION_SELECTION)], api)
    # Assert
    assert (report["expected"], report["violations"], report["unknown"]) == (
        [],
        [],
        ["central main revision changed during source qualification"],
    )


def test_protection_race_stays_a_violation_with_registry_integration():
    # Arrange
    api, _requests = central_case(weaken_protection=True)
    # Act
    report = contract.qualify_workflows([group(contract.TRANSITION_SELECTION)], api)
    # Assert
    assert (report["expected"], report["unknown"], report["violations"]) == (
        [],
        [],
        ["central main protection weakened: allow_deletions"],
    )


def test_explicit_byte_adapter_still_rejects_a_foreign_leaf():
    # Arrange
    requests = []
    refs = list(contract.IMMUTABLE_SELECTION) + [callers.STORAGE_SELECTION]
    # Act
    report = contract.qualify_workflows(
        [group(refs)],
        requests.append,
        workflow_hashes=contract.IMMUTABLE_HASHES[contract.OLD_REVISION],
        native_workflows=contract.NATIVE_WORKFLOWS[:7],
    )
    # Assert
    assert (report["expected"], report["violations"], requests) == (
        [],
        [
            "reviewed workflow selection count differs from the byte contract",
            "reviewed workflows must share one immutable revision",
        ],
        [],
    )


def proposed_r2_workflow():
    path = (
        Path(__file__).parents[2]
        / "_cli/audit/_project/fixtures/admission-destination-source.json.gz"
    )
    fixture = json.loads(gzip.decompress(path.read_bytes()))
    body = fixture["storage-r2"]["body"].encode()
    if (
        hashlib.sha256(body).hexdigest()
        != "1732864337b1c46fb32261db41a785805a2d2eabaaf80cac642b7a74caeef390"
    ):
        raise ValueError("proposed R2 source changed")
    return body


def test_actual_r2_binds_all_four_native_checkouts_without_registering_it():
    # Arrange
    body = proposed_r2_workflow()
    # Act
    callers._storage_checkout_shape(body)
    # Assert
    assert not any("scitex-storage/" in ref for ref in callers.REGISTERED_SELECTION)


@pytest.mark.parametrize("name", ["test", "build", "publish", "release"])
def test_proposal_without_defining_checkout_fence_cannot_become_an_accepted_caller(
    name,
):
    # Arrange
    doc = yaml.safe_load(proposed_r2_workflow())
    steps = doc["jobs"][name]["steps"]
    checkout = next(
        index
        for index, step in enumerate(steps)
        if step.get("uses") == "actions/checkout@v4"
    )
    steps.pop(checkout + 1)
    # Act
    candidate = yaml.safe_dump(doc)
    # Assert
    with pytest.raises(ValueError, match="^$"):
        callers._storage_checkout_shape(candidate)


def altered_checkout_binding(change):
    """Create an actual YAML mutation of the same defining-source fence."""
    doc = yaml.safe_load(proposed_r2_workflow())
    steps = doc["jobs"]["test"]["steps"]
    checkout = next(
        index
        for index, step in enumerate(steps)
        if step.get("uses") == "actions/checkout@v4"
    )
    guard = steps[checkout + 1]
    if change == "continued":
        guard["continue-on-error"] = True
    elif change == "conditional":
        guard["if"] = "${{ false }}"
    elif change == "wrong-source":
        guard["env"]["EXPECTED_SOURCE"] = "${{ inputs.version }}"
    else:
        steps.insert(
            checkout + 1, {"run": "bash .github/ci/exec-in-sif.sh run-in-sif.sh 3.11"}
        )
    return yaml.safe_dump(doc)


def defining_checkout_is_refused(body):
    """Observe the exact real defining-source refusal without a mock."""
    try:
        callers._storage_checkout_shape(body)
    except ValueError as error:
        return str(error) == ""
    return False


@pytest.mark.parametrize("change", ["continued", "conditional", "wrong-source", "late"])
def test_skipped_changed_or_late_checkout_binding_remains_a_source_refusal(change):
    # Arrange
    candidate = altered_checkout_binding(change)
    # Act
    refused = defining_checkout_is_refused(candidate)
    # Assert
    assert refused
