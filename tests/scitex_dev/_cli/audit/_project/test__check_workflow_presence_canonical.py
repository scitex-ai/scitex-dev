"""Generated CI coverage must agree with the owning template and real audits."""

from pathlib import Path

import pytest
import yaml

from scitex_dev._ecosystem.ci_template._canonical import (
    _WorkflowLoader, canonical_caller_job_ids,
)

from scitex_dev._ecosystem.ci_template import render
from scitex_dev._cli.audit._project._check_workflow_presence import (
    _CANONICAL_PYPI_PUBLISH_WORKFLOW,
    check_ps165_workflow_presence,
)
from scitex_dev._cli.audit._project._check_workflows_naming import check_ps164_workflow_naming
from scitex_dev._cli.audit._project._violation import Violation


@pytest.fixture
def generated_repo(tmp_path):
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    body = render("ci.yml.tmpl", pkg_name="owned-example", pkg_module="owned_example")
    (workflows / "ci.yml").write_text(body)
    for name in ("cla.yml", _CANONICAL_PYPI_PUBLISH_WORKFLOW,
                 "sync-main-to-release-tag-on-push.yml"):
        (workflows / name).write_text(f"name: {Path(name).stem}\non: push\njobs: {{}}\n")
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "conf.py").write_text("# owned Sphinx fixture\n")
    return tmp_path


def test_actual_rendered_caller_satisfies_workflow_naming(generated_repo):
    # Arrange
    findings = []
    # Act
    check_ps164_workflow_naming(generated_repo, Violation, findings)
    # Assert
    assert findings == []


def test_actual_rendered_caller_supplies_required_ci_checks(generated_repo):
    # Arrange
    findings = []
    # Act
    check_ps165_workflow_presence(generated_repo, Violation, findings)
    # Assert
    assert findings == []


@pytest.fixture(params=[
    ("@cd4e545a20a1e35385ffe88f4a963ae3c500819b", "@main"),
    ('secrets.CODECOV_TOKEN', 'secrets.OTHER_TOKEN'),
    ('ubuntu-latest', 'self-hosted'),
    ('name: ci', 'name: altered'),
    ('pull_request:', 'pull_request_target:'),
    ('cancel-in-progress:', 'altered-concurrency:'),
])
def altered_repo(generated_repo, request):
    path = generated_repo / ".github/workflows/ci.yml"
    old, new = request.param
    original = path.read_text()
    assert old in original
    path.write_text(original.replace(old, new))
    return generated_repo


def test_changed_configuration_does_not_supply_ci_checks(altered_repo):
    # Arrange
    findings = []
    # Act
    check_ps165_workflow_presence(altered_repo, Violation, findings)
    # Assert
    assert len(findings) == 4


def test_changed_configuration_retains_naming_findings(altered_repo):
    # Arrange
    findings = []
    # Act
    check_ps164_workflow_naming(altered_repo, Violation, findings)
    # Assert
    assert findings


@pytest.mark.parametrize("job", [
    "pytest-matrix", "import-smoke", "quality-audit", "rtd-sphinx-build",
])
def test_incomplete_caller_supplies_no_jobs(generated_repo, job):
    # Arrange
    path = generated_repo / ".github/workflows/ci.yml"
    document = yaml.load(path.read_text(), Loader=_WorkflowLoader)
    del document["jobs"][job]
    path.write_text(yaml.safe_dump(document))
    # Act
    jobs = canonical_caller_job_ids(generated_repo)
    # Assert
    assert jobs == frozenset()


@pytest.mark.parametrize("name", [
    "cla.yml", _CANONICAL_PYPI_PUBLISH_WORKFLOW,
    "sync-main-to-release-tag-on-push.yml",
])
def test_caller_does_not_replace_independent_workflows(generated_repo, name):
    # Arrange
    (generated_repo / ".github/workflows" / name).unlink()
    findings = []
    # Act
    check_ps165_workflow_presence(generated_repo, Violation, findings)
    # Assert
    assert len(findings) == 1


