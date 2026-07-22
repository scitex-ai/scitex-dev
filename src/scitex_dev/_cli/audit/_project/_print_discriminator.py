# -*- coding: utf-8 -*-
"""The PS-220 bucket-five discriminator — is this `print(...)` a MESSAGE?

Split out of `_check_no_print.py` (which owns the file walk, the exemption
handling and the rule tuple) so the classification logic is one cohesive,
separately-testable responsibility.

A blanket ban on `print` would be wrong, and would get worked around rather
than followed. Where output IS the product — a `--json` payload, piped data,
a value a shell consumes — routing it through a logger would CORRUPT it,
because scitex-logging writes every console record to STDERR. So the
carve-out is a design constraint, not a concession, and it is decided
STRUCTURALLY (from the AST) rather than by an honour-system comment:

* ALWAYS FLAG — `print(..., file=sys.stderr)`. scitex-logging owns stderr; a
  hand-rolled stderr write is exactly the unstructured, unfilterable output
  the mandate removes.
* ALWAYS FLAG — a stdout `print` whose payload is a string literal or an
  f-string. That is human prose by construction.
* SPARE — a stdout `print` (no `file=`, or `file=sys.stdout`) whose sole
  positional argument is a serializer call (`json.dumps(...)`, `.to_json()`,
  `.model_dump_json()`) or a variable holding an already-rendered payload.
* FLAG EVERYTHING ELSE. An undecidable destination or an undecidable payload
  is NOT evidence of safety. Unknown must never read as safe.

Destinations and payload variables are resolved within the ENCLOSING FUNCTION
when they are plain local names, so the common real-world shape
``out = file or sys.stdout; print(payload, file=out)`` classifies correctly
instead of falling into "undecidable".
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

# Destination classifications.
STDOUT, STDERR, UNKNOWN = "stdout", "stderr", "unknown"


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

    A serializer call qualifies directly. A bare variable qualifies UNLESS the
    enclosing scope assigns prose to it — that closes the obvious hole where
    `msg = f"..."` followed by `print(msg)` would launder prose past the check.
    """
    if len(call.args) != 1 or any(isinstance(a, ast.Starred) for a in call.args):
        return False
    arg = call.args[0]
    if is_serializer_call(arg):
        return True
    if isinstance(arg, ast.Name):
        return not any(
            is_prose(value) for value in _assignments_to(tree, call, arg.id)
        )
    return False


def should_flag(tree: ast.AST, call: ast.Call) -> tuple[bool, str]:
    """Apply the bucket-five discriminator. Returns `(flag, why)`."""
    dest = destination(tree, call)
    if dest == STDERR:
        return True, (
            "writes to stderr, which scitex-logging owns — use "
            "`log.warning(...)` / `log.error(...)` instead"
        )
    if dest == UNKNOWN:
        return True, (
            "writes to an undecidable destination (`file=` is not resolvably "
            "stdout or stderr), so it cannot be shown to be machine-readable "
            "stdout"
        )
    if payload_is_machine_readable(tree, call):
        return False, ""
    if len(call.args) == 1 and is_prose(call.args[0]):
        return True, (
            "prints human prose (a string literal or f-string) to stdout — "
            "this is a message, and messages go through scitex-logging"
        )
    return True, (
        "prints an undecidable payload to stdout; only a serializer call "
        "(`json.dumps(...)`, `.to_json()`, `.model_dump_json()`) or a variable "
        "holding a rendered payload is treated as machine-readable output"
    )


__all__ = [
    "SERIALIZER_ATTRS",
    "STDOUT",
    "STDERR",
    "UNKNOWN",
    "destination",
    "is_prose",
    "is_serializer_call",
    "payload_is_machine_readable",
    "should_flag",
]

# EOF
