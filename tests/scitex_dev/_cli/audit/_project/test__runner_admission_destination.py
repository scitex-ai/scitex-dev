"""Real workflow/YAML/filesystem and Bash controls for the narrow PS-224 door."""

import gzip
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest
import yaml

from scitex_dev._cli.audit._project._check_runner_destinations import (
    check_ps224_runner_destinations,
)
from scitex_dev._cli.audit._project._runner_admission_destination import (
    ADMISSION_SOURCE,
    ADMISSION_SOURCE_SHA256,
    resolve_admission_destination,
)
from scitex_dev._cli.audit._project._violation import Violation

FIXTURE = Path(__file__).parent / "fixtures" / "admission-destination-source.json.gz"


def sources():
    return json.loads(gzip.decompress(FIXTURE.read_bytes()))


def workflow(name):
    return yaml.safe_load(sources()[name]["body"])


def target_job(doc):
    return doc["jobs"]["test" if "test" in doc["jobs"] else "install-check"]


def audit_tree(tmp_path, body, *, checker=check_ps224_runner_destinations, served=True):
    repo = tmp_path / "repo"
    directory = repo / ".github" / "workflows"
    directory.mkdir(parents=True)
    (directory / "ci.yml").write_text(body)
    registry = tmp_path / "hosts.yaml"
    registry.write_text("hosts: {}\n")
    floor = [
        (
            "owned",
            frozenset({"self-hosted", "Linux", "X64", "scitex-ci", "scitex-org-cpu"}),
        )
    ]
    if not served:
        floor = [("owned", frozenset({"self-hosted", "Linux", "X64", "other-cpu"}))]
    found = []
    checker(repo, Violation, found, hosts_path=registry, floor_destinations=floor)
    return found


