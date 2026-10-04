"""Policy observations use explicit API adapters or owned process fixtures."""
import base64
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from scitex_dev.ci.runner import _policy, _policy_contract, register_ci_runner_commands


def pool():
    return [{"id": i, "name": name, "status": "online", "busy": i == 2}
            for i, name in enumerate(_policy.COMPANY_RUNNERS, 1)]


def group(refs):
    return {"id": 6, "name": "Organization", "default": False, "visibility": "all",
            "allows_public_repositories": True, "restricted_to_workflows": True,
            "selected_workflows": refs, "runners_url": "https://api.github.com/orgs/scitex-ai/actions/runner-groups/6/runners"}


@pytest.mark.parametrize("field,expected", [("state", "violation"), ("groups", 1),
                                           ("busy_runners", ["scitex-ci-03"]), ("last_completed_job_at", None)])
def test_unrestricted_group_never_gains_authorization_from_busy_or_labels(field, expected):
    # Arrange
    g = group([])
    g["restricted_to_workflows"] = False
    # Act
    result = _policy.assess_pool(pool(), [g], {6: [1, 2, 3, 4, 5]}, expected_workflows=[])
    value = len(result["groups"]) if field == "groups" else result.get(field, result["activity"].get(field))
    # Assert
    assert value == expected


def test_reviewed_exact_workflows_and_online_registration_are_qualified():
    # Arrange
    ref = "scitex-ai/.github/.github/workflows/pytest-matrix.yml@" + "a" * 40
    # Act
    result = _policy.assess_pool(pool(), [group([ref])], {6: [1, 2, 3, 4, 5]}, expected_workflows=[ref])
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
    result = _policy.assess_pool(pool(), [g], {g["id"]: [1, 2, 3, 4, 5]}, expected_workflows=[ref])
    # Assert
    assert result["state"] == "violation"


@pytest.mark.parametrize("refs", [["scitex-ai/.github/.github/workflows/ci.yml@main"],
                                   ["attacker/repo/.github/workflows/ci.yml@" + "a" * 40]])
def test_mutable_or_foreign_refs_remain_unqualified(refs):
    # Arrange
    g = group(refs)
    # Act
    result = _policy.assess_pool(pool(), [g], {6: [1, 2, 3, 4, 5]}, expected_workflows=refs)
    # Assert
    assert result["state"] == "violation"


@pytest.mark.parametrize("flag,state", [(True, "violation"), (None, "unknown")])
def test_default_or_unknown_group_cannot_authorize_company_resources(flag, state):
    # Arrange
    refs = ["scitex-ai/.github/.github/workflows/pytest-matrix.yml@" + "a" * 40]
    declared = group(refs)
    declared["default"] = flag
    # Act
    result = _policy.assess_pool(pool(), [declared], {6: [1, 2, 3, 4, 5]}, expected_workflows=refs)
    # Assert
    assert result["state"] == state


def test_temporary_company_group_is_not_the_final_organization_pool():
    # Arrange
    refs = ["scitex-ai/.github/.github/workflows/runner-health.yml@refs/heads/main"]
    declared = {**group(refs), "id": 8, "name": "scitex-company-ci"}
    # Act
    result = _policy.assess_pool(pool(), [declared], {8: [1, 2, 3, 4, 5]}, expected_workflows=refs)
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
    qualify, groups, api, _ref = contract_case()
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
    qualify, groups, _api, _ref = contract_case()
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
    data = {"orgs/scitex-ai/actions/runners?per_page=100": {"total_count": len(rows), "runners": rows},
            "orgs/scitex-ai/actions/runner-groups?per_page=100": {"total_count": 1, "runner_groups": [g]},
            "orgs/scitex-ai/actions/runner-groups/6/runners?per_page=100": {"total_count": len(rows), "runners": rows}}
    gh = bin_dir / "gh"
    gh.write_text("#!" + sys.executable + "\nimport json,sys\ndata=" + repr(data) + "\n"
                  + ("raise SystemExit(1)\n" if unavailable else "print(json.dumps(data.get(sys.argv[2],{})))\n"))
    gh.chmod(0o700)
    source = Path(_policy.__file__).resolve().parents[3]
    env = {"PATH": str(bin_dir) + ":/usr/bin:/bin", "PYTHONPATH": str(source), "LANG": "C"}
    code = "from scitex_dev._cli.cron.run import _run_body; raise SystemExit(_run_body('ci-runner-policy',only=None,dry_run=True))"
    # Act
    child = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=5, check=False)
    # Assert
    assert json.loads(child.stdout)["state"] == ("unknown" if unavailable else "violation")


