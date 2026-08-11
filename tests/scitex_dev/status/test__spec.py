#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The Python is DERIVED from ``spec/``. These tests prove it stayed derived.

``spec/`` is language-independent and normative; Python, TypeScript, Rust and
shell all read it. A Python table that has quietly drifted from the spec is
worse than no spec at all, because everyone downstream believes there is one
source of truth and there are two.

So these are not "does the code work" tests. They are "does the code still
agree with its own source of truth" tests, and they are the reason the
sentence "when the spec and an implementation disagree, the spec is right" is
a fact rather than a slogan.
"""

from __future__ import annotations

from scitex_dev.status import (
    KIND_DNS,
    KIND_ERRNO,
    KIND_GRPC,
    KIND_HTTP,
    KIND_PROCESS,
    KIND_SCITEX,
    RESERVED_PROCESS_CODES,
    SPEC_VERSION,
    kinds,
    load_boundaries,
    load_kinds,
    load_schema,
    load_scitex_codes,
)

_CONSTANTS = {KIND_HTTP, KIND_PROCESS, KIND_GRPC, KIND_DNS, KIND_ERRNO, KIND_SCITEX}


def _registry():
    """The kind names the spec declares."""
    return {entry["kind"] for entry in load_kinds()["kinds"]}


# -- the kind registry --------------------------------------------------------


def test_the_python_kind_constants_match_the_spec_registry():
    """A constant with no spec entry is a kind nobody else can read."""
    # Arrange
    declared = _registry()
    # Act
    exposed = _CONSTANTS
    # Assert
    assert exposed == declared


def test_the_kinds_function_reports_the_spec_registry():
    """`kinds()` is how a caller discovers the set; it must not be hand-typed."""
    # Arrange
    declared = _registry()
    # Act
    reported = set(kinds())
    # Assert
    assert reported == declared


def test_the_spec_declares_the_expected_six_kinds():
    """Pinned so that ADDING a kind is a deliberate, reviewed act."""
    # Arrange
    expected = {"http", "process", "grpc", "dns", "errno", "scitex"}
    # Act
    declared = _registry()
    # Assert
    assert declared == expected


# -- versions -----------------------------------------------------------------


def test_the_kind_registry_declares_the_implemented_spec_version():
    """A reader that meets another version must refuse, so it must know ours."""
    # Arrange
    document = load_kinds()
    # Act
    version = document["spec_version"]
    # Assert
    assert version == SPEC_VERSION


def test_the_scitex_code_list_declares_the_implemented_spec_version():
    """Two spec files at different versions is a split source of truth."""
    # Arrange
    document = load_scitex_codes()
    # Act
    version = document["spec_version"]
    # Assert
    assert version == SPEC_VERSION


def test_the_boundary_registry_declares_the_implemented_spec_version():
    """Same rule, third file."""
    # Arrange
    document = load_boundaries()
    # Act
    version = document["spec_version"]
    # Assert
    assert version == SPEC_VERSION


# -- the JSON schema agrees with the YAML -------------------------------------


def test_the_status_code_schema_enumerates_the_spec_kinds():
    """A JSON consumer and a Python consumer must accept the same values."""
    # Arrange
    schema = load_schema("status-code.schema.json")
    # Act
    enumerated = set(schema["properties"]["kind"]["enum"])
    # Assert
    assert enumerated == _registry()


def test_the_status_code_schema_forbids_a_stored_ok_field():
    """`ok` is derived. Two fields that can disagree eventually will."""
    # Arrange
    schema = load_schema("status-code.schema.json")
    # Act
    rule = schema["properties"]["ok"]["not"]
    # Assert
    assert rule == {}


def test_the_status_code_schema_forbids_a_stored_retryable_field():
    """Readable from the code within its kind; `message` says the useful part."""
    # Arrange
    schema = load_schema("status-code.schema.json")
    # Act
    rule = schema["properties"]["retryable"]["not"]
    # Assert
    assert rule == {}


def test_the_exchange_record_schema_enumerates_the_spec_kinds():
    """The ledger stores a StatusCode, so it must accept the same kinds."""
    # Arrange
    schema = load_schema("exchange-record.schema.json")
    # Act
    enumerated = set(schema["properties"]["kind"]["enum"])
    # Assert
    assert enumerated == _registry()


# -- boundaries ---------------------------------------------------------------


def test_every_declared_boundary_borrows_a_registered_kind():
    """A boundary borrowing an unregistered kind is unreadable to its peer."""
    # Arrange
    borrowed = {entry["borrows"] for entry in load_boundaries()["boundaries"]}
    # Act
    unknown = borrowed - _registry()
    # Assert
    assert unknown == set()


def test_every_boundary_scitex_code_is_in_the_closed_enumeration():
    """A boundary cannot declare a scitex code the validator would refuse."""
    # Arrange
    declared = {entry["code"] for entry in load_scitex_codes()["codes"]}
    # Act
    used = {
        code
        for entry in load_boundaries()["boundaries"]
        for code in entry.get("codes", ())
    }
    # Assert
    assert used <= declared


def test_the_scitex_enumeration_stays_short():
    """A long list means the canonical vocabulary ADR-0007 rejected regrew."""
    # Arrange
    limit = 5
    # Act
    count = len(load_scitex_codes()["codes"])
    # Assert
    assert count <= limit


# -- reserved codes -----------------------------------------------------------


def test_the_reserved_process_codes_match_the_spec():
    """1 and 2 are reserved so a missing verb cannot impersonate a value."""
    # Arrange
    reserved = load_kinds()["reserved"]
    declared = next(e["codes"] for e in reserved if e["kind"] == "process")
    # Act
    exposed = list(RESERVED_PROCESS_CODES)
    # Assert
    assert exposed == declared


# -- the message rules are spec-sourced ---------------------------------------


def test_the_forbidden_marker_list_comes_from_the_spec():
    """The M1 word list is normative, so it lives in the spec, not in code."""
    # Arrange
    rules = load_kinds()["message"]["no_inferred_cause"]
    # Act
    markers = rules["forbidden_markers"]
    # Assert
    assert "therefore" in markers


def test_the_observation_word_because_is_not_forbidden():
    """M1 bans CONCLUDING a cause, not REPORTING one you observed."""
    # Arrange
    rules = load_kinds()["message"]["no_inferred_cause"]
    # Act
    markers = rules["forbidden_markers"]
    # Assert
    assert "because" not in markers


def test_the_http_kind_requires_a_probe_for_an_accepted_202():
    """M2's trigger list is spec-sourced, not hard-coded in the validator."""
    # Arrange
    http = next(e for e in load_kinds()["kinds"] if e["kind"] == "http")
    # Act
    triggers = http["requires_probe"]
    # Assert
    assert 202 in triggers


# EOF
