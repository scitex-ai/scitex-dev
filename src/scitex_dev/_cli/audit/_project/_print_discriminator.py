# -*- coding: utf-8 -*-
"""Legacy output-shape introspection and logging-owned strict enforcement.

Destination, prose, and serializer helpers remain available to existing
callers. They do not exempt any builtin print. ``should_flag`` is a direct
compatibility alias to the owning logging distribution's strict rule.
"""

from __future__ import annotations

import ast

# Attribute names whose CALL renders an already-serialized payload. A print of
# one of these to stdout is machine-readable output, not a message.
SERIALIZER_ATTRS = frozenset(
    {
        "dumps",  # json.dumps(...) / yaml.dumps(...)
        "to_json",
        "model_dump_json",
        "json",  # pydantic v1 `.json()`
        "to_csv",
        "SerializeToString",
    }
)

# Destination classifications. ``INJECTED`` means a required function
# parameter is passed directly as ``file=``: the caller, rather than library
# code, owns that rendering stream.
STDOUT, STDERR, INJECTED, UNKNOWN = "stdout", "stderr", "injected", "unknown"


def _is_sys_stream(node: ast.AST) -> str | None:
    """Return "stdout"/"stderr" if `node` is a `sys.std*` attribute, else None."""
    if not isinstance(node, ast.Attribute):
        return None
    attr = node.attr
    if attr in ("stdout", "__stdout__"):
        return STDOUT
    if attr in ("stderr", "__stderr__"):
        return STDERR
    return None


def _enclosing_assignments(tree: ast.AST, target: ast.AST) -> list[ast.Assign]:
    """Return the `name = <value>` assignments in the scope around `target`.

    Walks the smallest function that contains `target` (falling back to the
    module) and collects every plain assignment. Used to resolve the common
    `out = file or sys.stdout` shape rather than giving up on it.
    """
    tline = getattr(target, "lineno", None)
    if tline is None:
        return []
    best: ast.AST | None = None
    best_span: int | None = None
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        start = getattr(node, "lineno", None)
        end = getattr(node, "end_lineno", None)
        if start is None or end is None or not (start <= tline <= end):
            continue
        span = end - start
        if best_span is None or span < best_span:
            best, best_span = node, span
    scope = best if best is not None else tree
    return [n for n in ast.walk(scope) if isinstance(n, ast.Assign)]


def _enclosing_function(
    tree: ast.AST, target: ast.AST
) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    """Return the smallest function containing ``target`` (if any)."""
    tline = getattr(target, "lineno", None)
    if tline is None:
        return None
    candidates = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        start = getattr(node, "lineno", None)
        end = getattr(node, "end_lineno", None)
        if start is not None and end is not None and start <= tline <= end:
            candidates.append(node)
    if not candidates:
        return None
    return min(candidates, key=lambda node: node.end_lineno - node.lineno)


