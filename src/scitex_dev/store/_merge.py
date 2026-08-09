#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Per-field merge — deciding what is PRESENTED, never what exists.

Every function here is pure: given two values and their stamps it returns
the winner. That matters more than it sounds. Because merging is pure and
deterministic, two replicas that have applied the same set of ops agree on
the result no matter what order the ops arrived in — which is what makes
the replication layer convergent rather than merely hopeful.

Nothing here deletes
--------------------
A merge picks a value to show. The value it did not pick is still in the
oplog, which is append-only, so "losing" a merge is not data loss — it is
a view. That distinction is the reason automatic merging is safe here and
is not safe in a system that overwrites its history: the objection to
automatic merges is really an objection to merges that DISCARD, and an
append-only log is precisely the constraint that stops them discarding.

The one rule that reports instead of deciding
---------------------------------------------
:attr:`~._policy.MergeRule.IMMUTABLE` cannot pick a winner when the two
values genuinely differ — that is a domain contradiction, not a race. It
keeps the existing value and returns a :class:`MergeConflict` alongside,
so the caller learns about it. Silently keeping one would hide a real bug
in whatever wrote the second value.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ._errors import StoreError
from ._hlc import HLC
from ._policy import FieldPolicy, MergeRule

__all__ = ["MergeConflict", "MergeOutcome", "merge_field"]


@dataclass(frozen=True, slots=True)
class MergeConflict:
    """A difference the merge rule could not reconcile by itself."""

    field: str
    kept: Any
    rejected: Any
    reason: str

    def describe(self) -> str:
        return (
            f"{self.field}: kept {self.kept!r}, rejected {self.rejected!r} "
            f"({self.reason})"
        )


@dataclass(frozen=True, slots=True)
class MergeOutcome:
    """The result of merging one field.

    ``changed`` says whether the incoming value won. ``conflict`` is
    ``None`` when there was nothing to report — an ordinary loss under
    last-writer-wins is not a conflict, it is the rule working.
    """

    value: Any
    stamp: HLC
    changed: bool
    conflict: "MergeConflict | None" = None


def merge_field(
    field: str,
    policy: FieldPolicy,
    *,
    current: Any,
    current_stamp: "HLC | None",
    incoming: Any,
    incoming_stamp: HLC,
) -> MergeOutcome:
    """Merge one field's incoming value against the current one.

    ``current_stamp`` is ``None`` when the field has never been written —
    genuinely unknown, not "very old". Treating an absent stamp as the
    epoch would make an unwritten field lose to anything, including a
    write that arrived out of order and should not have won.
    """
    if current_stamp is None:
        # Nothing to merge against: the first value always lands, whatever
        # the rule. IMMUTABLE included — immutability starts once there IS
        # a value.
        return MergeOutcome(value=incoming, stamp=incoming_stamp, changed=True)

    rule = policy.merge

    if rule is MergeRule.IMMUTABLE:
        if current == incoming:
            return MergeOutcome(value=current, stamp=current_stamp, changed=False)
        return MergeOutcome(
            value=current,
            stamp=current_stamp,
            changed=False,
            conflict=MergeConflict(
                field=field,
                kept=current,
                rejected=incoming,
                reason=(
                    "field is IMMUTABLE but two different values were written; "
                    "the first is kept. Both remain in the oplog. This is a "
                    "domain contradiction, not a race — find what wrote the "
                    "second value"
                ),
            ),
        )

    if rule is MergeRule.LAST_WRITER_WINS:
        if incoming_stamp > current_stamp:
            return MergeOutcome(value=incoming, stamp=incoming_stamp, changed=True)
        return MergeOutcome(value=current, stamp=current_stamp, changed=False)

    if rule is MergeRule.MAX:
        if current is None:
            return MergeOutcome(value=incoming, stamp=incoming_stamp, changed=True)
        if incoming is None:
            return MergeOutcome(value=current, stamp=current_stamp, changed=False)
        try:
            wins = incoming > current
        except TypeError:
            raise StoreError(
                f"MergeRule.MAX cannot compare {incoming!r} with {current!r} "
                f"for field {field!r}: incompatible types "
                f"({type(incoming).__name__} vs {type(current).__name__}). "
                "A MAX field must hold one comparable type — check what wrote "
                "the odd value rather than loosening the rule."
            ) from None
        if wins:
            return MergeOutcome(value=incoming, stamp=incoming_stamp, changed=True)
        return MergeOutcome(value=current, stamp=current_stamp, changed=False)

    if rule is MergeRule.APPEND:
        merged, changed = _merge_append(field, current, incoming)
        return MergeOutcome(
            value=merged,
            stamp=max(current_stamp, incoming_stamp),
            changed=changed,
        )

    if rule is MergeRule.UNION:
        merged, changed = _merge_union(field, current, incoming)
        return MergeOutcome(
            value=merged,
            stamp=max(current_stamp, incoming_stamp),
            changed=changed,
        )

    raise StoreError(  # pragma: no cover - MergeRule is exhaustive above
        f"No merge implementation for rule {rule!r} on field {field!r}."
    )


