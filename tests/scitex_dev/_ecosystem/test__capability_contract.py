"""Plain-data factories bind declaration identity without claiming behavior."""

import json
from statistics import mean

import pytest

from scitex_dev._core.provider_metadata import ProviderMetadata
from scitex_dev._ecosystem._capability_contract import parse_capability_declaration
from scitex_dev._ecosystem._capability_inventory import inspect_capability_inventory


@pytest.fixture
def provider():
    return ProviderMetadata(
        name="default", target="owned_provider:inventory",
        distribution="owned-example", version="1.2.3", summary="Owned fixture",
    )


@pytest.fixture
def payload():
    return {
        "schema_version": 1, "distribution": "Owned.Example", "provider": "default",
        "capabilities": [{
            "name": "summary", "purpose": "Summarize observations",
            "python": ["mean"], "mcp": ["calculate_summary"],
            "test_references": [__file__],
        }],
    }


def test_json_round_trip_produces_internal_immutable_bindings(provider, payload):
    # Arrange
    serialized = json.dumps(payload)
    # Act
    declarations = parse_capability_declaration(json.loads(serialized), provider=provider)
    # Assert
    assert (declarations[0].name, declarations[0].python, declarations[0].mcp) == (
        "summary", ("mean",), ("calculate_summary",)
    )


def test_parsed_lists_do_not_retain_mutable_factory_data(provider, payload):
    # Arrange
    declarations = parse_capability_declaration(payload, provider=provider)
    # Act
    payload["capabilities"][0]["python"].append("mutated")
    # Assert
    assert declarations[0].python == ("mean",)


@pytest.mark.parametrize("version", [True, "1", 1.0, 0, 2, None])
def test_unknown_or_noninteger_schema_versions_are_refused(provider, payload, version):
    # Arrange
    payload["schema_version"] = version
    # Act
    def parse():
        return parse_capability_declaration(payload, provider=provider)
    # Assert
    with pytest.raises(ValueError, match="schema_version"):
        parse()


@pytest.mark.parametrize("field,value", [
    ("distribution", "another-owner"), ("provider", "another-provider"),
    ("distribution", 12), ("provider", None),
])
def test_factory_cannot_change_its_declaring_identity(provider, payload, field, value):
    # Arrange
    payload[field] = value
    # Act
    def parse():
        return parse_capability_declaration(payload, provider=provider)
    # Assert
    with pytest.raises(ValueError, match="does not match"):
        parse()


@pytest.mark.parametrize("field", ["behavior_verified", "audit_exempt", "allowlist"])
def test_factory_acceptance_flags_are_not_part_of_the_contract(provider, payload, field):
    # Arrange
    payload[field] = True
    # Act
    def parse():
        return parse_capability_declaration(payload, provider=provider)
    # Assert
    with pytest.raises(ValueError, match="unexpected"):
        parse()


@pytest.mark.parametrize("field", ["schema_version", "distribution", "provider", "capabilities"])
def test_missing_envelope_fields_fail_loudly(provider, payload, field):
    # Arrange
    del payload[field]
    # Act
    def parse():
        return parse_capability_declaration(payload, provider=provider)
    # Assert
    with pytest.raises(ValueError, match="missing"):
        parse()


@pytest.mark.parametrize("field", ["name", "purpose", "python", "test_references"])
def test_missing_capability_fields_fail_loudly(provider, payload, field):
    # Arrange
    del payload["capabilities"][0][field]
    # Act
    def parse():
        return parse_capability_declaration(payload, provider=provider)
    # Assert
    with pytest.raises(ValueError, match="missing"):
        parse()


@pytest.mark.parametrize("field,value", [
    ("python", "mean"), ("python", [12]), ("mcp", ("calculate_summary",)),
    ("test_references", None), ("name", 12), ("purpose", None),
    ("mcp_not_applicable_reason", False),
])
def test_malformed_capability_values_are_refused(provider, payload, field, value):
    # Arrange
    payload["capabilities"][0][field] = value
    # Act
    def parse():
        return parse_capability_declaration(payload, provider=provider)
    # Assert
    with pytest.raises(ValueError):
        parse()


