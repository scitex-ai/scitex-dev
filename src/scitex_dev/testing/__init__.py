"""Pytest helpers for downstream SciTeX packages.

Public re-exports:

- `audit_all_for_package` — assert `audit-all <pkg>` exits 0.
- `classify_audit_outcome` — grade a run PASS / FAIL / UNKNOWN.

`classify_audit_outcome` is public because "the audit could not run" is a
verdict other tooling needs to be able to ASK FOR, not a private detail of
one assertion's wording.

Each ecosystem package drops a one-liner test that calls this helper
so the package's local pytest run includes the same audit gates that
CI used to run as a separate workflow. See the auto-generated
`tests/test_audit.py` template (via
`scitex-dev ecosystem write-audit-test <pkg>`) and the skill leaf
`_skills/general/02_package/07_github-actions.md` for the canonical
shape.
"""

from __future__ import annotations

from ._audit_conformance import audit_all_for_package
from ._audit_outcome import (
    VERDICT_FAIL,
    VERDICT_PASS,
    VERDICT_UNKNOWN,
    classify_audit_outcome,
    could_not_run_evidence,
)
from ._import_vantage import (
    DEFAULT_ENV_VAR,
    ForeignImportError,
    PackageNotImportableError,
    assert_imports_tree_under_test,
    assert_path_inside_tree,
    make_pytest_configure,
    resolve_package_path,
)

__all__ = [
    "DEFAULT_ENV_VAR",
    "VERDICT_FAIL",
    "VERDICT_PASS",
    "VERDICT_UNKNOWN",
    "ForeignImportError",
    "PackageNotImportableError",
    "assert_imports_tree_under_test",
    "assert_path_inside_tree",
    "audit_all_for_package",
    "classify_audit_outcome",
    "could_not_run_evidence",
    "make_pytest_configure",
    "resolve_package_path",
]
