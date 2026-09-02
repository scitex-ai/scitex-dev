"""Tests for the PS-140 gate tail repair.

The two input shapes below are TRANSCRIBED FROM THE FLEET, not invented:
`_STOCK_TAIL` is scitex-logging's and scitex-str's body as it stood on
`develop` on 2026-08-23, and `_STRENGTHENED_TAIL` is scitex-io's. Using the
real bytes is the point — a repair that works on a tidied-up sample and not on
what is actually deployed would pass this file and fix nothing.
"""

from __future__ import annotations

import importlib
import textwrap

import pytest

from scitex_dev._cli.ecosystem._cmds._gate_tail_repair import repair_tail

_STOCK_TAIL = '''# ===== END AUTO-GENERATED =====


@pytest.mark.parametrize("module_name", CROSS_PACKAGE_IMPORTS)
def test_cross_package_import_resolves_module_name(module_name):
    """Importing a declared cross-package dependency yields a module object."""
    # Arrange
    name = module_name
    # Act
    module = pytest.importorskip(name)
    # Assert
    assert module is not None
'''

_STRENGTHENED_TAIL = '''# ===== END AUTO-GENERATED =====


@pytest.mark.parametrize("module_name", CROSS_PACKAGE_IMPORTS)
def test_cross_package_import_resolves_to_module(module_name):
    """Importing scitex-io's declared cross-package dependency must succeed."""
    # Arrange
    # (importorskip skips when peer standalone absent; otherwise asserts
    # the imported object is the named module.)
    # Act
    mod = pytest.importorskip(module_name)
    # Assert
    assert getattr(mod, "__name__", None) == module_name
'''


def test_stock_tail_gains_the_root_split_guard():
    """The stock body's full-path guard becomes a root-split guard."""
    # Arrange
    tail = _STOCK_TAIL
    # Act
    result = repair_tail(tail)
    # Assert
    assert 'root = module_name.split(".")[0]' in result.tail


def test_stock_tail_binds_the_module_with_import_module():
    """The original binding name survives, now bound by a real import."""
    # Arrange
    tail = _STOCK_TAIL
    # Act
    result = repair_tail(tail)
    # Assert
    assert "module = importlib.import_module(module_name)" in result.tail


def test_stock_tail_drops_the_now_unused_alias():
    """`name = module_name` is removed once nothing reads `name`."""
    # Arrange
    tail = _STOCK_TAIL
    # Act
    result = repair_tail(tail)
    # Assert
    assert "name = module_name" not in result.tail


def test_strengthened_tail_keeps_its_stronger_assertion():
    """scitex-io's hand-written assertion is preserved verbatim."""
    # Arrange
    tail = _STRENGTHENED_TAIL
    # Act
    result = repair_tail(tail)
    # Assert
    assert 'assert getattr(mod, "__name__", None) == module_name' in result.tail


def test_strengthened_tail_keeps_its_binding_name():
    """The repair rebinds `mod`, not a name of its own choosing."""
    # Arrange
    tail = _STRENGTHENED_TAIL
    # Act
    result = repair_tail(tail)
    # Assert
    assert "mod = importlib.import_module(module_name)" in result.tail


def test_an_already_repaired_tail_is_left_alone():
    """Running the repair twice changes nothing the second time."""
    # Arrange
    once = repair_tail(_STOCK_TAIL).tail
    # Act
    twice = repair_tail(once)
    # Assert
    assert twice.changed is False


def test_an_already_repaired_tail_says_why_it_was_skipped():
    """`changed=False` must be distinguishable from a decline."""
    # Arrange
    once = repair_tail(_STOCK_TAIL).tail
    # Act
    twice = repair_tail(once)
    # Assert
    assert twice.reason == "already guards on the root"


def test_an_unrecognised_tail_is_declined_rather_than_guessed():
    """A body with no importorskip assignment is not rewritten."""
    # Arrange
    tail = "# ===== END AUTO-GENERATED =====\n\n\ndef test_nothing():\n    pass\n"
    # Act
    result = repair_tail(tail)
    # Assert
    assert result.changed is False


def test_an_unrecognised_tail_names_what_was_missing():
    """The decline reason has to be actionable, not just negative."""
    # Arrange
    tail = "# ===== END AUTO-GENERATED =====\n\n\ndef test_nothing():\n    pass\n"
    # Act
    result = repair_tail(tail)
    # Assert
    assert "importorskip" in result.reason


def test_a_guard_on_an_unresolvable_local_is_declined():
    """Skipping on a name that is not the parameter is refused, not guessed."""
    # Arrange
    tail = textwrap.dedent(
        '''\
        # ===== END AUTO-GENERATED =====


        @pytest.mark.parametrize("module_name", CROSS_PACKAGE_IMPORTS)
        def test_gate(module_name):
            whatever = compute_something()
            module = pytest.importorskip(whatever)
            assert module is not None
        '''
    )
    # Act
    result = repair_tail(tail)
    # Assert
    assert result.changed is False


def _run_repaired_body(tail: str, module_name: str):
    """Execute the repaired test function against one module name.

    `CROSS_PACKAGE_IMPORTS` is supplied because the tail references it in its
    `parametrize` decorator; the value is irrelevant here since the function is
    invoked directly with the name under test. `pytest.mark.parametrize`
    attaches metadata and returns the function unchanged, so calling it works.
    """
    source = tail.replace("# ===== END AUTO-GENERATED =====", "", 1)
    namespace = {
        "pytest": pytest,
        "importlib": importlib,
        "CROSS_PACKAGE_IMPORTS": [],
    }
    exec(compile(source, "<repaired>", "exec"), namespace)  # noqa: S102
    fn = next(v for k, v in namespace.items() if k.startswith("test_"))
    return fn(module_name)


def test_repaired_gate_fails_loudly_when_a_submodule_is_missing():
    """THE CONTROL: a rename inside an INSTALLED peer must FAIL, not skip.

    This is the behaviour the docstring promised and the original guard could
    not deliver, so it is the only assertion that shows the repair did the job
    rather than merely rearranging lines.
    """
    # Arrange
    repaired = repair_tail(_STOCK_TAIL).tail
    # Act
    expected = pytest.raises(ModuleNotFoundError)
    # Assert
    with expected:
        _run_repaired_body(repaired, "json._this_submodule_does_not_exist")


def test_original_gate_skips_where_the_repaired_one_fails():
    """The same input against the UNREPAIRED body skips — the defect itself.

    Asserting the broken behaviour explicitly is what establishes that the
    test above measures the repair and not something incidental.
    """
    # Arrange
    original = _STOCK_TAIL
    # Act
    expected = pytest.raises(pytest.skip.Exception)
    # Assert
    with expected:
        _run_repaired_body(original, "json._this_submodule_does_not_exist")


def test_repaired_gate_still_skips_when_the_root_is_absent():
    """A genuinely absent peer distribution must still SKIP, not fail.

    PS-140's own prose: banning the skip "would convert a legitimate absence
    into a hard failure — a gate that cannot PASS, in place of one that cannot
    FAIL."
    """
    # Arrange
    repaired = repair_tail(_STOCK_TAIL).tail
    # Act
    expected = pytest.raises(pytest.skip.Exception)
    # Assert
    with expected:
        _run_repaired_body(repaired, "_no_such_root_package_anywhere")


def test_repaired_gate_passes_for_a_module_that_imports():
    """The ordinary case still passes."""
    # Arrange
    repaired = repair_tail(_STOCK_TAIL).tail
    # Act
    outcome = _run_repaired_body(repaired, "json")
    # Assert
    assert outcome is None
