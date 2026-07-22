# -*- coding: utf-8 -*-
"""Tests for the PS-220 bucket-five discriminator (`_print_discriminator`).

The discriminator decides, from the AST alone, whether a `print(...)` is a
human-facing MESSAGE (flag — it must go through scitex-logging) or genuine
machine-readable stdout (spare — routing it through a logger would corrupt
it, because scitex-logging writes to stderr).

Every case here is a REAL code snippet parsed with `ast.parse` (no mocks).
The snippets marked "shape of <file>:<line>" reproduce the structure of an
actual site in this repo, so the carve-out is pinned against production
code rather than against invented examples.
"""

from __future__ import annotations

import ast

import pytest

from scitex_dev._cli.audit._project._print_discriminator import (
    STDERR,
    STDOUT,
    UNKNOWN,
    destination,
    is_prose,
    is_serializer_call,
    should_flag,
)


def _first_print(src: str) -> tuple[ast.AST, ast.Call]:
    """Parse `src` and return (tree, the first bare `print(...)` call)."""
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "print"
        ):
            return tree, node
    raise AssertionError("snippet contains no bare print() call")


def _flags(src: str) -> bool:
    tree, call = _first_print(src)
    flag, _why = should_flag(tree, call)
    return flag


# --- destination classification ---------------------------------------------


@pytest.mark.parametrize(
    "src, expected",
    [
        ("print('x')", STDOUT),
        ("import sys\nprint('x', file=sys.stdout)", STDOUT),
        ("import sys\nprint('x', file=sys.stderr)", STDERR),
        ("import sys\nprint('x', file=sys.__stderr__)", STDERR),
        ("print('x', file=None)", STDOUT),
        ("def f(h):\n    print('x', file=h)", UNKNOWN),
        ("print('x', file=open('/tmp/f', 'w'))", UNKNOWN),
    ],
)
def test_destination_of_print_matches_expected_stream(src, expected):
    # Arrange
    tree, call = _first_print(src)
    # Act
    actual = destination(tree, call)
    # Assert
    assert actual == expected


def test_local_name_resolving_to_stdout_reads_as_stdout():
    # Arrange — the real `out = file or sys.stdout` shape (_cli/_utils.py).
    src = (
        "import sys\n"
        "def emit(payload, file=None):\n"
        "    out = file or sys.stdout\n"
        "    print(payload, file=out)\n"
    )
    tree, call = _first_print(src)
    # Act
    actual = destination(tree, call)
    # Assert
    assert actual == STDOUT


# The real `emit_result` shape from `src/scitex_dev/_cli/_utils.py:35-51`.
# Three branches each rebind `out`; only the LAST one is stderr. Collecting
# every assignment let that stderr poison the stdout writers above it, so
# genuine `--json` payload writers were reported as "writes to stderr".
# CI caught this on scitex-dev's own tree (PR #406, run 29906963643).
_BRANCH_CHAIN = (
    "import sys, json\n"
    "def emit_result(result, as_json=False, file=None):\n"
    "    if as_json:\n"
    "        out = file or sys.stdout\n"
    "        print(result.to_json(), file=out)\n"
    "    elif result.success:\n"
    "        out = file or sys.stdout\n"
    "        data = result.data\n"
    "        print(json.dumps(data, indent=2, default=str), file=out)\n"
    "    else:\n"
    "        out = file or sys.stderr\n"
    "        print(f'Error: {result.error}', file=out)\n"
)


def _print_on_line(src: str, line: int) -> tuple[ast.AST, ast.Call]:
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "print"
            and node.lineno == line
        ):
            return tree, node
    raise AssertionError(f"no bare print() on line {line}")


@pytest.mark.parametrize(
    "line, expected",
    [
        (5, STDOUT),   # `out = file or sys.stdout` two lines above
        (9, STDOUT),   # a different stdout branch
        (12, STDERR),  # the stderr branch
    ],
)
def test_branch_chain_resolves_each_destination_independently(line, expected):
    # Arrange
    tree, call = _print_on_line(_BRANCH_CHAIN, line)
    # Act
    actual = destination(tree, call)
    # Assert
    assert actual == expected


@pytest.mark.parametrize("line, expected", [(5, False), (9, False), (12, True)])
def test_branch_chain_spares_only_the_payload_writers(line, expected):
    # Arrange
    tree, call = _print_on_line(_BRANCH_CHAIN, line)
    # Act
    flag, _why = should_flag(tree, call)
    # Assert
    assert flag is expected


def test_local_name_that_can_be_stderr_reads_as_stderr():
    # Arrange — fail-closed: if a destination CAN be stderr, treat it as stderr.
    src = (
        "import sys\n"
        "def emit(payload, quiet=False):\n"
        "    out = sys.stdout if quiet else sys.stderr\n"
        "    print(payload, file=out)\n"
    )
    tree, call = _first_print(src)
    # Act
    actual = destination(tree, call)
    # Assert
    assert actual == STDERR


# --- payload classification --------------------------------------------------


