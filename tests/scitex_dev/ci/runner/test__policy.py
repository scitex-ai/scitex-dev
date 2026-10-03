"""Policy observations use explicit API adapters or owned process fixtures."""
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import click
from click.testing import CliRunner
import pytest

from scitex_dev.ci.runner import register_ci_runner_commands
from scitex_dev.ci.runner import _policy, _policy_contract


def pool():
    return [{"id": i, "name": name, "status": "online", "busy": i == 2}
            for i, name in enumerate(_policy.CPU_RUNNERS, 1)]


def group(refs):
    return {"id": 6, "name": "Organization", "visibility": "all",
            "allows_public_repositories": True, "restricted_to_workflows": True,
            "selected_workflows": refs, "runners_url": "https://api.github.com/orgs/scitex-ai/actions/runner-groups/6/runners"}


@pytest.mark.parametrize("field,expected", [("state", "violation"), ("groups", 1),
                                           ("busy_runners", ["scitex-ci-03"]), ("last_completed_job_at", None)])
def test_unrestricted_group_never_gains_authorization_from_busy_or_labels(field, expected):
    # Arrange
    g = group([])
    g["restricted_to_workflows"] = False
    # Act
    result = _policy.assess_pool(pool(), [g], {6: [1, 2, 3]}, expected_workflows=[])
    value = len(result["groups"]) if field == "groups" else result.get(field, result["activity"].get(field))
    # Assert
    assert value == expected


def test_reviewed_exact_workflows_and_online_registration_are_qualified():
    # Arrange
    ref = "scitex-ai/.github/.github/workflows/pytest-matrix.yml@" + "a" * 40
    # Act
    result = _policy.assess_pool(pool(), [group([ref])], {6: [1, 2, 3]}, expected_workflows=[ref])
    # Assert
    assert result["state"] == "conformant"


@pytest.mark.parametrize("field,value", [("name", "Different"), ("id", 9),
                                       ("visibility", "private"), ("allows_public_repositories", False)])
def test_group_identity_and_repository_availability_match_admission_destination(field, value):
    # Arrange
    ref = "scitex-ai/.github/.github/workflows/pytest-matrix.yml@" + "a" * 40
    g = group([ref])
    g[field] = value
    # Act
    result = _policy.assess_pool(pool(), [g], {g["id"]: [1, 2, 3]}, expected_workflows=[ref])
    # Assert
    assert result["state"] == "violation"


@pytest.mark.parametrize("refs", [["scitex-ai/.github/.github/workflows/ci.yml@main"],
                                   ["attacker/repo/.github/workflows/ci.yml@" + "a" * 40]])
def test_mutable_or_foreign_refs_remain_unqualified(refs):
    # Arrange
    g = group(refs)
    # Act
    result = _policy.assess_pool(pool(), [g], {6: [1, 2, 3]}, expected_workflows=refs)
    # Assert
    assert result["state"] == "violation"


@pytest.mark.parametrize("runners,groups,memberships,expected", [
    (None, None, {}, "unknown"), (pool(), [group([])], {6: None}, "unknown"),
    (pool()[:-1], [group([])], {6: [1, 2]}, "violation")])
def test_unavailable_or_incomplete_inventory_cannot_be_conformant(runners, groups, memberships, expected):
    # Arrange
    inventory = (runners, groups, memberships)
    # Act
    result = _policy.assess_pool(*inventory)
    # Assert
    assert result["state"] == expected


@pytest.mark.parametrize("url", ["git@github.com:ywatanabe1989/.dotfiles.git", "https://github.com/ywatanabe1989/.dotfiles.git"])
def test_personal_dot_repository_is_an_unambiguous_origin(url):
    # Arrange
    origin = url
    # Act
    parsed = _policy.parse_repository(origin)
    # Assert
    assert parsed == "ywatanabe1989/.dotfiles"


def test_personal_dot_repository_defaults_to_hosted():
    # Arrange
    repo = "ywatanabe1989/.dotfiles"
    # Act
    labels = json.loads(_policy.default_runs_on(repo))
    # Assert
    assert labels == ["ubuntu-latest"]


@pytest.mark.parametrize("url", ["https://github.com.evil/scitex-ai/repo", "https://github.com/scitex-ai/repo/extra", "git@notgithub.com:scitex-ai/repo.git"])
def test_remote_ambiguity_refuses_repository_authority(url):
    # Arrange
    origin = url
    # Act
    # Assert
    with pytest.raises(ValueError):
        _policy.parse_repository(origin)


def test_personal_native_cli_refuses_without_an_available_gh_command():
    # Arrange
    @click.group()
    def root():
        pass
    register_ci_runner_commands(root)
    # Act
    result = CliRunner().invoke(root, ["ci", "runner", "use", "self-hosted", "--repo", "ywatanabe1989/.dotfiles"], env={"PATH": "/nonexistent"})
    # Assert
    assert "organization-only" in result.output


