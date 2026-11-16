"""Internal version-one plain-data contract for Python/MCP capability factories.

Leaves can return JSON-compatible dictionaries without depending on Dev's
private model. Parsing binds shape/version/identity; the inventory inspector
still owns semantic findings. No code is loaded and no behavior is certified.
"""

from __future__ import annotations

from .._core.names import normalize_distribution_name
from .._core.provider_metadata import ProviderMetadata
from ._capability_inventory import Capability

_ROOT = {"schema_version", "distribution", "provider", "capabilities"}
_REQUIRED = {"name", "purpose", "python", "test_references"}
_OPTIONAL = {"mcp", "mcp_not_applicable_reason"}


def _object(value, *, required, optional, label):
    if type(value) is not dict:
        raise ValueError(f"{label} must be a plain object")
    if any(type(key) is not str for key in value):
        raise ValueError(f"{label} keys must be strings")
    missing = required - value.keys()
    extra = value.keys() - required - optional
    if missing or extra:
        raise ValueError(
            f"{label} fields: missing={sorted(missing)}, unexpected={sorted(extra)}"
        )
    return value


def _strings(value, label):
    if type(value) is not list or any(type(item) is not str for item in value):
        raise ValueError(f"{label} must be a plain list of strings")
    return tuple(value)


def parse_capability_declaration(
    payload: object, *, provider: ProviderMetadata,
) -> tuple[Capability, ...]:
    """Parse a version-one owner-bound factory result without accepting its scope.

    Required envelope fields are schema_version (integer 1), distribution,
    provider and capabilities. Each capability provides name, purpose, python
    and test_references; mcp and mcp_not_applicable_reason are optional.
    Empty/duplicate bindings, purposes and domain reasons remain subject to
    inspect_capability_inventory. Test references are not resolved or run.
    """
    if not isinstance(provider, ProviderMetadata):
        raise TypeError("provider must be ProviderMetadata")
    data = _object(payload, required=_ROOT, optional=set(), label="declaration")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ValueError("unsupported capability schema_version")
    if type(data["distribution"]) is not str or (
        normalize_distribution_name(data["distribution"])
        != normalize_distribution_name(provider.distribution)
    ):
        raise ValueError("capability declaration distribution does not match provider")
    if type(data["provider"]) is not str or data["provider"] != provider.name:
        raise ValueError("capability declaration provider name does not match")
    if type(data["capabilities"]) is not list:
        raise ValueError("capabilities must be a plain list")

    result = []
    for index, value in enumerate(data["capabilities"]):
        row = _object(value, required=_REQUIRED, optional=_OPTIONAL,
                      label=f"capability[{index}]")
        for key in ("name", "purpose"):
            if type(row[key]) is not str:
                raise ValueError(f"capability[{index}].{key} must be a string")
        reason = row.get("mcp_not_applicable_reason", "")
        if type(reason) is not str:
            raise ValueError("mcp_not_applicable_reason must be a string")
        result.append(Capability(
            name=row["name"], purpose=row["purpose"],
            python=_strings(row["python"], "python"),
            mcp=_strings(row.get("mcp", []), "mcp"),
            mcp_not_applicable_reason=reason,
            test_references=_strings(row["test_references"], "test_references"),
        ))
    return tuple(result)
