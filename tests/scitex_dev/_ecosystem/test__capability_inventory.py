"""Capability inventories classify observed callables without granting exposure."""

from dataclasses import replace
from statistics import mean, median

import pytest

from scitex_dev._ecosystem._capability_inventory import (
    Capability,
    inspect_capability_inventory,
)


@pytest.fixture
def capability():
    return Capability(
        name="summary", purpose="Summarize numeric observations",
        python=("mean",), mcp=("calculate_summary",),
        test_references=(__file__,),
    )


def inspect_one(capability, *, python_apis=None, mcp_tools=None):
    return inspect_capability_inventory(
        [capability],
        python_apis={"mean": mean} if python_apis is None else python_apis,
        mcp_tools={"calculate_summary": mean} if mcp_tools is None else mcp_tools,
    )


def test_consistent_inventory_does_not_claim_behavior_or_exposure(capability):
    # Arrange
    # Act
    report = inspect_one(capability)
    # Assert
    assert (report["status"], report["inventory_consistent"],
            report["behavior_verified"], report["coverage"]) == (
                "incomplete", True, False, {"python": 1, "mcp": 1},
            )


def test_library_only_scope_requires_a_domain_reason(capability):
    # Arrange
    declaration = replace(
        capability, mcp=(), mcp_not_applicable_reason="Reusable in-process primitive"
    )
    # Act
    report = inspect_one(declaration, mcp_tools={})
    # Assert
    assert (report["inventory_consistent"], report["coverage"]) == (
        True, {"python": 1, "mcp": 0}
    )


def test_aliases_and_shared_dispatchers_do_not_require_extra_tools(capability):
    # Arrange
    first = replace(capability, python=("mean", "average"))
    second = replace(capability, name="median", python=("median",))
    # Act
    report = inspect_capability_inventory(
        [first, second], python_apis={"mean": mean, "average": mean, "median": median},
        mcp_tools={"calculate_summary": mean},
    )
    # Assert
    assert (report["inventory_consistent"], report["coverage"]) == (
        True, {"python": 3, "mcp": 1}
    )


@pytest.mark.parametrize(
    "changes, code",
    [
        ({"name": "Bad name"}, "invalid_capability_name"),
        ({"purpose": " "}, "missing_purpose"),
        ({"python": "mean"}, "invalid_binding_names"),
        ({"python": ("mean", "mean")}, "duplicate_binding"),
        ({"python": ()}, "missing_python_binding"),
        ({"mcp": ()}, "unexplained_python_only_scope"),
        ({"mcp_not_applicable_reason": 42}, "invalid_scope_reason"),
        ({"mcp_not_applicable_reason": "Library only"}, "conflicting_mcp_scope"),
        ({"test_references": ()}, "missing_test_references"),
        ({"test_references": "tests.py"}, "missing_test_references"),
    ],
)
def test_invalid_declarations_report_specific_findings(capability, changes, code):
    # Arrange
    declaration = replace(capability, **changes)
    # Act
    report = inspect_one(declaration)
    # Assert
    assert (report["status"], code in {row["code"] for row in report["issues"]}) == (
        "needs_update", True
    )


@pytest.mark.parametrize("interface", ["python", "mcp"])
def test_missing_implementations_are_reported(capability, interface):
    # Arrange
    observed = {"python_apis": {"mean": mean}, "mcp_tools": {"calculate_summary": mean}}
    observed[{"python": "python_apis", "mcp": "mcp_tools"}[interface]] = {}
    # Act
    report = inspect_one(capability, **observed)
    # Assert
    assert [(row["code"], row["interface"]) for row in report["issues"]] == [
        ("missing_implementation", interface)
    ]


@pytest.mark.parametrize("interface", ["python", "mcp"])
def test_observed_noncallables_do_not_count_as_implementations(capability, interface):
    # Arrange
    observed = {"python_apis": {"mean": mean}, "mcp_tools": {"calculate_summary": mean}}
    mapping = {"python": ("python_apis", "mean"), "mcp": ("mcp_tools", "calculate_summary")}
    key, name = mapping[interface]
    observed[key] = {name: 12}
    # Act
    report = inspect_one(capability, **observed)
    # Assert
    assert [(row["code"], row["interface"]) for row in report["issues"]] == [
        ("not_callable", interface)
    ]


def test_async_transport_is_not_a_native_python_implementation(capability):
    # Arrange
    async def calculate_summary(values):
        return mean(values)
    # Act
    report = inspect_one(capability, python_apis={"mean": calculate_summary})
    # Assert
    assert [row["code"] for row in report["issues"]] == ["async_python_binding"]


def test_async_mcp_callable_can_be_observed_without_invocation(capability):
    # Arrange
    async def calculate_summary(values):
        raise AssertionError("Inventory inspection must not execute implementations")
    # Act
    report = inspect_one(capability, mcp_tools={"calculate_summary": calculate_summary})
    # Assert
    assert (report["inventory_consistent"], report["behavior_verified"]) == (True, False)


def test_unclassified_names_are_not_silently_excluded(capability):
    # Arrange
    # Act
    report = inspect_one(
        capability, python_apis={"mean": mean, "median": median},
        mcp_tools={"calculate_summary": mean, "skills_list": list},
    )
    # Assert
    assert (report["unclassified"], len(report["issues"])) == (
        {"python": ["median"], "mcp": ["skills_list"]}, 2,
    )


def test_duplicate_capability_identifiers_are_ambiguous(capability):
    # Arrange
    # Act
    report = inspect_capability_inventory(
        [capability, capability], python_apis={"mean": mean},
        mcp_tools={"calculate_summary": mean},
    )
    # Assert
    assert [row["code"] for row in report["issues"]] == ["duplicate_capability"]


def test_invalid_observed_names_fail_loudly(capability):
    # Arrange
    observed = {12: mean}
    # Act
    def call():
        return inspect_one(capability, python_apis=observed)
    # Assert
    with pytest.raises(ValueError, match="Observed names"):
        call()


def test_unknown_declaration_objects_fail_loudly():
    # Arrange
    declarations = [{"name": "summary"}]
    # Act
    def call():
        return inspect_capability_inventory(declarations, python_apis={}, mcp_tools={})
    # Assert
    with pytest.raises(TypeError, match="Capability"):
        call()
