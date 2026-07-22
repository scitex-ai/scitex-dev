"""Tests: skipped rule categories must reach the VERDICT, not just stderr.

The L1/L2 fail-loud notices in :mod:`scitex_dev.linter._health` warn on
stderr that whole rule categories never evaluated. Before this change the
RESULT did not carry that fact: ``validate-files`` printed a bare "All
files clean" and ``--json`` emitted a payload with no skip field, so an
agent reading only the verdict took "clean" to mean "clean on the whole
rule corpus" when it meant "clean on the rules that ran".

The CONTROL ARM matters as much as the positive arm here: without tests
that pin "everything ran -> the verdict claims NOTHING was skipped", a
naive fix that unconditionally reports a skip would pass.

No mocks. The "plugin present" arm feeds a REAL ``Rule`` object through
the REAL ``_health.record_plugin_load`` recording API — the same call
``_plugin_loader.load_plugins`` makes in production — rather than
patching the predicate. The env-var arm sets the real variable in
``os.environ`` and pops it on teardown.
"""

from __future__ import annotations

import json
import os

import pytest

from scitex_dev.linter import _health
from scitex_dev.linter._cmd_check import _do_check
from scitex_dev.linter._rules._base import Rule


# --------------------------------------------------------------------- #
# Fixtures                                                               #
# --------------------------------------------------------------------- #


@pytest.fixture
def health_state():
    """Give each test a clean process-wide health slate, and restore it."""
    _health.reset()
    yield _health
    _health.reset()


def _io_plugin_payload():
    """A real plugin payload registering a real io-category Rule."""
    return [
        {
            "rules": [
                Rule(
                    id="STX-IO001",
                    severity="warning",
                    category="io",
                    message="use stx.io.load",
                    suggestion="stx.io.load(path)",
                )
            ]
        }
    ]


@pytest.fixture
def io_plugin_absent(health_state):
    """Health state after a plugin load that registered ZERO io/pa rules.

    Skips when scitex-io is genuinely installed, because the L1 condition
    this arm exercises then cannot arise.
    """
    if _health._scitex_io_installed():
        pytest.skip("scitex-io installed; the L1 condition cannot arise here")
    health_state.record_plugin_load([])
    return health_state


@pytest.fixture
def io_plugin_present(health_state):
    """CONTROL: health state after a plugin registered a real io rule."""
    health_state.record_plugin_load(_io_plugin_payload())
    return health_state


@pytest.fixture
def quiet_env():
    """Set the real SCITEX_DEV_LINTER_QUIET var; pop it on teardown."""
    key = "SCITEX_DEV_LINTER_QUIET"
    previous = os.environ.get(key)
    os.environ[key] = "1"
    yield
    if previous is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = previous


@pytest.fixture
def clean_tree(tmp_path):
    """A tree whose only file has no findings, so the verdict is clean.

    The real ``pyproject.toml`` marks ``lib/`` as library code, which is
    what spares the module the script-shaped STX-S001/S002 findings. Bare
    ``VALUE = 1`` in the tree root is NOT clean — it trips S002 (missing
    ``__main__`` guard), which would make every "clean verdict" assertion
    below vacuous.
    """
    (tmp_path / "pyproject.toml").write_text(
        '[tool.scitex-dev.linter]\nlibrary_dirs = ["lib"]\n'
    )
    lib = tmp_path / "lib"
    lib.mkdir()
    (lib / "clean_module.py").write_text("VALUE = 1\n")
    return str(tmp_path)


@pytest.fixture
def skipped_records(io_plugin_absent):
    """The structured skip records when the io plugin did not register."""
    return io_plugin_absent.skipped_categories()


@pytest.fixture
def requires_gate_records(io_plugin_present):
    """Records after two rules were dropped by the `requires=` gate."""
    io_plugin_present.record_rule_skip("scitex")
    io_plugin_present.record_rule_skip("scitex")
    return io_plugin_present.skipped_categories()


@pytest.fixture
def human_out_with_skip(io_plugin_absent, clean_tree, capsys):
    """Human verdict text of a clean run that skipped a category."""
    _do_check(clean_tree, False, True, "info", None)
    return capsys.readouterr().out


@pytest.fixture
def human_out_all_ran(io_plugin_present, clean_tree, capsys):
    """CONTROL: human verdict text of a clean run where all rules ran."""
    _do_check(clean_tree, False, True, "info", None)
    return capsys.readouterr().out


