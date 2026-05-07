"""AST-based checker that detects SciTeX anti-patterns."""

__all__ = ["Issue", "is_script", "lint_file", "lint_source"]

import ast
import re
from dataclasses import dataclass, replace
from pathlib import Path

from . import rules
from ._rule_tables import AXES_HINTS as _AXES_HINTS
from ._rule_tables import AXES_SKIP as _AXES_SKIP
from ._rule_tables import CALL_RULES as _CALL_RULES
from ._rule_tables import PRINT_RULE as _PRINT_RULE
from ._rules import lookup as _lk
from .rules import Rule


@dataclass
class Issue:
    rule: Rule
    line: int
    col: int
    source_line: str = ""


def is_script(filepath: str, config=None) -> bool:
    """Check if file is a script (not a library module).

    Uses config.library_patterns and config.library_dirs to determine
    which files are library modules (exempt from script-only rules).
    """
    from .config import load_config, matches_library_pattern

    if config is None:
        config = load_config(start_path=filepath)

    path = Path(filepath)
    name = path.name

    # Check filename against library patterns (e.g., __*__.py, test_*.py)
    if matches_library_pattern(name, config):
        return False

    # Check if file is inside a library directory (e.g., src/)
    parts = path.parts
    for lib_dir in config.library_dirs:
        if lib_dir in parts:
            return False

    # Check if file is inside a script directory (e.g., scripts/)
    # These are utility scripts called by shell, not SciTeX session scripts
    for script_dir in config.script_dirs:
        if script_dir in parts:
            return False

    return True


_STX_ALLOW_RE = re.compile(r"#\s*stx-allow\b(?::?\s*(.+))?")


def _is_allowed_by_comment(source_line: str, rule_id: str) -> bool:
    """Check if a source line has a ``# stx-allow`` comment suppressing *rule_id*.

    Supported forms::

        x = 1  # stx-allow                     → suppresses ALL rules on this line
        x = 1  # stx-allow: STX-S003           → suppresses STX-S003
        x = 1  # stx-allow: STX-S003, STX-I001 → suppresses both
    """
    if not source_line:
        return False
    m = _STX_ALLOW_RE.search(source_line)
    if m is None:
        return False
    ids_str = m.group(1)
    if not ids_str:
        return True  # bare ``# stx-allow`` suppresses everything
    allowed = {s.strip() for s in ids_str.split(",")}
    return rule_id in allowed


