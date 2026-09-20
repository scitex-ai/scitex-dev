#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: scitex_dev/_core/_test_execution_plugin.py

"""Auto-loaded pytest guard enforcing a package's test-execution recipe.

Registered as a ``pytest11`` plugin (see pyproject) so it loads automatically
in ANY environment where scitex-dev is installed — no per-package conftest
wiring. At collection start it discovers the recipe governing the checkout
under test (``discover_recipe``) and, if that recipe mandates remote execution
while we are running locally, aborts with an actionable ``UsageError``.

Stays INERT by default: the default mode is ``local`` and a package with no
recipe resolves to that default, so scitex-dev's own CI (and every other
package that has not opted in) is never affected. When the sanctioned remote
sets the recipe's marker env var, the guard also allows the run.
"""

from __future__ import annotations

from .test_execution import discover_recipe, guard_message


def pytest_configure(config) -> None:
    """Fail-fast if this checkout mandates remote tests and we're running local."""
    # `pytest` is declared in the `[all]` extra rather than in core, so this
    # import is guarded: the hook can only run under pytest, but a failure
    # here should still name the extra that provides it instead of raising a
    # bare ModuleNotFoundError (PS-233).
    try:
        import pytest
    except ImportError as e:  # pragma: no cover - pytest invokes this hook
        raise ImportError(
            "pytest is required by the scitex-dev test-execution plugin; "
            "install with: pip install 'scitex-dev[all]'"
        ) from e

    recipe = discover_recipe()
    message = guard_message(recipe)
    if message is not None:
        raise pytest.UsageError(message)


# EOF
