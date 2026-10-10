"""Bounded, declared transitions between installed linter providers."""

from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class ProviderReplacement:
    """Replace one exact predecessor's complete advertised rule ownership.

    An absent predecessor is dormant. An unfamiliar provider advertised by
    the named distribution fails; no unrelated provider can be displaced.
    """

    distribution: str
    entry_point: str
    value: str
    rule_ids: tuple[str, ...]


class ProviderReplacementError(ValueError):
    """A declared ownership transition cannot be proved complete."""


def _distribution(point):
    dist = getattr(point, "dist", None)
    if dist is None:
        return None
    name = dist.metadata.get("Name")
    return _normalize(name) if isinstance(name, str) else None


def _normalize(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def resolve_replacements(providers):
    """Select declared successors, using only the supplied provider records.

    Records are (entry_point, payload, is_logging, display_name). No lookup
    outside this discovery is performed, including in injected tests.
    """
    distributions = {}
    for index, (point, payload, is_logging, name) in enumerate(providers):
        distribution = _distribution(point)
        if distribution is not None:
            distributions.setdefault(distribution, []).append(index)
    replaced_by = {}
    graph = {}
    receipts = []
    for source, (point, payload, is_logging, name) in enumerate(providers):
        declarations = payload.get("replaces", ())
        if not isinstance(declarations, tuple):
            raise ProviderReplacementError(
                f"provider {name!r}: replaces must be a tuple"
            )
        offered = {rule.id for rule in payload.get("rules", ())}
        for declaration in declarations:
            if (
                not isinstance(declaration, ProviderReplacement)
                or not all(
                    isinstance(field, str) and field.strip()
                    for field in (
                        declaration.distribution,
                        declaration.entry_point,
                        declaration.value,
                    )
                )
                or not isinstance(declaration.rule_ids, tuple)
                or not declaration.rule_ids
                or not all(
                    isinstance(code, str) and code.strip()
                    for code in declaration.rule_ids
                )
                or len(set(declaration.rule_ids)) != len(declaration.rule_ids)
            ):
                raise ProviderReplacementError(
                    f"provider {name!r}: invalid ProviderReplacement"
                )
            expected = set(declaration.rule_ids)
            if "PS-220" in expected:
                raise ProviderReplacementError(
                    "mandatory logging ownership cannot be replaced"
                )
            if not expected <= offered:
                raise ProviderReplacementError(
                    f"provider {name!r}: replacement does not offer all declared rule IDs"
                )
            candidates = distributions.get(_normalize(declaration.distribution), ())
            if not candidates:
                continue
            matches = [
                index
                for index in candidates
                if providers[index][0].name == declaration.entry_point
                and providers[index][0].value == declaration.value
            ]
            if len(matches) != 1:
                raise ProviderReplacementError(
                    f"provider {name!r}: unknown or ambiguous predecessor {declaration.distribution!r}; "
                    "advertised entry point does not match the exact replacement contract"
                )
            target = matches[0]
            if target == source:
                raise ProviderReplacementError(
                    f"provider {name!r}: self-replacement is forbidden"
                )
            if providers[target][2]:
                raise ProviderReplacementError(
                    "mandatory logging ownership cannot be replaced"
                )
            actual = {rule.id for rule in providers[target][1].get("rules", ())}
            if actual != expected:
                raise ProviderReplacementError(
                    f"provider {name!r}: predecessor's complete advertised rule IDs differ from replacement contract"
                )
            if target in replaced_by:
                raise ProviderReplacementError(
                    f"provider {name!r}: multiple or repeated replacements for predecessor {providers[target][3]!r}"
                )
            replaced_by[target] = source
            graph.setdefault(source, []).append(target)
            receipts.append(
                {
                    "successor_distribution": _distribution(point),
                    "successor_entry_point": point.name,
                    "successor_value": point.value,
                    "predecessor_distribution": _normalize(declaration.distribution),
                    "predecessor_entry_point": declaration.entry_point,
                    "predecessor_value": declaration.value,
                    "rule_ids": declaration.rule_ids,
                }
            )
    visiting, visited = set(), set()

    def visit(index):
        if index in visiting:
            raise ProviderReplacementError("cyclic provider replacements are forbidden")
        if index in visited:
            return
        visiting.add(index)
        for target in graph.get(index, ()):
            visit(target)
        visiting.remove(index)
        visited.add(index)

    for index in graph:
        visit(index)
    return [
        record for index, record in enumerate(providers) if index not in replaced_by
    ], tuple(receipts)
