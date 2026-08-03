"""PS-224 must not tell you to relocate an attacker-triggerable secret job.

The defect these tests pin: PS-224 read a job's DESTINATION and PS-168 read
a secret's NAME, and neither read the workflow's TRIGGER — so for a job an
outsider can start that holds the fleet credential, the rule's remedy was
"re-point it at a registered destination", i.e. onto the box holding that
credential. Measured fleet-wide before the fix: 70 workflow files.

The `cla.yml` fixture below is the real shape, reduced: it is what
`scitex-logging/.github/workflows/cla.yml` actually contains.
"""

from __future__ import annotations

import yaml

from scitex_dev._cli.audit._project._workflow_exposure import (
    attacker_triggerable_events,
    delegated_exposure_detail,
    destination_detail,
    is_exposed_credential_job,
    job_secret_refs,
)

CLA_YML = """
name: CLA Assistant
on:
  issue_comment:
    types: [created]
  pull_request_target:
    types: [opened, synchronize]
jobs:
  CLAssistant:
    runs-on: ubuntu-latest
    steps:
      - uses: contributor-assistant/github-action@v2.6.1
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          PERSONAL_ACCESS_TOKEN: ${{ secrets.GH_PERSONAL_ACCESS_TOKEN }}
"""

PLAIN_CI_YML = """
name: ci
on:
  push:
    branches: [develop]
  pull_request:
jobs:
  pytest:
    runs-on: ubuntu-latest
    steps:
      - run: pytest
"""


def _detail(workflow: str, job_id: str) -> str:
    """Render PS-224's finding text for one job of one workflow."""
    doc = yaml.safe_load(workflow)
    exposed, events, secrets = is_exposed_credential_job(doc, doc["jobs"][job_id])
    return destination_detail(
        job_id, ["ubuntu-latest"], "machines.yaml", "scitex-ci", exposed, events, secrets
    )


def test_bare_on_key_parses_as_the_boolean_true():
    """The YAML gotcha that hides triggers from a naive `doc.get("on")`."""
    # Arrange
    text = CLA_YML
    # Act
    doc = yaml.safe_load(text)
    # Assert
    assert "on" not in doc and True in doc


def test_cla_workflow_is_recognized_as_attacker_triggerable():
    # Arrange
    doc = yaml.safe_load(CLA_YML)
    # Act
    events = attacker_triggerable_events(doc)
    # Assert
    assert events == {"issue_comment", "pull_request_target"}


def test_plain_pull_request_is_not_attacker_triggerable():
    """A fork `pull_request` runs without base secrets, so it is NOT this class."""
    # Arrange
    doc = yaml.safe_load(PLAIN_CI_YML)
    # Act
    events = attacker_triggerable_events(doc)
    # Assert
    assert events == frozenset()


def test_secret_refs_are_found_through_nested_step_env():
    # Arrange
    doc = yaml.safe_load(CLA_YML)
    # Act
    secrets = job_secret_refs(doc["jobs"]["CLAssistant"])
    # Assert
    assert secrets == {"GITHUB_TOKEN", "GH_PERSONAL_ACCESS_TOKEN"}


def test_cla_job_is_exposed():
    # Arrange
    doc = yaml.safe_load(CLA_YML)
    # Act
    exposed, _events, _secrets = is_exposed_credential_job(
        doc, doc["jobs"]["CLAssistant"]
    )
    # Assert
    assert exposed is True


def test_plain_ci_job_is_not_exposed():
    # Arrange
    doc = yaml.safe_load(PLAIN_CI_YML)
    # Act
    exposed, _events, _secrets = is_exposed_credential_job(doc, doc["jobs"]["pytest"])
    # Assert
    assert exposed is False


def test_exposed_job_is_told_not_to_relocate():
    # Arrange
    workflow = CLA_YML
    # Act
    detail = _detail(workflow, "CLAssistant")
    # Assert
    assert "DO NOT RE-POINT THIS JOB" in detail


def test_exposed_job_advice_never_says_re_point_the_job():
    """The positive control for the actual defect.

    Not merely "the new text is present" — the DANGEROUS sentence must be
    ABSENT. A fix that appended a warning while leaving the original remedy
    in place would pass the test above and still ship the advice that
    caused the finding.
    """
    # Arrange
    workflow = CLA_YML
    # Act
    detail = _detail(workflow, "CLAssistant")
    # Assert
    assert "re-point the job" not in detail


