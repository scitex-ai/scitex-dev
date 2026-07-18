#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ecosystem `update-branch-protection` (+ deprecated `set-branch-protection`
alias) / `unset-branch-protection`.

Split from the former flat `_branch_protection.py` module (2026-07-11,
CLI-standardization audit pass) — one command per file, mirroring the
`_audit_per_target/` package split from PR #320. This `__init__.py` is
the thin orchestrator; `ecosystem/_registry.py`'s
``from ._cmds import (..., _branch_protection, ...)`` +
``_branch_protection.register(ecosystem)`` call site is unchanged since
a package's ``__init__.py`` satisfies the same import shape as the
former module.

The shared non-CLI internals (`_gh_api`, `_resolve_owner_repo`,
`_apply_one`, `_deletion_only_body`, `_all_distributions`, ...) live in
`_helpers.py`, kept as ONE module so the behavioural test suite's real
injection-seam pattern (direct attribute assignment on `_helpers`, no
mocks) keeps working — see `_helpers.py`'s docstring for why.
"""

from . import _helpers
from ._unset_cmd import register as _register_unset
from ._update_cmd import register as _register_update


def register(ecosystem):
    _register_update(ecosystem)
    _register_unset(ecosystem)


__all__ = ["register", "_helpers"]
