"""Actual reviewed SDK defining bodies extend only complete finite profiles."""

import base64
import copy
import gzip
import hashlib
import json
from pathlib import Path

import pytest

from scitex_dev.ci.runner import _policy_contract as contract
from scitex_dev.ci.runner import _policy_dev_release as release

FIXTURES = Path(__file__).parent / "fixtures"


def source_case(*, publisher=False, mutate=None, move=False, weaken=False):
    """Deterministic source replay; fake API never calls a real network."""
    fixture = json.loads(
        gzip.decompress(
            (FIXTURES / "sdk-defining-workflow-source-contract.json.gz").read_bytes()
        )
    )
    responses = fixture["responses"]
    publisher_data = json.loads(
        gzip.decompress(
            (FIXTURES / "dev-protected-release-publisher.json.gz").read_bytes()
        )
    )
    responses.update(publisher_data["responses"])
    old_main = responses["repos/scitex-ai/.github/branches/main"]["commit"]["sha"]
    for endpoint, body in list(responses.items()):
        if endpoint.startswith("repos/scitex-ai/.github/") and endpoint.endswith(
            "?ref=" + old_main
        ):
            responses.setdefault(
                endpoint.removesuffix(old_main) + fixture["main"], body
            )
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
        if endpoint == "repos/scitex-ai/.github/branches/main":
            reads += 1
            return {
                "name": "main",
                "protected": True,
                "commit": {"sha": "a" * 40 if move and reads > 1 else fixture["main"]},
            }
        if endpoint == "repos/scitex-ai/.github/branches/main/protection":
            protection_reads += 1
            result = copy.deepcopy(responses[endpoint])
            if weaken and protection_reads > 1:
                result["allow_deletions"]["enabled"] = True
            return result
        return copy.deepcopy(responses.get(endpoint))

    extras = list(contract.SDK_SELECTION) + (
        [release.DEV_SELECTION] if publisher else []
    )
    return fixture, api, requests, extras


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
@pytest.mark.parametrize("publisher", [False, True])
def test_exact_sdk_pair_adds_whole_same_revision_admission_to_each_original_profile(
    base, count, publisher
):
    # Arrange
    fixture, api, requests, extras = source_case(publisher=publisher)
    refs = list(base) + extras
    # Act
    observed = contract.qualify_workflows([group(refs)], api)
    sdk_rows = [
        row for row in observed["source"] if row["workflow"] in contract.SDK_WORKFLOWS
    ]
    # Assert
    assert (
        observed["expected"],
        observed["unknown"],
        observed["violations"],
        len(observed["source"]),
        [(row["workflow"], row["revision"], row["sha256"]) for row in sdk_rows],
        requests.count("repos/scitex-ai/.github/branches/main/protection"),
    ) == (
        refs,
        [],
        [],
        count + 3 + (11 if publisher else 0),
        [
            (name, fixture["main"], contract.SDK_HASHES[name])
            for name in contract.SDK_WORKFLOWS
        ],
        4 if publisher else 2,
    )


@pytest.mark.parametrize(
    "extras",
    [
        contract.SDK_SELECTION[:1],
        contract.SDK_SELECTION[1:],
        contract.SDK_SELECTION + contract.SDK_SELECTION[:1],
        (
            contract.SDK_SELECTION[0].replace("refs/heads/main", "main"),
            contract.SDK_SELECTION[1],
        ),
        (
            contract.SDK_SELECTION[0].replace("refs/heads/main", "a" * 40),
            contract.SDK_SELECTION[1],
        ),
        (
            contract.SDK_SELECTION[0].replace("scitex-ai/", "outsider/"),
            contract.SDK_SELECTION[1],
        ),
        contract.SDK_SELECTION + (contract.PREFIX + "unknown-sdk.yml@refs/heads/main",),
        ("scitex-ai/scitex-sdk/.github/workflows/python-package.yml@refs/heads/main",),
    ],
)
def test_partial_duplicate_foreign_leaf_unknown_or_wrong_literal_ref_never_reads_source(
    extras,
):
    # Arrange
    requests = []
    refs = contract.TRANSITION_SELECTION + extras
    # Act
    observed = contract.qualify_workflows([group(refs)], requests.append)
    # Assert
    assert (observed["expected"], observed["violations"], requests) == (
        [],
        ["selected workflows differ from the finite literal organization profiles"],
        [],
    )


def test_sdk_pair_alone_cannot_replace_original_complete_profile():
    # Arrange
    requests = []
    # Act
    observed = contract.qualify_workflows(
        [group(contract.SDK_SELECTION)], requests.append
    )
    # Assert
    assert (observed["expected"], len(observed["violations"]), requests) == ([], 1, [])


@pytest.mark.parametrize("name", (*contract.SDK_WORKFLOWS, "runner-admission.yml"))
def test_rehashed_actual_sdk_or_same_revision_admission_mutation_is_not_authority(name):
    # Arrange
    _fixture, api, _requests, extras = source_case(mutate=name)
    # Act
    observed = contract.qualify_workflows(
        [group(list(contract.IMMUTABLE_SELECTION) + extras)], api
    )
    # Assert
    assert (observed["expected"], observed["unknown"], observed["violations"]) == (
        [],
        [],
        ["reviewed workflow bytes changed: " + name],
    )


