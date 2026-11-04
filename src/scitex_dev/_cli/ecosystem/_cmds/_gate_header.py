"""Preserve supported header imports without executing a gate or its imports."""

from __future__ import annotations

import ast


def _canonical_bindings(node: ast.Import | ast.ImportFrom) -> set[str]:
    """Prove reserved names bind canonical modules, without executing imports."""
    canonical = set()
    for alias in node.names:
        if alias.name == "*":
            raise ValueError(
                "Wildcard header imports have ambiguous generated bindings"
            )
        bound = alias.asname or alias.name.split(".")[0]
        if bound not in {"importlib", "pytest"}:
            continue
        if isinstance(node, ast.Import) and (
            alias.name == bound or alias.asname is None
        ):
            canonical.add(bound)
        else:
            raise ValueError(
                f"Header import changes reserved generated binding {bound!r}; "
                "use a different alias"
            )
    return canonical


def read_header_imports(prefix: str) -> tuple[str, ...]:
    """Admit only a module docstring, imports and comments before BEGIN."""
    try:
        tree = ast.parse(prefix)
        compile(prefix, "<cross-package gate header>", "exec")
    except SyntaxError as exc:
        raise ValueError("Cannot regenerate an unparseable gate header") from exc
    imports = []
    for index, node in enumerate(tree.body):
        if (
            index == 0
            and isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            continue
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            raise TypeError(
                "Gate header supports only a docstring, imports and comments"
            )
        _canonical_bindings(node)
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
        baseline.update(_canonical_bindings(node))
    ordinary.extend(
        "import " + name for name in ("importlib", "pytest") if name not in baseline
    )
    return "\n".join([*future, *ordinary]) + "\n\n"
