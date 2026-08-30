#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Field policy and schema — the layer with NO DEFAULTS, by design.

The rule
--------
**A field's policy has no default and cannot be inferred.** Declaring a
field without saying how it is typed, whether it is required, what part it
plays in the record, and how two concurrent values for it reconcile is an
error raised at SCHEMA CONSTRUCTION — not a silent choice made on the
caller's behalf, and not a surprise at write time.

Why it is worth the friction
----------------------------
A default merge rule is the dangerous one. Whatever we picked would be
right for some fields and quietly wrong for others: last-writer-wins on a
field that should never change (a creation stamp, an id) discards history
without a word, and immutability on a field that legitimately moves (a
status) makes every update after the first vanish. Neither failure raises
anything. Both are only visible as "the data is wrong" days later.

So there is nothing to fall back to, and :class:`FieldPolicy` has no
default arguments at all — every attribute is keyword-only and required.
:meth:`Schema.build` then re-checks the whole declaration and raises
:class:`~._errors.FieldPolicyError` naming every field that is missing a
policy, every policy that is missing a key, and the legal values. The
error is the feature.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Final, Mapping, Sequence

from ._errors import FieldPolicyError, SchemaError

__all__ = [
    "FieldKind",
    "FieldPolicy",
    "FieldRole",
    "MergeRule",
    "RESERVED_COLUMNS",
    "Schema",
    "WriterPolicy",
]


class FieldKind(str, Enum):
    """The stored value type, dialect-independent."""

    TEXT = "text"
    INTEGER = "integer"
    REAL = "real"
    BOOL = "bool"
    JSON = "json"
    BLOB = "blob"


class FieldRole(str, Enum):
    """What part the field plays in a record."""

    #: Part of the record's identity. Identity fields are immutable by
    #: construction — changing one makes a different record.
    IDENTITY = "identity"
    #: Ordinary payload.
    DATA = "data"
    #: The soft-delete marker. Nothing is ever deleted; this is how a row
    #: leaves the default view. At most one per schema.
    HIDE_FLAG = "hide_flag"


class MergeRule(str, Enum):
    """How two concurrent values for the same field reconcile.

    Chosen to cover what the first real consumer needs and nothing more:
    scalars, identity, monotone stamps, append-only collections and sets.
    No general CRDT machinery — scitex-cards explicitly does not need
    field-level CRDTs, and shipping them would be complexity nobody asked
    for.

    Every rule here is deterministic and order-independent, so two
    replicas applying the same ops in any interleaving converge. None of
    them discards a value irrecoverably: the losing version stays in the
    append-only log, so a rule decides what is PRESENTED, not what exists.
    """

    #: Higher hybrid-logical timestamp wins. The total order in
    #: :class:`~._hlc.HLC` makes this deterministic across replicas.
    LAST_WRITER_WINS = "last_writer_wins"
    #: First value wins forever. A later, DIFFERENT value is reported as a
    #: conflict rather than dropped — the caller decides what it means.
    IMMUTABLE = "immutable"
    #: The greater value wins regardless of timestamp. For monotone
    #: quantities (``last_activity``, high-water marks) where a late-
    #: arriving older write must not drag the value backwards.
    MAX = "max"
    #: Element-keyed append. Concurrent appends from different nodes all
    #: survive; re-appending the same element id is idempotent. For
    #: comments, notifications, messages.
    APPEND = "append"
    #: Set union. For edges and role assignments.
    UNION = "union"


class WriterPolicy(str, Enum):
    """Whether a store enforces one owner per record.

    Two modes, because one invariant does not fit both consumers.

    ``SINGLE_WRITER`` is the stronger guarantee: exactly one writer may
    append ops for a record, so concurrent divergence cannot arise in the
    first place and merges are trivial. Right for stores whose records
    have a genuine, stable owner — a host writing its own telemetry, a
    runner owning its own job rows.

    ``MULTI_WRITER`` is right where ownership is a mutable domain field
    that non-owners legitimately change. The fleet's card store is the
    worked example: ``reassign_task`` rewrites the owner field from
    another agent, any agent may comment on any card, and the operator
    resolves blocked cards from a different host than the assignee. Under
    ``SINGLE_WRITER`` the operator's first resolve-from-elsewhere would be
    an illegal write.

    Replay correctness does NOT depend on which mode is chosen — sequence
    numbers are keyed by ORIGIN (the node that accepted the write), never
    by record ownership. The mode only decides whether an ownership check
    runs on the local write path.
    """

    SINGLE_WRITER = "single_writer"
    MULTI_WRITER = "multi_writer"