def test_managed_policy_observation_schedule_is_fifteen_minutes():
    # Arrange
    from scitex_dev._cli.cron._jobs import JOB_REGISTRY
    # Act
    job = JOB_REGISTRY["ci-runner-policy"]
    # Assert
    assert job.schedule == "*/15 * * * *"


def protected_main():
    return {"required_pull_request_reviews": {"required_approving_review_count": 0},
            "required_status_checks": {"strict": True, "checks": [{"context": "pytest", "app_id": 15368}]},
            "enforce_admins": {"enabled": True}, "allow_force_pushes": {"enabled": False},
            "allow_deletions": {"enabled": False}}


def empty_contract_report():
    return {"expected": [], "source": [], "violations": [], "unknown": []}


def test_zero_approval_count_retains_mandatory_PR_and_strict_pinned_check():
    # Arrange
    result = empty_contract_report()
    # Act
    _policy_contract._protection(lambda endpoint: protected_main(), result)
    # Assert
    assert result == empty_contract_report()


@pytest.mark.parametrize("field,value", [("enforce_admins", False), ("allow_force_pushes", True), ("allow_deletions", True)])
def test_known_weakened_protection_is_a_violation(field, value):
    # Arrange
    protection = protected_main()
    protection[field]["enabled"] = value
    result = empty_contract_report()
    # Act
    _policy_contract._protection(lambda endpoint: protection, result)
    # Assert
    assert result["violations"] == ["central main protection weakened: " + field]


@pytest.mark.parametrize("changes", [{"strict": False}, {"checks": []}, {"checks": [{"context": "pytest", "app_id": None}]},
                                     {"checks": [{"context": "pytest", "app_id": 99}]}])
def test_known_absent_strict_GitHub_check_is_a_violation(changes):
    # Arrange
    protection = protected_main()
    protection["required_status_checks"].update(changes)
    result = empty_contract_report()
    # Act
    _policy_contract._protection(lambda endpoint: protection, result)
    # Assert
    assert result["violations"] == ["central main strict GitHub pytest protection weakened"]


@pytest.mark.parametrize("payload", [None, {}, "PRIVATE_BODY_DO_NOT_EMIT", {"message": "PRIVATE_BODY_DO_NOT_EMIT"}])
def test_unavailable_protection_remains_unknown_without_private_payload(payload):
    # Arrange
    result = empty_contract_report()
    # Act
    _policy_contract._protection(lambda endpoint: payload, result)
    # Assert
    assert result["unknown"]


@pytest.mark.parametrize("field", ["required_pull_request_reviews", "required_status_checks"])
def test_known_disabled_required_protection_is_a_violation(field):
    # Arrange
    protection = protected_main()
    protection[field] = None
    result = empty_contract_report()
    # Act
    _policy_contract._protection(lambda endpoint: protection, result)
    # Assert
    assert result["violations"]


@pytest.mark.parametrize("field,value", [("required_pull_request_reviews", "malformed"),
                                       ("required_status_checks", {"strict": "yes", "checks": []}),
                                       ("required_status_checks", {"strict": True, "checks": [{"context": "pytest", "app_id": "15368"}]})])
def test_malformed_protection_is_unknown(field, value):
    # Arrange
    protection = protected_main()
    protection[field] = value
    result = empty_contract_report()
    # Act
    _policy_contract._protection(lambda endpoint: protection, result)
    # Assert
    assert result["unknown"]


@pytest.mark.parametrize("payload", [None, {}, {"name": "main", "protected": True, "commit": {"sha": "short"}},
                                     {"name": "main", "protected": None, "commit": {"sha": "a" * 40}}])
def test_branch_revision_and_protection_need_typed_complete_evidence(payload):
    # Arrange
    result = empty_contract_report()
    # Act
    _policy_contract._main(lambda endpoint: payload, result)
    # Assert
    assert result["unknown"] == ["central main revision/protection unavailable"]


def test_known_unprotected_main_is_a_violation():
    # Arrange
    result = empty_contract_report()
    # Act
    _policy_contract._main(lambda endpoint: {"name": "main", "protected": False, "commit": {"sha": "a" * 40}}, result)
    # Assert
    assert result["violations"] == ["central main is not protected"]