def test_exposed_advice_names_the_triggering_event():
    # Arrange
    workflow = CLA_YML
    # Act
    detail = _detail(workflow, "CLAssistant")
    # Assert
    assert "pull_request_target" in detail


def test_exposed_advice_names_the_credential():
    # Arrange
    workflow = CLA_YML
    # Act
    detail = _detail(workflow, "CLAssistant")
    # Assert
    assert "GH_PERSONAL_ACCESS_TOKEN" in detail


def test_unexposed_job_keeps_the_original_remedy():
    """The rule must still do its job on the files that are NOT this class."""
    # Arrange
    workflow = PLAIN_CI_YML
    # Act
    detail = _detail(workflow, "pytest")
    # Assert
    assert "re-point the job" in detail


def test_unexposed_job_is_not_given_the_exposure_warning():
    # Arrange
    workflow = PLAIN_CI_YML
    # Act
    detail = _detail(workflow, "pytest")
    # Assert
    assert "DO NOT RE-POINT" not in detail


def test_exposed_branch_still_reports_the_underlying_fact():
    """Withholding the remedy must not withhold the FINDING."""
    # Arrange
    workflow = CLA_YML
    # Act
    detail = _detail(workflow, "CLAssistant")
    # Assert
    assert "NOT in the destination registry" in detail


REUSABLE_CALLED_YML = """
name: ci-called
on:
  workflow_call:
    secrets:
      GH_PERSONAL_ACCESS_TOKEN:
        required: true
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo hi
"""


def test_called_reusable_workflow_reports_unexposed_a_known_bound():
    """Pins the gap, so a future call-graph fix has a failing anchor.

    The called file declares `workflow_call`, which is not attacker-
    triggerable on its own; the `pull_request_target` that reaches it lives
    in the CALLER. This asserts the CURRENT (bounded) behaviour, not the
    desired one: `False` here means "not visible in this file", never
    "not exposed".
    """
    # Arrange
    doc = yaml.safe_load(REUSABLE_CALLED_YML)
    # Act
    events = attacker_triggerable_events(doc)
    # Assert
    assert events == frozenset()


ORG_CALLER_YML = """
name: CLA Assistant
on:
  issue_comment:
    types: [created]
  pull_request_target:
    types: [opened, closed, synchronize]
jobs:
  call:
    uses: scitex-ai/.github/.github/workflows/cla.yml@main
    secrets: inherit
"""

PLAIN_CALLER_YML = """
name: docs
on:
  push:
    branches: [develop]
jobs:
  call:
    uses: scitex-ai/.github/.github/workflows/docs.yml@main
    secrets: inherit
"""


def test_delegating_caller_under_attacker_trigger_is_flagged():
    """The live org-template shape, which PS-224 previously skipped entirely.

    The caller names no `runs-on`, so PS-224 never looked at this job. The
    destination is in the callee, whose own `on: workflow_call` looks safe
    read alone. `secrets: inherit` on an attacker-triggerable caller is
    decidable from the caller ALONE, which is why this needs no call graph.
    """
    # Arrange
    doc = yaml.safe_load(ORG_CALLER_YML)
    # Act
    detail = delegated_exposure_detail(doc, doc["jobs"]["call"], "call")
    # Assert
    assert detail is not None


def test_delegating_caller_detail_names_secrets_inherit():
    # Arrange
    doc = yaml.safe_load(ORG_CALLER_YML)
    # Act
    detail = delegated_exposure_detail(doc, doc["jobs"]["call"], "call")
    # Assert
    assert "secrets: inherit" in detail


def test_delegating_caller_without_attacker_trigger_is_not_flagged():
    """`secrets: inherit` alone is not the defect — the trigger is."""
    # Arrange
    doc = yaml.safe_load(PLAIN_CALLER_YML)
    # Act
    detail = delegated_exposure_detail(doc, doc["jobs"]["call"], "call")
    # Assert
    assert detail is None


def test_non_delegating_job_is_not_flagged_as_delegating():
    # Arrange
    doc = yaml.safe_load(CLA_YML)
    # Act
    detail = delegated_exposure_detail(doc, doc["jobs"]["CLAssistant"], "CLAssistant")
    # Assert
    assert detail is None


def test_unexposed_branch_still_reports_the_underlying_fact():
    # Arrange
    workflow = PLAIN_CI_YML
    # Act
    detail = _detail(workflow, "pytest")
    # Assert
    assert "NOT in the destination registry" in detail


# EOF
