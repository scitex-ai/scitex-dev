#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the import-vantage guard.

The two that matter are the CONTROLS, and they pull in opposite directions:

* it must REFUSE a genuine outside-the-tree resolution — otherwise it is a
  check that cannot fail, which is the same as no check;
* it must ACCEPT a tree reached through a SYMLINK — otherwise it fires on a
  legitimate CI setup, gets switched off, and a guard everyone disables is
  worse than none.

A false negative costs one bad green. A false positive costs the guard.

Everything here runs against REAL directories and REAL symlinks in
`tmp_path`. The containment decision is a pure function of two paths
precisely so it can be exercised that way rather than through a stand-in
for the import system.
"""

from __future__ import annotations

import io
import os
from pathlib import Path

import pytest

from scitex_dev.testing import (
    DEFAULT_ENV_VAR,
    ForeignImportError,
    PackageNotImportableError,
    assert_path_inside_tree,
    make_pytest_configure,
    resolve_package_path,
)


@pytest.fixture
def no_opt_out():
    """Guarantee the shared opt-out is absent, and restore it afterwards."""
    saved = os.environ.pop(DEFAULT_ENV_VAR, None)
    yield
    if saved is not None:
        os.environ[DEFAULT_ENV_VAR] = saved


@pytest.fixture
def shared_opt_out_set():
    """Set the shared opt-out for the duration of one test."""
    saved = os.environ.get(DEFAULT_ENV_VAR)
    os.environ[DEFAULT_ENV_VAR] = "1"
    yield
    if saved is None:
        os.environ.pop(DEFAULT_ENV_VAR, None)
    else:
        os.environ[DEFAULT_ENV_VAR] = saved


@pytest.fixture
def leaf_opt_out_set():
    """Set a leaf-scoped opt-out for the duration of one test."""
    name = "THING_ALLOW_FOREIGN_IMPORT"
    saved = os.environ.get(name)
    os.environ[name] = "1"
    yield name
    if saved is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = saved


def _make_package(root: Path) -> Path:
    """Create a real `<root>/src/thing/__init__.py` and return it."""
    pkg = root / "src" / "thing" / "__init__.py"
    pkg.parent.mkdir(parents=True)
    pkg.touch()
    return pkg


def test_accepts_a_package_inside_the_tree(tmp_path, no_opt_out):
    # Arrange
    root = tmp_path / "repo"
    pkg = _make_package(root)
    # Act
    resolved = assert_path_inside_tree("thing", pkg, root)
    # Assert
    assert resolved == pkg.resolve()


def test_refuses_a_genuine_site_packages_resolution(tmp_path, no_opt_out):
    """POSITIVE CONTROL — a guard never shown to fire is indistinguishable
    from one that cannot."""
    # Arrange
    root = tmp_path / "repo"
    root.mkdir()
    installed = tmp_path / "venv" / "site-packages" / "thing" / "__init__.py"
    installed.parent.mkdir(parents=True)
    installed.touch()
    # Act
    # Assert
    with pytest.raises(ForeignImportError):
        assert_path_inside_tree("thing", installed, root)


def _refusal_message(package: str, package_path: Path, root: Path) -> str:
    """Return the refusal text, or "" if the guard did not refuse.

    A helper rather than `pytest.raises(...) as excinfo` so each test below
    carries exactly one assertion: `raises` counts as an assertion itself,
    and a second one after it is silently skipped when the first fails —
    which is the same half-tested contract this module exists to prevent.
    """
    try:
        assert_path_inside_tree(package, package_path, root)
    except ForeignImportError as exc:
        return str(exc)
    return ""


def test_the_refusal_names_the_tree_under_test(tmp_path, no_opt_out):
    """The family this guards against is "the report does not say what
    answered it". A refusal naming only one side reproduces it."""
    # Arrange
    root = tmp_path / "repo"
    root.mkdir()
    installed = tmp_path / "site-packages" / "thing" / "__init__.py"
    installed.parent.mkdir(parents=True)
    installed.touch()
    # Act
    message = _refusal_message("thing", installed, root)
    # Assert
    assert str(root.resolve()) in message