#: Column names the store owns. A schema that declares one of these is
#: rejected: the primitive would otherwise overwrite the caller's column
#: with replication bookkeeping and neither side would notice.
RESERVED_COLUMNS: Final[frozenset[str]] = frozenset(
    {
        "_record",
        "_owner",
        "_origin",
        "_seq",
        "_revision",
        "_hlc",
        "_hidden",
        "_field_hlc",
    }
)

_POLICY_KEYS: Final[tuple[str, ...]] = ("kind", "role", "required", "merge", "indexed")

#: Kinds for which "greater" is well defined, so MergeRule.MAX is meaningful.
_ORDERABLE_KINDS: Final[frozenset[FieldKind]] = frozenset(
    {FieldKind.INTEGER, FieldKind.REAL, FieldKind.TEXT}
)

#: Rules that merge a collection rather than replace a scalar.
_COLLECTION_RULES: Final[frozenset[MergeRule]] = frozenset(
    {MergeRule.APPEND, MergeRule.UNION}
)


@dataclass(frozen=True, kw_only=True, slots=True)
class FieldPolicy:
    """How one field is typed, required, roled and reconciled.

    Every attribute is keyword-only and has **no default**. Omitting one is
    a ``TypeError`` from the constructor; building a policy from a mapping
    that omits one is a :class:`~._errors.FieldPolicyError` naming it.
    """

    kind: FieldKind
    role: FieldRole
    required: bool
    merge: MergeRule
    indexed: bool

    def __post_init__(self) -> None:
        if self.role is FieldRole.IDENTITY and self.merge is not MergeRule.IMMUTABLE:
            raise FieldPolicyError(
                f"An IDENTITY field must use merge=MergeRule.IMMUTABLE, got "
                f"{self.merge.value!r}. Identity values cannot be merged: "
                "changing one does not update the record, it names a "
                "different record."
            )
        if self.role is FieldRole.IDENTITY and not self.required:
            raise FieldPolicyError(
                "An IDENTITY field must have required=True. A NULL identity "
                "component makes the record key ambiguous."
            )
        if self.role is FieldRole.HIDE_FLAG:
            if self.kind is not FieldKind.BOOL:
                raise FieldPolicyError(
                    f"A HIDE_FLAG field must use kind=FieldKind.BOOL, got "
                    f"{self.kind.value!r}."
                )
            if self.merge is not MergeRule.LAST_WRITER_WINS:
                raise FieldPolicyError(
                    "A HIDE_FLAG field must use "
                    "merge=MergeRule.LAST_WRITER_WINS — hiding and unhiding "
                    "are ordinary state changes and must be able to follow "
                    "each other. MergeRule.MAX in particular would make a "
                    "hide permanent, turning the soft delete into the hard "
                    "one this store exists to prevent."
                )
        if self.merge is MergeRule.MAX and self.kind not in _ORDERABLE_KINDS:
            raise FieldPolicyError(
                f"merge=MergeRule.MAX needs an orderable kind "
                f"{sorted(k.value for k in _ORDERABLE_KINDS)}, got "
                f"{self.kind.value!r}. 'Greater' is undefined for it, so the "
                "merge could not be deterministic."
            )
        if self.merge in _COLLECTION_RULES and self.kind is not FieldKind.JSON:
            raise FieldPolicyError(
                f"merge={self.merge.value!r} operates on a collection and "
                f"needs kind=FieldKind.JSON, got {self.kind.value!r}. A "
                "scalar column cannot hold the merged result."
            )

    @classmethod
    def from_mapping(cls, name: str, mapping: Mapping[str, Any]) -> "FieldPolicy":
        """Build a policy from a plain mapping (YAML / JSON config).

        Raises :class:`~._errors.FieldPolicyError` listing EVERY missing or
        unknown key at once, rather than one per round trip.
        """
        if not isinstance(mapping, Mapping):
            raise FieldPolicyError(
                f"Policy for field {name!r} must be a mapping with keys "
                f"{list(_POLICY_KEYS)}, got {type(mapping).__name__}."
            )

        missing = [key for key in _POLICY_KEYS if key not in mapping]
        unknown = [key for key in mapping if key not in _POLICY_KEYS]
        problems: list[str] = []
        if missing:
            problems.append(f"missing key(s) {missing}")
        if unknown:
            problems.append(f"unknown key(s) {unknown}")
        if problems:
            raise FieldPolicyError(
                f"Policy for field {name!r} is incomplete: "
                + "; ".join(problems)
                + f". Every field needs all of {list(_POLICY_KEYS)} stated "
                "explicitly — there is no default policy, because a wrong "
                "default merge rule loses data silently. Legal values: "
                f"kind={[k.value for k in FieldKind]}, "
                f"role={[r.value for r in FieldRole]}, "
                f"merge={[m.value for m in MergeRule]}, "
                "required/indexed=true|false."
            )

        def _enum(enum_cls: type[Enum], key: str) -> Any:
            raw = mapping[key]
            try:
                return enum_cls(raw)
            except ValueError:
                raise FieldPolicyError(
                    f"Policy for field {name!r} has {key}={raw!r}, which is "
                    f"not one of {[e.value for e in enum_cls]}."
                ) from None

        def _bool(key: str) -> bool:
            raw = mapping[key]
            if not isinstance(raw, bool):
                raise FieldPolicyError(
                    f"Policy for field {name!r} has {key}={raw!r}; it must be "
                    "a real boolean, not a truthy value. An accidental "
                    '"false" string would read as True.'
                )
            return raw

        return cls(
            kind=_enum(FieldKind, "kind"),
            role=_enum(FieldRole, "role"),
            required=_bool("required"),
            merge=_enum(MergeRule, "merge"),
            indexed=_bool("indexed"),
        )


