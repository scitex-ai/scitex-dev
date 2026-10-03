"""Organization scope and workflow ACLs are distinct from label liveness."""
import json
import base64
import subprocess

import click
from click.testing import CliRunner
import pytest

from scitex_dev.ci.runner import register_ci_runner_commands
from scitex_dev.ci.runner import _policy


def pool():
    names = ["scitex-ci-02", "scitex-ci-03", "scitex-ci-04"]
    return [{"id": i, "name": name, "status": "online", "busy": i == 2,
             "labels": [{"name": "scitex-org-cpu"}]} for i, name in enumerate(names, 1)]


def group(refs):
    return {"id": 6, "name": "Organization", "visibility": "all",
            "allows_public_repositories": True, "restricted_to_workflows": True,
            "selected_workflows": refs, "runners_url": "https://api.github.com/orgs/scitex-ai/actions/runner-groups/6/runners"}


def test_common_labels_do_not_authorize_unrestricted_public_workflows():
    g = group([])
    g["restricted_to_workflows"] = False
    result = _policy.assess_pool(pool(), [g], {6: [1, 2, 3]}, expected_workflows=[])
    assert result["state"] == "violation"
    assert any("workflow" in x for x in result["violations"])
    assert result["activity"]["busy_runners"] == ["scitex-ci-03"]
    assert result["activity"]["last_completed_job_at"] is None
    assert len(result["groups"]) == 1


def test_reviewed_exact_workflows_plus_online_registration_are_qualified():
    ref = "scitex-ai/.github/.github/workflows/pytest-matrix.yml@" + "a" * 40
    result = _policy.assess_pool(pool(), [group([ref])], {6: [1, 2, 3]}, expected_workflows=[ref])
    assert result["state"] == "conformant"
    assert result["activity"]["busy_runners"] == ["scitex-ci-03"]


def test_group_destination_identity_cannot_drift_from_workflow_output():
    ref = "scitex-ai/.github/.github/workflows/pytest-matrix.yml@" + "a" * 40
    g = group([ref])
    g["name"] = "Different"
    assert _policy.assess_pool(pool(), [g], {6: [1, 2, 3]}, expected_workflows=[ref])["state"] == "violation"


@pytest.mark.parametrize("refs", [["scitex-ai/.github/.github/workflows/ci.yml@main"],
                                   ["attacker/repo/.github/workflows/ci.yml@" + "a" * 40]])
def test_mutable_or_foreign_workflow_policy_cannot_be_qualified(refs):
    result = _policy.assess_pool(pool(), [group(refs)], {6: [1, 2, 3]}, expected_workflows=refs)
    assert result["state"] == "violation"


def test_unavailable_or_incomplete_observation_never_reports_conformant():
    assert _policy.assess_pool(None, None, {})["state"] == "unknown"
    assert _policy.assess_pool(pool(), [group([])], {6: None})["state"] == "unknown"
    rows = pool()
    rows.pop()
    assert _policy.assess_pool(rows, [group([])], {6: [1, 2]})["state"] == "violation"


@pytest.mark.parametrize("url", ["git@github.com:ywatanabe1989/.dotfiles.git",
                                 "https://github.com/ywatanabe1989/.dotfiles.git"])
def test_personal_dot_repository_parses_and_defaults_hosted(url):
    assert _policy.parse_repository(url) == "ywatanabe1989/.dotfiles"
    assert json.loads(_policy.default_runs_on("ywatanabe1989/.dotfiles")) == ["ubuntu-latest"]


@pytest.mark.parametrize("url", ["https://github.com.evil/scitex-ai/repo", "https://github.com/scitex-ai/repo/extra",
                                 "git@notgithub.com:scitex-ai/repo.git"])
def test_remote_host_or_path_ambiguity_refuses_self_hosted_authority(url):
    with pytest.raises(ValueError):
        _policy.parse_repository(url)


def test_personal_self_hosted_switch_refuses_before_any_gh_mutation(monkeypatch):
    from scitex_dev.ci.runner import _use
    from scitex_dev.ci.runner import _variables
    monkeypatch.setattr(_use.config, "load_runner_config", lambda: {
        "github": {"default_repo": "ywatanabe1989/.dotfiles", "variable_name": "CI_RUNS_ON"}})
    calls = []
    monkeypatch.setattr(_variables.subprocess, "run", lambda *a, **k: calls.append(a))
    @click.group()
    def root():
        pass
    register_ci_runner_commands(root)
    result = CliRunner().invoke(root, ["ci", "runner", "use", "self-hosted"])
    assert result.exit_code != 0
    assert "organization" in result.output.lower()
    assert calls == []