def recorded_checker(tmp_path):
    body = sources()["published-baseline-checker"]["body"].encode()
    if (
        hashlib.sha256(body).hexdigest()
        != "2e03f4e193ae4267247865e2ed0f256d752ad8a35a8f29f9d6b59557a8db1de6"
    ):
        raise ValueError("published baseline bytes changed")
    path = tmp_path / "recorded-public-checker.py"
    path.write_bytes(body)
    spec = importlib.util.spec_from_file_location(
        "scitex_dev._cli.audit._project._recorded_checker", path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.check_ps224_runner_destinations


@pytest.mark.parametrize(
    "name,digest",
    [
        (
            "storage-r2",
            "1732864337b1c46fb32261db41a785805a2d2eabaaf80cac642b7a74caeef390",
        ),
        (
            "dev-docs",
            "36e4dac8cc5954dcd82854b51d3bd8f3f789f726f407088f504677fc0625ba6f",
        ),
        (
            "dev-import",
            "a5018dd9cb921f2a59cb2fb9a663223c1188d3ee094f9a1e4f897a2934eb56d4",
        ),
        ("central-admission", ADMISSION_SOURCE_SHA256),
        (
            "published-baseline-checker",
            "2e03f4e193ae4267247865e2ed0f256d752ad8a35a8f29f9d6b59557a8db1de6",
        ),
    ],
)
def test_complete_actual_source_fixture_remains_byte_pinned(name, digest):
    # Arrange
    body = sources()[name]["body"].encode()
    # Act
    observed = hashlib.sha256(body).hexdigest()
    # Assert
    assert observed == digest


@pytest.mark.parametrize(
    "name,count", [("storage-r2", 4), ("dev-docs", 1), ("dev-import", 1)]
)
def test_published_checker_really_refuses_the_gated_output(tmp_path, name, count):
    # Arrange
    checker = recorded_checker(tmp_path)
    # Act
    found = audit_tree(
        tmp_path,
        sources()[name]["body"],
        checker=checker,
    )
    # Assert
    assert len(found) == count


@pytest.mark.parametrize("name", ["storage-r2", "dev-docs", "dev-import"])
def test_full_real_workflow_now_resolves_against_the_same_registry_floor(
    tmp_path, name
):
    # Arrange
    body = sources()[name]["body"]
    # Act
    found = audit_tree(tmp_path, body)
    # Assert
    assert found == []


def changed_workflow(change):
    doc = workflow("storage-r2")
    job = target_job(doc)
    admission = doc["jobs"]["runner-admission"]
    first = job["steps"][0]
    if change.startswith("callee-"):
        admission["uses"] = {
            "callee-revision": ADMISSION_SOURCE.rsplit("@", 1)[0] + "@" + "a" * 40,
            "callee-branch": ADMISSION_SOURCE.rsplit("@", 1)[0] + "@refs/heads/main",
            "callee-path": ADMISSION_SOURCE.replace(
                "runner-admission.yml", "other.yml"
            ),
            "callee-repository": ADMISSION_SOURCE.replace(
                "scitex-ai/.github", "attacker/.github"
            ),
        }[change]
    elif change.startswith("input-"):
        admission["with"]["runs_on"] = {
            "input-object": '{"group":"Organization","labels":["self-hosted","scitex-ci"]}',
            "input-dynamic": "${{ vars.UNKNOWN }}",
            "input-unknown-label": '["self-hosted","unknown-cpu"]',
            "input-duplicates": '["self-hosted","scitex-ci","scitex-ci"]',
            "input-boolean": True,
        }[change]
    elif change == "missing-fence":
        job["steps"].pop(0)
    elif change == "late-fence":
        job["steps"].insert(0, {"run": "echo work-before-admission"})
    elif change == "skipped-fence":
        first["if"] = "${{ false }}"
    elif change == "continued-fence":
        first["continue-on-error"] = True
    elif change == "alternate-shell":
        first["shell"] = "bash {0}"
    elif change == "bypass-fence":
        first["run"] = "true\n" + first["run"] + "true\n"
    elif change == "wrong-auth-output":
        first["env"]["NATIVE_AUTHORIZED"] = "true"
    elif change == "missing-native-condition":
        job.pop("if")
    elif change == "missing-needs":
        job["needs"] = "require-release-admission"
    elif change == "arbitrary-output":
        job["runs-on"] = "${{ fromJSON(needs.other.outputs.runs_on) }}"
    elif change == "inherited-shell-code":
        doc["env"]["BASH_ENV"] = "unreviewed.sh"
    else:
        raise ValueError(change)
    return doc


@pytest.mark.parametrize(
    "change",
    [
        "callee-revision",
        "callee-branch",
        "callee-path",
        "callee-repository",
        "input-object",
        "input-dynamic",
        "input-unknown-label",
        "input-duplicates",
        "input-boolean",
        "missing-fence",
        "late-fence",
        "skipped-fence",
        "continued-fence",
        "alternate-shell",
        "bypass-fence",
        "wrong-auth-output",
        "missing-native-condition",
        "missing-needs",
        "arbitrary-output",
        "inherited-shell-code",
    ],
)
def test_changed_callee_input_or_native_fence_retains_the_real_audit_error(
    tmp_path, change
):
    # Arrange
    doc = changed_workflow(change)
    # Act
    found = audit_tree(tmp_path, yaml.safe_dump(doc))
    # Assert
    assert any(
        item.where.endswith("::test") and item.rule == "PS-224" for item in found
    )


def test_gated_output_cannot_bypass_unserved_destination_floor(tmp_path):
    # Arrange
    body = sources()["dev-import"]["body"]
    # Act
    found = audit_tree(tmp_path, body, served=False)
    # Assert
    assert len(found) == 1


@pytest.mark.parametrize("name", ["dev-docs", "dev-import"])
def test_actual_hybrid_guard_allows_outsiders_on_hosted_with_original_body_retained(
    name,
):
    # Arrange
    doc = workflow(name)
    job = next(value for value in doc["jobs"].values() if "runs-on" in value)
    script = job["steps"][0]["run"]
    environment = {
        "PATH": "/usr/bin:/bin",
        "RUNNER_ENVIRONMENT": "github-hosted",
        "NATIVE_AUTHORIZED": "false",
        "ADMISSION_REASON": "membership-not-confirmed",
        "ADMISSION_RUNS_ON": '["ubuntu-latest"]',
    }
    # Act
    result = subprocess.run(
        ["bash", "-e", "-c", script],
        env=environment,
        capture_output=True,
        timeout=2,
        check=False,
    )
    resolved = resolve_admission_destination(doc, job)
    # Assert
    assert (result.returncode, resolved) == (
        0,
        ["self-hosted", "Linux", "X64", "scitex-org-cpu"],
    )


@pytest.mark.parametrize("authorized", ["false", "", "unknown"])
def test_actual_hybrid_guard_refuses_unconfirmed_native_before_work(authorized):
    # Arrange
    job = target_job(workflow("dev-import"))
    environment = {
        "PATH": "/usr/bin:/bin",
        "RUNNER_ENVIRONMENT": "self-hosted",
        "NATIVE_AUTHORIZED": authorized,
        "ADMISSION_REASON": "confirmed-organization-members",
        "ADMISSION_RUNS_ON": '{"group":"Organization","labels":["self-hosted","Linux","X64","scitex-org-cpu"]}',
    }
    # Act
    result = subprocess.run(
        ["bash", "-e", "-c", job["steps"][0]["run"]],
        env=environment,
        capture_output=True,
        timeout=2,
        check=False,
    )
    # Assert
    assert result.returncode != 0


@pytest.mark.parametrize(
    "authorized,runner_environment,expected",
    [
        ("true", "self-hosted", 0),
        ("false", "self-hosted", 1),
        ("true", "github-hosted", 1),
    ],
)
def test_actual_storage_first_fence_requires_native_authorization(
    authorized, runner_environment, expected
):
    # Arrange
    script = target_job(workflow("storage-r2"))["steps"][0]["run"]
    environment = {
        "PATH": "/usr/bin:/bin",
        "NATIVE_AUTHORIZED": authorized,
        "RUNNER_ENVIRONMENT": runner_environment,
    }
    # Act
    result = subprocess.run(
        ["bash", "-e", "-c", script],
        env=environment,
        capture_output=True,
        timeout=2,
        check=False,
    )
    # Assert
    assert result.returncode == expected
