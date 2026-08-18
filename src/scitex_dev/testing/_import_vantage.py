#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Refuse to grade a tree we are not importing.

A green is a CLAIM ABOUT THE CODE THAT PRODUCED IT. If ``figrecipe``
resolves to site-packages while you are testing a worktree, the run cannot
make that claim — so it must refuse rather than emit a number about
somewhere else.

WHY THIS IS A CHECK AND NOT A PARAGRAPH IN A CONTRIBUTING GUIDE
----------------------------------------------------------------
Four instances in ONE DAY, 2026-08-18, and three of them hit people who had
already read or written the warning:

* ``audit-all`` resolves its sub-auditors from ``PATH``. A 0.53.0 entry
  point ran 0.50.0 checks and produced output BYTE-IDENTICAL to 0.50.0.
  Read at face value: "the rule corpus made no difference." It came within
  one message of being reported as a refuted measurement.
* ``audit-cli --path <tree>`` IMPORTS the CLI, so it graded site-packages
  rather than the tree it was pointed at. That invalidated a set of counts
  already quoted as properties of a branch.
* scitex-dev ran their own suite from a worktree: 1049 PASSED against
  site-packages instead of the code they had just edited. Only three
  UNRELATED failures revealed the wrong vantage point — a no-op change
  would have reported a clean green about code the run never touched.
* figrecipe: ``pytest tests/figrecipe/_cli/`` from a worktree returned
  ``4 passed`` while importing the installed 0.34.6. CI, which puts the
  checkout on the path, failed on the first run — on a capability
  regression the local green had hidden.

In every case the wrong answer was WELL-FORMED, SELF-CONSISTENT and
CONFIDENT. Nothing warns, because from inside the process there is nothing
anomalous about importing an installed package.

Knowing about it demonstrably did not prevent it. Discipline had a fair
trial that day and lost twice. Hence a mechanical barrier.

BIASED TOWARDS ACCEPTING, ON PURPOSE
-------------------------------------
A FALSE NEGATIVE costs one bad green. A FALSE POSITIVE costs the guard
itself: a check that refuses a legitimate CI setup gets switched off, and a
guard everyone disables is worse than none. So this accepts ANY resolution
inside the tree — editable installs, ``--target`` layouts, linked worktrees
— and refuses only what is PROVABLY outside it.

That is also why both sides are ``resolve()``d before comparing. This
environment is full of symlinks: a linked git worktree, an editable install
pointing at a ``src/`` that is itself a link, a venv whose ``python`` is a
symlink chain. Comparing unresolved paths as strings gets legitimate setups
wrong in both directions.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

#: The documented, shared opt-out. One name people learn once. A leaf that
#: needs its own scope passes ``env_var=`` rather than forking this module.
DEFAULT_ENV_VAR = "SCITEX_ALLOW_FOREIGN_IMPORT"


class ForeignImportError(RuntimeError):
    """The package under test resolves outside the tree under test."""


class PackageNotImportableError(ForeignImportError):
    """The package under test could not be imported at all.

    A SUBCLASS so every existing ``except ForeignImportError`` keeps
    working: a caller that wants "the guard refused" does not have to learn
    a second name, and a caller that wants to distinguish "wrong tree" from
    "no package" now can.
    """


def resolve_package_path(
    package: str, *, tree_under_test: str | os.PathLike[str] | None = None
) -> Path:
    """Where ``package`` actually resolves, fully resolved.

    Split out from the assertion so the CONTAINMENT DECISION below is a
    pure function of two paths. That is not tidiness: the subtle half of
    this guard is the symlink handling, and separating the two lets it be
    tested against real directories and real links rather than against a
    stand-in for the import system.

    ``tree_under_test`` appears ONLY in the failure message. A bare
    ``ModuleNotFoundError`` is loud and honest, so it was never a defect —
    but it says neither WHICH TREE was being checked nor THAT A GUARD WAS
    RUNNING, and naming what it looked at is this module's entire value.
    A guard whose own failure does not identify itself reproduces, one
    level up, the family it exists to catch.

    The original exception is CHAINED, never replaced: the import error is
    the actual diagnosis (a typo, a missing install, a broken dependency),
    and this only adds the context it lacks.
    """
    try:
        module = importlib.import_module(package)
    except ImportError as exc:
        checked = (
            f"  tree under test : {Path(tree_under_test).resolve()}\n"
            if tree_under_test is not None
            else ""
        )
        raise PackageNotImportableError(
            f"the import-vantage guard could not import {package!r}, so it "
            f"cannot tell which tree the tests would grade.\n"
            f"{checked}"
            f"  import error    : {exc}\n"
            f"This is the guard speaking, not the test suite: nothing has "
            f"been graded. Install the package (`pip install -e <tree>`) or "
            f"put it on the path, then re-run."
        ) from exc
    location = getattr(module, "__file__", None)
    if location is None:
        # A namespace package has no __file__. Use its first path entry
        # rather than returning None: "cannot tell" must not become "fine",
        # which is the exact collapse this module exists to prevent. An
        # empty __path__ is a broken install and surfaces as the IndexError
        # it is.
        location = list(module.__path__)[0]
    return Path(location).resolve()


