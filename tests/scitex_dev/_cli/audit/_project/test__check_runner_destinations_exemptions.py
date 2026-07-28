"""PS-224 `audit.exemptions` — the escape hatch must actually work.

The rule ADVERTISES a per-site opt-out (module docstring + violation text).
Until this suite existed the hatch was INERT: the check never read the config,
so a user could write a correct-by-schema entry and nothing happened — false
advertising in an error message.

No mocks (NM001-003): every case builds a REAL repo tree under `tmp_path`
(`.github/workflows/*.yml` + a REAL `.scitex/dev/config.yaml`) and lets the
check LOAD THAT CONFIG ITSELF — nothing is injected and nothing is patched, so
what is tested is exactly what a repo owner would write. The registry is a real
`hosts.yaml` passed through the check's `hosts_path=` file-path seam.

One assert per test (STX-TQ007), Arrange/Act/Assert markers (STX-TQ002).

The site key is JOB-QUALIFIED — `<workflow-path>::<job-id>` — because PS-224
reports per JOB while a path-keyed exemption would OVER-EXEMPT: one workflow
file routinely holds a job that must stay hosted AND a job already migrated,
so a file-wide exemption would silently cover a future regression in the
migrated job. `test_exemption_does_not_suppress_the_other_job_in_the_same_file`
is that guard.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scitex_dev._cli.audit._project._check_runner_destinations import (
    check_ps224_runner_destinations,
)
from scitex_dev._cli.audit._project._violation import Violation

_REGISTRY = """\
hosts:
  spartan:
    kind: hpc-login
    ssh_alias: spartan
    scitex_root: "/data/gpfs/projects/punim0264/ywatanabe/.scitex"
    runner_labels:
      - [self-hosted, Linux, X64, spartan-cpu]
      - [self-hosted, Linux, X64, spartan-cpu, scitex-ci]
"""

#: One file, two UNSERVED jobs — the over-exemption fixture.
_TWO_BAD_JOBS = (
    "name: ci\non: [push]\njobs:\n"
    "  test:\n    runs-on: ubuntu-latest\n"
    "  lint:\n    runs-on: [self-hosted, ghost]\n"
)

_WF = ".github/workflows/ci.yml"
_SITE_TEST = f"{_WF}::test"
_SITE_LINT = f"{_WF}::lint"


@pytest.fixture
def registry(tmp_path) -> Path:
    """A real hosts.yaml recording spartan's two live runner label sets."""
    path = tmp_path / "hosts.yaml"
    path.write_text(_REGISTRY)
    return path


def _repo_with_workflow(tmp_path: Path, body: str) -> Path:
    """Build a repo whose `.github/workflows/ci.yml` holds `body`."""
    repo = tmp_path / "repo"
    wf_dir = repo / ".github" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    (wf_dir / "ci.yml").write_text(body)
    return repo


def _workflow(runs_on: str) -> str:
    return f"name: ci\non: [push]\njobs:\n  test:\n    runs-on: {runs_on}\n"


def _write_config(repo: Path, body: str) -> Path:
    """Write a REAL `.scitex/dev/config.yaml` under `repo`."""
    cfg = repo / ".scitex" / "dev" / "config.yaml"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(body)
    return cfg


def _exemption_config(
    path: str,
    reason: str | None = "job installs system packages as root",
    rule: str = "PS-224",
) -> str:
    """The exact YAML a repo owner writes (reason omitted when None)."""
    body = (
        "project-type:\n  - pip\n"
        f"audit:\n  exemptions:\n    {rule}:\n"
        f"      - path: {path}\n        line: 0\n"
    )
    if reason is not None:
        body += f"        reason: {reason!r}\n"
    return body


def _run(repo: Path, registry_path: Path) -> list[Violation]:
    out: list[Violation] = []
    check_ps224_runner_destinations(repo, Violation, out, hosts_path=registry_path)
    return out


# -------- the advertised spelling is the reported spelling -----------------


def test_job_finding_site_key_is_job_qualified(tmp_path, registry):
    # Arrange — the reported location IS the exemption site key, so it can be
    # copied verbatim out of the audit output.
    repo = _repo_with_workflow(tmp_path, _workflow("ubuntu-latest"))
    # Act
    found = _run(repo, registry)
    # Assert
    assert found[0].where == _SITE_TEST


def test_job_finding_detail_documents_the_working_spelling(tmp_path, registry):
    # Arrange — an instruction that does not work is worse than none.
    repo = _repo_with_workflow(tmp_path, _workflow("ubuntu-latest"))
    # Act
    found = _run(repo, registry)
    # Assert
    assert f"path: {_SITE_TEST}" in found[0].detail


# -------- a reasoned, job-qualified exemption SUPPRESSES that job ----------


def test_job_qualified_exemption_suppresses_that_job(tmp_path, registry):
    # Arrange
    repo = _repo_with_workflow(tmp_path, _workflow("ubuntu-latest"))
    _write_config(repo, _exemption_config(_SITE_TEST))
    # Act
    found = _run(repo, registry)
    # Assert
    assert found == []


