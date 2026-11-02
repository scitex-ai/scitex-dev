"""Conservative source contradictions for name-based MCP suffix candidates.

No callable is invoked. Unknown/callback/conditional/foreign bindings are not
proof: their existing name heuristic remains explicitly unverified. Traversal
stops at the first public API boundary, never inside domain implementations.
"""

from __future__ import annotations

import ast
import types
from dataclasses import dataclass
from pathlib import Path

from scitex_dev._interfaces._source import SourceTree, UnprovenBinding

from ._mcp_names import _short_name


@dataclass(frozen=True)
class _Ref:
    module: str
    path: Path
    node: ast.FunctionDef | ast.AsyncFunctionDef

    @property
    def key(self):
        return self.path, self.node.lineno, self.node.name


@dataclass(frozen=True)
class _Module:
    name: str


class _Unknown(ValueError):
    pass


class _OwnedTrace:
    def __init__(self, repo, package, public_names):
        self.source = SourceTree(Path(repo))
        self.root_module = package.replace("-", "_")
        self.public = {}
        for name in sorted(public_names):
            try:
                ref = self.named(self.root_module, name)
            except (UnprovenBinding, _Unknown):
                continue
            if isinstance(ref, _Ref):
                self.public.setdefault(ref.key, set()).add(name)

    def module_name(self, path):
        for root in (self.source.repo / "src", self.source.repo):
            try:
                parts = list(path.relative_to(root).parts)
            except ValueError:
                continue
            if parts[-1] == "__init__.py":
                parts.pop()
            else:
                parts[-1] = Path(parts[-1]).stem
            if parts and all(part.isidentifier() for part in parts):
                return ".".join(parts)
        raise _Unknown("foreign-source")

    def named(self, module, name):
        path, _tree, node = self.source.resolve(module, name)
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            raise _Unknown("dynamic-binding")
        return _Ref(self.module_name(path), path, node)

    def callable_ref(self, function):
        if not isinstance(function, types.FunctionType):
            raise _Unknown("unsupported-callable")
        code = function.__code__  # Intrinsic code identity; __wrapped__/names can lie.
        if code.co_freevars:
            raise _Unknown("closure-binding")
        path = Path(code.co_filename).resolve()
        module = self.module_name(path)
        actual_path, tree = self.source.module(module)
        if actual_path.resolve() != path:
            raise _Unknown("source-identity")
        nodes = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == code.co_name
            and min([node.lineno, *[d.lineno for d in node.decorator_list]])
            == code.co_firstlineno
        ]
        if len(nodes) != 1:
            raise _Unknown("source-identity")
        return _Ref(module, path, nodes[0])

    def imported(self, owner, node, alias):
        if not node.level:
            module = node.module or ""
        else:
            parent = (
                owner.module.split(".")
                if owner.path.name == "__init__.py"
                else owner.module.split(".")[:-1]
            )
            if node.level > len(parent):
                raise _Unknown("foreign-source")
            module = ".".join(
                [
                    *parent[: len(parent) - node.level + 1],
                    *str(node.module or "").split("."),
                ]
            ).strip(".")
        if module.split(".")[0] != self.root_module.split(".")[0]:
            return _Module(module + "." + alias.name)
        try:
            return self.named(module, alias.name)
        except UnprovenBinding:
            self.source.module(module + "." + alias.name)
            return _Module(module + "." + alias.name)

    def expression(self, owner, expr, local):
        if isinstance(expr, ast.Name):
            if expr.id in local:
                value = local[expr.id]
                if value is None:
                    raise _Unknown("ambiguous-binding")
                return value
            try:
                return self.named(owner.module, expr.id)
            except UnprovenBinding:
                if expr.id in {
                    "str",
                    "len",
                    "list",
                    "dict",
                    "set",
                    "tuple",
                    "bool",
                    "int",
                    "float",
                    "Exception",
                }:
                    return _Module("builtins." + expr.id)
                raise _Unknown("dynamic-call") from None
        if isinstance(expr, ast.Attribute):
            base = self.expression(owner, expr.value, local)
            if isinstance(base, _Module):
                if base.name.split(".")[0] != self.root_module.split(".")[0]:
                    return _Module(base.name + "." + expr.attr)
                return self.named(base.name, expr.attr)
        raise _Unknown("dynamic-call")

    def walk(self, ref, seen=()):
        if ref.key in self.public:
            return {ref.key}, set()
        if ref.key in seen:
            return set(), {"cycle"}
        if len(seen) >= 8:
            return set(), {"depth-limit"}
        local = {}
        _path, module_tree = self.source.module(ref.module)
        for statement in module_tree.body:
            if isinstance(statement, ast.Import):
                for alias in statement.names:
                    local[alias.asname or alias.name.split(".")[0]] = _Module(
                        alias.name if alias.asname else alias.name.split(".")[0]
                    )
            elif isinstance(statement, ast.ImportFrom):
                for alias in statement.names:
                    try:
                        local[alias.asname or alias.name] = self.imported(
                            ref, statement, alias
                        )
                    except (UnprovenBinding, _Unknown):
                        local[alias.asname or alias.name] = None
            elif isinstance(statement, (ast.Assign, ast.AnnAssign)):
                for target in (
                    statement.targets
                    if isinstance(statement, ast.Assign)
                    else [statement.target]
                ):
                    if isinstance(target, ast.Name) and target.id in local:
                        local[target.id] = None
        local.update(
            {
                arg.arg: None
                for arg in (
                    *ref.node.args.posonlyargs,
                    *ref.node.args.args,
                    *ref.node.args.kwonlyargs,
                )
            }
        )
        targets, unknown = set(), set()
        count = [0]

        def visit_suite(statements):
            for index, statement in enumerate(statements):
                if visit(statement):
                    if index + 1 < len(statements):
                        unknown.add("unreachable-code")
                    return True
            return False

        def visit(node):
            count[0] += 1
            if count[0] > 2048:
                unknown.add("node-limit")
                return
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                local[node.name] = _Ref(ref.module, ref.path, node)
                return  # An uncalled nested helper is not an executed binding.
            if isinstance(node, ast.If):
                if isinstance(node.test, ast.Constant) and isinstance(
                    node.test.value, bool
                ):
                    return visit_suite(node.body if node.test.value else node.orelse)
                else:
                    unknown.add("conditional-call")
                return
            if isinstance(node, ast.Try):
                exits = [visit_suite(node.body)]
                exits.extend(visit_suite(handler.body) for handler in node.handlers)
                visit_suite(node.orelse)
                final_exits = visit_suite(node.finalbody)
                return final_exits or all(exits)
            if isinstance(
                node,
                (
                    ast.For,
                    ast.AsyncFor,
                    ast.While,
                    ast.Lambda,
                    getattr(ast, "Match", ast.If),
                ),
            ):
                unknown.add("dynamic-control")
                return
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    try:
                        local[alias.asname or alias.name] = self.imported(
                            ref, node, alias
                        )
                    except (UnprovenBinding, _Unknown):
                        local[alias.asname or alias.name] = None
                return
            if isinstance(node, ast.Import):
                for alias in node.names:
                    local[alias.asname or alias.name.split(".")[0]] = _Module(
                        alias.name if alias.asname else alias.name.split(".")[0]
                    )
                return
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                if node.value is not None:
                    visit(node.value)
                for target in (
                    node.targets if isinstance(node, ast.Assign) else [node.target]
                ):
                    if isinstance(target, ast.Name):
                        try:
                            local[target.id] = self.expression(ref, node.value, local)
                        except (UnprovenBinding, _Unknown):
                            local[target.id] = None
                return
            if isinstance(node, ast.Call):
                try:
                    target = self.expression(ref, node.func, local)
                    callable_arg = False
                    for argument in [*node.args, *[kw.value for kw in node.keywords]]:
                        try:
                            callable_arg |= isinstance(
                                self.expression(ref, argument, local), _Ref
                            )
                        except (UnprovenBinding, _Unknown):
                            pass
                    if callable_arg:
                        unknown.add("callable-forwarding")
                    if isinstance(target, _Ref) and isinstance(
                        target.node, ast.AsyncFunctionDef
                    ):
                        unknown.add("async-call-unproven")
                    elif isinstance(target, _Ref):
                        hits, failures = self.walk(target, (*seen, ref.key))
                        targets.update(hits)
                        unknown.update(failures)
                    elif not target.name.startswith(("builtins.", "json.")):
                        unknown.add("foreign-call")
                except (UnprovenBinding, _Unknown) as exc:
                    unknown.add(
                        str(exc) if isinstance(exc, _Unknown) else "unproven-owned-call"
                    )
            for child in ast.iter_child_nodes(node):
                visit(child)
            return isinstance(node, (ast.Return, ast.Raise))

        visit_suite(ref.node.body)
        return targets, unknown


