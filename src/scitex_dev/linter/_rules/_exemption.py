"""STX-EX001 — a malformed or unsupported file-level exemption pragma.

The file-level pragma (parsed by ``linter/_exemptions.py``) lets a file opt
out of named rules for an auditable, written-down reason::

    # stx-allow-file: STX-S001, STX-S005  (reason: measures the clew store; a session would record itself into it)

Its canonical use is instrumentation/measurement scripts, which must NOT
be ``@stx.session`` scripts (they would record themselves into the very
store they measure), and which previously had only ``library_dirs`` as an
escape — a silent, directory-wide exemption nobody reviews.

An exemption that cannot be audited is no exemption: STX-EX001 fires, and
the pragma is NOT honoured, when it names no rule, omits a non-empty
``(reason: ...)``, names an unknown rule id, names a rule that forbids
suppression (the ``testing`` category — no-mocks / test-quality), or sits
outside the module header.
"""

from ._base import Rule

EX001 = Rule(
    id="STX-EX001",
    severity="error",
    category="exemption",
    message="Invalid file-level `stx-allow-file` exemption — it is NOT applied",
    suggestion=(
        "Write the pragma in the module header (top comments or the module\n"
        "docstring), naming the rule ids AND a reason:\n"
        "  # stx-allow-file: STX-S001  (reason: instrumentation — a session would record itself)\n"
        "Rules:\n"
        "  - at least one STX-<ID>; every id must be a registered rule\n"
        "  - `(reason: <non-empty text>)` is mandatory\n"
        "  - `testing` rules (STX-NM*, STX-TQ*) cannot be exempted\n"
        "  - it must appear before the first statement after the docstring\n"
        "Exemptions are listed in every `scitex-dev linter validate-files` run\n"
        "(text: 'File-level exemptions' block; JSON: `_meta.exemptions`)."
    ),
)

__all__ = ["EX001"]