def test_the_refusal_names_where_the_package_was_found(tmp_path, no_opt_out):
    # Arrange
    root = tmp_path / "repo"
    root.mkdir()
    installed = tmp_path / "site-packages" / "thing" / "__init__.py"
    installed.parent.mkdir(parents=True)
    installed.touch()
    # Act
    message = _refusal_message("thing", installed, root)
    # Assert
    assert str(installed.resolve()) in message


def test_accepts_a_package_reached_through_a_symlinked_tree(
    tmp_path, no_opt_out
):
    """CONTROL IN THE OTHER DIRECTION — the expensive false positive.

    A linked git worktree, an editable install pointing at a `src/` that is
    itself a link, a `--target` layout: all legitimate, all comparing
    unequal if the paths are matched as strings.
    """
    # Arrange
    real_root = tmp_path / "real-checkout"
    pkg = _make_package(real_root)
    linked_root = tmp_path / "linked-checkout"
    linked_root.symlink_to(real_root, target_is_directory=True)
    # Act
    resolved = assert_path_inside_tree(
        "thing", linked_root / "src" / "thing" / "__init__.py", linked_root
    )
    # Assert
    assert resolved == pkg.resolve()


def test_accepts_when_the_two_sides_name_the_link_and_the_real_path(
    tmp_path, no_opt_out
):
    """The sides named DIFFERENTLY — link on one, real path on the other.
    Resolving both is the whole reason this passes."""
    # Arrange
    real_root = tmp_path / "real-checkout"
    pkg = _make_package(real_root)
    linked_root = tmp_path / "linked-checkout"
    linked_root.symlink_to(real_root, target_is_directory=True)
    # Act
    resolved = assert_path_inside_tree(
        "thing", linked_root / "src" / "thing" / "__init__.py", real_root
    )
    # Assert
    assert resolved == pkg.resolve()


def test_opt_out_allows_the_run(tmp_path, shared_opt_out_set):
    # Arrange
    root = tmp_path / "repo"
    root.mkdir()
    installed = tmp_path / "site-packages" / "thing" / "__init__.py"
    installed.parent.mkdir(parents=True)
    installed.touch()
    # Act
    resolved = assert_path_inside_tree(
        "thing", installed, root, stream=io.StringIO()
    )
    # Assert
    assert resolved == installed.resolve()


def test_opt_out_says_so_loudly(tmp_path, shared_opt_out_set):
    """An opt-out that hides itself is the defect wearing the fix's
    clothes."""
    # Arrange
    root = tmp_path / "repo"
    root.mkdir()
    installed = tmp_path / "site-packages" / "thing" / "__init__.py"
    installed.parent.mkdir(parents=True)
    installed.touch()
    stream = io.StringIO()
    # Act
    assert_path_inside_tree("thing", installed, root, stream=stream)
    # Assert
    assert "DOES NOT GRADE THE TREE UNDER TEST" in stream.getvalue()


def test_a_leaf_can_scope_the_opt_out_to_its_own_variable(
    tmp_path, no_opt_out, leaf_opt_out_set
):
    # Arrange
    root = tmp_path / "repo"
    root.mkdir()
    installed = tmp_path / "site-packages" / "thing" / "__init__.py"
    installed.parent.mkdir(parents=True)
    installed.touch()
    stream = io.StringIO()
    # Act
    assert_path_inside_tree(
        "thing", installed, root, env_var=leaf_opt_out_set, stream=stream
    )
    # Assert
    assert leaf_opt_out_set in stream.getvalue()


def test_the_shared_opt_out_does_not_open_a_leaf_scoped_guard(
    tmp_path, shared_opt_out_set
):
    """Scoping must actually scope: the shared name in the environment must
    NOT open a leaf that asked for its own."""
    # Arrange
    root = tmp_path / "repo"
    root.mkdir()
    installed = tmp_path / "site-packages" / "thing" / "__init__.py"
    installed.parent.mkdir(parents=True)
    installed.touch()
    os.environ.pop("THING_ALLOW_FOREIGN_IMPORT", None)
    # Act
    # Assert
    with pytest.raises(ForeignImportError):
        assert_path_inside_tree(
            "thing", installed, root, env_var="THING_ALLOW_FOREIGN_IMPORT"
        )


