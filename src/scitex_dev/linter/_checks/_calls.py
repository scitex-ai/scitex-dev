"""Call-expression visitor for SciTeXChecker (Phase 2 call rules)."""

from __future__ import annotations

import ast

from .. import rules
from .._rule_tables import AXES_HINTS as _AXES_HINTS
from .._rule_tables import AXES_SKIP as _AXES_SKIP
from .._rule_tables import CALL_RULES as _CALL_RULES
from .._rule_tables import PRINT_RULE as _PRINT_RULE


class CallChecksMixin:
    """Call visitors. Expects host ``_add`` / ``_get_source`` / ``_imports`` /
    ``_plugin_call_rules`` / ``_has_session_decorator`` / ``_MOCK_SYMBOLS`` /
    ``_check_stx_io_path``."""

    def visit_Call(self, node: ast.Call) -> None:
        self._check_call(node)
        self.generic_visit(node)

    def _check_call(self, node: ast.Call) -> None:
        """Check function calls against Phase 2 rules."""
        func = node.func

        # module.func() pattern -- e.g., np.save(), stats.ttest_ind()
        if isinstance(func, ast.Attribute):
            func_name = func.attr
            mod_name = None

            if isinstance(func.value, ast.Name):
                mod_name = func.value.id
            elif isinstance(func.value, ast.Attribute):
                # module.sub.func() -- e.g., scipy.stats.ttest_ind()
                if isinstance(func.value.value, ast.Name):
                    mod_name = func.value.attr  # use "stats" from scipy.stats

            # Check stx.io path patterns before skipping stx.* calls
            if mod_name in ("stx", "scitex", "scitex_io") or (
                isinstance(func.value, ast.Attribute)
                and isinstance(func.value.value, ast.Name)
                and func.value.value.id in ("stx", "scitex", "scitex_io")
            ):
                self._check_stx_io_path(node)
                return

            # Resolve alias: if user did `import numpy as np`, resolve np -> numpy
            resolved = self._imports.get(mod_name, mod_name)

            # Check (module, func) against rule table
            rule = _CALL_RULES.get((mod_name, func_name))
            if rule is None and resolved != mod_name:
                rule = _CALL_RULES.get((resolved, func_name))
            if rule is None:
                rule = _CALL_RULES.get((None, func_name))

            # Fallback to plugin-contributed rules
            if rule is None:
                rule = self._plugin_call_rules.get((mod_name, func_name))
            if rule is None and resolved != mod_name:
                rule = self._plugin_call_rules.get((resolved, func_name))
            if rule is None:
                rule = self._plugin_call_rules.get((None, func_name))

            # Special cases
            if rule is not None:
                # plt.show() -- only flag if mod resolves to matplotlib
                if rule is rules.P004:
                    if mod_name not in ("plt", "pyplot") and resolved not in (
                        "matplotlib.pyplot",
                    ):
                        return

                # to_csv / savefig -- skip on non-data/figure objects
                if rule in (rules.IO004, rules.IO007):
                    if mod_name in ("stx", "scitex", "scitex_io", "os", "sys", "Path"):
                        return

                # FM rules: exempt stx.*/fr.*/figrecipe.* calls
                if rule.category == "figure":
                    _exempt = ("stx", "scitex", "scitex_io", "fr", "figrecipe")
                    if mod_name in _exempt:
                        return
                    # Check root of chained call: fr.fig.set_size_inches()
                    if (
                        isinstance(func.value, ast.Attribute)
                        and isinstance(func.value.value, ast.Name)
                        and func.value.value.id in _exempt
                    ):
                        return

                line = self._get_source(node.lineno)
                self._add(rule, node.lineno, node.col_offset, line)
                return

            # Axes hints: ax.plot(), ax.scatter(), ax.bar()
            if func_name in _AXES_HINTS and mod_name not in _AXES_SKIP:
                # Heuristic: if variable name looks like axes
                if mod_name and (
                    mod_name.startswith("ax") or mod_name in ("axes", "subplot")
                ):
                    line = self._get_source(node.lineno)
                    self._add(
                        _AXES_HINTS[func_name], node.lineno, node.col_offset, line
                    )
                return

            # Path(...).mkdir() pattern
            if func_name == "mkdir" and mod_name not in (
                "os",
                "stx",
                "scitex",
                "sys",
            ):
                # Heuristic: if it's called on something that looks like a Path
                line = self._get_source(node.lineno)
                if "Path" in line or "path" in line.lower():
                    pa003 = getattr(rules, "PA-003", None)
                    if pa003 is not None:
                        self._add(pa003, node.lineno, node.col_offset, line)

        # bare func() pattern -- e.g., print(), open()
        elif isinstance(func, ast.Name):
            if func.id == "print" and self._has_session_decorator:
                line = self._get_source(node.lineno)
                self._add(_PRINT_RULE, node.lineno, node.col_offset, line)
            elif func.id == "open" and self._has_session_decorator:
                line = self._get_source(node.lineno)
                self._add(rules.PA002, node.lineno, node.col_offset, line)
            # NM003 — bare call to a mock symbol: Mock(), MagicMock(), patch(...)
            elif func.id in self._MOCK_SYMBOLS:
                line = self._get_source(node.lineno)
                self._add(rules.NM003, node.lineno, node.col_offset, line)

        # NM003 — attribute call to a mock symbol: mock.patch(...),
        # unittest.mock.MagicMock(...), pytest_mock.MockerFixture(...).
        if isinstance(func, ast.Attribute) and func.attr in self._MOCK_SYMBOLS:
            line = self._get_source(node.lineno)
            self._add(rules.NM003, node.lineno, node.col_offset, line)

    def _check_stx_io_path(self, node: ast.Call) -> None:
        from .._path_checker import check_stx_io_path

        check_stx_io_path(self, node)