def test_protected_main_literal_is_accepted_only_with_an_explicit_contract():
    # Arrange
    refs = list(_policy_contract.BRANCH_SELECTION)
    # Act
    result = _policy.assess_pool(pool(), [group(refs)], {6: [1, 2, 3, 4, 5]}, expected_workflows=refs)
    # Assert
    assert result["state"] == "conformant"


def test_duplicate_literal_ref_does_not_gain_pool_authorization():
    # Arrange
    refs = list(_policy_contract.BRANCH_SELECTION)
    # Act
    result = _policy.assess_pool(pool(), [group(refs + refs[:1])], {6: [1, 2, 3, 4, 5]}, expected_workflows=refs)
    # Assert
    assert result["state"] == "violation"


def undeclared_profile(change):
    refs = list(_policy_contract.BRANCH_SELECTION)
    if change == "duplicate":
        refs[-1] = refs[0]
    elif change == "extra":
        refs.append(_policy_contract.PREFIX + "extra.yml@refs/heads/main")
    elif change == "partial-transition":
        refs += list(_policy_contract.IMMUTABLE_SELECTION[:-1])
    else:
        refs[0] = {"foreign": refs[0].replace("scitex-ai/.github", "attacker/repo"),
                   "bare-main": refs[0].replace("refs/heads/main", "main"),
                   "tag": refs[0].replace("refs/heads/main", "refs/tags/v1"),
                   "arbitrary-sha": refs[0].replace("refs/heads/main", "a" * 40)}[change]
    return refs


@pytest.mark.parametrize("change", ["duplicate", "extra", "foreign", "bare-main", "tag", "arbitrary-sha", "partial-transition"])
def test_undeclared_literal_profile_refuses_without_source_requests(change):
    # Arrange
    refs = undeclared_profile(change)
    requests = []
    # Act
    _policy_contract.qualify_workflows([group(refs)], lambda endpoint: requests.append(endpoint))
    # Assert
    assert requests == []


@pytest.mark.parametrize("change", ["duplicate", "extra", "foreign", "bare-main", "tag", "arbitrary-sha", "partial-transition"])
def test_undeclared_literal_profile_reports_a_violation(change):
    # Arrange
    refs = undeclared_profile(change)
    # Act
    result = _policy_contract.qualify_workflows([group(refs)], lambda endpoint: None)
    # Assert
    assert result["violations"] == ["selected workflows differ from the finite literal organization profiles"]


def test_private_protection_error_body_is_never_part_of_the_report():
    # Arrange
    private = "PRIVATE_PROTECTION_BODY_DO_NOT_EMIT"
    result = empty_contract_report()
    # Act
    _policy_contract._protection(lambda endpoint: {"message": private}, result)
    # Assert
    assert private not in json.dumps(result)


def test_branch_revision_race_stays_unknown():
    # Arrange
    revisions = iter(("a" * 40, "b" * 40))
    def api(endpoint):
        if endpoint.endswith("branches/main"):
            return {"name": "main", "protected": True, "commit": {"sha": next(revisions)}}
        if endpoint.endswith("/protection"):
            return protected_main()
        return None
    # Act
    result = _policy_contract.qualify_workflows([group(list(_policy_contract.BRANCH_SELECTION))], api)
    # Assert
    assert "central main revision changed during source qualification" in result["unknown"]


def test_protection_weakened_during_source_reads_is_a_violation():
    # Arrange
    changed = protected_main()
    changed["allow_deletions"]["enabled"] = True
    protections = iter((protected_main(), changed))
    def api(endpoint):
        if endpoint.endswith("branches/main"):
            return {"name": "main", "protected": True, "commit": {"sha": "a" * 40}}
        return next(protections) if endpoint.endswith("/protection") else None
    # Act
    result = _policy_contract.qualify_workflows([group(list(_policy_contract.BRANCH_SELECTION))], api)
    # Assert
    assert "central main protection weakened: allow_deletions" in result["violations"]


def dependency_case():
    bodies = {"pytest-matrix.yml": b"on:\n  workflow_call:\njobs:\n  admission:\n    uses: ./.github/workflows/runner-admission.yml\n",
              "runner-admission.yml": b"on:\n  workflow_call:\njobs:\n  gate:\n    runs-on: ubuntu-latest\n"}
    hashes = {name: hashlib.sha256(body).hexdigest() for name, body in bodies.items()}
    def api(endpoint):
        name = endpoint.split("/")[-1].split("?")[0]
        return {"type": "file", "encoding": "base64", "content": base64.b64encode(bodies[name]).decode()}
    return bodies, hashes, api