@dataclass(frozen=True, slots=True)
class Schema:
    """A validated table declaration: name plus one policy per field."""

    name: str
    fields: Mapping[str, FieldPolicy]
    #: Fields a full-text query searches, as ONE declaration. The store
    #: builds its text index from this list and the query compiler builds
    #: its match expression from the same list, so the two cannot drift —
    #: an expression index that differs from its query by one character is
    #: never used, the planner says nothing, and the only symptom is that
    #: search got slow. Empty means this schema is not full-text searchable
    #: and asking it to be is an error rather than an empty result.
    text_search: tuple[str, ...] = ()
    #: The text-search dictionary those fields are analysed with. ``english``
    #: stems and drops stopwords; ``simple`` does neither and is the closer
    #: match for identifiers, part numbers and code.
    text_config: str = "english"

    @classmethod
    def build(
        cls,
        name: str,
        fields: Mapping[str, Any],
        *,
        declared_columns: "list[str] | None" = None,
        text_search: "Sequence[str] | None" = None,
        text_config: str = "english",
    ) -> "Schema":
        """Validate and construct.

        ``fields`` maps a column name to either a :class:`FieldPolicy` or a
        mapping accepted by :meth:`FieldPolicy.from_mapping`.

        ``declared_columns`` is the caller's own list of columns it intends
        to write, when it has one. Any column in that list with no policy
        is reported here — the whole point of the exercise, since that is
        the case a per-field constructor cannot catch.

        ``text_search`` names the fields a full-text query searches. It is
        declared here, once, rather than passed at each call site, because
        the store's text index and the query's match expression are both
        generated from it and must be character-identical to each other.
        Only TEXT and JSON fields qualify: a number has no words in it, and
        casting one to text so it could be searched would make ``2020``
        match a subject count as readily as a year.
        """
        if not name or not name.isidentifier():
            raise SchemaError(
                f"Schema name {name!r} must be a valid identifier — it "
                "becomes a table name prefix and is not quoted defensively "
                "in every dialect."
            )
        if not fields:
            raise SchemaError(
                f"Schema {name!r} declares no fields. An empty schema cannot "
                "identify a record."
            )

        reserved_used = sorted(set(fields) & RESERVED_COLUMNS)
        if reserved_used:
            raise SchemaError(
                f"Schema {name!r} declares reserved column(s) {reserved_used}. "
                f"The store owns {sorted(RESERVED_COLUMNS)} for replication "
                "bookkeeping; rename your field."
            )

        if declared_columns is not None:
            unpoliced = [col for col in declared_columns if col not in fields]
            if unpoliced:
                raise FieldPolicyError(
                    f"Schema {name!r}: column(s) {unpoliced} are declared but "
                    "have no FieldPolicy. There is no default policy to apply "
                    "— state kind/role/required/merge/indexed for each, or "
                    "drop the column from declared_columns."
                )

        resolved: dict[str, FieldPolicy] = {}
        for field_name, policy in fields.items():
            if not field_name or not field_name.isidentifier():
                raise SchemaError(
                    f"Schema {name!r}: field name {field_name!r} must be a "
                    "valid identifier."
                )
            if isinstance(policy, FieldPolicy):
                resolved[field_name] = policy
            elif policy is None:
                raise FieldPolicyError(
                    f"Schema {name!r}: field {field_name!r} has policy None. "
                    "A missing policy is never filled in with a default — "
                    "state kind/role/required/merge/indexed explicitly."
                )
            else:
                resolved[field_name] = FieldPolicy.from_mapping(field_name, policy)

        identity = [n for n, p in resolved.items() if p.role is FieldRole.IDENTITY]
        if not identity:
            raise SchemaError(
                f"Schema {name!r} has no IDENTITY field. Without one there is "
                "no record key, so single-writer-per-record ownership and "
                "oplog replay have nothing to attach to."
            )

        hide_flags = [n for n, p in resolved.items() if p.role is FieldRole.HIDE_FLAG]
        if len(hide_flags) > 1:
            raise SchemaError(
                f"Schema {name!r} declares {len(hide_flags)} HIDE_FLAG fields "
                f"{hide_flags}; exactly one (or none) is allowed — two "
                "soft-delete markers cannot both define the default view."
            )

        searchable = tuple(text_search or ())
        unknown_search = [n for n in searchable if n not in resolved]
        if unknown_search:
            raise SchemaError(
                f"Schema {name!r}: text_search names {unknown_search}, which "
                f"the schema does not declare. Known fields: "
                f"{sorted(resolved)}."
            )
        wrong_kind = [
            n
            for n in searchable
            if resolved[n].kind not in (FieldKind.TEXT, FieldKind.JSON)
        ]
        if wrong_kind:
            raise SchemaError(
                f"Schema {name!r}: text_search names {wrong_kind}, which are "
                "neither TEXT nor JSON. Full-text search analyses words; a "
                "number, a boolean or a blob has none, and casting one to "
                "text to make it searchable turns every digit into a term."
            )
        if not text_config or not text_config.isidentifier():
            raise SchemaError(
                f"Schema {name!r}: text_config {text_config!r} must be a "
                "valid identifier — it names a PostgreSQL text-search "
                "configuration and is embedded in an index expression. "
                "'english' and 'simple' are the usual two."
            )

        return cls(
            name=name,
            fields=dict(resolved),
            text_search=searchable,
            text_config=text_config,
        )

    # -- derived views ----------------------------------------------------
    @property
    def identity_fields(self) -> tuple[str, ...]:
        """Identity columns, in declaration order. This is the record key."""
        return tuple(
            n for n, p in self.fields.items() if p.role is FieldRole.IDENTITY
        )

    @property
    def hide_flag_field(self) -> "str | None":
        """The soft-delete column, or ``None`` if the schema has none."""
        for n, p in self.fields.items():
            if p.role is FieldRole.HIDE_FLAG:
                return n
        return None

    @property
    def data_fields(self) -> tuple[str, ...]:
        """Non-identity columns, in declaration order."""
        return tuple(
            n for n, p in self.fields.items() if p.role is not FieldRole.IDENTITY
        )

    @property
    def indexed_fields(self) -> tuple[str, ...]:
        """Columns asking for a secondary index."""
        return tuple(n for n, p in self.fields.items() if p.indexed)

    def policy(self, field: str) -> FieldPolicy:
        """The policy for ``field``, or a pointed error naming the schema."""
        try:
            return self.fields[field]
        except KeyError:
            raise FieldPolicyError(
                f"Schema {self.name!r} has no field {field!r}. Known fields: "
                f"{sorted(self.fields)}. A value cannot be written without a "
                "policy — add the field to the schema rather than writing it "
                "untyped."
            ) from None

# EOF
