"""Execute the shipped outer shell with owned argv/space/refusal controls."""
import hashlib
import json
import re
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / ".github/ci/exec-in-sif.sh"


@pytest.fixture
def shell_case(tmp_path):
    image = tmp_path / "fixture.sif"
    image.write_bytes(b"Owned argv fixture; never executed as a container image")
    recorder = tmp_path / "fake-apptainer"
    recorder.write_text("#!" + sys.executable + "\n" + """import json,os,sys
from pathlib import Path
Path(os.environ['SCITEX_FAKE_RECORD']).write_text(json.dumps({
 'argv':sys.argv[1:], 'environment':{name:os.environ.get(name) for name in
 ['APPTAINER_TMPDIR','APPTAINER_CACHEDIR','APPTAINER_CONFIGDIR','APPTAINERENV_TMPDIR','HOME']}}))
sys.exit(int(os.environ.get('SCITEX_FAKE_EXIT','0')))
""")
    recorder.chmod(0o700)
    parent = tmp_path / "runner temp with spaces"
    parent.mkdir()
    bootstrap = tmp_path / "owned-shell-env.sh"
    bootstrap.write_text("""df() {
 printf '%s\\n' 'Filesystem 1024-blocks Used Available Capacity Mounted on' \
 'fixture 16777216 1024 '"${SCITEX_FAKE_FREE_KB:-8388608}"' 1% /owned'
}
function [ {
 if builtin [ "$1" = -d ] && builtin [ "${2:-}" = /data/gpfs/projects/punim0264 ]; then
  builtin [ "${SCITEX_FAKE_GPFS_EXISTS:-false}" = true ]
  return
 fi
 builtin [ "$@"
}
""")
    private_home = tmp_path / "owned-home"
    private_home.mkdir()
    env = {"PATH": str(Path(sys.executable).parent) + ":/usr/local/bin:/usr/bin:/bin",
           "HOME": str(private_home), "PYTHONDONTWRITEBYTECODE": "1"}
    env.update({"SCITEX_CI_APPTAINER": str(recorder), "SCITEX_CI_SIF": str(image),
                "SCITEX_CI_SIF_SHA256": hashlib.sha256(image.read_bytes()).hexdigest(),
                "RUNNER_TEMP": str(parent), "BASH_ENV": str(bootstrap)})
    return {"root": tmp_path, "image": image, "parent": parent, "env": env}


def execute(case, overrides=None, remove=(), label="one", inner="run-in-sif.sh"):
    env = dict(case["env"])
    env.update(overrides or {})
    for key in remove:
        env.pop(key, None)
    record = case["root"] / (label + ".json")
    env["SCITEX_FAKE_RECORD"] = str(record)
    result = subprocess.run(["bash", str(WRAPPER), inner, "3.12", "one argument"],
                            env=env, cwd=ROOT, capture_output=True, text=True)
    return result, record


@pytest.mark.parametrize("value", ["", "relative"])
def test_empty_or_relative_job_parent_refuses(shell_case, value):
    # Arrange
    case = shell_case
    # Act
    result, _ = execute(case, {"RUNNER_TEMP": value})
    # Assert
    assert result.returncode != 0


def test_absent_job_parent_refuses(shell_case):
    # Arrange
    case = shell_case
    path = case["root"] / "absent"
    # Act
    result, _ = execute(case, {"RUNNER_TEMP": str(path)})
    # Assert
    assert result.returncode != 0


def test_regular_file_job_parent_refuses(shell_case):
    # Arrange
    case = shell_case
    path = case["root"] / "regular-file"
    path.write_text("not a directory")
    # Act
    result, _ = execute(case, {"RUNNER_TEMP": str(path)})
    # Assert
    assert result.returncode != 0


@pytest.mark.parametrize("separator", [",", ":", "\n"])
def test_ambiguous_bind_parent_refuses(shell_case, separator):
    # Arrange
    case = shell_case
    path = case["root"] / ("has" + separator + "separator")
    path.mkdir()
    # Act
    result, _ = execute(case, {"RUNNER_TEMP": str(path)})
    # Assert
    assert result.returncode != 0


@pytest.mark.parametrize("available", ["0", "1024", "2097151", "unknown"])
def test_low_or_unmeasured_space_refuses_container_execution(shell_case, available):
    # Arrange
    case = shell_case
    # Act
    _, record = execute(case, {"SCITEX_FAKE_FREE_KB": available})
    # Assert
    assert not record.exists()


def test_missing_runner_temp_never_falls_back_to_user_home(shell_case):
    # Arrange
    case = shell_case
    # Act
    _, record = execute(case, remove=("RUNNER_TEMP",))
    # Assert
    assert not record.exists()


def test_bad_space_probe_creates_no_job_directory(shell_case):
    # Arrange
    case = shell_case
    # Act
    execute(case, {"SCITEX_FAKE_FREE_KB": "unknown"})
    # Assert
    assert list(case["parent"].iterdir()) == []


def test_tampered_fixture_image_still_refuses_before_execution(shell_case):
    # Arrange
    case = shell_case
    case["image"].write_bytes(b"Changed owned fixture")
    # Act
    result, _ = execute(case)
    # Assert
    assert "digest mismatch" in result.stdout


def test_approved_fixture_plan_succeeds_at_space_threshold(shell_case):
    # Arrange
    case = shell_case
    # Act
    result, _ = execute(case, {"SCITEX_FAKE_FREE_KB": "2097152"})
    # Assert
    assert result.returncode == 0, result.stdout + result.stderr


