"""Optional whole published CodeQL source preserves complete original profiles."""

import base64
import copy
import gzip
import hashlib
import json
from pathlib import Path

import pytest

from scitex_dev.ci.runner import _policy_contract as contract
from scitex_dev.ci.runner import _policy_dev_release as release

FIXTURE = Path(__file__).parent / "fixtures/hub-codeql-source-contract.json.gz"
MAIN = "9bc2493eca5d804f2d0a979dcef8ab7152f8d840"
CODEQL = "hub-codeql-security-analysis.yml"


def source_case(*, mutate=None, drift=False, weaken=False, unprotected=False):
    fixture = json.loads(gzip.decompress(FIXTURE.read_bytes()))
    responses = fixture["responses"]
    if mutate:
        endpoint = (
            "repos/scitex-ai/.github/contents/.github/workflows/"
            + mutate
            + "?ref="
            + MAIN
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
@pytest.mark.parametrize("hub", [False, True])
@pytest.mark.parametrize("publisher", [False, True])
def test_codeql_optional_singleton_keeps_original_sdk_hub_and_publisher(
    base, count, sdk, hub, publisher
):
    # Arrange
    _fixture, api, requests = source_case()
    refs = (
        list(base)
        + (list(contract.SDK_SELECTION) if sdk else [])
        + (list(contract.HUB_SELECTION) if hub else [])
        + list(contract.HUB_CODEQL_SELECTION)
        + ([release.DEV_SELECTION] if publisher else [])
    )
    # Act
    observed = contract.qualify_workflows([group(refs)], api)
    rows = [row for row in observed["source"] if row["workflow"] == CODEQL]
    # Assert
    assert (
        observed["expected"],
        observed["unknown"],
        observed["violations"],
        len(observed["source"]),
        rows,
        requests.count("repos/scitex-ai/.github/branches/main/protection"),
    ) == (
        refs,
        [],
        [],
        count + (3 if sdk else 0) + (8 if hub else 0) + 2 + (11 if publisher else 0),
        [
            {
                "workflow": CODEQL,
                "revision": MAIN,
                "sha256": contract.HUB_CODEQL_HASHES[CODEQL],
            }
        ],
        4 if publisher else 2,
    )


@pytest.mark.parametrize(
    "base",
    [
        contract.BRANCH_SELECTION,
        contract.IMMUTABLE_SELECTION,
        contract.TRANSITION_SELECTION,
    ],
)
@pytest.mark.parametrize("hub", [False, True])
def test_absent_codeql_preserves_existing_31_and_never_requests_its_source(base, hub):
    # Arrange
    _fixture, api, requests = source_case()
    refs = (
        list(base)
        + list(contract.SDK_SELECTION)
        + (list(contract.HUB_SELECTION) if hub else [])
        + [release.DEV_SELECTION]
    )
    # Act
    observed = contract.qualify_workflows([group(refs)], api)
    # Assert
    assert (
        observed["expected"],
        observed["unknown"],
        observed["violations"],
        any(CODEQL in endpoint for endpoint in requests),
    ) == (refs, [], [], False)


@pytest.mark.parametrize(
    "extra",
    [
        contract.HUB_CODEQL_SELECTION * 2,
        (contract.HUB_CODEQL_SELECTION[0].replace("refs/heads/main", "main"),),
        (contract.HUB_CODEQL_SELECTION[0].replace("refs/heads/main", "a" * 40),),
        (contract.HUB_CODEQL_SELECTION[0].replace("scitex-ai/", "outsider/"),),
        (contract.PREFIX + "unknown-codeql.yml@refs/heads/main",),
        ("scitex-ai/scitex-hub/.github/workflows/codeql-analysis.yml@refs/heads/main",),
    ],
)
def test_duplicate_or_unreviewed_codeql_never_queries(extra):
    # Arrange
    requests = []
    # Act
    observed = contract.qualify_workflows(
        [group(contract.TRANSITION_SELECTION + contract.HUB_SELECTION + extra)],
        requests.append,
    )
    # Assert
    assert (observed["expected"], observed["violations"], requests) == (
        [],
        ["selected workflows differ from the finite literal organization profiles"],
        [],
    )


@pytest.mark.parametrize("missing", range(7))
def test_codeql_does_not_authorize_partial_hub_bundle(missing):
    # Arrange
    requests = []
    hub = tuple(
        ref for index, ref in enumerate(contract.HUB_SELECTION) if index != missing
    )
    # Act
    observed = contract.qualify_workflows(
        [group(contract.TRANSITION_SELECTION + hub + contract.HUB_CODEQL_SELECTION)],
        requests.append,
    )
    # Assert
    assert (observed["expected"], len(observed["violations"]), requests) == ([], 1, [])


def test_codeql_cannot_replace_original_organization_profile():
    # Arrange
    requests = []
    # Act
    observed = contract.qualify_workflows(
        [group(contract.HUB_CODEQL_SELECTION)], requests.append
    )
    # Assert
    assert (observed["expected"], len(observed["violations"]), requests) == ([], 1, [])


@pytest.mark.parametrize("name", [CODEQL, "runner-admission.yml"])
def test_rehashed_real_codeql_or_same_revision_gate_mutation_refuses(name):
    # Arrange
    _fixture, api, _requests = source_case(mutate=name)
    # Act
    observed = contract.qualify_workflows(
        [group(contract.IMMUTABLE_SELECTION + contract.HUB_CODEQL_SELECTION)],
        api,
    )
    # Assert
    assert (observed["expected"], observed["unknown"], observed["violations"]) == (
        [],
        [],
        ["reviewed workflow bytes changed: " + name],
    )


@pytest.mark.parametrize(
    "mode,field",
    [
        ("drift", "unknown"),
        ("weaken", "violations"),
        ("unprotected", "violations"),
    ],
)
def test_codeql_added_to_immutable_profile_still_fences_protected_current_source(
    mode, field
):
    # Arrange
    _fixture, api, _requests = source_case(
        drift=mode == "drift",
        weaken=mode == "weaken",
        unprotected=mode == "unprotected",
    )
    # Act
    observed = contract.qualify_workflows(
        [group(contract.IMMUTABLE_SELECTION + contract.HUB_CODEQL_SELECTION)],
        api,
    )
    # Assert
    assert (observed["expected"], bool(observed[field])) == ([], True)


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"type": "file", "encoding": "base64", "content": "!"},
    ],
)
def test_missing_codeql_source_remains_unknown(payload):
    # Arrange
    _fixture, api, _requests = source_case()
    endpoint = f"repos/scitex-ai/.github/contents/.github/workflows/{CODEQL}?ref={MAIN}"
    # Act
    observed = contract.qualify_workflows(
        [group(contract.IMMUTABLE_SELECTION + contract.HUB_CODEQL_SELECTION)],
        lambda requested: payload if requested == endpoint else api(requested),
    )
    # Assert
    assert (observed["expected"], observed["violations"], observed["unknown"]) == (
        [],
        [],
        ["reviewed workflow bytes unavailable: " + CODEQL],
    )


def test_groups_cannot_mix_optional_codeql_selections():
    # Arrange
    requests = []
    # Act
    observed = contract.qualify_workflows(
        [
            group(contract.TRANSITION_SELECTION),
            group(contract.TRANSITION_SELECTION + contract.HUB_CODEQL_SELECTION),
        ],
        requests.append,
    )
    # Assert
    assert (observed["expected"], observed["violations"], requests) == (
        [],
        ["organization groups select different reviewed profiles"],
        [],
    )


def test_all_whole_public_bodies_bind_protected_actual_merge_and_git_objects():
    # Arrange
    fixture, _api, _requests = source_case()
    actual = []
    expected = []
    # Act
    for row in fixture["public_body_rows"]:
        payload = fixture["responses"][
            f"repos/{row['repository']}/contents/{row['path']}?ref={row['revision']}"
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
    ) == (expected, 33, MAIN, MAIN, MAIN, True)