@pytest.fixture
def json_meta_with_skip(io_plugin_absent, clean_tree, capsys):
    """`_meta` block of a --json run that skipped a category."""
    _do_check(clean_tree, True, True, "info", None)
    return json.loads(capsys.readouterr().out)["_meta"]


@pytest.fixture
def json_meta_all_ran(io_plugin_present, clean_tree, capsys):
    """CONTROL: `_meta` block of a --json run where all rules ran."""
    _do_check(clean_tree, True, True, "info", None)
    return json.loads(capsys.readouterr().out)["_meta"]


# --------------------------------------------------------------------- #
# Guard: this suite is meaningless if the interpreter resolved a         #
# different scitex-dev than the worktree under test.                     #
# --------------------------------------------------------------------- #


def test_ps220_default_severity_proves_the_worktree_build_was_imported():
    # Arrange
    from scitex_dev._cli.audit._project import _check_no_print

    # Act
    severity = _check_no_print._DEFAULT_SEVERITY

    # Assert
    assert severity == "W"


# --------------------------------------------------------------------- #
# skipped_categories() — the structured fact                             #
# --------------------------------------------------------------------- #


def test_missing_io_plugin_yields_exactly_one_skip_record(skipped_records):
    # Arrange
    records = skipped_records

    # Act
    count = len(records)

    # Assert
    assert count == 1


def test_missing_io_plugin_record_is_kind_plugin_missing(skipped_records):
    # Arrange
    records = skipped_records

    # Act
    kind = records[0]["kind"]

    # Assert
    assert kind == "plugin_missing"


def test_missing_io_plugin_record_names_the_io_and_path_categories(
    skipped_records,
):
    # Arrange
    records = skipped_records

    # Act
    categories = records[0]["categories"]

    # Assert
    assert categories == ["io", "path"]


def test_missing_io_plugin_record_names_the_skipped_rule_ranges(
    skipped_records,
):
    # Arrange
    records = skipped_records

    # Act
    rules = records[0]["rules"]

    # Assert
    assert "STX-IO001-014" in rules and "STX-PA001-005" in rules


def test_missing_io_plugin_record_carries_an_actionable_remedy(
    skipped_records,
):
    # Arrange
    records = skipped_records

    # Act
    remedy = records[0]["remedy"]

    # Assert
    assert remedy == "pip install scitex-io"


def test_registered_io_plugin_yields_no_skip_records(io_plugin_present):
    """CONTROL ARM: an io-category rule registered -> nothing skipped."""
    # Arrange
    health = io_plugin_present

    # Act
    records = health.skipped_categories()

    # Assert
    assert records == []


def test_requires_gate_drop_is_reported_as_its_own_record_kind(
    requires_gate_records,
):
    # Arrange
    records = requires_gate_records

    # Act
    kind = records[0]["kind"]

    # Assert
    assert kind == "requires_gate"


def test_requires_gate_record_names_the_unimportable_package(
    requires_gate_records,
):
    # Arrange
    records = requires_gate_records

    # Act
    requires = records[0]["requires"]

    # Assert
    assert requires == "scitex"


def test_requires_gate_record_counts_the_dropped_evaluations(
    requires_gate_records,
):
    # Arrange
    records = requires_gate_records

    # Act
    dropped = records[0]["skipped_evaluations"]

    # Assert
    assert dropped == 2


def test_quiet_env_switch_does_not_suppress_the_skip_fact(
    quiet_env, io_plugin_absent
):
    """SCITEX_DEV_LINTER_QUIET silences the NOTICE, never the FACT — a
    quiet run still skipped the rules and its verdict must say so."""
    # Arrange
    health = io_plugin_absent

    # Act
    kinds = [r["kind"] for r in health.skipped_categories()]

    # Assert
    assert kinds == ["plugin_missing"]


# --------------------------------------------------------------------- #
# describe_skips() — the human rendering                                 #
# --------------------------------------------------------------------- #


def test_describe_skips_returns_no_lines_when_nothing_was_skipped(
    io_plugin_present,
):
    """CONTROL ARM: the human verdict gains nothing when all rules ran."""
    # Arrange
    health = io_plugin_present

    # Act
    lines = health.describe_skips()

    # Assert
    assert lines == []


def test_describe_skips_leads_with_the_count_of_skipped_groups(
    io_plugin_absent,
):
    # Arrange
    health = io_plugin_absent
    health.record_rule_skip("scitex")

    # Act
    headline = health.describe_skips()[0]

    # Assert
    assert "2 rule category group(s) skipped" in headline