def test_probe_errors_persist_only_fixed_diagnostics(monkeypatch):
    private = "SHOULD_NEVER_APPEAR_IN_REPORT"
    def fail(*a, **k):
        return subprocess.CompletedProcess(a[0], 1, stdout=private, stderr=private)
    monkeypatch.setattr(_policy.subprocess, "run", fail)
    report = _policy.collect_policy()
    assert report["state"] == "unknown"
    assert private not in json.dumps(report)


def workflow_contract(monkeypatch):
    import hashlib
    import scitex_dev.ci.runner._policy_contract as contract
    bodies = {"pytest-matrix.yml": b"reviewed pytest", "runner-admission.yml": b"reviewed admission"}
    monkeypatch.setattr(contract, "WORKFLOW_HASHES", {n: hashlib.sha256(b).hexdigest() for n, b in bodies.items()})
    monkeypatch.setattr(contract, "NATIVE_WORKFLOWS", ("pytest-matrix.yml",))
    sha = "a" * 40
    ref = "scitex-ai/.github/.github/workflows/pytest-matrix.yml@" + sha
    def api(endpoint):
        name = endpoint.split("/")[-1].split("?")[0]
        return {"type": "file", "encoding": "base64", "content": base64.b64encode(bodies[name]).decode()}
    return contract, [group([ref])], api, ref


def test_exact_group_revision_is_qualified_only_with_all_reviewed_workflow_bytes(monkeypatch):
    contract, groups, api, ref = workflow_contract(monkeypatch)
    result = contract.qualify_workflows(groups, api)
    assert result["expected"] == [ref]
    assert result["violations"] == result["unknown"] == []


def test_changed_hosted_admission_bytes_refuse_even_with_exact_native_refs(monkeypatch):
    contract, groups, api, ref = workflow_contract(monkeypatch)
    def changed(endpoint):
        data = api(endpoint)
        if "runner-admission" in endpoint:
            data["content"] = base64.b64encode(b"unreviewed admission").decode()
        return data
    result = contract.qualify_workflows(groups, changed)
    assert result["expected"] == []
    assert result["violations"]


def test_unavailable_workflow_body_and_mutable_revision_remain_unqualified(monkeypatch):
    contract, groups, api, ref = workflow_contract(monkeypatch)
    assert contract.qualify_workflows(groups, lambda endpoint: None)["unknown"]
    groups[0]["selected_workflows"] = [ref[:-40] + "main"]
    result = contract.qualify_workflows(groups, api)
    assert result["violations"] and not result["expected"]


def test_completed_job_activity_is_separate_from_busy_and_policy(monkeypatch):
    def api(endpoint):
        if "actions/runs?" in endpoint:
            return {"workflow_runs": [{"id": 44}]}
        return {"total_count": 1, "jobs": [{"id": 55, "runner_id": 2, "status": "completed",
                "conclusion": "success", "completed_at": "2020-01-01T00:01:00Z"}]}
    result = _policy.collect_activity(pool(), api)
    assert result["last_completed_job_at"] == "2020-01-01T00:01:00+00:00"
    assert result["sample_complete"] is True
    assert result["organization_wide"] is False
    assert result["jobs"][0]["runner_name"] == "scitex-ci-03"


def test_missing_activity_never_invents_completed_job_or_zero_age():
    result = _policy.collect_activity(pool(), lambda endpoint: None)
    assert result["last_completed_job_at"] is None
    assert result["last_completed_job_age_s"] is None
    assert result["sample_complete"] is False


@pytest.mark.parametrize("state,code", [("conformant", 0), ("violation", 1), ("unknown", 1)])
def test_managed_policy_job_dispatches_real_read_only_handler(monkeypatch, capsys, state, code):
    from scitex_dev._cli.cron import run
    from scitex_dev._cli.cron._jobs import JOB_REGISTRY

    calls = []
    def observe():
        calls.append("read-only")
        return {"state": state, "activity": {"last_completed_job_at": None}}
    monkeypatch.setattr(_policy, "collect_policy", observe)
    assert JOB_REGISTRY["ci-runner-policy"].schedule == "*/15 * * * *"
    assert run._run_body("ci-runner-policy", only=None, dry_run=True) == code
    assert calls == ["read-only"]
    assert json.loads(capsys.readouterr().out)["state"] == state