@pytest.mark.parametrize(
    "expr, expected",
    [
        ("'hello'", True),
        ("f'hi {name}'", True),
        ("'a' + name", True),
        ("'a %s' % name", True),
        ("'{}'.format(name)", True),
        ("json.dumps(x)", False),
        ("payload", False),
    ],
)
def test_is_prose_classifies_string_shapes(expr, expected):
    # Arrange
    node = ast.parse(expr, mode="eval").body
    # Act
    actual = is_prose(node)
    # Assert
    assert actual is expected


@pytest.mark.parametrize(
    "expr, expected",
    [
        ("json.dumps(x)", True),
        ("result.to_json()", True),
        ("model.model_dump_json()", True),
        ("'hello'", False),
        ("payload", False),
    ],
)
def test_is_serializer_call_classifies_render_shapes(expr, expected):
    # Arrange
    node = ast.parse(expr, mode="eval").body
    # Act
    actual = is_serializer_call(node)
    # Assert
    assert actual is expected


# --- ALWAYS FLAG -------------------------------------------------------------


def test_stderr_print_with_serializer_payload_still_flags():
    # Arrange — scitex-logging OWNS stderr; a serializer payload does not
    # buy an exemption there.
    src = "import sys, json\nprint(json.dumps(x), file=sys.stderr)"
    # Act
    actual = _flags(src)
    # Assert
    assert actual is True


def test_stderr_prose_shape_of_linter_runner_flags():
    # Arrange — shape of src/scitex_dev/linter/runner.py:47
    src = "import sys\nprint(f'\\n{header}\\n', file=sys.stderr)"
    # Act
    actual = _flags(src)
    # Assert
    assert actual is True


def test_bare_stderr_print_without_payload_flags():
    # Arrange — shape of src/scitex_dev/linter/runner.py:61
    src = "import sys\nprint(file=sys.stderr)"
    # Act
    actual = _flags(src)
    # Assert
    assert actual is True


def test_string_literal_printed_to_stdout_flags():
    # Arrange
    src = "print('done')"
    # Act
    actual = _flags(src)
    # Assert
    assert actual is True


def test_fstring_printed_to_stdout_flags():
    # Arrange — shape of _core/dispatch/_skills_argparse.py:144
    src = "print(f'No skills found for {package}.')"
    # Act
    actual = _flags(src)
    # Assert
    assert actual is True


def test_prose_laundered_through_a_variable_flags():
    # Arrange — `msg = f"..."` then `print(msg)` must NOT slip past the check
    # just because the payload is a Name at the call site.
    src = "def go(pkg):\n    msg = f'No skills found for {pkg}.'\n    print(msg)\n"
    # Act
    actual = _flags(src)
    # Assert
    assert actual is True


# --- UNDECIDABLE MUST FLAG ---------------------------------------------------


def test_undecidable_destination_flags_despite_serializer():
    # Arrange — an unresolvable `file=` is NOT evidence of safety.
    src = "import json\ndef emit(handle, x):\n    print(json.dumps(x), file=handle)\n"
    # Act
    actual = _flags(src)
    # Assert
    assert actual is True


def test_multiple_positional_args_are_not_spared():
    # Arrange — `print(a, b)` is not a single rendered payload.
    src = "import json\nprint(json.dumps(a), json.dumps(b))"
    # Act
    actual = _flags(src)
    # Assert
    assert actual is True


def test_starred_args_are_not_spared():
    # Arrange
    src = "print(*parts)"
    # Act
    actual = _flags(src)
    # Assert
    assert actual is True


def test_arbitrary_expression_payload_is_not_spared():
    # Arrange — an arithmetic/attribute expression is not a rendered payload.
    src = "print(obj.count + 1)"
    # Act
    actual = _flags(src)
    # Assert
    assert actual is True


# --- SPARE (machine-readable stdout) -----------------------------------------


def test_json_dumps_to_stdout_shape_of_ssh_is_spared():
    # Arrange — shape of src/scitex_dev/ssh.py:255
    src = "import json\nprint(json.dumps(results))"
    # Act
    actual = _flags(src)
    # Assert
    assert actual is False


def test_json_dumps_with_kwargs_shape_of_cmd_rules_is_spared():
    # Arrange — shape of src/scitex_dev/linter/_cmd_rules.py:52
    src = "import json\nprint(json.dumps(data, indent=2))"
    # Act
    actual = _flags(src)
    # Assert
    assert actual is False


def test_to_json_to_resolved_stdout_shape_of_cli_utils_is_spared():
    # Arrange — shape of src/scitex_dev/_cli/_utils.py:37
    src = (
        "import sys\n"
        "def emit(result, file=None):\n"
        "    out = file or sys.stdout\n"
        "    print(result.to_json(), file=out)\n"
    )
    # Act
    actual = _flags(src)
    # Assert
    assert actual is False


def test_rendered_payload_variable_shape_of_cli_utils_is_spared():
    # Arrange — shape of src/scitex_dev/_cli/_utils.py:44
    src = (
        "import sys\n"
        "def emit(result, file=None):\n"
        "    out = file or sys.stdout\n"
        "    data = result.data\n"
        "    print(data, file=out)\n"
    )
    # Act
    actual = _flags(src)
    # Assert
    assert actual is False


def test_explicit_stdout_serializer_call_is_spared():
    # Arrange
    src = "import sys, json\nprint(json.dumps(x), file=sys.stdout)"
    # Act
    actual = _flags(src)
    # Assert
    assert actual is False


# EOF
