"""Exercise actual artifact/claim gates with whole disposable distributions."""
import base64
import csv
import hashlib
import importlib.util
import io
import json
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".github/ci/release-identity.py"
spec = importlib.util.spec_from_file_location("dev_release_identity", SCRIPT)
identity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(identity)


def wheel(version="0.62.3", *, alter_record=False, extra=None):
    prefix = f"scitex_dev-{version}.dist-info/"
    files = {"scitex_dev/__init__.py": b"# disposable public package\n",
             prefix + "METADATA": f"Metadata-Version: 2.1\nName: scitex-dev\nVersion: {version}\n".encode()}
    if extra:
        files.update(extra)
    output = io.StringIO()
    writer = csv.writer(output)
    for name, body in files.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(body).digest()).rstrip(b"=").decode()
        writer.writerow([name, "sha256=" + ("a" * 43 if alter_record else digest), str(len(body))])
    writer.writerow([prefix + "RECORD", "", ""])
    files[prefix + "RECORD"] = output.getvalue().encode()
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        for name, body in files.items():
            archive.writestr(name, body)
    return data.getvalue()


def sdist(version="0.62.3", *, escaping=False):
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w:gz") as archive:
        body = f"Metadata-Version: 2.1\nName: scitex-dev\nVersion: {version}\n".encode()
        member = tarfile.TarInfo(f"scitex_dev-{version}/PKG-INFO")
        member.size = len(body)
        archive.addfile(member, io.BytesIO(body))
        if escaping:
            member = tarfile.TarInfo("../../outside")
            member.size = 1
            archive.addfile(member, io.BytesIO(b"x"))
    return data.getvalue()


@pytest.fixture
def repository(tmp_path):
    root = tmp_path / "public-release"
    root.mkdir()
    environment = {"PATH": "/usr/local/bin:/usr/bin:/bin", "GIT_CONFIG_GLOBAL": "/dev/null",
                   "GIT_CONFIG_NOSYSTEM": "1", "GIT_AUTHOR_NAME": "Owned release fixture",
                   "GIT_COMMITTER_NAME": "Owned release fixture",
                   "GIT_AUTHOR_EMAIL": "release-fixture@example.invalid",
                   "GIT_COMMITTER_EMAIL": "release-fixture@example.invalid"}
    for command in (["git", "init", "-q"], ["git", "commit", "--allow-empty", "-qm", "Owned fixture"]):
        subprocess.run(command, cwd=root, env=environment, check=True, capture_output=True, timeout=5)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root,
                                     env=environment, text=True, timeout=5).strip()
    dist = root / "dist"
    dist.mkdir()
    (dist / "scitex_dev-0.62.3-py3-none-any.whl").write_bytes(wheel())
    (dist / "scitex_dev-0.62.3.tar.gz").write_bytes(sdist())
    return root, environment, commit


def execute(case, operation="write", commit=None, tag="v0.62.3"):
    root, environment, head = case
    return subprocess.run([sys.executable, "-I", "-B", str(SCRIPT), operation,
                           "--tag", tag, "--commit", commit or head],
                          cwd=root, env=environment, text=True, capture_output=True, timeout=5,
                          check=False)


def test_real_disposable_git_wheel_sdist_manifest_roundtrip(repository):
    # Arrange
    case = repository
    # Act
    written = execute(case)
    verified = execute(case, "verify")
    # Assert
    assert (written.returncode, verified.returncode,
            len(json.loads(verified.stdout)["files"])) == (0, 0, 2)


def test_manifest_is_exclusive_and_cannot_be_overwritten(repository):
    # Arrange
    first = execute(repository)
    original = (repository[0] / "release-manifest.json").read_bytes()
    # Act
    second = execute(repository)
    # Assert
    assert (first.returncode == 0 and second.returncode != 0
            and (repository[0] / "release-manifest.json").read_bytes() == original)