def test_resolve_package_path_finds_an_importable_package(no_opt_out):
    """Exercised against a REAL import rather than a stand-in."""
    # Arrange
    package = "scitex_dev"
    # Act
    resolved = resolve_package_path(package)
    # Assert
    assert resolved.name == "__init__.py"


def test_make_pytest_configure_returns_a_callable_hook(tmp_path, no_opt_out):
    # Arrange
    root = tmp_path / "repo"
    root.mkdir()
    # Act
    hook = make_pytest_configure("scitex_dev", root)
    # Assert
    assert callable(hook)


def test_the_hook_refuses_when_the_package_is_outside_the_tree(
    tmp_path, no_opt_out
):
    # Arrange
    root = tmp_path / "repo"
    root.mkdir()
    hook = make_pytest_configure("scitex_dev", root)
    # Act
    # Assert
    with pytest.raises(ForeignImportError):
        hook(config=None)



# ---------------------------------------------------------------------------
# A package that cannot be imported AT ALL.
#
# The bare ModuleNotFoundError this used to raise was loud and honest, so it
# was never a defect. But it named neither the tree being checked nor the fact
# that a guard was running — and naming what it looked at is this module's
# whole value. A guard whose own failure does not identify itself reproduces,
# one level up, the family it exists to catch.
# ---------------------------------------------------------------------------

_ABSENT = "scitex_dev_no_such_package_exists_anywhere"


def _import_failure(package: str, root):
    """Return the raised error, or None if the call unexpectedly succeeded."""
    try:
        resolve_package_path(package, tree_under_test=root)
    except PackageNotImportableError as exc:
        return exc
    return None


def test_an_unimportable_package_raises_the_guards_own_error(tmp_path):
    # Arrange
    root = tmp_path / "repo"
    root.mkdir()
    # Act
    # Assert
    with pytest.raises(PackageNotImportableError):
        resolve_package_path(_ABSENT, tree_under_test=root)


def test_that_error_is_still_a_foreign_import_error(tmp_path):
    """A SUBCLASS, so every existing `except ForeignImportError` keeps
    working — a caller wanting "the guard refused" learns no second name."""
    # Arrange
    root = tmp_path / "repo"
    root.mkdir()
    # Act
    error = _import_failure(_ABSENT, root)
    # Assert
    assert isinstance(error, ForeignImportError)


def test_the_message_names_the_tree_it_was_checking(tmp_path):
    # Arrange
    root = tmp_path / "repo"
    root.mkdir()
    # Act
    error = _import_failure(_ABSENT, root)
    # Assert
    assert str(root.resolve()) in str(error)


def test_the_message_says_a_guard_was_running(tmp_path):
    # Arrange
    root = tmp_path / "repo"
    root.mkdir()
    # Act
    error = _import_failure(_ABSENT, root)
    # Assert
    assert "guard speaking" in str(error)


def test_the_original_import_error_is_chained_not_replaced(tmp_path):
    """The import error is the actual diagnosis — a typo, a missing install,
    a broken dependency. This only adds the context it lacked."""
    # Arrange
    root = tmp_path / "repo"
    root.mkdir()
    # Act
    error = _import_failure(_ABSENT, root)
    # Assert
    assert isinstance(error.__cause__, ImportError)


def test_the_tree_is_optional_so_a_bare_caller_still_gets_the_guards_error():
    """`tree_under_test` appears only in the message, so omitting it must
    still produce the guard's error rather than a bare ModuleNotFoundError."""
    # Arrange
    package = _ABSENT
    # Act
    # Assert
    with pytest.raises(PackageNotImportableError):
        resolve_package_path(package)

# EOF
