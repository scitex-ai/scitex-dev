"""Whole original workflow and changed-authority controls for Figrecipe."""

import copy
import gzip
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from scitex_dev._cli.audit._project._check_runner_destinations import (
    check_ps224_runner_destinations,
)
from scitex_dev._cli.audit._project._runner_admission_destination import (
    resolve_admission_destination,
)
from scitex_dev._cli.audit._project._violation import Violation

FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "figrecipe-c647-admission-workflows.json.gz"
)
SOURCES = json.loads(gzip.decompress(FIXTURE.read_bytes()))
WORKFLOWS = SOURCES["whole_original_workflows"]
SITES = [(row, job) for row in WORKFLOWS for job in row["jobs"]]


@pytest.mark.parametrize("source", WORKFLOWS, ids=lambda row: row["path"])
def test_whole_archived_workflow_bytes_and_all_sites_pass_original_audit(
    tmp_path, source
):
    # Arrange
    body = source["body"]
    repo = tmp_path / "repo"
    path = repo / source["path"]
    path.parent.mkdir(parents=True)
    path.write_text(body)
    registry = tmp_path / "hosts.yaml"
    registry.write_text("hosts: {}\n")
    found = []
    # Act
    check_ps224_runner_destinations(
        repo,
        Violation,
        found,
        hosts_path=registry,
        floor_destinations=[
            ("owned", frozenset({"self-hosted", "Linux", "X64", "scitex-ci"}))
        ],
    )
    # Assert
    assert hashlib.sha256(body.encode()).hexdigest() == source["sha256"]
    assert found == []


@pytest.mark.parametrize("source,job_name", SITES)
def test_all_eight_original_sites_resolve_the_actual_hosted_literal(source, job_name):
    # Arrange
    doc = yaml.safe_load(source["body"])
    # Act
    result = resolve_admission_destination(doc, doc["jobs"][job_name])
    # Assert
    assert result == ["ubuntu-latest"]


@pytest.mark.parametrize(
    "change",
    [
        "drop-fork",
        "drop-native",
        "preceding-work",
        "fork-bypass",
        "native-bypass",
        "continue",
        "shell",
        "callee",
        "producer-input",
        "arbitrary-output",
        "inherited-shell",
        "unreviewed-hosted-label",
        "native-unregistered-label",
    ],
)
def test_changed_guard_input_or_output_cannot_resolve(change):
    # Arrange
    doc = copy.deepcopy(yaml.safe_load(WORKFLOWS[0]["body"]))
    job = doc["jobs"]["build"]
    admission = doc["jobs"]["runner-admission"]
    if change == "drop-fork":
        job["steps"].pop(0)
    elif change == "drop-native":
        job["steps"].pop(1)
    elif change == "preceding-work":
        job["steps"].insert(0, {"uses": "actions/checkout@v4"})
    elif change == "fork-bypass":
        job["steps"][0]["if"] = "false"
    elif change == "native-bypass":
        job["steps"][1]["run"] = "exit 0"
    elif change == "continue":
        job["steps"][1]["continue-on-error"] = True
    elif change == "shell":
        job["steps"][1]["shell"] = "bash {0}"
    elif change == "callee":
        admission["uses"] = admission["uses"].split("@")[0] + "@main"
    elif change == "producer-input":
        admission["with"]["extra"] = "arbitrary"
    elif change == "arbitrary-output":
        job["runs-on"] = "${{ fromJSON(needs.other.outputs.runs_on) }}"
    elif change == "inherited-shell":
        doc["env"]["BASH_ENV"] = "unreviewed.sh"
    elif change == "unreviewed-hosted-label":
        admission["with"]["runs_on"] = '["other-hosted"]'
    elif change == "native-unregistered-label":
        admission["with"]["runs_on"] = '["self-hosted","unknown-cpu"]'
    else:
        raise AssertionError(change)
    # Act
    result = resolve_admission_destination(doc, job)
    # Assert
    assert result is None
