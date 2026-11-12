"""Read closed literal PEP 562 declarations without executing the module."""

from __future__ import annotations

import ast


def _literal_guard_exports(node: ast.AST) -> set[str]:
    if not isinstance(node, ast.FunctionDef) or node.name != "__getattr__":
        return set()
    positional = node.args.posonlyargs + node.args.args
    if (len(positional) != 1 or node.args.vararg is not None
            or node.args.kwarg is not None or node.args.kwonlyargs):
        return set()
    parameter = positional[0].arg
    names = set()
    for statement in node.body:
        if not isinstance(statement, ast.If):
            continue
        test = statement.test
        if not (
            isinstance(test, ast.Compare)
            and isinstance(test.left, ast.Name)
            and test.left.id == parameter
            and len(test.ops) == len(test.comparators) == 1
            and isinstance(test.ops[0], ast.In)
            and isinstance(test.comparators[0], (ast.Set, ast.Tuple, ast.List))
        ):
            continue
        elements = test.comparators[0].elts
        if not elements or not all(
            isinstance(value, ast.Constant) and isinstance(value.value, str)
            for value in elements
        ):
            continue
        # Only straight-line preparation before a direct return is recognized.
        # Nested helpers, conditional returns and raises remain unverified.
        for action in statement.body:
            if isinstance(action, ast.Return) and action.value is not None:
                names.update(value.value for value in elements)
                break
            if not isinstance(action, (ast.Assign, ast.AnnAssign, ast.Import,
                                       ast.ImportFrom, ast.Expr, ast.Pass)):
                break
    return names