def test_describe_skips_headline_qualifies_the_verdict_as_partial(
    io_plugin_absent,
):
    # Arrange
    health = io_plugin_absent

    # Act
    headline = health.describe_skips()[0]

    # Assert
    assert "only the rules that ran" in headline


# --------------------------------------------------------------------- #
# _do_check human verdict                                                #
# --------------------------------------------------------------------- #


def test_clean_verdict_is_qualified_when_a_category_did_not_run(
    human_out_with_skip,
):
    # Arrange
    out = human_out_with_skip

    # Act
    qualified = "All files clean ON THE RULES THAT RAN" in out

    # Assert
    assert qualified


def test_clean_verdict_states_that_not_all_rules_ran(human_out_with_skip):
    # Arrange
    out = human_out_with_skip

    # Act
    stated = "NOT ALL RULES RAN" in out

    # Assert
    assert stated


def test_clean_verdict_names_the_skipped_rule_ranges(human_out_with_skip):
    # Arrange
    out = human_out_with_skip

    # Act
    named = "STX-IO001-014" in out

    # Assert
    assert named


def test_clean_verdict_is_unqualified_when_every_category_ran(
    human_out_all_ran,
):
    """CONTROL ARM: the verdict is the plain 'All files clean'."""
    # Arrange
    out = human_out_all_ran

    # Act
    unqualified = "All files clean" in out and "ON THE RULES THAT RAN" not in out

    # Assert
    assert unqualified


def test_clean_verdict_claims_no_skip_when_every_category_ran(
    human_out_all_ran,
):
    """CONTROL ARM: nothing in the output asserts a skip."""
    # Arrange
    out = human_out_all_ran

    # Act
    claims_skip = "NOT ALL RULES RAN" in out

    # Assert
    assert not claims_skip


# --------------------------------------------------------------------- #
# Exit code — REPORTED, never promoted                                   #
# --------------------------------------------------------------------- #


def test_skipped_category_does_not_change_the_clean_exit_code(
    io_plugin_absent, clean_tree
):
    """A missing OPTIONAL plugin is not a lint failure."""
    # Arrange
    health = io_plugin_absent

    # Act
    rc = _do_check(clean_tree, False, True, "info", None)

    # Assert
    assert rc == 0 and health.skipped_categories() != []


def test_clean_exit_code_matches_between_skipped_and_all_ran_runs(
    io_plugin_present, clean_tree
):
    """CONTROL PAIR: same rc whether or not a category was skipped."""
    # Arrange
    rc_all_ran = _do_check(clean_tree, False, True, "info", None)
    io_plugin_present.reset()
    io_plugin_present.record_plugin_load([])

    # Act
    rc_with_skip = _do_check(clean_tree, False, True, "info", None)

    # Assert
    assert rc_with_skip == rc_all_ran


# --------------------------------------------------------------------- #
# _do_check --json payload                                               #
# --------------------------------------------------------------------- #


def test_json_meta_reports_all_rules_ran_false_when_a_category_skipped(
    json_meta_with_skip,
):
    # Arrange
    meta = json_meta_with_skip

    # Act
    all_ran = meta["all_rules_ran"]

    # Assert
    assert all_ran is False


def test_json_meta_counts_the_skipped_categories(json_meta_with_skip):
    # Arrange
    meta = json_meta_with_skip

    # Act
    count = meta["skipped_category_count"]

    # Assert
    assert count == 1


def test_json_meta_carries_the_skip_as_structured_data_not_prose(
    json_meta_with_skip,
):
    # Arrange
    meta = json_meta_with_skip

    # Act
    kind = meta["skipped_categories"][0]["kind"]

    # Assert
    assert kind == "plugin_missing"


def test_json_meta_reports_all_rules_ran_true_when_nothing_skipped(
    json_meta_all_ran,
):
    """CONTROL ARM: the field is present and POSITIVE when everything
    ran, so its absence is never what an agent has to detect."""
    # Arrange
    meta = json_meta_all_ran

    # Act
    all_ran = meta["all_rules_ran"]

    # Assert
    assert all_ran is True


def test_json_meta_skipped_list_is_empty_when_nothing_skipped(
    json_meta_all_ran,
):
    """CONTROL ARM."""
    # Arrange
    meta = json_meta_all_ran

    # Act
    skipped = meta["skipped_categories"]

    # Assert
    assert skipped == []


# EOF