def suffix_contradictions(package, public_names, tools, repo):
    """Veto only unambiguous owned-source proof of a different public boundary."""
    notes = {
        "basis": "name-based coverage with bounded owned-source contradiction veto; not schema/runtime equivalence",
        "verified_suffix_boundaries": [],
        "contradictions": [],
        "unproven_suffix_matches": [],
    }
    vetoes = set()
    if repo is None or tools is None:
        notes["source_status"] = "unavailable; suffix matches are name-based/unproven"
        return vetoes, notes
    short = _short_name(package)
    try:
        trace = _OwnedTrace(repo, package, public_names)
    except (OSError, ValueError, SyntaxError):
        notes["source_status"] = "unavailable; suffix matches are name-based/unproven"
        return vetoes, notes
    for tool in tools:
        try:
            data = vars(tool)
        except TypeError:
            continue
        raw_name = data.get("name", "")
        if not isinstance(raw_name, str):
            continue
        name = raw_name.removeprefix(short + "_")
        candidates = sorted(
            api for api in public_names if name != api and name.endswith("_" + api)
        )
        if not candidates:
            continue
        try:
            boundaries, uncertain = trace.walk(trace.callable_ref(data.get("fn")))
        except (OSError, ValueError, SyntaxError) as exc:
            boundaries, uncertain = (
                set(),
                {str(exc) if isinstance(exc, _Unknown) else "source-unavailable"},
            )
        for api in candidates:
            record = {"tool": name, "api": api}
            api_keys = {key for key, names in trace.public.items() if api in names}
            if uncertain or len(boundaries) != 1 or len(api_keys) != 1:
                notes["unproven_suffix_matches"].append(
                    dict(
                        record,
                        reasons=sorted(uncertain or {"ambiguous-public-boundary"}),
                    )
                )
            elif boundaries == api_keys:
                notes["verified_suffix_boundaries"].append(record)
            else:
                actual = sorted(
                    {name for key in boundaries for name in trace.public[key]}
                )
                vetoes.add((name, api))
                notes["contradictions"].append(dict(record, first_public_apis=actual))
    return vetoes, notes