def test_local_reusable_dependency_is_read_at_the_defining_commit():
    # Arrange
    _bodies, hashes, api = dependency_case()
    requests = []
    result = empty_contract_report()
    def observed(endpoint):
        requests.append(endpoint)
        return api(endpoint)
    # Act
    _policy_contract._source_closure(observed, ["pytest-matrix.yml"], "a" * 40, hashes, result)
    # Assert
    assert requests == [f"repos/scitex-ai/.github/contents/.github/workflows/{name}?ref=" + "a" * 40
                        for name in ("pytest-matrix.yml", "runner-admission.yml")]


def test_changed_local_admission_bytes_are_a_violation():
    # Arrange
    bodies, hashes, api = dependency_case()
    bodies["runner-admission.yml"] += b"# changed\n"
    result = empty_contract_report()
    # Act
    _policy_contract._source_closure(api, ["pytest-matrix.yml"], "a" * 40, hashes, result)
    # Assert
    assert result["violations"] == ["reviewed workflow bytes changed: runner-admission.yml"]


def test_unreviewed_local_dependency_cannot_add_authority():
    # Arrange
    _bodies, hashes, api = dependency_case()
    hashes.pop("runner-admission.yml")
    result = empty_contract_report()
    # Act
    _policy_contract._source_closure(api, ["pytest-matrix.yml"], "a" * 40, hashes, result)
    # Assert
    assert result["violations"] == ["local reusable dependency outside reviewed byte contract"]


@pytest.mark.parametrize("payload", [None, {"type": "file", "encoding": "base64", "content": "!not-base64"},
                                     {"type": "file", "encoding": "base64", "content": "A" * (256 * 1024 + 1)}])
def test_missing_invalid_or_oversized_source_is_unknown(payload):
    # Arrange
    result = empty_contract_report()
    # Act
    _policy_contract._source_closure(lambda endpoint: payload, ["pytest-matrix.yml"], "a" * 40,
                                   {"pytest-matrix.yml": "0" * 64}, result)
    # Assert
    assert result["unknown"] == ["reviewed workflow bytes unavailable: pytest-matrix.yml"]


def test_immutable_profile_keeps_each_exact_reviewed_revision():
    # Arrange
    requests = []
    # Act
    _policy_contract.qualify_workflows([group(list(_policy_contract.IMMUTABLE_SELECTION))],
                                     lambda endpoint: requests.append(endpoint))
    # Assert
    assert set(requests) == {f"repos/scitex-ai/.github/contents/.github/workflows/{name}?ref={revision}"
                             for name, revision in _policy_contract.IMMUTABLE_REVISIONS.items()}



def transition_case(*, corrupt=None, move_main=False):
    """Feed exact public workflow bytes through the existing API adapter."""
    import gzip
    fixture = Path(__file__).parent / "fixtures" / "organization-workflow-source-contract.json.gz"
    payload = json.loads(gzip.decompress(fixture.read_bytes()))
    main = payload["main"]
    requests = []
    branch_reads = 0
    def api(endpoint):
        nonlocal branch_reads
        requests.append(endpoint)
        if endpoint.endswith("branches/main"):
            branch_reads += 1
            revision = "d" * 40 if move_main and branch_reads > 1 else main
            return {"name": "main", "protected": True, "commit": {"sha": revision}}
        if endpoint.endswith("/protection"):
            return protected_main()
        data = dict(payload["responses"].get(endpoint, {}))
        if corrupt and endpoint.endswith("/" + corrupt[0] + "?ref=" + corrupt[1]):
            data["content"] = base64.b64encode(
                base64.b64decode(data["content"]) + b"# changed\n").decode()
        return data
    return list(_policy_contract.TRANSITION_SELECTION), api, requests, main


@pytest.mark.parametrize("field,expected", [
    ("selection", list(_policy_contract.TRANSITION_SELECTION)),
    ("unknown", []), ("violations", []), ("source_count", 25),
    ("protection_reads", 2)])