@pytest.mark.parametrize(
    "mode,expected", [("move", "unknown"), ("weaken", "violations")]
)
def test_sdk_extension_of_immutable_base_still_fences_fresh_main_and_protection(
    mode, expected
):
    # Arrange
    _fixture, api, _requests, extras = source_case(
        move=mode == "move", weaken=mode == "weaken"
    )
    # Act
    observed = contract.qualify_workflows(
        [group(list(contract.IMMUTABLE_SELECTION) + extras)], api
    )
    # Assert
    assert (observed["expected"], bool(observed[expected])) == ([], True)


@pytest.mark.parametrize(
    "payload", [None, {}, {"type": "file", "encoding": "base64", "content": "!"}]
)
def test_missing_or_malformed_sdk_body_remains_unknown_without_live_api(payload):
    # Arrange
    fixture, api, _requests, extras = source_case()
    endpoint = (
        "repos/scitex-ai/.github/contents/.github/workflows/sdk-python-package.yml?ref="
        + fixture["main"]
    )
    # Act
    observed = contract.qualify_workflows(
        [group(list(contract.IMMUTABLE_SELECTION) + extras)],
        lambda requested: payload if requested == endpoint else api(requested),
    )
    # Assert
    assert (observed["expected"], observed["violations"], observed["unknown"]) == (
        [],
        [],
        ["reviewed workflow bytes unavailable: sdk-python-package.yml"],
    )


def test_different_group_sdk_extensions_never_synthesize_common_selection():
    # Arrange
    requests = []
    # Act
    observed = contract.qualify_workflows(
        [
            group(contract.TRANSITION_SELECTION),
            group(contract.TRANSITION_SELECTION + contract.SDK_SELECTION),
        ],
        requests.append,
    )
    # Assert
    assert (observed["expected"], observed["violations"], requests) == (
        [],
        ["organization groups select different reviewed profiles"],
        [],
    )


def altered_helper(response, change):
    """Construct four independent actual-body/API negative fixtures."""
    if change == "missing":
        response = None
    elif change == "size":
        response["size"] += 1
    elif change == "oid":
        response["sha"] = "a" * 40
    else:
        body = base64.b64decode(response["content"]) + b"\n// altered\n"
        response.update(
            content=base64.b64encode(body).decode(),
            size=len(body),
            sha=hashlib.sha1(
                b"blob " + str(len(body)).encode() + b"\0" + body
            ).hexdigest(),
        )
    return response


@pytest.mark.parametrize("change", ["body", "size", "oid", "missing"])
def test_current_cla_requires_exact_immutable_helper_without_widening_old_cla(change):
    # Arrange
    fixture, api, _requests, extras = source_case()
    repository, revision, path, size, digest, oid = contract.CLA_HELPER_SOURCE
    endpoint = f"repos/{repository}/contents/{path}?ref={revision}"
    response = altered_helper(api(endpoint), change)
    # Act
    observed = contract.qualify_workflows(
        [group(list(contract.TRANSITION_SELECTION) + extras)],
        lambda requested: response if requested == endpoint else api(requested),
    )
    old_cla = next(
        row
        for row in observed["source"]
        if row["workflow"] == "cla.yml" and row["revision"] == contract.OLD_REVISION
    )
    # Assert
    assert (
        observed["expected"],
        bool(observed["unknown"] if change == "missing" else observed["violations"]),
        old_cla["sha256"],
        (size, digest, oid),
        fixture["main"],
    ) == (
        [],
        True,
        "55b422a674acb918d247b3a025bf413fe751de16b85f5f06f1251331c4d98c06",
        (
            10003,
            "01d63df199614ff1ee63a116c21f964daf8534424a560427793a90ac1b6bc340",
            "e09aa444b4a0f2e6fef062d8ba85bdb3758f060b",
        ),
        "7db48d94e2acf3645a1a8c5d95b14f9815281a1e",
    )


def test_current_publisher_fixture_resolves_all_eleven_original_whole_source_pins():
    # Arrange
    fixture = json.loads(
        gzip.decompress(
            (FIXTURES / "dev-protected-release-publisher.json.gz").read_bytes()
        )
    )
    # Act
    actual = []
    expected = []
    for repository, revision, path, size, digest, oid in fixture["source_rows"]:
        commit = (
            fixture["source_revisions"][repository]
            if revision == "refs/heads/main"
            else revision
        )
        row = fixture["responses"][f"repos/{repository}/contents/{path}?ref={commit}"]
        raw = base64.b64decode(row["content"])
        actual.append(
            (len(raw), hashlib.sha256(raw).hexdigest(), row["sha"], row["size"])
        )
        expected.append((size, digest, oid, size))
    # Assert
    assert (actual, len(actual), fixture["source_revisions"]["scitex-ai/.github"]) == (
        expected,
        11,
        "7db48d94e2acf3645a1a8c5d95b14f9815281a1e",
    )
