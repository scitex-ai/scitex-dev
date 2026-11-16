"""Inspect leaf-owned Python/MCP capability mappings against observed callables.

This internal primitive does not discover providers, invoke implementations,
change audit rules or grant exposure. A consistent inventory remains incomplete:
callable presence and declaration-provided test references do not establish
argument/result parity, scientific behavior, installed ownership or hosting.
"""

from __future__ import annotations

import inspect
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Capability:
    """One leaf-owned operation or library scope with explicit API bindings."""

    name: str
    purpose: str
    python: tuple[str, ...]
    mcp: tuple[str, ...] = ()
    mcp_not_applicable_reason: str = ""
    test_references: tuple[str, ...] = ()


def inspect_capability_inventory(
    capabilities: Sequence[Capability],
    *,
    python_apis: Mapping[str, object],
    mcp_tools: Mapping[str, object],
) -> dict:
    """Compare declarations with caller-supplied observations without invoking them.

    All observed names must be classified. Multiple capabilities may share a
    dispatcher, and aliases may share a callable. Python-only scopes require a
    reason. Native Python bindings must be synchronous callables; MCP bindings
    may be asynchronous. Test references are recorded but not resolved/executed.
    The caller must obtain observations from the actual owning interfaces.
    """
    for observed in (python_apis, mcp_tools):
        if any(not isinstance(name, str) or not name.strip() for name in observed):
            raise ValueError("Observed names must be nonempty strings")

    issues = []
    covered = {"python": set(), "mcp": set()}
    seen = set()
    references = {}

    def issue(code, capability, interface=None, name=None):
        issues.append({"code": code, "capability": capability,
                       "interface": interface, "name": name})

    for cap in capabilities:
        if not isinstance(cap, Capability):
            raise TypeError("Every declaration must be a Capability")
        label = cap.name if isinstance(cap.name, str) else repr(cap.name)
        if not isinstance(cap.name, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", cap.name):
            issue("invalid_capability_name", label)
        if label in seen:
            issue("duplicate_capability", label)
        seen.add(label)
        if not isinstance(cap.purpose, str) or not cap.purpose.strip():
            issue("missing_purpose", label)

        for interface, names, observed in (
            ("python", cap.python, python_apis), ("mcp", cap.mcp, mcp_tools)
        ):
            if not isinstance(names, tuple) or any(
                not isinstance(name, str) or not name.strip() for name in names
            ):
                issue("invalid_binding_names", label, interface)
                continue
            if len(set(names)) != len(names):
                issue("duplicate_binding", label, interface)
            for name in names:
                covered[interface].add(name)
                if name not in observed:
                    issue("missing_implementation", label, interface, name)
                elif not callable(observed[name]):
                    issue("not_callable", label, interface, name)
                elif interface == "python" and (
                    inspect.iscoroutinefunction(observed[name])
                    or inspect.isasyncgenfunction(observed[name])
                ):
                    issue("async_python_binding", label, interface, name)

        if not cap.python:
            issue("missing_python_binding", label, "python")
        reason = cap.mcp_not_applicable_reason
        if not isinstance(reason, str):
            issue("invalid_scope_reason", label, "mcp")
        elif cap.mcp and reason.strip():
            issue("conflicting_mcp_scope", label, "mcp")
        elif not cap.mcp and not reason.strip():
            issue("unexplained_python_only_scope", label, "mcp")

        refs = cap.test_references
        if not isinstance(refs, tuple) or not refs or any(
            not isinstance(ref, str) or not ref.strip() for ref in refs
        ):
            issue("missing_test_references", label)
        else:
            references[label] = list(refs)

    unclassified = {}
    for interface, observed in (("python", python_apis), ("mcp", mcp_tools)):
        unclassified[interface] = sorted(set(observed) - covered[interface])
        for name in unclassified[interface]:
            issue("unclassified_observed_name", None, interface, name)

    return {
        "status": "needs_update" if issues else "incomplete",
        "inventory_consistent": not issues,
        "behavior_verified": False,
        "issues": issues,
        "coverage": {
            "python": len(covered["python"] & set(python_apis)),
            "mcp": len(covered["mcp"] & set(mcp_tools)),
        },
        "unclassified": unclassified,
        "test_references": references,
        "limitations": [
            "Observed mappings are supplied by the caller; discovery/ownership is not verified.",
            "Implementations are not invoked; callable presence is not argument/result parity.",
            "Declaration test references are not resolved or executed.",
            "Installed packaging, CLI, Web API, skills and live hosting are not qualified.",
            "Existing audit rules and exposure preferences are unchanged.",
        ],
    }
