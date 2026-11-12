"""Check plain local function call shapes without importing reviewed code."""

from __future__ import annotations

import ast
import inspect

from ._source_references import _check_reference, _module_file, _writes_name


def _signature(node):
    """Use default-presence markers; never evaluate defaults or annotations."""
    args = node.args
    positional = args.posonlyargs + args.args
    required = len(positional) - len(args.defaults)
    parameters = []
    for index, arg in enumerate(positional):
        kind = (
            inspect.Parameter.POSITIONAL_ONLY
            if index < len(args.posonlyargs)
            else inspect.Parameter.POSITIONAL_OR_KEYWORD
        )
        default = inspect.Parameter.empty if index < required else None
        parameters.append(inspect.Parameter(arg.arg, kind, default=default))
    if args.vararg:
        parameters.append(
            inspect.Parameter(args.vararg.arg, inspect.Parameter.VAR_POSITIONAL)
        )
    for arg, default in zip(args.kwonlyargs, args.kw_defaults):
        parameters.append(
            inspect.Parameter(
                arg.arg,
                inspect.Parameter.KEYWORD_ONLY,
                default=inspect.Parameter.empty if default is None else None,
            )
        )
    if args.kwarg:
        parameters.append(
            inspect.Parameter(args.kwarg.arg, inspect.Parameter.VAR_KEYWORD)
        )
    return inspect.Signature(parameters)


def _bindings(root, tree):
    """Only explicit module-level imports identify a documented call target."""
    imports = {}
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                module = alias.name if alias.asname else alias.name.split(".")[0]
                imports[alias.asname or module] = (
                    module,
                    None,
                    (node.lineno, node.col_offset),
                )
        elif isinstance(node, ast.ImportFrom) and not node.level:
            for alias in node.names:
                if alias.name != "*":
                    imports[alias.asname or alias.name] = (
                        node.module,
                        alias.name,
                        (node.lineno, node.col_offset),
                    )
    return {
        name: (module, symbol, position)
        for name, (module, symbol, position) in imports.items()
        if module and _module_file(root, module.split(".")[0]) is not None
    }


def _target(node, bindings):
    function = node.func
    if isinstance(function, ast.Name) and function.id in bindings:
        return function.id, *bindings[function.id]
    if isinstance(function, ast.Attribute):
        owner = function.value
        if isinstance(owner, ast.Name) and owner.id in bindings:
            module, symbol, position = bindings[owner.id]
            if symbol is None:
                return owner.id, module, function.attr, position
            return owner.id, None, None, position
        while isinstance(owner, ast.Attribute):
            owner = owner.value
        if isinstance(owner, ast.Name) and owner.id in bindings:
            return owner.id, None, None, bindings[owner.id][2]
    return None


def _calls(node, nested=False):
    """Nested Python scopes require binding analysis beyond this check."""
    nested = nested or isinstance(
        node,
        (
            ast.FunctionDef,
            ast.AsyncFunctionDef,
            ast.ClassDef,
            ast.Lambda,
            ast.ListComp,
            ast.SetComp,
            ast.DictComp,
            ast.GeneratorExp,
        ),
    )
    if isinstance(node, ast.Call):
        yield node, nested
    for child in ast.iter_child_nodes(node):
        yield from _calls(child, nested)


def check_calls(root, tree):
    """Yield (line, reference, state, detail) for source-linked calls only."""
    bindings = _bindings(root, tree)
    for call, nested in _calls(tree):
        target = _target(call, bindings)
        if target is None:
            continue
        alias, module, name, position = target
        reference = f"{module}.{name}" if module and name else alias
        reason = None
        if nested:
            reason = "call in a nested Python scope"
        elif (call.lineno, call.col_offset) < position:
            reason = "example call precedes its import binding"
        elif sum(_writes_name(node, alias) for node in tree.body) != 1:
            reason = "reassigned or ambiguous example import binding"
        elif not module or not name:
            reason = "constructor, module or nested attribute call target"
        elif any(isinstance(arg, ast.Starred) for arg in call.args) or any(
            keyword.arg is None for keyword in call.keywords
        ):
            reason = "dynamic argument expansion"
        if reason:
            yield call.lineno, reference, "unverified", reason
            continue
        definitions = []
        state, detail = _check_reference(root, module, name, definitions=definitions)
        if state != "checked":
            yield call.lineno, reference, state, detail
            continue
        if len(definitions) != 1 or not isinstance(
            definitions[0], (ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            yield call.lineno, reference, "unverified", "not a plain source function"
            continue
        definition = definitions[0]
        if definition.decorator_list:
            yield call.lineno, reference, "unverified", "decorated source function"
            continue
        keywords = [keyword.arg for keyword in call.keywords]
        if len(keywords) != len(set(keywords)):
            yield call.lineno, reference, "issue", "call signature: repeated keyword"
            continue
        try:
            _signature(definition).bind(
                *[None for _ in call.args],
                **{keyword.arg: None for keyword in call.keywords},
            )
        except TypeError as exc:
            yield call.lineno, reference, "issue", f"call signature: {exc}"
        else:
            yield call.lineno, reference, "checked", "plain source call shape binds"