def test_valid_caller_does_not_hide_other_bad_workflow(generated_repo):
    # Arrange
    (generated_repo / ".github/workflows/lint.yml").write_text(
        "name: lint\non: push\njobs: {}\n"
    )
    findings = []
    # Act
    check_ps164_workflow_naming(generated_repo, Violation, findings)
    # Assert
    assert findings


def test_reformatting_preserves_actual_job_coverage(generated_repo):
    # Arrange
    path = generated_repo / ".github/workflows/ci.yml"
    document = yaml.load(path.read_text(), Loader=_WorkflowLoader)
    path.write_text("# owned reformatted caller\n" + yaml.safe_dump(document))
    # Act
    jobs = canonical_caller_job_ids(generated_repo)
    # Assert
    assert jobs == frozenset(document["jobs"])


@pytest.mark.parametrize("body", [
    "", "[]", "jobs: [", "jobs: {}\njobs: {}\n",
    "jobs: &jobs {}\nother: *jobs\n", "jobs: {<<: {a: 1}}\n",
    "jobs: !unsupported {}\n", "jobs: {}\n---\njobs: {}\n",
    "1: value\n", "jobs: !!bool yes\n", "jobs: .nan\n",
    "#" * 65537, "jobs: !!binary aGk=\n",
])
def test_unsupported_documents_supply_no_jobs(generated_repo, body):
    # Arrange
    path = generated_repo / ".github/workflows/ci.yml"
    path.write_text(body)
    # Act
    jobs = canonical_caller_job_ids(generated_repo)
    # Assert
    assert jobs == frozenset()


@pytest.mark.parametrize("relative", [".github", ".github/workflows", ".github/workflows/ci.yml"])
def test_symlinked_caller_paths_supply_no_jobs(generated_repo, relative):
    # Arrange
    path = generated_repo / relative
    target = generated_repo / "owned-target"
    path.rename(target)
    path.symlink_to(target, target_is_directory=target.is_dir())
    # Act
    jobs = canonical_caller_job_ids(generated_repo)
    # Assert
    assert jobs == frozenset()


def test_workflow_loader_does_not_change_global_yaml_boolean_rules(generated_repo):
    # Arrange
    canonical_caller_job_ids(generated_repo)
    # Act
    parsed = yaml.safe_load("on: yes\n")
    # Assert
    assert parsed == {True: True}



@pytest.mark.parametrize("size, recognized", [(65536, True), (65537, False)])
def test_caller_size_boundary(generated_repo, size, recognized):
    # Arrange
    path = generated_repo / ".github/workflows/ci.yml"
    body = path.read_text()
    path.write_text(body + "#" * (size - len(body.encode())))
    # Act
    jobs = canonical_caller_job_ids(generated_repo)
    # Assert
    assert bool(jobs) is recognized


@pytest.mark.parametrize("addition", [
    "    secrets: inherit\n", "    steps: []\n",
])
def test_added_job_configuration_supplies_no_jobs(generated_repo, addition):
    # Arrange
    path = generated_repo / ".github/workflows/ci.yml"
    path.write_text(path.read_text() + addition)
    # Act
    jobs = canonical_caller_job_ids(generated_repo)
    # Assert
    assert jobs == frozenset()


def test_extra_job_supplies_no_coverage(generated_repo):
    # Arrange
    path = generated_repo / ".github/workflows/ci.yml"
    path.write_text(path.read_text() + "  extra-job:\n    steps: []\n")
    # Act
    jobs = canonical_caller_job_ids(generated_repo)
    # Assert
    assert jobs == frozenset()


def test_invalid_utf8_supplies_no_jobs(generated_repo):
    # Arrange
    path = generated_repo / ".github/workflows/ci.yml"
    path.write_bytes(b"\xff\xfe")
    # Act
    jobs = canonical_caller_job_ids(generated_repo)
    # Assert
    assert jobs == frozenset()