def test_exemption_suppresses_an_unresolvable_destination_job(tmp_path, registry):
    # Arrange — the second per-job arm honours the same site key.
    repo = _repo_with_workflow(tmp_path, _workflow("${{ vars.RUNNER }}"))
    _write_config(repo, _exemption_config(_SITE_TEST))
    # Act
    found = _run(repo, registry)
    # Assert
    assert found == []


# -------- OVER-EXEMPTION GUARD: the sibling job still reports --------------


def test_exemption_does_not_suppress_the_other_job_in_the_same_file(
    tmp_path, registry
):
    # Arrange — `ci.yml` holds one exempted job and one that must keep
    # failing. A path-keyed exemption would silence both, and a later
    # regression in the migrated job would go unnoticed.
    repo = _repo_with_workflow(tmp_path, _TWO_BAD_JOBS)
    _write_config(repo, _exemption_config(_SITE_TEST))
    # Act
    found = _run(repo, registry)
    # Assert
    assert [v.where for v in found] == [_SITE_LINT]


def test_bare_path_exemption_does_not_suppress_a_job_finding(tmp_path, registry):
    # Arrange — the file-wide spelling must NOT cover per-job findings.
    repo = _repo_with_workflow(tmp_path, _TWO_BAD_JOBS)
    _write_config(repo, _exemption_config(_WF))
    # Act
    found = _run(repo, registry)
    # Assert
    assert len(found) == 2


# -------- constitution §2: no reason, no exemption -------------------------


def test_exemption_without_a_reason_does_not_suppress(tmp_path, registry):
    # Arrange — enforced MECHANICALLY: the loader rejects a reasonless entry,
    # so it exempts nothing (and the rejection is reported as a config error
    # by the shared config-error arm).
    repo = _repo_with_workflow(tmp_path, _workflow("ubuntu-latest"))
    _write_config(repo, _exemption_config(_SITE_TEST, reason=None))
    # Act
    found = _run(repo, registry)
    # Assert
    assert len(found) == 1


def test_blank_reason_exemption_does_not_suppress(tmp_path, registry):
    # Arrange — whitespace is not a reason.
    repo = _repo_with_workflow(tmp_path, _workflow("ubuntu-latest"))
    _write_config(repo, _exemption_config(_SITE_TEST, reason="   "))
    # Act
    found = _run(repo, registry)
    # Assert
    assert len(found) == 1


# -------- a non-matching exemption suppresses nothing ----------------------


def test_exemption_for_another_job_id_does_not_suppress(tmp_path, registry):
    # Arrange
    repo = _repo_with_workflow(tmp_path, _workflow("ubuntu-latest"))
    _write_config(repo, _exemption_config(f"{_WF}::publish"))
    # Act
    found = _run(repo, registry)
    # Assert
    assert len(found) == 1


def test_exemption_for_another_workflow_file_does_not_suppress(tmp_path, registry):
    # Arrange
    repo = _repo_with_workflow(tmp_path, _workflow("ubuntu-latest"))
    _write_config(repo, _exemption_config(".github/workflows/release.yml::test"))
    # Act
    found = _run(repo, registry)
    # Assert
    assert len(found) == 1


def test_exemption_for_another_rule_does_not_suppress(tmp_path, registry):
    # Arrange — an exemption is pinned to ONE rule code.
    repo = _repo_with_workflow(tmp_path, _workflow("ubuntu-latest"))
    _write_config(repo, _exemption_config(_SITE_TEST, rule="PS-169"))
    # Act
    found = _run(repo, registry)
    # Assert
    assert len(found) == 1


def test_repo_without_any_config_still_reports(tmp_path, registry):
    # Arrange — the default is unchanged: no config, rule still fires.
    repo = _repo_with_workflow(tmp_path, _workflow("ubuntu-latest"))
    # Act
    found = _run(repo, registry)
    # Assert
    assert len(found) == 1


# -------- whole-file findings key on the BARE path -------------------------


def test_bare_path_exemption_suppresses_an_unparseable_workflow(tmp_path, registry):
    # Arrange — a whole-file finding names no job, so its site key is the bare
    # workflow path.
    repo = _repo_with_workflow(
        tmp_path, "name: ci\njobs:\n  test:\n   runs-on: [unclosed\n"
    )
    _write_config(repo, _exemption_config(_WF))
    # Act
    found = _run(repo, registry)
    # Assert
    assert found == []


def test_job_qualified_exemption_does_not_suppress_an_unparseable_workflow(
    tmp_path, registry
):
    # Arrange — the file could not be parsed, so no job id was ever read; a
    # job-qualified key must not silence the honest "could not check".
    repo = _repo_with_workflow(
        tmp_path, "name: ci\njobs:\n  test:\n   runs-on: [unclosed\n"
    )
    _write_config(repo, _exemption_config(_SITE_TEST))
    # Act
    found = _run(repo, registry)
    # Assert
    assert len(found) == 1


# EOF