def test_scratch_is_explicitly_bound_to_container_tmp(shell_case):
    # Arrange
    case = shell_case
    # Act
    _, record = execute(case)
    argv = json.loads(record.read_text())["argv"]
    tmp_bind = argv[6]
    # Assert
    assert tmp_bind == str(Path(json.loads(record.read_text())["environment"]["APPTAINER_TMPDIR"]).parent / "tmp") + ":/tmp"


def test_checkout_bind_preserves_source_path_as_one_argument(shell_case):
    # Arrange
    case = shell_case
    # Act
    _, record = execute(case)
    argv = json.loads(record.read_text())["argv"]
    # Assert
    assert argv[4] == str(ROOT) + ":" + str(ROOT)


def test_inner_script_arguments_survive_shell_quoting(shell_case):
    # Arrange
    case = shell_case
    # Act
    _, record = execute(case)
    argv = json.loads(record.read_text())["argv"]
    # Assert
    assert argv[-3:] == [".github/ci/run-in-sif.sh", "3.12", "one argument"]


@pytest.mark.parametrize("name", ["APPTAINER_TMPDIR", "APPTAINER_CACHEDIR", "APPTAINER_CONFIGDIR"])
def test_apptainer_state_is_under_owned_job_parent(shell_case, name):
    # Arrange
    case = shell_case
    # Act
    _, record = execute(case)
    location = Path(json.loads(record.read_text())["environment"][name])
    # Assert
    assert case["parent"] in location.parents


def test_container_tmp_env_targets_the_explicit_bind(shell_case):
    # Arrange
    case = shell_case
    # Act
    _, record = execute(case)
    environment = json.loads(record.read_text())["environment"]
    # Assert
    assert environment["APPTAINERENV_TMPDIR"] == "/tmp"


def test_wrapper_preserves_actual_home_value(shell_case):
    # Arrange
    case = shell_case
    before = case["env"].get("HOME")
    # Act
    _, record = execute(case)
    environment = json.loads(record.read_text())["environment"]
    # Assert
    assert environment["HOME"] == before


def test_separate_invocations_get_separate_owned_scratch(shell_case):
    # Arrange
    case = shell_case
    # Act
    _, first = execute(case, label="first")
    _, second = execute(case, label="second")
    first_root = json.loads(first.read_text())["environment"]["APPTAINER_TMPDIR"]
    second_root = json.loads(second.read_text())["environment"]["APPTAINER_TMPDIR"]
    # Assert
    assert first_root != second_root


def test_container_failure_exit_status_is_not_masked(shell_case):
    # Arrange
    case = shell_case
    # Act
    result, _ = execute(case, {"SCITEX_FAKE_EXIT": "17"})
    # Assert
    assert result.returncode == 17


@pytest.mark.parametrize("present", [False, True])
def test_gpfs_bind_matches_detected_host_capability(shell_case, present):
    # Arrange
    case = shell_case
    # Act
    _, record = execute(case, {"SCITEX_FAKE_GPFS_EXISTS": str(present).lower()})
    argv = json.loads(record.read_text())["argv"]
    # Assert
    assert ("/data/gpfs/projects/punim0264" in argv) is present


@pytest.mark.parametrize("present", [False, True])
def test_both_host_profiles_keep_scratch_under_owned_job_parent(shell_case, present):
    # Arrange
    case = shell_case
    # Act
    _, record = execute(case, {"SCITEX_FAKE_GPFS_EXISTS": str(present).lower()})
    location = Path(json.loads(record.read_text())["environment"]["APPTAINER_TMPDIR"])
    # Assert
    assert case["parent"] in location.parents


def _workflow_wrapper_calls():
    calls = []
    for path in sorted((ROOT / ".github/workflows").glob("*.yml")):
        workflow = yaml.safe_load(path.read_text())
        for name, job in workflow.get("jobs", {}).items():
            for index, step in enumerate(job.get("steps", [])):
                command = step.get("run", "")
                if "exec-in-sif.sh " not in command:
                    continue
                environment = dict(workflow.get("env", {}))
                environment.update(job.get("env", {}))
                environment.update(step.get("env", {}))
                for inner in re.findall(
                    r"(?m)^\s*bash\s+\.github/ci/exec-in-sif\.sh\s+(\S+)", command
                ):
                    calls.append((path.name + "/" + name + "/" + str(index), environment, inner))
    return calls


WORKFLOW_WRAPPER_CALLS = _workflow_wrapper_calls()


def test_outer_wrapper_workflow_inventory_is_not_empty():
    # Arrange
    paths = ROOT / ".github/workflows"
    # Act
    calls = _workflow_wrapper_calls()
    # Assert
    assert calls, f"no executable outer-wrapper call found under {paths}"


@pytest.mark.parametrize("call", WORKFLOW_WRAPPER_CALLS, ids=lambda call: call[0])
def test_every_workflow_call_supplies_the_verified_image_digest(shell_case, call):
    # Arrange
    case = shell_case
    _, environment, inner = call
    digest = {"${{ vars.SCITEX_CI_SIF_SHA256 }}": case["env"]["SCITEX_CI_SIF_SHA256"]}.get(
        environment.get("SCITEX_CI_SIF_SHA256"), ""
    )
    # Act
    result, _ = execute(case, {"SCITEX_CI_SIF_SHA256": digest}, inner=inner)
    # Assert
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("call", WORKFLOW_WRAPPER_CALLS, ids=lambda call: call[0])
def test_absent_effective_digest_mapping_refuses_every_workflow_call(shell_case, call):
    # Arrange
    case = shell_case
    _, _, inner = call
    # Act
    _, record = execute(case, remove=("SCITEX_CI_SIF_SHA256",), inner=inner)
    # Assert
    assert not record.exists()
