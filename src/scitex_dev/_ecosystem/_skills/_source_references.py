"""Bounded static source references; never import or execute reviewed code."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Optional


def _read(path: Path, root: Path) -> str:
    if not path.resolve().is_relative_to(root):
        raise ValueError("path is outside package root")
    return path.read_text(encoding="utf-8")


def _module_file(root: Path, module: str) -> Optional[Path]:
    base = root / "src" / Path(*module.split("."))
    # Python's file finder prefers a regular package to a same-named module.
    for candidate in (base / "__init__.py", base.with_suffix(".py")):
        if candidate.is_file():
            return candidate
    return None


def _writes_name(node, name):
    """Recognize possible bindings without entering function/class scopes."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return node.name == name
    if isinstance(node, ast.ImportFrom):
        return any(
            alias.name == "*" or (alias.asname or alias.name) == name
            for alias in node.names
        )
    if isinstance(node, ast.Import):
        return any(
            (alias.asname or alias.name.split(".")[0]) == name for alias in node.names
        )
    if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
        return node.id == name
    return any(_writes_name(child, name) for child in ast.iter_child_nodes(node))


def _target_module(module, source, node):
    if not node.level:
        return node.module or ""
    package = (
        module.split(".") if source.name == "__init__.py" else module.split(".")[:-1]
    )
    if node.level > len(package):
        return None
    parts = package[: len(package) - node.level + 1]
    if node.module:
        parts.extend(node.module.split("."))
    return ".".join(parts)


def _check_reference(
    root: Path, module: str, name: Optional[str], seen=frozenset(), *, definitions=None
):
    """Trace explicit local imports; distinguish failure from unsupported scope."""
    if _module_file(root, module.split(".")[0]) is None:
        return "unverified", "external or unsupported source-layout module"
    source = _module_file(root, module)
    if source is None:
        return "issue", "local source module does not exist"
    tree = ast.parse(_read(source, root), filename=str(source))
    if name is None:
        return "checked", "local source module exists and parses"
    if name == "*":
        return "unverified", "star import"
    key = (module, name)
    if key in seen:
        return "unverified", "cyclic local re-export"
    if len(seen) >= 32:
        return "unverified", "local re-export chain exceeds static depth limit (32)"
    bindings = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name == name:
                bindings.append(("definition", node, None))
        elif isinstance(node, ast.ImportFrom):
            matches = [
                alias
                for alias in node.names
                if alias.name != "*" and (alias.asname or alias.name) == name
            ]
            if matches:
                bindings.extend(("reexport", node, alias) for alias in matches)
            elif _writes_name(node, name):
                bindings.append(("uncertain", node, None))
        elif _writes_name(node, name):
            bindings.append(("uncertain", node, None))
    if len(bindings) > 1:
        return "unverified", "multiple or conditional source bindings"
    if bindings:
        kind, node, alias = bindings[0]
        if kind == "definition":
            if definitions is not None:
                definitions.append(node)
            return "checked", "direct source definition exists"
        if kind == "uncertain":
            return "unverified", "assignment, conditional or unsupported source binding"
        target = _target_module(module, source, node)
        if target is None:
            return "issue", "relative re-export goes beyond the source package"
        state, detail = _check_reference(
            root, target, alias.name, seen | {key}, definitions=definitions
        )
        return state, f"re-export {target}.{alias.name}: {detail}"
    # A from-import can also select a local submodule.
    if _module_file(root, module + "." + name) is not None:
        return _check_reference(
            root, module + "." + name, None, seen | {key}, definitions=definitions
        )
    if any(
        not isinstance(
            node, (ast.Expr, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        )
        for node in tree.body
    ) or any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "__getattr__"
        for node in tree.body
    ):
        return "unverified", "assignment, conditional or dynamic binding"
    return "issue", "name has no direct source definition"
