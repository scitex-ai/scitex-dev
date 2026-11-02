"""Source evidence for interface presence, not live availability or parity."""

from __future__ import annotations

import ast

from ._conventions import MCP_MODULE_SUFFIXES
from ._source import SourceTree, UnprovenBinding, meaningful


def entry_target(value: str):
    if not isinstance(value, str) or value.count(":") != 1:
        raise UnprovenBinding("expected an owned module:attribute entry-point binding")
    module, attribute = value.split(":")
    if not attribute.isidentifier():
        raise UnprovenBinding("entry point must name one source attribute")
    return module, attribute


def python_binding(source: SourceTree, modules: list[str]):
    problems = []
    for module in modules:
        try:
            names = source.exports(module)
        except UnprovenBinding as exc:
            problems.append(str(exc))
            continue
        for name in names:
            try:
                _path, _tree, node = source.resolve(module, name)
                if meaningful(node):
                    return None
            except UnprovenBinding as exc:
                problems.append(str(exc))
    return "Python public operation cannot be proven in the owned facade" + (
        f": {problems[0]}"
        if problems
        else "; empty/placeholder facades are not implementations"
    )


def cli_binding(source: SourceTree, project: dict):
    scripts = project.get("scripts", {})
    if not isinstance(scripts, dict) or not scripts:
        return "CLI is missing: declare a real [project.scripts] entry point"
    for name, value in scripts.items():
        try:
            module, attribute = entry_target(value)
            _path, tree, node = source.resolve(module, attribute)
            implemented = meaningful(node)
            # Click groups commonly have a docstring/pass body; their actual
            # decorated child commands provide the executable operation.
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                group = any(
                    isinstance(d, ast.Call)
                    and isinstance(d.func, ast.Attribute)
                    and d.func.attr == "group"
                    for d in node.decorator_list
                )
                if group:
                    implemented |= any(
                        meaningful(n)
                        and any(
                            isinstance(d, ast.Call)
                            and isinstance(d.func, ast.Attribute)
                            and d.func.attr == "command"
                            for d in n.decorator_list
                        )
                        for n in ast.walk(tree)
                        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                    )
            if not implemented:
                raise UnprovenBinding("entry point has no proven executable operation")
        except UnprovenBinding as exc:
            return f"CLI entry point {name!r} is unproven: {exc}"
    return None


def _mcp_evidence(source: SourceTree, module: str):
    _path, tree = source.module(module)
    factories = set()
    for node in tree.body:
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.split(".")[0] == "fastmcp"
        ):
            factories.update(
                alias.asname or alias.name
                for alias in node.names
                if alias.name == "FastMCP"
            )
    servers = {
        name
        for name, value in source.assignments(tree)
        if isinstance(value, ast.Call)
        and isinstance(value.func, ast.Name)
        and value.func.id in factories
    }
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef)
        ) or not meaningful(node):
            continue
        for decorator in node.decorator_list:
            target = decorator.func if isinstance(decorator, ast.Call) else decorator
            if (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id in servers
                and target.attr == "tool"
            ):
                return True
    # mcp.tool()(owned_handler) is the other normal FastMCP binding.
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Call):
            continue
        target = node.func.func
        if (
            isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id in servers
            and target.attr == "tool"
            and len(node.args) == 1
            and isinstance(node.args[0], ast.Name)
        ):
            try:
                if meaningful(source.resolve(module, node.args[0].id)[2]):
                    return True
            except UnprovenBinding:
                pass
    return False


def mcp_binding(source: SourceTree, modules: list[str]):
    for module in modules:
        for suffix in MCP_MODULE_SUFFIXES:
            try:
                if _mcp_evidence(source, f"{module}.{suffix}"):
                    return None
            except UnprovenBinding:
                continue
    return "MCP server with an owned implemented tool cannot be proven; absent/dynamic/placeholder bindings are findings, not skipped interfaces"


def web_binding(source: SourceTree, project: dict):
    points = project.get("entry-points", {}).get("scitex.apis", {})
    if not isinstance(points, dict) or not points:
        return "Web API is missing: declare an SDK scitex.apis owner binding; serving/admission is a separate host decision"
    for name, value in points.items():
        try:
            module, attribute = entry_target(value)
            source.resolve(module, attribute)
        except UnprovenBinding as exc:
            return f"Web API owner binding {name!r} is unproven: {exc}"
    # The SDK-owned auditor validates ApiPlugin DATA, operations, routes,
    # schemas and handlers. A source function here is NOT a quality pass.
    return None


def skills_binding(source: SourceTree, project: dict):
    points = project.get("entry-points", {}).get("scitex_dev.skills", {})
    if not isinstance(points, dict) or not points:
        return "Skills are missing: declare scitex_dev.skills and ship real SKILL.md instructions"
    for name, value in points.items():
        try:
            if not isinstance(value, str) or ":" in value:
                raise UnprovenBinding(
                    "skills entry point must identify its owned package module"
                )
            path, _tree = source.module(value)
            if path.name != "__init__.py":
                raise UnprovenBinding("skills owner must be a package")
            candidates = (
                path.parent / "_skills" / name / "SKILL.md",
                path.parent / "_skills" / "SKILL.md",
            )
            found = False
            for candidate in candidates:
                if not source.exists(candidate):
                    continue
                text = source.read(candidate).strip()
                if (
                    len(text) >= 40
                    and "#" in text
                    and text.lower()
                    not in {"# skills\n\ntodo", "# skills\n\nnot implemented"}
                ):
                    found = True
                    break
            if not found:
                raise UnprovenBinding(
                    "nonempty package-owned SKILL.md cannot be proven"
                )
        except UnprovenBinding as exc:
            return f"Skills entry point {name!r} is unproven: {exc}"
    return None