def test_exact_transition_reads_both_complete_public_source_closures(field, expected):
    # Arrange
    refs, api, requests, _main = transition_case()
    # Act
    result = _policy_contract.qualify_workflows([group(refs)], api)
    observed = {"selection": result["expected"], "unknown": result["unknown"],
                "violations": result["violations"], "source_count": len(result["source"]),
                "protection_reads": requests.count("repos/scitex-ai/.github/branches/main/protection")}
    # Assert
    assert observed[field] == expected


@pytest.mark.parametrize("name,revision", [
    ("pytest-matrix.yml", "1ad4e6e7acdab47d4a9675b1f825abc4848558a6"),
    ("runner-admission.yml", "1ad4e6e7acdab47d4a9675b1f825abc4848558a6"),
    ("ci-sif-matrix.yml", "1ad4e6e7acdab47d4a9675b1f825abc4848558a6"),
    ("ci-sif-matrix.yml", _policy_contract.SIF_REVISION),
    ("import-smoke.yml", "1ad4e6e7acdab47d4a9675b1f825abc4848558a6"),
    ("rtd-sphinx-build.yml", "1ad4e6e7acdab47d4a9675b1f825abc4848558a6"),
    ("rtd-sphinx-build.yml", _policy_contract.OLD_REVISION),
    ("pytest-matrix.yml", _policy_contract.OLD_REVISION),
    ("runner-admission.yml", _policy_contract.OLD_REVISION)])
def test_transition_changed_current_or_immutable_bytes_never_authorize(name, revision):
    # Arrange
    refs, api, _requests, _main = transition_case(corrupt=(name, revision))
    # Act
    result = _policy_contract.qualify_workflows([group(refs)], api)
    # Assert
    assert (result["expected"], result["violations"]) == (
        [], ["reviewed workflow bytes changed: " + name])


def test_transition_main_move_during_immutable_source_reads_remains_unknown():
    # Arrange
    refs, api, _requests, _main = transition_case(move_main=True)
    # Act
    result = _policy_contract.qualify_workflows([group(refs)], api)
    # Assert
    assert (result["expected"], result["unknown"]) == (
        [], ["central main revision changed during source qualification"])


def test_current_and_immutable_sif_qualify_their_distinct_whole_bodies():
    # Arrange
    refs, api, _requests, current = transition_case()
    # Act
    result = _policy_contract.qualify_workflows([group(refs)], api)
    observed = {row["revision"]: row["sha256"] for row in result["source"]
                if row["workflow"] == "ci-sif-matrix.yml"}
    # Assert
    assert (result["expected"], result["unknown"], result["violations"], observed) == (refs, [], [], {
        current: "84aa0118ee9b97b4e1ecd7a81c84ca6455609eebed6412b82873c056f1c88d69",
        _policy_contract.SIF_REVISION: "f2abf8459abf711beb25355061df43572e506ae1461ffaf62cdaab2b05abcce1",
    })


@pytest.mark.parametrize("replace_current", [True, False])
def test_current_and_immutable_sif_cannot_substitute_each_others_bytes(replace_current):
    # Arrange
    refs, api, _requests, current = transition_case()
    prefix = "repos/scitex-ai/.github/contents/.github/workflows/ci-sif-matrix.yml?ref="
    target = prefix + (current if replace_current else _policy_contract.SIF_REVISION)
    replacement = api(prefix + (_policy_contract.SIF_REVISION if replace_current else current))
    def substituted(endpoint):
        return replacement if endpoint == target else api(endpoint)
    # Act
    result = _policy_contract.qualify_workflows([group(refs)], substituted)
    # Assert
    assert (result["expected"], result["unknown"], result["violations"]) == (
        [], [], ["reviewed workflow bytes changed: ci-sif-matrix.yml"])


def test_current_docs_and_immutable_docs_keep_independent_whole_source_identities():
    # Arrange
    refs, api, _requests, current = transition_case()
    # Act
    result = _policy_contract.qualify_workflows([group(refs)], api)
    observed = {row["revision"]: row["sha256"] for row in result["source"]
                if row["workflow"] == "rtd-sphinx-build.yml"}
    # Assert
    assert (result["expected"], result["unknown"], result["violations"], observed) == (
        refs, [], [], {
            current: "cc680b6ceecac73566b212a0db96ba016b3aa28766700e95b04691981ededaad",
            _policy_contract.OLD_REVISION: "51be02f591beeeb5398b6447a7c26f0959e5487cad5b974bf62d2cf56fd51b5d",
        })