def test_wrong_checkout_commit_refuses(repository):
    # Arrange
    # Act
    result = execute(repository, commit="a" * 40)
    # Assert
    assert result.returncode != 0 and "checkout-commit-mismatch" in result.stderr


def test_wrong_distribution_version_refuses(repository):
    # Arrange
    (repository[0] / "dist/scitex_dev-0.62.3-py3-none-any.whl").write_bytes(wheel("0.62.2"))
    # Act
    result = execute(repository)
    # Assert
    assert result.returncode != 0 and not (repository[0] / "release-manifest.json").exists()


def test_whole_record_byte_mismatch_refuses(repository):
    # Arrange
    (repository[0] / "dist/scitex_dev-0.62.3-py3-none-any.whl").write_bytes(wheel(alter_record=True))
    # Act
    result = execute(repository)
    # Assert
    assert result.returncode != 0 and "wheel-record-byte-mismatch" in result.stderr


def test_sdist_path_escape_refuses_without_extraction(repository):
    # Arrange
    (repository[0] / "dist/scitex_dev-0.62.3.tar.gz").write_bytes(sdist(escaping=True))
    # Act
    result = execute(repository)
    # Assert
    assert result.returncode != 0 and "archive-path-refused" in result.stderr


def test_additional_artifact_refuses(repository):
    # Arrange
    (repository[0] / "dist/old.whl").write_bytes(b"owned extra artifact")
    # Act
    result = execute(repository)
    # Assert
    assert result.returncode != 0 and "distribution-membership-mismatch" in result.stderr


def test_artifact_symlink_refuses(repository):
    # Arrange
    root = repository[0]
    path = root / "dist/scitex_dev-0.62.3.tar.gz"
    path.rename(root / "owned-original.tar.gz")
    path.symlink_to(root / "owned-original.tar.gz")
    # Act
    result = execute(repository)
    # Assert
    assert result.returncode != 0 and not (root / "release-manifest.json").exists()


def test_valid_rebuilt_artifact_cannot_replace_recorded_bytes(repository):
    # Arrange
    first = execute(repository)
    (repository[0] / "dist/scitex_dev-0.62.3-py3-none-any.whl").write_bytes(
        wheel(extra={"scitex_dev/new_public_data.txt": b"owned changed source bytes"}))
    # Act
    result = execute(repository, "verify")
    # Assert
    assert (first.returncode == 0 and result.returncode != 0
            and "release-manifest-mismatch" in result.stderr)


def claims():
    workflow = "scitex-ai/scitex-dev/.github/workflows/pypi-publish-and-github-release-on-tag.yml@refs/heads/main"
    return {"iss": "https://token.actions.githubusercontent.com", "aud": "pypi",
            "repository": "scitex-ai/scitex-dev", "repository_owner": "scitex-ai",
            "sub": "repo:scitex-ai/scitex-dev:environment:pypi", "environment": "pypi",
            "ref": "refs/heads/main", "sha": "a" * 40, "event_name": "workflow_dispatch",
            "workflow_ref": workflow, "job_workflow_ref": workflow,
            "runner_environment": "self-hosted"}


def synthetic_token(fields):
    payload = base64.urlsafe_b64encode(json.dumps(fields).encode()).rstrip(b"=").decode()
    return "e30." + payload + ".b3duZWQtZml4dHVyZQ"


def test_local_claim_projection_accepts_declared_native_caller_without_signature_claim():
    # Arrange
    token = synthetic_token(claims())
    # Act
    result = identity.verify_oidc(token, "a" * 40)
    # Assert
    assert result is None


@pytest.mark.parametrize("field,value", [("runner_environment", "github-hosted"),
                                         ("job_workflow_ref", "scitex-ai/.github/.github/workflows/ci-sif-matrix.yml@refs/heads/main"),
                                         ("ref", "refs/tags/v0.62.3"),
                                         ("sha", "b" * 40), ("repository", "outside/project"),
                                         ("environment", "other"), ("event_name", "pull_request")])