def test_unknown_capability_fields_are_not_silently_dropped(provider, payload):
    # Arrange
    payload["capabilities"][0]["skip_audit"] = True
    # Act
    def parse():
        return parse_capability_declaration(payload, provider=provider)
    # Assert
    with pytest.raises(ValueError, match="unexpected"):
        parse()


def test_semantic_scope_errors_still_reach_the_inventory_inspector(provider, payload):
    # Arrange
    payload["capabilities"][0]["purpose"] = ""
    declarations = parse_capability_declaration(payload, provider=provider)
    # Act
    report = inspect_capability_inventory(
        declarations, python_apis={"mean": mean},
        mcp_tools={"calculate_summary": mean},
    )
    # Assert
    assert (report["status"], report["behavior_verified"],
            [row["code"] for row in report["issues"]]) == (
                "needs_update", False, ["missing_purpose"],
            )


def test_valid_contract_does_not_certify_behavior(provider, payload):
    # Arrange
    declarations = parse_capability_declaration(payload, provider=provider)
    # Act
    report = inspect_capability_inventory(
        declarations, python_apis={"mean": mean},
        mcp_tools={"calculate_summary": mean},
    )
    # Assert
    assert (report["status"], report["inventory_consistent"],
            report["behavior_verified"]) == ("incomplete", True, False)


def test_empty_declaration_does_not_hide_observed_apis(provider, payload):
    # Arrange
    payload["capabilities"] = []
    declarations = parse_capability_declaration(payload, provider=provider)
    # Act
    report = inspect_capability_inventory(declarations, python_apis={"mean": mean}, mcp_tools={})
    # Assert
    assert (report["status"], report["unclassified"]) == (
        "needs_update", {"python": ["mean"], "mcp": []}
    )


def test_library_scope_uses_plain_data_and_an_explicit_reason(provider, payload):
    # Arrange
    row = payload["capabilities"][0]
    del row["mcp"]
    row["mcp_not_applicable_reason"] = "Reusable in-process numerical primitive"
    declarations = parse_capability_declaration(payload, provider=provider)
    # Act
    report = inspect_capability_inventory(declarations, python_apis={"mean": mean}, mcp_tools={})
    # Assert
    assert (report["inventory_consistent"], declarations[0].mcp) == (True, ())


def test_non_object_envelope_is_refused(provider):
    # Arrange
    payload = []
    # Act
    def parse():
        return parse_capability_declaration(payload, provider=provider)
    # Assert
    with pytest.raises(ValueError, match="plain object"):
        parse()


def test_nonstring_object_keys_are_refused(provider, payload):
    # Arrange
    payload[12] = "invalid"
    # Act
    def parse():
        return parse_capability_declaration(payload, provider=provider)
    # Assert
    with pytest.raises(ValueError, match="keys must be strings"):
        parse()


def test_non_metadata_owner_context_is_refused(payload):
    # Arrange
    provider = {"distribution": "owned-example"}
    # Act
    def parse():
        return parse_capability_declaration(payload, provider=provider)
    # Assert
    with pytest.raises(TypeError, match="ProviderMetadata"):
        parse()


@pytest.mark.parametrize("value", [None, {}, ()])
def test_capability_collection_must_be_a_plain_list(provider, payload, value):
    # Arrange
    payload["capabilities"] = value
    # Act
    def parse():
        return parse_capability_declaration(payload, provider=provider)
    # Assert
    with pytest.raises(ValueError, match="plain list"):
        parse()


@pytest.mark.parametrize("value", [None, [], "summary"])
def test_capability_rows_must_be_plain_objects(provider, payload, value):
    # Arrange
    payload["capabilities"] = [value]
    # Act
    def parse():
        return parse_capability_declaration(payload, provider=provider)
    # Assert
    with pytest.raises(ValueError, match="plain object"):
        parse()