class SciTeXChecker(ast.NodeVisitor):
    """AST visitor detecting non-SciTeX patterns."""

    def __init__(self, source_lines: list, filepath: str = "<stdin>", config=None):
        from .config import load_config

        self.source_lines = source_lines
        self.filepath = filepath
        self.config = config or load_config(start_path=filepath)
        self.issues: list = []
        # Package availability for rule gating
        from ._packages import detect as _detect_pkgs

        self._available = _detect_pkgs()
        # Tracking state
        self._has_stx_import = False
        self._has_main_guard = False
        self._has_session_decorator = False
        self._has_module_decorator = False
        self._session_func_returns_int = False
        self._imports: dict = {}  # alias -> full module path
        self._is_script = is_script(filepath, self.config)
        self._func_depth = 0  # >0 means inside a function body
        from ._plugin_loader import load_plugins

        _plugins = load_plugins()
        # Filter plugin rules by config.enable (FM rules need opt-in)
        _enabled = set(self.config.enable) if self.config else set()
        _CAT_ENABLE = {"figure": "FM"}  # categories requiring opt-in
        self._plugin_call_rules = {
            k: r
            for k, r in _plugins["call_rules"].items()
            if r.category not in _CAT_ENABLE or _CAT_ENABLE[r.category] in _enabled
        }
        self._plugin_checkers = _plugins["checkers"]

    # -- Import visitors --

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            name = alias.asname or alias.name
            self._imports[name] = alias.name

            if alias.name == "scitex":
                self._has_stx_import = True

            self._check_import(alias.name, node)

        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        for alias in node.names:
            name = alias.asname or alias.name
            full = f"{module}.{alias.name}"
            self._imports[name] = full

        self._check_import_from(module, node)
        self.generic_visit(node)

    def _check_import(self, module_name: str, node: ast.Import) -> None:
        """Check bare `import X` statements."""
        line = self._get_source(node.lineno)

        # import matplotlib.pyplot as plt
        if "matplotlib.pyplot" in module_name:
            self._add(_lk("STX-I001"), node.lineno, node.col_offset, line)

        if module_name == "argparse" and self._is_script:
            self._add(_lk("STX-S003"), node.lineno, node.col_offset, line)

        if module_name == "pickle":
            self._add(_lk("STX-I003"), node.lineno, node.col_offset, line)

        if module_name == "random":
            self._add(_lk("STX-I006"), node.lineno, node.col_offset, line)

        if module_name == "logging":
            self._add(_lk("STX-I007"), node.lineno, node.col_offset, line)

    def _check_import_from(self, module: str, node: ast.ImportFrom) -> None:
        """Check `from X import Y` statements."""
        line = self._get_source(node.lineno)

        # from matplotlib import pyplot / from matplotlib.pyplot import *
        if module == "matplotlib":
            for alias in node.names:
                if alias.name == "pyplot":
                    self._add(_lk("STX-I001"), node.lineno, node.col_offset, line)
                    break
        elif module and "matplotlib.pyplot" in module:
            self._add(_lk("STX-I001"), node.lineno, node.col_offset, line)

        # from scipy import stats / from scipy.stats import *
        if module in ("scipy", "scipy.stats"):
            if module == "scipy":
                for alias in node.names:
                    if alias.name == "stats":
                        self._add(_lk("STX-I002"), node.lineno, node.col_offset, line)
                        break
            else:
                self._add(_lk("STX-I002"), node.lineno, node.col_offset, line)

        # from argparse import *
        if module == "argparse" and self._is_script:
            self._add(_lk("STX-S003"), node.lineno, node.col_offset, line)

    # -- Try/Except visitor (EH001) --

    # Stdlib modules where ImportError is the only realistic failure mode.
    # These are skipped to avoid false positives.
    _EH001_STDLIB_SKIP = frozenset(
        {
            "tomllib",
            "tomli",
            "importlib",
            "importlib.metadata",
            "importlib.resources",
            "typing_extensions",
            "typing",
            "zoneinfo",
            "backports",
            "argparse",
            "dataclasses",
            "pathlib",
            "asyncio",
            "contextlib",
            "functools",
            "itertools",
            "collections",
            "collections.abc",
            "enum",
            "json",
            "os",
            "sys",
            "re",
            "subprocess",
        }
    )

    def visit_Try(self, node: ast.Try) -> None:
        self._check_eh001(node)
        self.generic_visit(node)

    def _check_eh001(self, node: ast.Try) -> None:
        # Body must be exactly one statement: an Import / ImportFrom.
        if len(node.body) != 1:
            return
        stmt = node.body[0]
        if isinstance(stmt, ast.Import):
            mod_names = [alias.name for alias in stmt.names]
        elif isinstance(stmt, ast.ImportFrom):
            mod_names = [stmt.module] if stmt.module else []
        else:
            return

        # Skip stdlib-only imports (where narrow ImportError is correct).
        if mod_names and all(
            (m or "").split(".")[0] in self._EH001_STDLIB_SKIP for m in mod_names
        ):
            return

        if not node.handlers:
            return

        # Collect all exception types listed in handlers.
        narrow_only = True
        for handler in node.handlers:
            exc = handler.type
            names = self._extract_exc_names(exc)
            # Bare `except:` (exc is None) — broad, do not fire.
            if exc is None:
                return
            for n in names:
                # If any handler catches Exception/BaseException, rule does
                # not fire — already broad enough.
                if n in ("Exception", "BaseException"):
                    return
                if n not in ("ImportError", "ModuleNotFoundError"):
                    # Some other narrow exception is in play (e.g. OSError).
                    # Treat as not-purely-import-narrow; still fire only if
                    # the only types are ImportError/ModuleNotFoundError.
                    narrow_only = False

        if not narrow_only:
            return

        line = self._get_source(stmt.lineno)
        self._add(rules.EH001, stmt.lineno, stmt.col_offset, line)

    @staticmethod
    def _extract_exc_names(exc) -> list:
        """Flatten an exception type expression into a list of bare names."""
        if exc is None:
            return []
        if isinstance(exc, ast.Name):
            return [exc.id]
        if isinstance(exc, ast.Attribute):
            return [exc.attr]
        if isinstance(exc, ast.Tuple):
            out = []
            for elt in exc.elts:
                out.extend(SciTeXChecker._extract_exc_names(elt))
            return out
        return []

    # -- Assignment visitors --

    def visit_Assign(self, node: ast.Assign) -> None:
        from ._naming_checker import check_assignment

        check_assignment(self, node)
        self.generic_visit(node)

    # -- Call visitors (Phase 2) --

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
            if mod_name in ("stx", "scitex") or (
                isinstance(func.value, ast.Attribute)
                and isinstance(func.value.value, ast.Name)
                and func.value.value.id in ("stx", "scitex")
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
                    if mod_name in ("stx", "scitex", "os", "sys", "Path"):
                        return

                # FM rules: exempt stx.*/fr.*/figrecipe.* calls
                if rule.category == "figure":
                    _exempt = ("stx", "scitex", "fr", "figrecipe")
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
                    self._add(rules.PA003, node.lineno, node.col_offset, line)

        # bare func() pattern -- e.g., print(), open()
        elif isinstance(func, ast.Name):
            if func.id == "print" and self._has_session_decorator:
                line = self._get_source(node.lineno)
                self._add(_PRINT_RULE, node.lineno, node.col_offset, line)
            elif func.id == "open" and self._has_session_decorator:
                line = self._get_source(node.lineno)
                self._add(rules.PA002, node.lineno, node.col_offset, line)

    # -- stx.io path checking (delegated to _path_checker) --

    def _check_stx_io_path(self, node: ast.Call) -> None:
        from ._path_checker import check_stx_io_path

        check_stx_io_path(self, node)

    # -- Function/decorator visitors --

    @property
    def _REQUIRED_INJECTED(self):
        return set(self.config.required_injected)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if self._has_session_deco(node):
            self._has_session_decorator = True
            self._check_session_return(node)
            self._check_injected_params(node)
        elif self._has_module_deco(node):
            self._has_module_decorator = True
        self._func_depth += 1
        self.generic_visit(node)
        self._func_depth -= 1

    visit_AsyncFunctionDef = visit_FunctionDef

    def _has_session_deco(self, node: ast.FunctionDef) -> bool:
        """Check if function has @stx.session or @session decorator."""
        for deco in node.decorator_list:
            # @stx.session
            if isinstance(deco, ast.Attribute):
                if (
                    isinstance(deco.value, ast.Name)
                    and deco.value.id in ("stx", "scitex")
                    and deco.attr == "session"
                ):
                    return True
            # @session (bare)
            if isinstance(deco, ast.Name) and deco.id == "session":
                return True
        return False

    def _has_module_deco(self, node: ast.FunctionDef) -> bool:
        """Check if function has @stx.module(...) decorator."""
        for deco in node.decorator_list:
            # @stx.module(...) — Call wrapping Attribute
            if isinstance(deco, ast.Call) and isinstance(deco.func, ast.Attribute):
                if (
                    isinstance(deco.func.value, ast.Name)
                    and deco.func.value.id in ("stx", "scitex")
                    and deco.func.attr == "module"
                ):
                    return True
            # @stx.module (bare, no parens)
            if isinstance(deco, ast.Attribute):
                if (
                    isinstance(deco.value, ast.Name)
                    and deco.value.id in ("stx", "scitex")
                    and deco.attr == "module"
                ):
                    return True
            # @module(...) (bare call)
            if isinstance(deco, ast.Call) and isinstance(deco.func, ast.Name):
                if deco.func.id == "module":
                    return True
        return False

    def _check_session_return(self, node: ast.FunctionDef) -> None:
        """Check that session function returns an int."""
        for child in ast.walk(node):
            if isinstance(child, ast.Return) and child.value is not None:
                if isinstance(child.value, ast.Constant) and isinstance(
                    child.value.value, int
                ):
                    self._session_func_returns_int = True
                    return
        # No int return found
        line = self._get_source(node.lineno)
        self._add(_lk("STX-S004"), node.lineno, node.col_offset, line)

    def _check_injected_params(self, node: ast.FunctionDef) -> None:
        """Check that @stx.session function declares all INJECTED parameters."""
        declared = {arg.arg for arg in node.args.args}
        missing = sorted(self._REQUIRED_INJECTED - declared)
        if missing:
            line = self._get_source(node.lineno)
            missing_str = ", ".join(missing)
            s006 = _lk("STX-S006")
            dynamic_rule = Rule(
                id=s006.id,
                severity=s006.severity,
                category=s006.category,
                message=(
                    f"@stx.session function missing INJECTED parameters: {missing_str}. "
                    f"All 5 must be declared: CONFIG, COLORS, logger, plt, rngg"
                ),
                suggestion=s006.suggestion,
                requires=s006.requires,
            )
            self._add(dynamic_rule, node.lineno, node.col_offset, line)

    # -- Module-level checks (run after visiting entire tree) --

    def visit_If(self, node: ast.If) -> None:
        """Detect if __name__ == '__main__' guard."""
        if self._is_main_guard(node):
            self._has_main_guard = True
        self.generic_visit(node)

    def _is_main_guard(self, node: ast.If) -> bool:
        test = node.test
        if isinstance(test, ast.Compare):
            if (
                isinstance(test.left, ast.Name)
                and test.left.id == "__name__"
                and len(test.comparators) == 1
                and isinstance(test.comparators[0], ast.Constant)
                and test.comparators[0].value == "__main__"
            ):
                return True
        return False

    # -- Finalization --

    def get_issues(self) -> list:
        """Return all issues, including post-visit structural checks."""
        if not self._is_script:
            return self.issues

        if not self._has_main_guard:
            self._add(_lk("STX-S002"), 1, 0, "")

        if self._has_main_guard and not (
            self._has_session_decorator or self._has_module_decorator
        ):
            self._add(_lk("STX-S001"), 1, 0, "")

        if self._has_main_guard and not self._has_stx_import:
            self._add(_lk("STX-S005"), 1, 0, "")

        # Sort: errors first, then by line
        from .rules import SEVERITY_ORDER

        self.issues.sort(key=lambda i: (-SEVERITY_ORDER[i.rule.severity], i.line))
        return self.issues

    def _add(self, rule: Rule, line: int, col: int, source_line: str) -> None:
        if rule.requires and rule.requires not in self._available:
            return
        if rule.id in self.config.disable:
            return
        if _is_allowed_by_comment(source_line, rule.id):
            return
        sev = self.config.per_rule_severity.get(rule.id)
        if sev:
            rule = replace(rule, severity=sev)
        self.issues.append(
            Issue(rule=rule, line=line, col=col, source_line=source_line)
        )

    def _get_source(self, lineno: int) -> str:
        if 1 <= lineno <= len(self.source_lines):
            return self.source_lines[lineno - 1].rstrip()
        return ""


def lint_source(source: str, filepath: str = "<stdin>", config=None) -> list:
    """Lint Python source code and return list of Issues."""
    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError:
        return []

    lines = source.splitlines()
    checker = SciTeXChecker(lines, filepath=filepath, config=config)
    checker.visit(tree)
    if config and "FM" in config.enable:
        from ._fm_checker import FMChecker

        fm = FMChecker(lines, config)
        fm.visit(tree)
        checker.issues.extend(fm.issues)

    # Plugin-contributed checkers (respect opt-in gating)
    from ._plugin_loader import load_plugins

    _enabled = set(config.enable) if config else set()
    for checker_cls in load_plugins()["checkers"]:
        # Gate FM-category checkers behind config.enable=["FM"]
        cat = getattr(checker_cls, "category", None)
        if cat == "figure" and "FM" not in _enabled:
            continue
        try:
            extra = checker_cls(lines, config)
            extra.visit(tree)
            checker.issues.extend(extra.issues)
        except Exception:
            pass

    return checker.get_issues()


from ._dispatch import lint_file  # noqa: E402,F401  re-export
