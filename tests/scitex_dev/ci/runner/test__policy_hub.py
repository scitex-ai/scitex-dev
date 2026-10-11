"""Whole published Hub defining source extends complete finite profiles only."""

import base64
import copy
import gzip
import hashlib
import json
from pathlib import Path

import pytest

from scitex_dev.ci.runner import _policy_contract as contract
from scitex_dev.ci.runner import _policy_dev_release as release

FIXTURE = (
    Path(__file__).parent / "fixtures/hub-defining-workflow-source-contract.json.gz"
)
MAIN = "a44b774412b1210288b944f036319e0995df4161"


def source_case(*, mutate=None, drift=False, weaken=False, unprotected=False):
    """Deterministic whole real-source replay, without any real API request."""
    fixture = json.loads(gzip.decompress(FIXTURE.read_bytes()))
    responses = fixture["responses"]
    if mutate:
        endpoint = (
            "repos/scitex-ai/.github/contents/.github/workflows/"
            + mutate
            + "?ref="
            + fixture["main"]
        )
        body = base64.b64decode(responses[endpoint]["content"]) + b"\n# changed\n"
        responses[endpoint].update(
            content=base64.b64encode(body).decode(),
            size=len(body),
            sha=hashlib.sha1(
                b"blob " + str(len(body)).encode() + b"\0" + body
            ).hexdigest(),
        )
    requests = []
    reads = 0
    protection_reads = 0

    def api(endpoint):
        nonlocal reads, protection_reads
        requests.append(endpoint)
        result = copy.deepcopy(responses.get(endpoint))
        if endpoint == "repos/scitex-ai/.github/branches/main":
            reads += 1
            if drift and reads > 1:
                result["commit"]["sha"] = "a" * 40
            if unprotected:
                result["protected"] = False
        if endpoint == "repos/scitex-ai/.github/branches/main/protection":
            protection_reads += 1
            if weaken and protection_reads > 1:
                result["allow_deletions"]["enabled"] = True
        return result

    return fixture, api, requests


def group(refs):
    return {
        "id": 6,
        "name": "Organization",
        "restricted_to_workflows": True,
        "selected_workflows": list(refs),
    }


@pytest.mark.parametrize(
    "base,count",
    [
        (contract.BRANCH_SELECTION, 13),
        (contract.IMMUTABLE_SELECTION, 13),
        (contract.TRANSITION_SELECTION, 26),
    ],
)
@pytest.mark.parametrize("sdk", [False, True])
@pytest.mark.parametrize("publisher", [False, True])
def test_complete_hub_bundle_retains_original_sdk_and_publisher_source_contracts(
    base, count, sdk, publisher
):
    # Arrange
    fixture, api, requests = source_case()
    refs = (
        list(base)
        + (list(contract.SDK_SELECTION) if sdk else [])
        + list(contract.HUB_SELECTION)
        + ([release.DEV_SELECTION] if publisher else [])
    )
    # Act
    observed = contract.qualify_workflows([group(refs)], api)
    rows = [
        row for row in observed["source"] if row["workflow"] in contract.HUB_WORKFLOWS
    ]
    # Assert
    assert (
        observed["expected"],
        observed["unknown"],
        observed["violations"],
        len(observed["source"]),
        [(row["workflow"], row["revision"], row["sha256"]) for row in rows],
        requests.count("repos/scitex-ai/.github/branches/main/protection"),
    ) == (
        refs,
        [],
        [],
        count + 8 + (3 if sdk else 0) + (11 if publisher else 0),
        [
            (name, fixture["main"], contract.HUB_HASHES[name])
            for name in contract.HUB_WORKFLOWS
        ],
        4 if publisher else 2,
    )


@pytest.mark.parametrize("missing", range(7))
def test_any_single_hub_omission_refuses_before_source_queries(missing):
    # Arrange
    requests = []
    extras = tuple(
        ref for index, ref in enumerate(contract.HUB_SELECTION) if index != missing
    )
    # Act
    observed = contract.qualify_workflows(
        [group(contract.TRANSITION_SELECTION + contract.SDK_SELECTION + extras)],
        requests.append,
    )
    # Assert
    assert (observed["expected"], observed["violations"], requests) == (
        [],
        ["selected workflows differ from the finite literal organization profiles"],
        [],
    )