def _merge_append(field: str, current: Any, incoming: Any) -> tuple[list[Any], bool]:
    """Element-keyed append: every element from both sides survives.

    Elements are mappings carrying an ``id``. Re-appending the same id is
    idempotent, which is what makes replay safe to repeat. Order is by
    first appearance, so a replica that saw the elements in a different
    order still renders the same list.
    """
    current_list = _as_list(field, current)
    incoming_list = _as_list(field, incoming)

    merged: list[Any] = list(current_list)
    seen = {_element_id(field, element) for element in current_list}
    changed = False
    for element in incoming_list:
        element_id = _element_id(field, element)
        if element_id not in seen:
            merged.append(element)
            seen.add(element_id)
            changed = True
    return merged, changed


def _merge_union(field: str, current: Any, incoming: Any) -> tuple[list[Any], bool]:
    """Set union, rendered as a sorted list so the result is canonical."""
    current_set = {_hashable(field, v) for v in _as_list(field, current)}
    incoming_set = {_hashable(field, v) for v in _as_list(field, incoming)}
    merged = current_set | incoming_set
    return sorted(merged, key=repr), merged != current_set


def _as_list(field: str, value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    raise StoreError(
        f"Field {field!r} uses a collection merge rule but holds "
        f"{type(value).__name__}. Store a JSON list — a scalar cannot be "
        "appended to or unioned."
    )


def _element_id(field: str, element: Any) -> Any:
    """The element's stable identity. Required, and never inferred.

    There is deliberately no fallback to position or a content hash. Both
    converge WRONGLY on edited or duplicated elements, and they do it
    quietly — an APPEND that tolerates id-less elements trades a loud
    failure here for a silent one later.

    The id must also be GLOBALLY unique, not merely unique locally. An
    autoincrement primary key is worse than no id at all: two hosts each
    appending a comment both mint ``id=8``, so replay treats two DIFFERENT
    elements as the same one and DROPS one of them. That is a lost write
    presenting as successful convergence, and every count still looks
    correct. Mint ids at creation (a random token, not a counter).
    """
    if isinstance(element, Mapping):
        if "id" not in element:
            raise StoreError(
                f"Field {field!r} uses MergeRule.APPEND, so every element "
                f"needs an 'id' key; got {element!r}.\n"
                "\n"
                "The id must be minted at creation and globally unique — a "
                "random token, NOT a per-store counter. An autoincrement key "
                "or a per-record sequence collides across hosts, and a "
                "collision under APPEND silently DROPS one of two distinct "
                "elements while every row count still looks right.\n"
                "\n"
                "Do not work around this by removing the id requirement: "
                "falling back to positional or content-hash identity "
                "converges wrongly on edited and duplicate elements, quietly."
            )
        return element["id"]
    return _hashable(field, element)


def _hashable(field: str, value: Any) -> Any:
    try:
        hash(value)
    except TypeError:
        raise StoreError(
            f"Field {field!r} uses MergeRule.UNION but contains the unhashable "
            f"element {value!r}. Union members must be scalars; use "
            "MergeRule.APPEND with 'id' keys for structured elements."
        ) from None
    return value

# EOF
