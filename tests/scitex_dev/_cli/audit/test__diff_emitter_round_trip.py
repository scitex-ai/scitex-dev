#!/usr/bin/env python3
# Timestamp: 2026-07-30
# File: tests/scitex_dev/_cli/audit/test__diff_emitter_round_trip.py

"""Which emitted finding shapes can the violation-key extractor actually read?

FIVE emitters render findings; `_diff._FINDING_RE` reads them. Nobody had
measured which of the five round-trip, so the answer lived only in incident
reports. Read from the code 2026-07-30:

    _django/_audit.py:307       [{sev}] [{rule} {sec}{slug}] {where}: {detail}
    _project/_violation.py:32   [{sev}] [{rule} {sec}{slug}] {where}: {detail}
    _skills/_violation.py:25            [{rule} {sec}{slug}] {where}: {detail}
    _api/_checks/_model.py:152           [{rule} {sec}{slug}] {where}: {detail}
    _summary/_run.py:198                 [{rule}] {command}: {message}

THREE distinct formats from five emitters, and the extractor expects a
fourth thing: `LEVEL: [TAG] <bare-dist>: msg`. That mismatch is the root
under the P0 in which a required gate printed errors and exited 0, under
`--new-only`'s blindness to section-format findings, and under the
`not-auditable` miscount — three incidents, one cause.

THIS TEST IS A CHARACTERIZATION TEST, NOT AN ASSERTION THAT THE CURRENT
BEHAVIOUR IS CORRECT. It pins WHICH shapes key today so that unifying the
emitters (the actual fix) fails loudly here and tells the author to update
it, rather than silently changing coverage underneath the diff. The last
tripwire of this kind on this codebase fired exactly as intended and
caught a real coverage change; that is why the shape is worth repeating.

If you are here because this test failed after an emitter change: good.
Re-measure which shapes round-trip, update the expectations, and check
that `_audit_all_new_only.unparsed_finding_lines` still catches whatever
remains unkeyable.
"""

import pytest

from scitex_dev._cli.audit._diff import extract_violation_keys

# One real line per emitter format, level-prefixed as the auditors emit
# them. Values are representative, not invented: `where` is a path and
# `command` is a subcommand path, because that is what those fields hold.
_DOUBLE_BRACKET = (
    "ERRO:   [E] [PS-221 §3 public-extra-not-closed-under-all] "
    "/tree/pyproject.toml: requirement `pytest>=7.0` in PUBLIC extra"
)
_SINGLE_BRACKET_PATH = (
    "ERRO:   [PS-202 §2 src-tests-mirror-dir-missing] "
    "/tree/src/scitex_dev/_cli: no matching tests/scitex_dev/_cli/"
)
_SUMMARY_COMMAND = (
    "WARN:   [§12] scitex-dev ecosystem gui: `gui` group is missing "
    "required verb(s) serve, status, stop"
)
_BARE_DIST = (
    "ERRO:   [PA-306 §3 no-mocks] scitex-dev: tests/x.py:43: monkeypatch"
)


@pytest.mark.parametrize(
    "shape, emitters",
    [
        (_DOUBLE_BRACKET, "_django/_audit.py, _project/_violation.py"),
        (_SINGLE_BRACKET_PATH, "_skills/_violation.py, _api/_checks/_model.py"),
        (_SUMMARY_COMMAND, "_summary/_run.py"),
    ],
)
def test_these_emitted_shapes_do_not_round_trip_today(shape, emitters):
    """PINNED GAP — these produce NO structured key. See module docstring.

    The subject after the rule tag is a PATH or a COMMAND PATH, while the
    extractor expects a single distribution token. Three of the three
    non-trivial emitter formats fail for the same reason.
    """
    # Arrange
    text = shape
    # Act
    keys = extract_violation_keys(text)
    # Assert — UNPARSED-keyed (fail-open, 0.40.2) but never structured.
    assert all(k.rule == "UNPARSED" for k in keys), emitters


def test_the_bare_distribution_shape_does_round_trip():
    """The one shape the extractor was written for. Positive control.

    Without this, "everything is UNPARSED" would be indistinguishable
    from an extractor that had stopped working altogether.
    """
    # Arrange
    text = _BARE_DIST
    # Act
    keys = extract_violation_keys(text)
    # Assert
    assert any(k.rule != "UNPARSED" for k in keys)


def test_no_emitted_error_shape_is_silently_dropped():
    """Whatever the format, an ERRO must produce SOME key (0.40.2).

    This is the invariant that survives emitter unification: the shapes
    above may start round-tripping, but none of them may ever go back to
    contributing nothing to the diff.
    """
    # Arrange
    text = "\n".join([_DOUBLE_BRACKET, _SINGLE_BRACKET_PATH, _BARE_DIST])
    # Act
    keys = extract_violation_keys(text)
    # Assert
    assert len(keys) == 3
