"""Workflow integrity checks must participate in the normal project dispatcher."""

import json

import pytest
import yaml
from click.testing import CliRunner

from scitex_dev._cli import main


def _run(root, script, *, workflow_shell=None, job_shell=None, step_shell=None):
    (root / "pyproject.toml").write_text(
        '[project]\nname="workflow-integrity-fixture"\n'
    )
    directory = root / ".github/workflows"
    directory.mkdir(parents=True)
    workflow = {
        "on": {"push": {"tags": ["v*"]}},
        "jobs": {"test": {"runs-on": "ubuntu-latest", "steps": [{"run": script}]}},
    }
    if workflow_shell is not None:
        workflow["defaults"] = {"run": {"shell": workflow_shell}}
    job = workflow["jobs"]["test"]
    if job_shell is not None:
        job["defaults"] = {"run": {"shell": job_shell}}
    if step_shell is not None:
        job["steps"][0]["shell"] = step_shell
    (directory / "release.yml").write_text(yaml.safe_dump(workflow))
    result = CliRunner().invoke(
        main,
        [
            "ecosystem",
            "audit-project",
            "workflow-integrity-fixture",
            "--path",
            str(root),
            "--json",
        ],
    )
    return result, json.loads(result.stdout)


@pytest.mark.parametrize(
    "script,code",
    [
        (
            'pip install -e ".[all,dev]" || pip install -e ".[dev]" || pip install -e .',
            "PS-235",
        ),
        ('gh pr merge "$PR" --merge --admin', "PS-236"),
    ],
)
def test_normal_project_dispatch_reports_unsafe_literal_workflow_commands(
    tmp_path, script, code
):
    # Arrange
    expected = code
    # Act
    result, payload = _run(tmp_path, script)
    found = [v["rule"] for v in payload["violations"] if v["rule"] == expected]
    # Assert
    assert (result.exit_code, bool(found)) == (1, True)


@pytest.mark.parametrize(
    "script,code",
    [
        ('uv pip install -e ".[all,dev]" || uv pip install -e .', "PS-235"),
        (
            'python -m pip install -e ".[all,dev]" || python -m pip install -e ".[dev]"',
            "PS-235",
        ),
        ('pip3 install ".[all,dev]" || pip3 install .', "PS-235"),
        ('pip install -e".[all,dev]"||pip install -e".[dev]"', "PS-235"),
        (
            "pip install --editable=.[all,dev] || pip install --editable=.[dev]",
            "PS-235",
        ),
        (
            'pip install -e ".[all,dev]" ||\n# retained failure branch\npip install -e ".[dev]"',
            "PS-235",
        ),
        ("command gh pr merge 1 --admin", "PS-236"),
        ("GH_TOKEN='placeholder with spaces' gh pr merge 1 --admin", "PS-236"),
        ("echo ready; /usr/bin/gh pr merge 1 --admin", "PS-236"),
        ("gh pr merge 1 \\\n --admin", "PS-236"),
    ],
)
def test_literal_variants_keep_the_same_protection(tmp_path, script, code):
    # Arrange
    expected = code
    # Act
    _, payload = _run(tmp_path, script)
    found = [v["rule"] for v in payload["violations"] if v["rule"] == expected]
    # Assert
    assert bool(found)


@pytest.mark.parametrize(
    "script",
    [
        'pip install -e ".[all,dev]"',
        'pip install -e ".[dev,all]" || pip install -e ".[all,dev]"',
        'pip install -e ".[test_tools]" || pip install -e ".[test.tools]"',
        "gh pr merge 1 --merge",
        "echo 'gh pr merge 1 --admin'",
        """printf '%s\\n' 'pip install -e .[all,dev] || pip install -e .' """,
        'echo "||" gh pr merge 1 --admin',
        "cat <<'DOC'\ngh pr merge 1 --admin\nDOC\necho finished",
        "ENV='example with spaces' printf '%s\\n' '--admin'",
        "python - <<'PY'\nprint('gh pr merge 1 --admin')\nPY",
        "gh pr view 1 --json body",
    ],
)
def test_explicit_profiles_and_nonexecuted_examples_do_not_trigger_rules(
    tmp_path, script
):
    # Arrange
    guarded = {"PS-235", "PS-236"}
    # Act
    _, payload = _run(tmp_path, script)
    found = [v["rule"] for v in payload["violations"] if v["rule"] in guarded]
    # Assert
    assert found == []


@pytest.mark.parametrize(
    "shells,expected",
    [
        ({"workflow_shell": "python"}, False),
        ({"job_shell": "python"}, False),
        ({"step_shell": "python"}, False),
        ({"workflow_shell": "python", "job_shell": "bash"}, True),
        ({"job_shell": "python", "step_shell": "bash"}, True),
    ],
)
def test_workflow_and_job_shell_defaults_respect_step_overrides(
    tmp_path, shells, expected
):
    # Arrange
    script = "gh pr merge 1 --admin"
    # Act
    _, payload = _run(tmp_path, script, **shells)
    found = any(v["rule"] == "PS-236" for v in payload["violations"])
    # Assert
    assert found is expected
