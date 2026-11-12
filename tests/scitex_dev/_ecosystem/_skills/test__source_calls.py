"""Documented call shape controls use real source, without executing it."""

import pytest

from scitex_dev import verify_docs_and_skills


def _report(tmp_path, source, example):
    package = tmp_path / "src/owned"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(source)
    (tmp_path / "README.md").write_text(f"```python\n{example}\n```\n")
    return verify_docs_and_skills(tmp_path)


@pytest.mark.parametrize(
    "source,example",
    [
        ("def public(x): pass\n", "from owned import public\npublic()"),
        ("def public(x): pass\n", "from owned import public\npublic(1, 2)"),
        ("def public(x): pass\n", "from owned import public\npublic(x=1, bad=2)"),
        ("def public(x, /): pass\n", "from owned import public\npublic(x=1)"),
        ("def public(*, x): pass\n", "from owned import public\npublic(1)"),
        ("def public(*, x): pass\n", "from owned import public\npublic()"),
        ("def public(x): pass\n", "from owned import public\npublic(x=1, x=2)"),
        (
            "def public(df, cols): pass\n",
            "import owned as api\napi.public(None, id_vars=[] )",
        ),
    ],
)
def test_definite_argument_mismatches_are_issues(tmp_path, source, example):
    # Arrange: each example violates a concrete source parameter contract.
    # Act
    report = _report(tmp_path, source, example)
    # Assert
    assert (
        report["status"],
        any("call signature:" in issue for issue in report["issues"]),
        report["stale_files"],
    ) == ("needs_update", True, [str(tmp_path / "README.md")])


@pytest.mark.parametrize(
    "source,example",
    [
        ("def public(x=0): pass\n", "from owned import public as p\np()"),
        ("def public(x, /, *, y=None): pass\n", "import owned as a\na.public(1, y=2)"),
        (
            "def public(x, *args, **kw): pass\n",
            "from owned import public\npublic(1, 2, z=3)",
        ),
        ("async def public(x): pass\n", "from owned import public\npublic(x=1)"),
        ("def public(x, *, y): pass\n", "from owned import public\npublic(1, y=2)"),
    ],
)
def test_supported_call_shapes_are_recorded(tmp_path, source, example):
    # Arrange: defaults, positional-only, keyword-only and variadic functions.
    # Act
    report = _report(tmp_path, source, example)
    # Assert
    assert (report["status"], len(report["checked_scope"]["calls"])) == ("ok", 1), (
        report
    )


@pytest.mark.parametrize(
    "source,example,reason",
    [
        (
            "@unknown\ndef public(x): pass\n",
            "from owned import public\npublic()",
            "decorated",
        ),
        (
            "class public: pass\n",
            "from owned import public\npublic()",
            "plain source function",
        ),
        (
            "def public(x): pass\n",
            "from owned import public\npublic(*args)",
            "expansion",
        ),
        (
            "def public(x): pass\n",
            "from owned import public\npublic(**kw)",
            "expansion",
        ),
        (
            "def public(x): pass\n",
            "import owned as a\na=object()\na.public()",
            "ambiguous",
        ),
        (
            "def public(x): pass\n",
            "import owned as a\na.child.public()",
            "nested attribute",
        ),
        (
            "def public(x): pass\n",
            "from owned import public\ndef f(public):\n    public()",
            "nested Python scope",
        ),
        (
            "def public(x): pass\n",
            "from owned import public\n[public() for public in items]",
            "nested Python scope",
        ),
        ("def public(x): pass\n", "public(); from owned import public", "precedes"),
    ],
)
def test_unsupported_bindings_are_explicitly_unverified(
    tmp_path, source, example, reason
):
    # Arrange: the target or argument expansion needs runtime binding analysis.
    # Act
    report = _report(tmp_path, source, example)
    # Assert
    assert (
        report["status"],
        bool(report["issues"]),
        any(reason in note for note in report["unverified"]),
        bool(report["checked_scope"]["calls"]),
    ) == ("incomplete", False, True, False), report


def test_relative_reexport_resolves_the_owning_function(tmp_path):
    # Arrange
    report = _report(
        tmp_path,
        "from .implementation import real as public\n",
        "from owned import public as alias\nalias(wrong=1)",
    )
    # The first read correctly failed because the owning module is absent.
    missing_module_status = report["status"]
    (tmp_path / "src/owned/implementation.py").write_text("def real(value): pass\n")
    # Act
    report = verify_docs_and_skills(tmp_path)
    # Assert
    assert (
        missing_module_status,
        report["status"],
        any("call signature:" in issue for issue in report["issues"]),
    ) == ("needs_update", "needs_update", True)


def test_source_bodies_defaults_annotations_and_examples_never_execute(tmp_path):
    # Arrange
    sentinel = tmp_path / "executed"
    dangerous = f"Path({str(sentinel)!r}).touch()"
    source = (
        "from pathlib import Path\n"
        f"def public(x: {dangerous} = {dangerous}):\n    {dangerous}\n"
        "raise RuntimeError('module import forbidden')\n"
    )
    # Act
    report = _report(
        tmp_path,
        source,
        f"from owned import public\npublic({dangerous})",
    )
    # Assert
    assert (
        report["status"],
        len(report["checked_scope"]["calls"]),
        sentinel.exists(),
    ) == ("ok", 1, False), report


def test_explicit_submodule_alias_is_checked(tmp_path):
    # Arrange
    _report(tmp_path, "", "import owned.backend as api\napi.public(before=1)")
    (tmp_path / "src/owned/backend.py").write_text("def public(position): pass\n")
    # Act
    report = verify_docs_and_skills(tmp_path)
    # Assert
    assert (
        report["status"],
        any("call signature:" in issue for issue in report["issues"]),
    ) == ("needs_update", True)
