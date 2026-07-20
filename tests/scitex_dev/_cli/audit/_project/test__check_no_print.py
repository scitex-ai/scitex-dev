# -*- coding: utf-8 -*-
"""Tests for `_check_no_print.py` (PS-220).

SciTeX code must emit messages through scitex-logging, never the builtin
`print`. This check AST-scans the shippable `src/<pkg>/**.py` tree and
flags each `print(...)` call. Each test builds a REAL temp package tree
(no mocks) then asserts whether PS-220 fires.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scitex_dev._cli.audit._project._check_no_print import (
    check_ps220_no_print,
)


@dataclass
class _StubViolation:
    rule: str
    where: str
    detail: str


def _write_src(repo: Path, rel: str, body: str) -> Path:
    """Write `body` to `repo/src/<rel>`, creating parent dirs."""
    target = repo / "src" / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    return target


def _codes(out: list) -> list[str]:
    return [v.rule for v in out]


# --- PS-220 fires (positive cases) ------------------------------------------


def test_ps220_fires_on_print_in_source(tmp_path):
    # Arrange — a bare print() in package source
    _write_src(
        tmp_path,
        "scitex_demo/_core.py",
        "def go():\n    print('hello')\n",
    )
    out: list = []
    # Act
    check_ps220_no_print(tmp_path, _StubViolation, out)
    # Assert
    assert "PS-220" in _codes(out)


def test_ps220_reports_one_violation_per_print(tmp_path):
    # Arrange — two print calls ⇒ two violations
    _write_src(
        tmp_path,
        "scitex_demo/_core.py",
        "def go():\n    print('a')\n    print('b')\n",
    )
    out: list = []
    # Act
    check_ps220_no_print(tmp_path, _StubViolation, out)
    # Assert
    assert _codes(out) == ["PS-220", "PS-220"]


def test_ps220_detail_points_at_the_offending_line(tmp_path):
    # Arrange
    _write_src(
        tmp_path,
        "scitex_demo/_core.py",
        "def go():\n    print('x')\n",
    )
    out: list = []
    # Act
    check_ps220_no_print(tmp_path, _StubViolation, out)
    # Assert — the print is on line 2
    assert out[0].where.endswith(":2")


# --- PS-220 silent (negative cases) -----------------------------------------


def test_ps220_silent_on_scitex_logging_source(tmp_path):
    # Arrange — the canonical scitex-logging form, no print
    _write_src(
        tmp_path,
        "scitex_demo/_core.py",
        "import scitex_logging as slogging\n"
        "log = slogging.getLogger(__name__)\n"
        "def go():\n    log.warning('hi')\n",
    )
    out: list = []
    # Act
    check_ps220_no_print(tmp_path, _StubViolation, out)
    # Assert
    assert out == []


def test_ps220_silent_on_noqa_opt_out(tmp_path):
    # Arrange — a print explicitly opted out with `# noqa`
    _write_src(
        tmp_path,
        "scitex_demo/_cli.py",
        "def render(report):\n    print(report)  # noqa: CLI stdout payload\n",
    )
    out: list = []
    # Act
    check_ps220_no_print(tmp_path, _StubViolation, out)
    # Assert
    assert out == []


def test_ps220_silent_on_attribute_print(tmp_path):
    # Arrange — `logger.print(...)` is an attribute call, not the builtin
    _write_src(
        tmp_path,
        "scitex_demo/_core.py",
        "def go(logger):\n    logger.print('x')\n",
    )
    out: list = []
    # Act
    check_ps220_no_print(tmp_path, _StubViolation, out)
    # Assert
    assert out == []


def test_ps220_excludes_in_package_scripts_examples_docs(tmp_path):
    # Arrange — prints living in non-shippable in-package subtrees
    _write_src(tmp_path, "scitex_demo/scripts/run.py", "print('script')\n")
    _write_src(tmp_path, "scitex_demo/examples/demo.py", "print('example')\n")
    _write_src(tmp_path, "scitex_demo/docs/gen.py", "print('docs')\n")
    _write_src(tmp_path, "scitex_demo/tests/helper.py", "print('test')\n")
    out: list = []
    # Act
    check_ps220_no_print(tmp_path, _StubViolation, out)
    # Assert
    assert out == []


# EOF