@pytest.mark.parametrize(
    "extras",
    [
        contract.HUB_SELECTION + contract.HUB_SELECTION[:1],
        (contract.HUB_SELECTION[0].replace("refs/heads/main", "main"),)
        + contract.HUB_SELECTION[1:],
        (contract.HUB_SELECTION[0].replace("refs/heads/main", "a" * 40),)
        + contract.HUB_SELECTION[1:],
        (contract.HUB_SELECTION[0].replace("scitex-ai/", "outsider/"),)
        + contract.HUB_SELECTION[1:],
        contract.HUB_SELECTION + (contract.PREFIX + "unknown-hub.yml@refs/heads/main",),
        ("scitex-ai/scitex-hub/.github/workflows/tests.yml@refs/heads/main",),
        contract.HUB_SELECTION[:1],
    ],
)
def test_duplicate_foreign_leaf_unknown_partial_or_wrong_literal_never_queries_source(
    extras,
):
    # Arrange
    requests = []
    # Act
    observed = contract.qualify_workflows(
        [group(contract.TRANSITION_SELECTION + extras)], requests.append
    )
    # Assert
    assert (observed["expected"], observed["violations"], requests) == (
        [],
        ["selected workflows differ from the finite literal organization profiles"],
        [],
    )


def test_hub_bundle_alone_cannot_replace_complete_original_profiles():
    # Arrange
    requests = []
    # Act
    observed = contract.qualify_workflows(
        [group(contract.HUB_SELECTION)], requests.append
    )
    # Assert
    assert (observed["expected"], len(observed["violations"]), requests) == ([], 1, [])


@pytest.mark.parametrize("name", (*contract.HUB_WORKFLOWS, "runner-admission.yml"))
def test_rehashed_actual_hub_or_same_revision_admission_mutation_is_not_authority(name):
    # Arrange
    _fixture, api, _requests = source_case(mutate=name)
    # Act
    observed = contract.qualify_workflows(
        [group(contract.IMMUTABLE_SELECTION + contract.HUB_SELECTION)], api
    )
    # Assert
    assert (observed["expected"], observed["unknown"], observed["violations"]) == (
        [],
        [],
        ["reviewed workflow bytes changed: " + name],
    )


@pytest.mark.parametrize(
    "mode,field",
    [("drift", "unknown"), ("weaken", "violations"), ("unprotected", "violations")],
)
def test_hub_added_to_immutable_base_still_fences_fresh_protected_main(mode, field):
    # Arrange
    _fixture, api, _requests = source_case(
        drift=mode == "drift",
        weaken=mode == "weaken",
        unprotected=mode == "unprotected",
    )
    # Act
    observed = contract.qualify_workflows(
        [group(contract.IMMUTABLE_SELECTION + contract.HUB_SELECTION)], api
    )
    # Assert
    assert (observed["expected"], bool(observed[field])) == ([], True)


@pytest.mark.parametrize(
    "payload", [None, {}, {"type": "file", "encoding": "base64", "content": "!"}]
)
def test_unavailable_hub_source_stays_unknown_without_real_api(payload):
    # Arrange
    fixture, api, _requests = source_case()
    endpoint = (
        "repos/scitex-ai/.github/contents/.github/workflows/hub-pytest-matrix.yml?ref="
        + fixture["main"]
    )
    # Act
    observed = contract.qualify_workflows(
        [group(contract.IMMUTABLE_SELECTION + contract.HUB_SELECTION)],
        lambda requested: payload if requested == endpoint else api(requested),
    )
    # Assert
    assert (observed["expected"], observed["violations"], observed["unknown"]) == (
        [],
        [],
        ["reviewed workflow bytes unavailable: hub-pytest-matrix.yml"],
    )


def test_groups_with_different_hub_bundles_do_not_synthesize_selection():
    # Arrange
    requests = []
    # Act
    observed = contract.qualify_workflows(
        [
            group(contract.TRANSITION_SELECTION),
            group(contract.TRANSITION_SELECTION + contract.HUB_SELECTION),
        ],
        requests.append,
    )
    # Assert
    assert (observed["expected"], observed["violations"], requests) == (
        [],
        ["organization groups select different reviewed profiles"],
        [],
    )


def test_all_public_fixture_bodies_bind_actual_protected_merge_and_exact_git_objects():
    # Arrange
    fixture, _api, _requests = source_case()
    # Act
    actual = []
    expected = []
    for row in fixture["public_body_rows"]:
        repository, revision, path = row["repository"], row["revision"], row["path"]
        payload = fixture["responses"][
            f"repos/{repository}/contents/{path}?ref={revision}"
        ]
        raw = base64.b64decode(payload["content"])
        actual.append(
            (
                len(raw),
                hashlib.sha256(raw).hexdigest(),
                hashlib.sha1(
                    b"blob " + str(len(raw)).encode() + b"\0" + raw
                ).hexdigest(),
            )
        )
        expected.append((row["bytes"], row["sha256"], row["git_oid"]))
    # Assert
    assert (
        actual,
        len(actual),
        fixture["main"],
        fixture["central_branch_before"]["commit"]["sha"],
        fixture["central_branch_after"]["commit"]["sha"],
        fixture["central_branch_after"]["protected"],
    ) == (expected, 32, MAIN, MAIN, MAIN, True)