def test_incorrect_publisher_claims_refuse(field, value):
    # Arrange
    fields = claims()
    fields[field] = value
    token = synthetic_token(fields)
    # Act
    # Assert
    with pytest.raises(ValueError, match="^oidc-publisher-claims-mismatch$"):
        identity.verify_oidc(token, "a" * 40)


def test_native_publish_and_release_keep_full_guards_and_original_identity():
    # Arrange
    workflow = yaml.safe_load((ROOT / ".github/workflows/pypi-publish-and-github-release-on-tag.yml").read_text())
    # Act
    jobs = [workflow["jobs"][name] for name in ("publish", "release")]
    # Assert
    assert (all(job["if"] == "github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main'" for job in jobs)
            and all(job["steps"][1]["run"].endswith('test "$NATIVE_AUTHORIZED" = true\n') for job in jobs)
            and workflow["jobs"]["publish"]["environment"]["name"] == "pypi"
            and workflow["jobs"]["publish"]["permissions"]["id-token"] == "write"
            and jobs[0]["steps"][-1]["run"] == "bash .github/ci/exec-in-sif.sh publish-in-sif.sh 3.12")


def test_uv_build_keeps_genuine_entrypoint_import_gate_and_no_pip_fallback():
    # Arrange
    build = (ROOT / ".github/ci/build-in-sif.sh").read_text()
    publish = (ROOT / ".github/ci/publish-in-sif.sh").read_text()
    # Act
    fallback = [body for body in (build, publish) if '"$PY" -m pip install' in body]
    # Assert
    assert (fallback == [] and "-m build --installer uv --outdir dist" in build
            and "audit_wheel_entry_point_imports(sys.argv[1], \"scitex-dev\")" in build
            and "--non-interactive --disable-progress-bar dist/*" in publish)


def test_actual_immutable_admission_and_first_guard_resolve_known_native_labels():
    # Arrange
    from scitex_dev._cli.audit._project._runner_admission_destination import (
        resolve_admission_destination,
    )
    workflow = yaml.safe_load((ROOT / ".github/workflows/pypi-publish-and-github-release-on-tag.yml").read_text())
    # Act
    destinations = [resolve_admission_destination(workflow, workflow["jobs"][name])
                    for name in ("publish", "release")]
    # Assert
    assert destinations == [["self-hosted", "Linux", "X64", "scitex-org-cpu"]] * 2


@pytest.mark.parametrize("runner,authorized,reason,labels,accepted", [
    ("self-hosted", "true", "confirmed-organization-members", "Organization", True),
    ("github-hosted", "false", "unknown", "Organization", False),
    ("self-hosted", "false", "confirmed-organization-members", "Organization", False),
    ("self-hosted", "true", "unknown", "Organization", False),
    ("self-hosted", "true", "confirmed-organization-members", "Other", False),
    ("unknown", "true", "confirmed-organization-members", "Organization", False),
])
def test_actual_precheckout_release_guards_refuse_hosted_unknown_and_wrong_admission(
    runner, authorized, reason, labels, accepted,
):
    # Arrange
    workflow = yaml.safe_load((ROOT / ".github/workflows/pypi-publish-and-github-release-on-tag.yml").read_text())
    guard = "\n".join(step["run"] for step in workflow["jobs"]["publish"]["steps"][:2])
    environment = {"PATH": "/usr/bin:/bin", "RUNNER_ENVIRONMENT": runner,
                   "NATIVE_AUTHORIZED": authorized, "ADMISSION_REASON": reason,
                   "ADMISSION_RUNS_ON": json.dumps({"group": labels, "labels": [
                       "self-hosted", "Linux", "X64", "scitex-org-cpu"]}, separators=(",", ":"))}
    # Act
    result = subprocess.run(["bash", "-c", guard], env=environment, capture_output=True,
                            text=True, timeout=5, check=False)
    # Assert
    assert (result.returncode == 0) is accepted
