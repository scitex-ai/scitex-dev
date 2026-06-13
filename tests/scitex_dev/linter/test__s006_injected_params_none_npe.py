"""Dedicated regression test for issue #60.

`scitex-dev linter check-files` crashed with
``AttributeError: 'NoneType' object has no attribute 'id'``
when linting a @stx.session function that declared
``CONFIG=stx.session.INJECTED`` style INJECTED params (the canonical
pattern). Root cause: the legacy umbrella plugin's S006 implementation
dereferenced ``.id`` on each injected param's default-value /
annotation AST, which the canonical pattern never satisfies (the
default is an ``ast.Attribute``, not an ``ast.Name``; for ``*args`` /
``**kwargs`` / posonly the corresponding default slot is ``None``).

The engine-side S006 (``SciTeXChecker._check_injected_params``) has
been hardened to read only ``arg.arg`` name strings — never the
default value or annotation node — so the ``.id`` path no longer
exists by construction. This test file pins that contract end-to-end
against the *file-dispatch* entry point (``lint_file``), the same
path that ``scitex-dev linter check-files`` uses. The existing
``test__session_structure.py`` tests exercise ``lint_source``; this
file complements them by exercising the path issue #60 actually
crashed on.
"""

from __future__ import annotations

from pathlib import Path

from scitex_dev.linter._dispatch import lint_file
from scitex_dev.linter.checker import lint_source
from scitex_dev.linter.config import LinterConfig


_NEUROVISTA_SOURCE = (
    "#!/usr/bin/env python3\n"
    '"""v4i_headline_stats.py — neurovista repro for issue #60."""\n'
    "\n"
    "import scitex as stx\n"
    "\n"
    "\n"
    "@stx.session\n"
    "def main(\n"
    "    data_path: str,\n"
    "    threshold: float = 0.5,\n"
    "    CONFIG=stx.session.INJECTED,\n"
    "    plt=stx.session.INJECTED,\n"
    "    COLORS=stx.session.INJECTED,\n"
    "    rngg=stx.session.INJECTED,\n"
    "    logger=stx.session.INJECTED,\n"
    "):\n"
    '    """Annotated args + INJECTED defaults — the #60 repro shape."""\n'
    "    return 0\n"
    "\n"
    "\n"
    "if __name__ == '__main__':\n"
    "    main()\n"
)


def _s006(issues):
    return [i for i in issues if i.rule.id == "STX-S006"]


def test_lint_source_does_not_raise_on_issue_60_neurovista_shape():
    """#60 — lint_source must not NPE on annotated + INJECTED defaults."""
    # Arrange
    config = LinterConfig()
    # Act
    issues = lint_source(_NEUROVISTA_SOURCE, filepath="<test>", config=config)
    # Assert
    assert _s006(issues) == []


def test_lint_file_does_not_raise_on_issue_60_neurovista_shape(tmp_path: Path):
    """#60 — `scitex-dev linter check-files` goes through `lint_file`."""
    # Arrange
    script = tmp_path / "v4i_headline_stats.py"
    script.write_text(_NEUROVISTA_SOURCE, encoding="utf-8")
    config = LinterConfig()
    # Act
    issues = lint_file(str(script), config=config)
    # Assert
    assert _s006(issues) == []


def test_lint_source_does_not_raise_on_partial_injected_with_annotations():
    """#60 — even when S006 fires (missing params), no NPE on .id."""
    # Arrange — only 2 of 5 INJECTED declared, others missing
    source = (
        "import scitex as stx\n"
        "\n"
        "@stx.session\n"
        "def main(\n"
        "    data_path: str,\n"
        "    CONFIG=stx.session.INJECTED,\n"
        "    plt=stx.session.INJECTED,\n"
        "):\n"
        "    return 0\n"
    )
    # Act
    issues = lint_source(source, filepath="<test>", config=LinterConfig())
    # Assert
    assert len(_s006(issues)) == 1


def test_lint_source_does_not_raise_on_vararg_kwarg_combo():
    """#60 — *args / **kwargs slots have None defaults; must not NPE."""
    # Arrange — kwonly INJECTED between *args and **kwargs (None default slots)
    source = (
        "import scitex as stx\n"
        "\n"
        "@stx.session\n"
        "def main(\n"
        "    *args,\n"
        "    CONFIG=stx.session.INJECTED,\n"
        "    plt=stx.session.INJECTED,\n"
        "    COLORS=stx.session.INJECTED,\n"
        "    rngg=stx.session.INJECTED,\n"
        "    logger=stx.session.INJECTED,\n"
        "    **kwargs,\n"
        "):\n"
        "    return 0\n"
    )
    # Act
    issues = lint_source(source, filepath="<test>", config=LinterConfig())
    # Assert
    assert _s006(issues) == []


def test_lint_file_does_not_raise_on_bare_session_with_no_args(tmp_path: Path):
    """#60 — bare `def main():` with @stx.session must not NPE on .id."""
    # Arrange
    source = (
        "import scitex as stx\n"
        "\n"
        "@stx.session\n"
        "def main():\n"
        "    return 0\n"
        "\n"
        "if __name__ == '__main__':\n"
        "    main()\n"
    )
    script = tmp_path / "bare.py"
    script.write_text(source, encoding="utf-8")
    # Act
    issues = lint_file(str(script), config=LinterConfig())
    # Assert
    assert len(_s006(issues)) == 1
