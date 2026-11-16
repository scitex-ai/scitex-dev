"""Raw-file-I/O visitor for SciTeXChecker (STX-RIO001-003 + deferred STX-PA002).

Detection is recorded during the visit and EMITTED once the whole module is
seen (``_emit_raw_io``, called from ``get_issues``), for the same reason as
STX-P010: a helper ``def write_results(...)`` that does the raw I/O usually
sits ABOVE the ``@stx.session def main``, so at visit time we cannot yet know
whether the module is a session script.

That deferral also fixes a STX-PA002 gap: ``open()`` used to be flagged only
once ``_has_session_decorator`` had already flipped, i.e. only for calls
textually AFTER ``main``'s decorator — every ``open()`` in a helper above
``main`` slipped through.

Gate (low false positives): the module is a research script — it declares
an ``@stx.session`` / ``@stx.module`` entry point, or it lives under a
configured ``script_dirs`` entry of a ``project-type: research`` project —
and it is not a test file.
"""

from __future__ import annotations

import ast
from pathlib import Path

_STX = frozenset(("stx", "scitex", "scitex_io"))
_PATH_WRITE = frozenset(("write_text", "write_bytes"))
_PATH_READ = frozenset(("read_text", "read_bytes"))
_PATH_CTORS = frozenset(("Path", "PurePath", "PosixPath", "WindowsPath"))
_SHUTIL_FUNCS = frozenset(("copy", "copy2", "copyfile", "copytree", "move"))
_WRITE_MODE_CHARS = frozenset("wax+")


def _call_root_name(expr: ast.expr) -> str | None:
    while isinstance(expr, ast.Attribute):
        expr = expr.value
    if isinstance(expr, ast.Call):
        return _call_root_name(expr.func)
    return expr.id if isinstance(expr, ast.Name) else None


def _is_path_expr(expr: ast.expr) -> bool:
    """``Path(...)`` / ``pathlib.Path(...)`` / ``base / "x"`` receivers."""
    if isinstance(expr, ast.Call):
        f = expr.func
        name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
        return name in _PATH_CTORS
    if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Div):
        return True
    return False


def _open_mode(node: ast.Call, pos: int) -> str:
    """The literal mode string of an ``open``-like call ('' when absent/dynamic)."""
    mode = None
    if len(node.args) > pos:
        mode = node.args[pos]
    for kw in node.keywords:
        if kw.arg == "mode":
            mode = kw.value
    if isinstance(mode, ast.Constant) and isinstance(mode.value, str):
        return mode.value
    return ""


class RawIOChecksMixin:
    """Records raw I/O call sites. Host provides ``_add`` / ``_get_source`` /
    ``_imports`` / ``config`` / ``filepath`` / ``_has_session_decorator`` /
    ``_has_module_decorator``."""

    def _rio_record(self, node: ast.Call) -> None:
        """Classify *node* as raw I/O; append ``(rule_id, node)`` if so."""
        func = node.func
        if isinstance(func, ast.Name):
            if func.id == "open":
                self._raw_io_usages.append(("STX-PA002", node))
            return
        if not isinstance(func, ast.Attribute):
            return
        if _call_root_name(func.value) in _STX:
            return
        attr = func.attr
        if attr in _PATH_WRITE:
            self._raw_io_usages.append(("STX-RIO001", node))
        elif attr in _PATH_READ:
            self._raw_io_usages.append(("STX-RIO002", node))
        elif attr == "open" and _is_path_expr(func.value):
            is_write = bool(_WRITE_MODE_CHARS & set(_open_mode(node, 0)))
            self._raw_io_usages.append(
                ("STX-RIO001" if is_write else "STX-RIO002", node)
            )
        elif attr in _SHUTIL_FUNCS and isinstance(func.value, ast.Name):
            mod = self._imports.get(func.value.id, func.value.id)
            if mod == "shutil":
                self._raw_io_usages.append(("STX-RIO003", node))

    def _rio_is_research_script(self) -> bool:
        p = Path(self.filepath)
        name = p.name
        if (
            name.startswith("test_")
            or name.endswith("_test.py")
            or name == "conftest.py"
            or any(seg in {"tests", "test"} for seg in p.parts)
        ):
            return False
        if self._has_session_decorator or self._has_module_decorator:
            return True
        research = "research" in (getattr(self.config, "project_types", None) or ())
        script_dirs = getattr(self.config, "script_dirs", None) or ()
        return research and any(d in p.parts for d in script_dirs)

    def _emit_raw_io(self) -> None:
        usages = self._raw_io_usages
        if not usages or not self._rio_is_research_script():
            return
        from .._rules import lookup

        for rule_id, node in usages:
            rule = lookup(rule_id)
            line = self._get_source(node.lineno)
            self._add(rule, node.lineno, node.col_offset, line)
