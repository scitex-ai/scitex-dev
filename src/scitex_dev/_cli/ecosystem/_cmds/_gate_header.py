"""Preserve supported header imports without executing a gate or its imports."""

from __future__ import annotations

import ast


def read_header_imports(prefix: str) -> tuple[str, ...]:
    """Admit only a module docstring, imports and comments before BEGIN."""
    try:
        tree = ast.parse(prefix)
        compile(prefix, "<cross-package gate header>", "exec")
    except SyntaxError as exc:
        raise ValueError("Cannot regenerate an unparseable gate header") from exc
    imports = []
    for index, node in enumerate(tree.body):
        if index == 0 and isinstance(node, ast.Expr):
            if isinstance(node.value, ast.Constant) and isinstance(
                node.value.value, str
            ):
                continue
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            raise ValueError(
                "Gate header supports only a docstring, imports and comments"
            )
        source = ast.get_source_segment(prefix, node)
        assert source is not None
        imports.append(source)
    return tuple(imports)


def render_header_imports(imports: tuple[str, ...]) -> str:
    """Keep aliases/multiline source and place future imports before normal ones."""
    future, ordinary = [], []
    baseline = set()
    for source in imports:
        # Validate even callers that did not obtain these segments from the reader.
        if read_header_imports(source) != (source,):
            raise ValueError("Expected one exact import source segment")
        node = ast.parse(source).body[0]
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            future.append(source)
        else:
            ordinary.append(source)
        if isinstance(node, ast.Import):
            baseline.update(
                alias.name for alias in node.names if alias.asname in (None, alias.name)
            )
    ordinary.extend(
        "import " + name for name in ("importlib", "pytest") if name not in baseline
    )
    return "\n".join([*future, *ordinary]) + "\n\n"
