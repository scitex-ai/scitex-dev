"""Unit tests for the pure `runs-on` parsing layer used by PS-224.

No mocks (NM001-003): the functions under test are pure — they take YAML
values and real `tmp_path` trees and return data. `.github` is a HIDDEN
directory, so the workflow-discovery fixtures build that path explicitly
rather than relying on any walker (a walker that skips dotted dirs returns
zero files, which is indistinguishable from "this repo has no workflows").

One assert per test (STX-TQ007), Arrange/Act/Assert markers (STX-TQ002).
"""

from __future__ import annotations

from pathlib import Path

from scitex_dev._cli.audit._project._runs_on_parsing import (
    as_labels,
    describe_destinations,
    fromjson_literal,
    resolve_destination,
    workflow_files,
)

_FLEET_IDIOM = (
    "${{ fromJSON(vars.CI_RUNS_ON || "
    "'[\"self-hosted\",\"Linux\",\"X64\",\"scitex-ci\"]') }}"
)


# -------- as_labels: the three spellings GitHub accepts --------------------


def test_as_labels_scalar_form():
    # Arrange
    value = "ubuntu-latest"
    # Act
    got = as_labels(value)
    # Assert
    assert got == ["ubuntu-latest"]


def test_as_labels_list_form():
    # Arrange
    value = ["self-hosted", "Linux"]
    # Act
    got = as_labels(value)
    # Assert
    assert got == ["self-hosted", "Linux"]


def test_as_labels_mapping_labels_key():
    # Arrange
    value = {"labels": ["self-hosted", "scitex-ci"]}
    # Act
    got = as_labels(value)
    # Assert
    assert got == ["self-hosted", "scitex-ci"]


def test_as_labels_mapping_group_key():
    # Arrange
    value = {"group": "scitex-fleet"}
    # Act
    got = as_labels(value)
    # Assert
    assert got == ["scitex-fleet"]


def test_as_labels_unsupported_type_yields_nothing():
    # Arrange — e.g. a `runs-on:` with a null value.
    value = None
    # Act
    got = as_labels(value)
    # Assert
    assert got == []


# -------- fromjson_literal: the `|| '[...]'` fallback ----------------------


def test_fromjson_literal_reads_the_or_fallback():
    # Arrange
    args = "vars.CI_RUNS_ON || '[\"self-hosted\",\"Linux\"]'"
    # Act
    got = fromjson_literal(args)
    # Assert
    assert got == ["self-hosted", "Linux"]


def test_fromjson_literal_without_any_array_is_none():
    # Arrange — nothing static to read.
    args = "vars.CI_RUNS_ON"
    # Act
    got = fromjson_literal(args)
    # Assert
    assert got is None


def test_fromjson_literal_skips_an_unparseable_array():
    # Arrange — the first bracket group is not JSON; the second is.
    args = "[not json] || '[\"self-hosted\"]'"
    # Act
    got = fromjson_literal(args)
    # Assert
    assert got == ["self-hosted"]


# -------- resolve_destination ---------------------------------------------


def test_resolve_destination_fleet_idiom_resolves_to_its_literal():
    # Arrange
    runs_on = _FLEET_IDIOM
    # Act
    got = resolve_destination(runs_on)
    # Assert
    assert got == ["self-hosted", "Linux", "X64", "scitex-ci"]


def test_resolve_destination_bare_variable_is_unresolvable():
    # Arrange — a destination that cannot be read names none.
    runs_on = "${{ vars.RUNNER }}"
    # Act
    got = resolve_destination(runs_on)
    # Assert
    assert got is None


def test_resolve_destination_matrix_expression_is_unresolvable():
    # Arrange
    runs_on = "${{ matrix.os }}"
    # Act
    got = resolve_destination(runs_on)
    # Assert
    assert got is None


def test_resolve_destination_strips_whitespace():
    # Arrange
    runs_on = ["  self-hosted  ", "Linux"]
    # Act
    got = resolve_destination(runs_on)
    # Assert
    assert got == ["self-hosted", "Linux"]


def test_resolve_destination_of_empty_list_is_none():
    # Arrange
    runs_on: list[str] = []
    # Act
    got = resolve_destination(runs_on)
    # Assert
    assert got is None


# -------- workflow_files: `.github` is hidden ------------------------------


def test_workflow_files_finds_both_extensions(tmp_path: Path):
    # Arrange
    wf_dir = tmp_path / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "ci.yml").write_text("name: ci\n")
    (wf_dir / "release.yaml").write_text("name: release\n")
    # Act
    got = [p.name for p in workflow_files(tmp_path)]
    # Assert
    assert got == ["ci.yml", "release.yaml"]


def test_workflow_files_ignores_non_yaml_files(tmp_path: Path):
    # Arrange
    wf_dir = tmp_path / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "README.md").write_text("notes\n")
    # Act
    got = workflow_files(tmp_path)
    # Assert
    assert got == []


def test_workflow_files_of_repo_without_workflows_dir(tmp_path: Path):
    # Arrange
    repo = tmp_path
    # Act
    got = workflow_files(repo)
    # Assert
    assert got == []


# -------- describe_destinations -------------------------------------------


def test_describe_destinations_renders_host_and_sorted_labels():
    # Arrange
    destinations = [("spartan", frozenset({"Linux", "self-hosted"}))]
    # Act
    got = describe_destinations(destinations)
    # Assert
    assert got == "spartan: [Linux, self-hosted]"


# EOF