def assert_path_inside_tree(
    package: str,
    package_path: str | os.PathLike[str],
    root: str | os.PathLike[str],
    *,
    env_var: str = DEFAULT_ENV_VAR,
    stream=None,
) -> Path:
    """Raise unless ``package_path`` is inside ``root``. Both are resolved.

    Args:
        package: the importable name, used only in the message.
        package_path: where the package was found.
        root: the tree the caller believes it is grading.
        env_var: the opt-out variable. Defaults to the shared
            :data:`DEFAULT_ENV_VAR`; override only when a leaf genuinely
            needs its own scope.
        stream: where the opt-out notice is written (default
            ``sys.stderr``).

    Returns:
        The resolved package path, so a caller can log what it graded.

    Raises:
        ForeignImportError: naming BOTH paths and the fixes, in preference
            order.

    The opt-out is for deliberately testing an INSTALLED build (verifying a
    wheel, say), and it PRINTS LOUDLY when used. AN OPT-OUT THAT HIDES
    ITSELF IS THE DEFECT WEARING THE FIX'S CLOTHES — the whole family this
    guard exists for is "the report does not say what answered it", and a
    silent bypass would reproduce it one level up.
    """
    resolved_root = Path(root).resolve()
    resolved_pkg = Path(package_path).resolve()

    if resolved_pkg.is_relative_to(resolved_root):
        return resolved_pkg

    if os.environ.get(env_var):
        print(
            f"\n{package} imported from {resolved_pkg}, OUTSIDE "
            f"{resolved_root} — allowed by {env_var}. THIS RUN DOES NOT "
            f"GRADE THE TREE UNDER TEST.\n",
            file=stream if stream is not None else sys.stderr,
        )
        return resolved_pkg

    raise ForeignImportError(
        f"tests would grade a DIFFERENT {package} than this checkout.\n"
        f"  tree under test : {resolved_root}\n"
        f"  {package} found : {resolved_pkg}\n"
        f"A pass here would describe code your change never touched.\n"
        f"Fix, in order of preference:\n"
        f"  1. pip install -e {resolved_root}\n"
        f"  2. PYTHONPATH={resolved_root / 'src'} pytest ...\n"
        f"  3. {env_var}=1 — only when testing an installed build ON PURPOSE."
    )


def assert_imports_tree_under_test(
    package: str,
    root: str | os.PathLike[str],
    *,
    env_var: str = DEFAULT_ENV_VAR,
    stream=None,
) -> Path:
    """Import ``package`` and raise unless it resolves INSIDE ``root``."""
    return assert_path_inside_tree(
        package,
        # `root` is passed here ONLY so a failed import can name the tree it
        # was checking. This is the composing entry point, so it is the one
        # place that knows both halves.
        resolve_package_path(package, tree_under_test=root),
        root,
        env_var=env_var,
        stream=stream,
    )


def make_pytest_configure(
    package: str,
    root: str | os.PathLike[str],
    *,
    env_var: str = DEFAULT_ENV_VAR,
):
    """Build a ``pytest_configure`` hook wrapping the assertion.

    For a leaf's ``conftest.py``::

        from pathlib import Path
        from scitex_dev.testing import make_pytest_configure

        pytest_configure = make_pytest_configure(
            "figrecipe", Path(__file__).resolve().parent.parent
        )

    The FUNCTION above is the primitive and this is the convenience, not the
    other way round: the check is useful anywhere a runner decides what it
    is grading — a CI preflight, a release script, ``audit-all`` itself,
    which has the same defect one level up. If the only entry point were a
    pytest hook, every non-pytest caller would re-implement it, which is the
    duplication this module exists to end.
    """

    def pytest_configure(config) -> None:  # noqa: ANN001  (pytest's Config)
        del config
        assert_imports_tree_under_test(package, root, env_var=env_var)

    return pytest_configure


__all__ = [
    "DEFAULT_ENV_VAR",
    "ForeignImportError",
    "PackageNotImportableError",
    "assert_imports_tree_under_test",
    "assert_path_inside_tree",
    "make_pytest_configure",
    "resolve_package_path",
]

# EOF
