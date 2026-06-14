"""Visitors for the HARDCODE-LINT extension (STX-S009 / S010 / S012).

Operator directive 2026-06-15. The actual rule logic lives in
``_naming_checker.py``; this mixin only wires AST visitor entry points
to the dispatch helpers so ``checker.py`` stays focused on the
S001-S008 / NL001 / TQ001+ legacy surface.

Visitors provided here:

* ``visit_Module``        — kick off STX-S012 walk on module-level body
* ``visit_If``            — scan if-block bodies (``__main__`` guard)
* ``visit_With``          — scan with-block bodies
* ``visit_For``           — scan for-loop bodies
* ``visit_While``         — scan while-loop bodies
* ``visit_Try``           — scan try / except / finally bodies
* ``visit_ClassDef``      — mark class docstring skip
* ``visit_JoinedStr``     — skip f-string string children for S009/S010
* ``_mark_docstring_skips`` — Module/Function/Class first-stmt docstring skip
* augmented ``visit_Call`` — skip ``keyword=str-literal`` args from S009/S010

The mixin expects the host class to expose ``filepath``, ``_is_script``,
``_func_depth``, ``_add``, ``_get_source``, ``_check_call``, and
``_is_main_guard``. ``SciTeXChecker`` does.
"""

from __future__ import annotations

import ast


class HardcodeChecksMixin:
    """Statement-level visitors for the HARDCODE-LINT family."""

    # -- Module-level entry --

    def visit_Module(self, node: ast.Module) -> None:
        self._mark_docstring_skips(node.body)
        from .._naming_checker import check_redundant_save_log

        check_redundant_save_log(self, node.body)
        self.generic_visit(node)

    # -- Block-statement scanners (S012 = redundant save log) --

    def visit_If(self, node: ast.If) -> None:
        if self._is_main_guard(node):
            self._has_main_guard = True
        from .._naming_checker import check_redundant_save_log

        check_redundant_save_log(self, node.body)
        check_redundant_save_log(self, node.orelse)
        self.generic_visit(node)

    def visit_With(self, node: ast.With) -> None:
        from .._naming_checker import check_redundant_save_log

        check_redundant_save_log(self, node.body)
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        from .._naming_checker import check_redundant_save_log

        check_redundant_save_log(self, node.body)
        check_redundant_save_log(self, node.orelse)
        self.generic_visit(node)

    def visit_While(self, node: ast.While) -> None:
        from .._naming_checker import check_redundant_save_log

        check_redundant_save_log(self, node.body)
        self.generic_visit(node)

    def visit_Try(self, node: ast.Try) -> None:
        from .._naming_checker import check_redundant_save_log

        check_redundant_save_log(self, node.body)
        check_redundant_save_log(self, node.orelse)
        check_redundant_save_log(self, node.finalbody)
        for handler in node.handlers:
            check_redundant_save_log(self, handler.body)
        self.generic_visit(node)

    # -- Docstring + f-string string skipping (S009 / S010 noise control) --

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._mark_docstring_skips(node.body)
        self.generic_visit(node)

    def visit_JoinedStr(self, node: ast.JoinedStr) -> None:
        for v in node.values:
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                v._stx_string_skip = True
        self.generic_visit(node)

    def _mark_docstring_skips(self, body: list) -> None:
        """Tag the first-statement docstring (if any) so it bypasses S009/S010."""
        if not body:
            return
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            first.value._stx_string_skip = True


_LOGLIKE_NAMES = frozenset(
    {"print", "logger", "log", "logging", "warnings", "sys", "echo"}
)


def mark_keyword_str_skips(node: ast.Call) -> None:
    """Mark ``func(key="literal")`` string-value kwargs as skipped.

    Also skips POSITIONAL string args to log-like calls
    (``print(...)``, ``logger.info(...)``, ``logging.debug(...)``,
    ``warnings.warn(...)``, ``sys.stderr.write(...)``) — these are
    natural-language messages, not provenance values. STX-S012 still
    fires on redundant save-log pairs because it inspects the Call
    statement structure directly, not individual string nodes.

    Called from the augmented ``visit_Call`` in ``checker.py`` — kept
    standalone so the call-checking mixin doesn't need to import from
    here.
    """
    # Keyword args — always skip string literals (`logger.info(msg="x")`).
    for kw in node.keywords:
        v = kw.value
        if isinstance(v, ast.Constant) and isinstance(v.value, str):
            v._stx_string_skip = True
    # Positional string args to log-like calls.
    func = node.func
    is_loglike = False
    if isinstance(func, ast.Name) and func.id in _LOGLIKE_NAMES:
        is_loglike = True
    elif isinstance(func, ast.Attribute):
        # logger.info, logging.debug, sys.stderr.write, warnings.warn, …
        root = func.value
        while isinstance(root, ast.Attribute):
            root = root.value
        if isinstance(root, ast.Name) and root.id in _LOGLIKE_NAMES:
            is_loglike = True
    if is_loglike:
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                arg._stx_string_skip = True