def _required_parameters(function: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    """Return parameters for which the caller must supply a value."""
    positional = [*function.args.posonlyargs, *function.args.args]
    optional_count = len(function.args.defaults)
    required = positional[: len(positional) - optional_count]
    required.extend(
        arg
        for arg, default in zip(function.args.kwonlyargs, function.args.kw_defaults)
        if default is None
    )
    return {arg.arg for arg in required if arg.arg not in {"self", "cls"}}


def _is_injected_stream(tree: ast.AST, call: ast.Call, node: ast.AST) -> bool:
    """Whether ``node`` is a required, caller-owned stream parameter."""
    if not isinstance(node, ast.Name):
        return False
    function = _enclosing_function(tree, call)
    return function is not None and node.id in _required_parameters(function)


def _assignments_to(tree: ast.AST, call: ast.Call, name: str) -> list[ast.expr]:
    """Value expressions assigned to `name` in the scope enclosing `call`."""
    call_line = getattr(call, "lineno", None)
    if call_line is None:
        return []
    candidates = [
        assign
        for assign in _enclosing_assignments(tree, call)
        if any(isinstance(t, ast.Name) and t.id == name for t in assign.targets)
        and getattr(assign, "lineno", call_line) <= call_line
    ]
    if not candidates:
        return []
    nearest = max(candidates, key=lambda a: a.lineno)
    return [nearest.value]


def _resolve_name_stream(tree: ast.AST, call: ast.Call, name: str) -> str:
    """Classify a local variable used as a `file=` destination.

    `sys.stderr` anywhere in an assigned expression wins (fail-closed: if a
    destination can be stderr, treat it as stderr); otherwise `sys.stdout`
    classifies it as stdout. Anything else stays UNKNOWN, which flags.
    """
    saw_stdout = False
    for value in _assignments_to(tree, call, name):
        for sub in ast.walk(value):
            stream = _is_sys_stream(sub)
            if stream == STDERR:
                return STDERR
            if stream == STDOUT:
                saw_stdout = True
    return STDOUT if saw_stdout else UNKNOWN


def destination(tree: ast.AST, call: ast.Call) -> str:
    """Classify where a `print(...)` call writes."""
    for kw in call.keywords:
        if kw.arg != "file":
            continue
        stream = _is_sys_stream(kw.value)
        if stream is not None:
            return stream
        if isinstance(kw.value, ast.Name):
            if _is_injected_stream(tree, call, kw.value):
                return INJECTED
            return _resolve_name_stream(tree, call, kw.value.id)
        if isinstance(kw.value, ast.Constant) and kw.value.value is None:
            return STDOUT  # `file=None` is stdout, per builtins
        return UNKNOWN
    return STDOUT  # no `file=` ⇒ stdout


def is_prose(node: ast.AST) -> bool:
    """True iff `node` is human prose by construction (str literal / f-string)."""
    if isinstance(node, ast.JoinedStr):  # f"..."
        return True
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return True
    # "a" + x and "a %s" % x are prose too.
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mod)):
        return is_prose(node.left) or is_prose(node.right)
    # "...".format(...) / "".join(...) on a literal.
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if node.func.attr in ("format", "join") and is_prose(node.func.value):
            return True
    return False


def is_serializer_call(node: ast.AST) -> bool:
    """True iff `node` is a call that renders a machine-readable payload."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    return isinstance(func, ast.Attribute) and func.attr in SERIALIZER_ATTRS


def payload_is_machine_readable(tree: ast.AST, call: ast.Call) -> bool:
    """True iff the sole positional arg is a rendered, machine-readable payload.

    A serializer call qualifies directly. A variable qualifies only when its
    nearest assignment is itself a serializer call. Merely naming an unknown
    value ``payload`` is not proof that it is deterministic data transport.
    """
    if len(call.args) != 1 or any(isinstance(a, ast.Starred) for a in call.args):
        return False
    arg = call.args[0]
    if is_serializer_call(arg):
        return True
    if isinstance(arg, ast.Name):
        assigned = _assignments_to(tree, call, arg.id)
        return len(assigned) == 1 and is_serializer_call(assigned[0])
    return False


_CONTENT_FUNCTION_PREFIXES = ("emit_", "print_", "render_", "show_", "write_")
_CONTENT_PARAMETER_NAMES = frozenset({"content", "document", "text"})


def payload_is_explicitly_requested(tree: ast.AST, call: ast.Call) -> bool:
    """Recognize the narrow ``render_content(content)`` transport contract.

    This is deliberately not a generic "one argument was printed" escape.
    The enclosing API must explicitly be an output operation and print its
    caller-supplied content parameter verbatim.
    """
    if len(call.args) != 1 or call.keywords:
        return False
    arg = call.args[0]
    if not isinstance(arg, ast.Name) or arg.id not in _CONTENT_PARAMETER_NAMES:
        return False
    function = _enclosing_function(tree, call)
    if function is None or not function.name.startswith(_CONTENT_FUNCTION_PREFIXES):
        return False
    return arg.id in _required_parameters(function)


from scitex_logging._output_auditor import should_flag


__all__ = [
    "SERIALIZER_ATTRS",
    "INJECTED",
    "STDOUT",
    "STDERR",
    "UNKNOWN",
    "destination",
    "is_prose",
    "is_serializer_call",
    "payload_is_machine_readable",
    "payload_is_explicitly_requested",
    "should_flag",
]

# EOF
