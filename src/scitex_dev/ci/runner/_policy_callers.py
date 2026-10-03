"""Explicit immutable leaf callers and their complete reviewed source closure.

These source-only observations confer no runner access and do not qualify an
actual release tag, image, account, OIDC publisher or running job. Provisional
sources remain excluded from accepted selections until the owning workflow's
checkout is bound to its final reviewed defining commit. Registry additions
require normal source review.
"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from types import MappingProxyType

import yaml


@dataclass(frozen=True)
class SourcePin:
    repository: str
    revision: str
    path: str
    bytes: int
    sha256: str
    git_oid: str


@dataclass(frozen=True)
class Caller:
    selection: str
    sources: tuple[SourcePin, ...]


STORAGE_REVISION = "1fd948f3b2e57d96a198d8f6c2834abddae1fbbb"
ADMISSION_REVISION = "d7d96c34d68cdfbb5503a933591f7748b5aa30ee"
STORAGE_SELECTION = (
    "scitex-ai/scitex-storage/.github/workflows/"
    "pypi-publish-and-github-release-on-tag.yml@" + STORAGE_REVISION
)
_STORAGE_SOURCES = (
    SourcePin(
        "scitex-ai/scitex-storage",
        STORAGE_REVISION,
        ".github/workflows/pypi-publish-and-github-release-on-tag.yml",
        11_820,
        "64907f87697db8a6a1119949a0eeedf9540a77eceb4811b6c639f15a62df4e06",
        "9a36d025664e6c0a51d716672b06925c379ca22b",
    ),
    SourcePin(
        "scitex-ai/scitex-storage",
        STORAGE_REVISION,
        ".github/ci/exec-in-sif.sh",
        6_540,
        "16a80deef97be0366d99e7b4c5c626f5a852df557e72acb343e6d08e8a7eafc4",
        "0b15e8a62515b77be8611645633ccaafe366fb50",
    ),
    SourcePin(
        "scitex-ai/scitex-storage",
        STORAGE_REVISION,
        ".github/ci/run-in-sif.sh",
        4_332,
        "21348975765ed6fd20d4d8d0e155ccff25f37df59a8afbb56fe741b0c0df8368",
        "54fc63ff492968539042c3fe4ceaedfc71f7b211",
    ),
    SourcePin(
        "scitex-ai/scitex-storage",
        STORAGE_REVISION,
        ".github/ci/build-in-sif.sh",
        2_921,
        "85533a07ca1a20e64fa860de38dc340e914e1501edfb86473bcfd0d89c6dfded",
        "e28294b3cdae2bc10c4f16cb9312d3622807c045",
    ),
    SourcePin(
        "scitex-ai/scitex-storage",
        STORAGE_REVISION,
        ".github/ci/publish-in-sif.sh",
        5_207,
        "57fcf8d47aa8de94e415c0ef11049ff2cce80bb9535ac2c17081165fba81afcb",
        "ef2bc8b90d572cdae6511f9dbb5e73c1b89b0c5a",
    ),
    SourcePin(
        "scitex-ai/.github",
        ADMISSION_REVISION,
        ".github/workflows/runner-admission.yml",
        4_642,
        "f2e92f6a50526c2133cd12ae7c5cbd98ce2922354bd85c628ca48aad4acc6d18",
        "3e988cf244f5ec84c703619491707012095cdcaf",
    ),
)
PROVISIONAL_CALLERS = MappingProxyType(
    {
        STORAGE_SELECTION: Caller(STORAGE_SELECTION, _STORAGE_SOURCES),
    }
)
# The proposed 1fd workflow checks out a requested tag before running helpers.
# Its source closure is retained for review, but it is not admission authority.
REGISTERED_CALLERS = MappingProxyType({})
REGISTERED_SELECTION = tuple(REGISTERED_CALLERS)


def _source(pin: SourcePin, api, result):
    endpoint = f"repos/{pin.repository}/contents/{pin.path}?ref={pin.revision}"
    payload = api(endpoint)
    try:
        if not isinstance(payload, dict):
            raise TypeError
        encoded = payload.get("content")
        if (
            payload.get("type") != "file"
            or payload.get("encoding") != "base64"
            or not isinstance(encoded, str)
            or len(encoded) > 256 * 1024
            or type(payload.get("size")) is not int
            or not isinstance(payload.get("sha"), str)
        ):
            raise ValueError
        body = base64.b64decode("".join(encoded.split()), validate=True)
    except (TypeError, ValueError):
        result["unknown"].append(
            f"registered caller source unavailable: {pin.repository}/{pin.path}"
        )
        return None
    digest = hashlib.sha256(body).hexdigest()
    oid = hashlib.sha1(b"blob " + str(len(body)).encode() + b"\0" + body).hexdigest()
    result["source"].append(
        {
            "repository": pin.repository,
            "workflow": pin.path,
            "revision": pin.revision,
            "sha256": digest,
        }
    )
    if (
        len(body) != pin.bytes
        or payload["size"] != pin.bytes
        or digest != pin.sha256
        or oid != pin.git_oid
        or payload["sha"] != pin.git_oid
    ):
        result["violations"].append(
            f"registered caller source changed: {pin.repository}/{pin.path}"
        )
        return None
    return body


def _storage_shape(bodies):
    """Prove the registered job fences and original commands as actual YAML."""
    workflow = yaml.safe_load(bodies[0])
    events = workflow.get("on", workflow.get(True))
    jobs = workflow["jobs"]
    if set(events) != {"push", "workflow_dispatch"} or set(jobs) != {
        "runner-admission",
        "require-release-admission",
        "test",
        "build",
        "publish",
        "release",
    }:
        raise ValueError
    admission = jobs["runner-admission"]
    if (
        admission["uses"]
        != (
            "scitex-ai/.github/.github/workflows/runner-admission.yml@"
            + ADMISSION_REVISION
        )
        or admission["permissions"] != {}
        or set(admission["with"]) != {"runs_on"}
    ):
        raise ValueError
    barrier = jobs["require-release-admission"]
    if barrier["needs"] != "runner-admission" or barrier["runs-on"] != "ubuntu-latest":
        raise ValueError
    if barrier["steps"][0]["run"] != 'test "$NATIVE_AUTHORIZED" = "true"':
        raise ValueError
    guard = (
        'test "$NATIVE_AUTHORIZED" = "true"\n'
        'test "$RUNNER_ENVIRONMENT" = "self-hosted"\n'
    )
    commands = {
        "test": [
            "bash .github/ci/exec-in-sif.sh run-in-sif.sh ${{ matrix.python-version }}"
        ],
        "build": ["bash .github/ci/exec-in-sif.sh build-in-sif.sh 3.12"],
        "publish": ["bash .github/ci/exec-in-sif.sh publish-in-sif.sh 3.12"],
        "release": [],
    }
    for name, expected in commands.items():
        job = jobs[name]
        if not {"runner-admission", "require-release-admission"}.issubset(job["needs"]):
            raise ValueError
        if (
            job["if"]
            != "${{ needs.runner-admission.outputs.native_authorized == 'true' }}"
        ):
            raise ValueError
        if job["runs-on"] != "${{ fromJSON(needs.runner-admission.outputs.runs_on) }}":
            raise ValueError
        first = job["steps"][0]
        if first["run"] != guard or first["env"] != {
            "NATIVE_AUTHORIZED": "${{ needs.runner-admission.outputs.native_authorized }}",
            "RUNNER_ENVIRONMENT": "${{ runner.environment }}",
        }:
            raise ValueError
        actual = [
            step["run"]
            for step in job["steps"]
            if isinstance(step.get("run"), str)
            and step["run"].startswith("bash .github/ci/")
        ]
        if actual != expected:
            raise ValueError
    if jobs["test"]["strategy"] != {
        "fail-fast": False,
        "matrix": {"python-version": ["3.11", "3.12", "3.13"]},
    }:
        raise ValueError
    if jobs["publish"]["environment"]["name"] != "pypi" or jobs["publish"][
        "permissions"
    ] != {"id-token": "write"}:
        raise ValueError
    wrapper = bodies[1].decode()
    for call in (
        'verify_release_pin "$SIF" "${SCITEX_CI_SIF_SHA256:?qualified SIF SHA256 required}" "CI SIF"',
        'verify_release_pin "$APPTAINER" "${SCITEX_CI_APPTAINER_SHA256:?qualified apptainer SHA256 required}" "Apptainer entrypoint"',
    ):
        if call not in wrapper or wrapper.index(call) > wrapper.index(
            'exec "$APPTAINER"'
        ):
            raise ValueError
    if 'timeout 120 sha256sum -- "$release_path"' not in wrapper:
        raise ValueError
    callee = yaml.safe_load(bodies[-1])
    declaration = callee.get("on", callee.get(True))["workflow_call"]
    if set(declaration["inputs"]) != {"runs_on"} or set(declaration["outputs"]) != {
        "runs_on",
        "native_authorized",
        "reason",
    }:
        raise ValueError
    if callee["jobs"]["admission"]["runs-on"] != "ubuntu-latest":
        raise ValueError


def qualify_caller_sources(caller: Caller, api, result):
    """Observe a pinned closure without accepting any runner selection."""
    bodies = [_source(pin, api, result) for pin in caller.sources]
    if any(body is None for body in bodies):
        return
    try:
        _storage_shape(bodies)
    except (
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        UnicodeError,
        yaml.YAMLError,
    ):
        result["violations"].append(
            "registered caller admission or native job contract changed"
        )
        return None
    return bodies


def _storage_checkout_shape(workflow_body):
    """Accepted callers must bind each native checkout before helper work."""
    jobs = yaml.safe_load(workflow_body)["jobs"]
    expected_guard = (
        'actual_source="$(git rev-parse HEAD)"\n'
        'if [ "$actual_source" != "$EXPECTED_SOURCE" ]; then\n'
        '  echo "::error::Requested release tag differs from the reviewed defining workflow source"\n'
        "  exit 1\n"
        "fi\n"
    )
    for name in ("test", "build", "publish", "release"):
        steps = jobs[name]["steps"]
        checkouts = [
            index
            for index, step in enumerate(steps)
            if step.get("uses") == "actions/checkout@v4"
        ]
        if len(checkouts) != 1:
            raise ValueError
        guard = steps[checkouts[0] + 1]
        if (
            set(guard) != {"name", "env", "run"}
            or guard["env"] != {"EXPECTED_SOURCE": "${{ github.sha }}"}
            or guard["run"] != expected_guard
        ):
            raise ValueError


def qualify_registered_callers(selections, api, result):
    """Read only an accepted registered subset; no repository/branch wildcard."""
    for selection in REGISTERED_SELECTION:
        if selection in selections:
            bodies = qualify_caller_sources(REGISTERED_CALLERS[selection], api, result)
            if bodies is None:
                continue
            try:
                _storage_checkout_shape(bodies[0])
            except (
                AttributeError,
                IndexError,
                KeyError,
                TypeError,
                ValueError,
                yaml.YAMLError,
            ):
                result["violations"].append(
                    "registered caller defining checkout fence changed"
                )