def test_failed_api_driver_body_cannot_escape_the_policy_report():
    # Arrange
    private = "PRIVATE_BODY_DO_NOT_EMIT"
    def failed(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 1, stdout=private, stderr=private)
    # Act
    result = _policy.collect_policy(api=lambda endpoint: _policy._api(endpoint, invoke=failed))
    # Assert
    assert private not in json.dumps(result)


def contract_case():
    bodies = {"pytest-matrix.yml": b"reviewed pytest", "runner-admission.yml": b"reviewed admission"}
    hashes = {name: hashlib.sha256(body).hexdigest() for name, body in bodies.items()}
    ref = "scitex-ai/.github/.github/workflows/pytest-matrix.yml@" + "a" * 40
    def api(endpoint):
        name = endpoint.split("/")[-1].split("?")[0]
        return {"type": "file", "encoding": "base64", "content": base64.b64encode(bodies[name]).decode()}
    def qualify(groups, callback):
        return _policy_contract.qualify_workflows(groups, callback, workflow_hashes=hashes, native_workflows=("pytest-matrix.yml",))
    return qualify, [group([ref])], api, ref


def test_same_revision_is_qualified_only_with_reviewed_native_and_admission_bytes():
    # Arrange
    qualify, groups, api, ref = contract_case()
    # Act
    result = qualify(groups, api)
    # Assert
    assert result["expected"] == [ref]


def test_changed_admission_bytes_refuse_the_exact_native_ref():
    # Arrange
    qualify, groups, api, ref = contract_case()
    def changed(endpoint):
        data = api(endpoint)
        if "runner-admission" in endpoint:
            data["content"] = base64.b64encode(b"unreviewed admission").decode()
        return data
    # Act
    result = qualify(groups, changed)
    # Assert
    assert result["expected"] == []


def test_missing_reviewed_public_bytes_remain_unknown():
    # Arrange
    qualify, groups, api, ref = contract_case()
    # Act
    result = qualify(groups, lambda endpoint: None)
    # Assert
    assert result["unknown"]


def test_mutable_revision_cannot_be_qualified_by_a_matching_body():
    # Arrange
    qualify, groups, api, ref = contract_case()
    groups[0]["selected_workflows"] = [ref[:-40] + "main"]
    # Act
    result = qualify(groups, api)
    # Assert
    assert result["violations"]


@pytest.mark.parametrize("field,expected", [("last_completed_job_at", "2020-01-01T00:01:00+00:00"),
                                           ("sample_complete", True), ("organization_wide", False)])
def test_completed_job_sample_has_independent_bounded_evidence(field, expected):
    # Arrange
    def api(endpoint):
        if "actions/runs?" in endpoint:
            return {"workflow_runs": [{"id": 44}]}
        return {"total_count": 1, "jobs": [{"id": 55, "runner_id": 2, "status": "completed", "completed_at": "2020-01-01T00:01:00Z"}]}
    # Act
    result = _policy.collect_activity(pool(), api)
    # Assert
    assert result[field] == expected


@pytest.mark.parametrize("field,expected", [("last_completed_job_at", None), ("last_completed_job_age_s", None), ("sample_complete", False)])
def test_missing_activity_does_not_invent_a_job_timestamp_or_age(field, expected):
    # Arrange
    api = lambda endpoint: None
    # Act
    result = _policy.collect_activity(pool(), api)
    # Assert
    assert result[field] == expected


@pytest.mark.parametrize("unavailable", [True, False])
def test_real_cron_handler_refuses_unknown_or_unrestricted_owned_api_fixture(tmp_path, unavailable):
    # Arrange
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    rows = pool()
    g = group([])
    g["restricted_to_workflows"] = False
    data = {"orgs/scitex-ai/actions/runners?per_page=100": {"total_count": 3, "runners": rows},
            "orgs/scitex-ai/actions/runner-groups?per_page=100": {"total_count": 1, "runner_groups": [g]},
            "orgs/scitex-ai/actions/runner-groups/6/runners?per_page=100": {"total_count": 3, "runners": rows}}
    gh = bin_dir / "gh"
    gh.write_text("#!" + sys.executable + "\nimport json,sys\ndata=" + repr(data) + "\n"
                  + ("raise SystemExit(1)\n" if unavailable else "print(json.dumps(data.get(sys.argv[2],{})))\n"))
    gh.chmod(0o700)
    source = Path(_policy.__file__).resolve().parents[3]
    env = {"PATH": str(bin_dir) + ":/usr/bin:/bin", "PYTHONPATH": str(source), "LANG": "C"}
    code = "from scitex_dev._cli.cron.run import _run_body; raise SystemExit(_run_body('ci-runner-policy',only=None,dry_run=True))"
    # Act
    child = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=5)
    # Assert
    assert json.loads(child.stdout)["state"] == ("unknown" if unavailable else "violation")


def test_managed_policy_observation_schedule_is_fifteen_minutes():
    # Arrange
    from scitex_dev._cli.cron._jobs import JOB_REGISTRY
    # Act
    job = JOB_REGISTRY["ci-runner-policy"]
    # Assert
    assert job.schedule == "*/15 * * * *"
