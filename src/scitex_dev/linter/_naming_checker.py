"""Naming convention checks for SciTeX linter.

Rules:
  _lk("STX-S007") — load_configs() result should use UPPER_CASE variable name

STX-S008 (hard-coded analysis parameters) lives in ``_magic_numbers.py``;
it needs the whole module (signatures, calls, comparisons), not just
assignments.
"""

import ast

from ._rules import lookup as _lk


def check_assignment(checker, node: ast.Assign) -> None:
    """Run all assignment-level checks."""
    check_config_naming(checker, node)


def check_config_naming(checker, node: ast.Assign) -> None:
    """Warn when load_configs() result is assigned to a non-UPPER_CASE name."""
    if not isinstance(node.value, ast.Call):
        return

    func = node.value.func
    is_load_configs = False

    # bare load_configs()
    if isinstance(func, ast.Name) and func.id == "load_configs":
        is_load_configs = True
    # stx.io.load_configs() / scitex.io.load_configs() / any.load_configs()
    elif isinstance(func, ast.Attribute) and func.attr == "load_configs":
        is_load_configs = True

    if not is_load_configs:
        return

    for target in node.targets:
        if isinstance(target, ast.Name) and not target.id.isupper():
            line = checker._get_source(node.lineno)
            checker._add(_lk("STX-S007"), node.lineno, node.col_offset, line)
