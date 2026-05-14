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

    # Mock-related module / symbol names. The no-mock rule is intentionally
    # exception-free: any presence of these in a SciTeX codebase is a
    # violation.
    _MOCK_MODULES = frozenset({"mock", "unittest.mock", "pytest_mock"})
    _MOCK_SYMBOLS = frozenset(
        {
            "Mock",
            "MagicMock",
            "AsyncMock",
            "NonCallableMock",
            "NonCallableMagicMock",
            "PropertyMock",
            "patch",
            "mock_open",
            "create_autospec",
            "sentinel",
            "ANY",
            "MockerFixture",
        }
    )
    _MOCK_FIXTURE_PARAMS = frozenset({"mocker", "monkeypatch"})

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

        # NM001 — no-mock imports (no exceptions)
        if module_name in self._MOCK_MODULES:
            self._add(rules.NM001, node.lineno, node.col_offset, line)

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

        # NM001 — no-mock imports (no exceptions)
        # `from unittest.mock import ...`, `from mock import ...`,
        # `from pytest_mock import MockerFixture`, `from unittest import mock`.
        if module in self._MOCK_MODULES:
            self._add(rules.NM001, node.lineno, node.col_offset, line)
        elif module == "unittest":
            for alias in node.names:
                if alias.name == "mock":
                    self._add(rules.NM001, node.lineno, node.col_offset, line)
                    break

        # NM003 — mock symbols imported by name (Mock, MagicMock, patch, ...).
        # Catches `from somewhere import Mock` regardless of source module.
        for alias in node.names:
            if alias.name in self._MOCK_SYMBOLS:
                self._add(rules.NM003, node.lineno, node.col_offset, line)
                break

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

    # -- Numeric-literal visitor (NL001) --

    def visit_Constant(self, node: ast.Constant) -> None:
        """Flag integer literals ≥ 1_000 written without `_` separators
        (STX-NL001 / PEP 515 — see
        `_skills/general/03_interface_01_python-api/14_numeric-literals.md`).

        Carve-outs:
        - bool / float / complex / str / bytes / None — skipped.
        - abs(value) < 1000 — under threshold.
        - source segment already contains `_` — already conformant.
        - source segment is non-decimal (`0x…`, `0o…`, `0b…`) — left
          alone; the PEP applies but the rule keeps its scope narrow.
        - `# noqa: STX-NL001` on the line — explicit suppression for
          identifiers that read as a whole (years, ports, codes).
        """
        # Only int literals; explicitly reject bool (`True is 1`).
        if not isinstance(node.value, int) or isinstance(node.value, bool):
            self.generic_visit(node)
            return
        if abs(node.value) < 1000:
            self.generic_visit(node)
            return
        # Need the original source segment to see if `_` was used —
        # `node.value` normalises `21_600` and `21600` to the same int.
        src = ast.get_source_segment("\n".join(self.source_lines), node)
        if src is None or "_" in src:
            self.generic_visit(node)
            return
        if src.startswith(("0x", "0o", "0b", "0X", "0O", "0B")):
            # Non-decimal — same PEP applies but the rule keeps its
            # scope narrow to base-10 quantities for now.
            self.generic_visit(node)
            return
        line = (
            self.source_lines[node.lineno - 1]
            if node.lineno - 1 < len(self.source_lines)
            else ""
        )
        if _is_allowed_by_comment(line, "STX-NL001"):
            self.generic_visit(node)
            return
        self._add(rules.NL001, node.lineno, node.col_offset, line)
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

    # -- stx.io path checking (delegated to _path_checker) --

    def _check_stx_io_path(self, node: ast.Call) -> None:
        from ._path_checker import check_stx_io_path

        check_stx_io_path(self, node)

    # -- Function/decorator visitors --

    @property
    def _REQUIRED_INJECTED(self):
        return set(self.config.required_injected)

    # Names that count as a "real" pytest-style assertion construct when
    # used inside a `test_*` function body. Detected as either a Call
    # (e.g. `pytest.raises(ValueError)`) or a With-context item.
    _TQ001_PYTEST_ASSERT_ATTRS = frozenset(
        {"raises", "warns", "fail", "deprecated_call", "skip", "xfail"}
    )

    # State-mutation method names that flag a session/module-scope fixture.
    _TQ004_MUTATION_ATTRS = frozenset(
        {
            "insert",
            "write",
            "write_text",
            "write_bytes",
            "writelines",
            "append",
            "update",
            "set",
            "save",
            "delete",
            "remove",
            "unlink",
            "mkdir",
            "rmdir",
            "touch",
        }
    )

    # Resource-acquisition call names that flag a `return`-not-`yield` fixture.
    _TQ005_RESOURCE_NAMES = frozenset(
        {"open", "connect", "urlopen", "socket", "Session", "TemporaryFile"}
    )

    def _tq001_is_test_file(self) -> bool:
        """True iff the current file looks like a pytest test file.

        Pytest's own collection rules (filename `test_*.py` / `*_test.py`,
        or located under a `tests/` directory) are the same signal we use
        here — we only want TQ001 firing on files pytest will actually run.
        """
        parts = Path(self.filepath).parts
        name = Path(self.filepath).name
        return (
            name.startswith("test_")
            or name.endswith("_test.py")
            or any(seg in {"tests", "test"} for seg in parts)
        )

    @classmethod
    def _tq_is_pytest_fixture(cls, node) -> tuple[bool, str | None]:
        """Return (is_fixture, scope) for a function. scope is one of
        'function' / 'class' / 'module' / 'package' / 'session' / None
        (default = function when not specified)."""
        for deco in node.decorator_list:
            # @pytest.fixture (bare)
            if (
                isinstance(deco, ast.Attribute)
                and deco.attr == "fixture"
                and isinstance(deco.value, ast.Name)
                and deco.value.id == "pytest"
            ):
                return True, "function"
            # @fixture (bare, after `from pytest import fixture`)
            if isinstance(deco, ast.Name) and deco.id == "fixture":
                return True, "function"
            # @pytest.fixture(scope="session", ...) or @fixture(...)
            if isinstance(deco, ast.Call):
                f = deco.func
                is_pytest_fixture = (
                    isinstance(f, ast.Attribute)
                    and f.attr == "fixture"
                    and isinstance(f.value, ast.Name)
                    and f.value.id == "pytest"
                ) or (isinstance(f, ast.Name) and f.id == "fixture")
                if is_pytest_fixture:
                    scope = "function"
                    for kw in deco.keywords:
                        if kw.arg == "scope" and isinstance(kw.value, ast.Constant):
                            scope = str(kw.value.value)
                    return True, scope
        return False, None

    @staticmethod
    def _tq_has_parametrize(node) -> bool:
        """True iff the function is decorated with a `parametrize` form:
        `@pytest.mark.parametrize(...)`, `@mark.parametrize(...)`,
        or bare `@parametrize(...)` after `from pytest.mark import parametrize`.
        """
        for deco in node.decorator_list:
            f = deco.func if isinstance(deco, ast.Call) else deco
            if isinstance(f, ast.Attribute) and f.attr == "parametrize":
                # @pytest.mark.parametrize  (Attribute on Attribute)
                if isinstance(f.value, ast.Attribute) and f.value.attr == "mark":
                    return True
                # @mark.parametrize  (Attribute on Name "mark")
                if isinstance(f.value, ast.Name) and f.value.id == "mark":
                    return True
            # @parametrize  (bare Name)
            if isinstance(f, ast.Name) and f.id == "parametrize":
                return True
        return False

    @classmethod
    def _tq004_body_mutates_state(cls, node) -> bool:
        """True iff the function body contains a state-mutation call
        (insert/write/append/update/set/save method, or a writable open)."""
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Call):
                continue
            f = sub.func
            if isinstance(f, ast.Attribute) and f.attr in cls._TQ004_MUTATION_ATTRS:
                return True
            # `open(path, "w")` / `open(path, "a")`
            if (
                isinstance(f, ast.Name)
                and f.id == "open"
                and len(sub.args) >= 2
                and isinstance(sub.args[1], ast.Constant)
                and isinstance(sub.args[1].value, str)
                and any(m in sub.args[1].value for m in ("w", "a", "x", "+"))
            ):
                return True
        return False

    @classmethod
    def _tq005_acquires_resource(cls, node) -> bool:
        """True iff the body has a call to a resource-acquiring constructor."""
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Call):
                continue
            f = sub.func
            if isinstance(f, ast.Name) and f.id in cls._TQ005_RESOURCE_NAMES:
                return True
            if isinstance(f, ast.Attribute) and f.attr in cls._TQ005_RESOURCE_NAMES:
                return True
        return False

    @staticmethod
    def _tq005_returns_not_yields(node) -> bool:
        """True iff the body has a top-level `return <expr>` AND no `yield`
        anywhere. Returning a freshly-acquired resource bypasses cleanup."""
        has_yield = False
        has_return_value = False
        for sub in ast.walk(node):
            if isinstance(sub, (ast.Yield, ast.YieldFrom)):
                has_yield = True
                break
            if isinstance(sub, ast.Return) and sub.value is not None:
                has_return_value = True
        return has_return_value and not has_yield

    @staticmethod
    def _tq006_body_has_toplevel_if(node) -> bool:
        """True iff the function body has an `if` at the top level (not
        nested inside another statement)."""
        for stmt in node.body:
            if isinstance(stmt, ast.If):
                return True
        return False

    @staticmethod
    def _tq003_name_word_count(name: str) -> int:
        """Count the word-tokens after the `test_` prefix. Splits on `_`,
        drops empties, drops leading 'test'."""
        if not name.startswith("test_"):
            return -1
        rest = name[len("test_") :]
        tokens = [t for t in rest.split("_") if t]
        return len(tokens)

    def _tq002_missing_aaa_markers(self, node) -> str:
        """Return a short reason string if the test body is missing AAA
        marker comments (`# Arrange`, `# Act`, `# Assert`) in order, or
        an empty string if all three are present and ordered.

        Markers are matched case-insensitively. Descriptive text after
        the keyword is allowed (`# Arrange: build the fixture`).
        """
        start = node.lineno  # 1-indexed
        end = getattr(node, "end_lineno", None) or len(self.source_lines)
        # source_lines is 0-indexed; the function body lives at
        # indices [start, end). The decorator-line case is rare for tests.
        body = self.source_lines[start:end]
        seen = {"arrange": -1, "act": -1, "assert": -1}
        for i, raw in enumerate(body):
            text = raw.strip()
            if not text.startswith("#"):
                continue
            # Strip "#" + whitespace.
            comment = text.lstrip("#").strip().lower()
            for kw in seen:
                if seen[kw] != -1:
                    continue
                # Match "arrange" / "arrange:" / "arrange — note" forms.
                if (
                    comment == kw
                    or comment.startswith(kw + ":")
                    or comment.startswith(kw + " ")
                ):
                    seen[kw] = i
                    break
        missing = [k.capitalize() for k, v in seen.items() if v == -1]
        if missing:
            return "missing " + "/".join(missing) + " marker"
        # Order check: arrange < act < assert.
        a, b, c = seen["arrange"], seen["act"], seen["assert"]
        if not (a < b < c):
            return "AAA markers are out of order"
        return ""

    @classmethod
    def _tq007_count_assertions(cls, node) -> int:
        """Count assertions in a function body:
        - every `ast.Assert` (recursive, includes inside if/for/while/with);
        - every call to `pytest.raises` / `pytest.warns` / `pytest.fail` /
          `pytest.deprecated_call` (treated as one assertion each).
        """
        count = 0
        for sub in ast.walk(node):
            if isinstance(sub, ast.Assert):
                count += 1
                continue
            if isinstance(sub, ast.Call):
                f = sub.func
                if (
                    isinstance(f, ast.Attribute)
                    and f.attr in cls._TQ001_PYTEST_ASSERT_ATTRS
                ):
                    count += 1
                elif isinstance(f, ast.Name) and f.id in cls._TQ001_PYTEST_ASSERT_ATTRS:
                    count += 1
        return count

    @classmethod
    def _tq001_function_has_assertion(cls, node) -> bool:
        """True iff a `test_*` body contains a real assertion construct.

        Counts:
          - any `ast.Assert` anywhere in the body (including nested);
          - any call to `pytest.raises(...)` / `pytest.warns(...)` /
            `pytest.fail(...)` / `pytest.deprecated_call(...)` /
            `pytest.skip(...)` / `pytest.xfail(...)`;
          - any `with pytest.raises(...)` / `with pytest.warns(...)`
            context-manager use.
        """
        for sub in ast.walk(node):
            if isinstance(sub, ast.Assert):
                return True
            if isinstance(sub, ast.Call):
                f = sub.func
                if (
                    isinstance(f, ast.Attribute)
                    and f.attr in cls._TQ001_PYTEST_ASSERT_ATTRS
                ):
                    return True
                # Bare `raises(...)` after `from pytest import raises`.
                if isinstance(f, ast.Name) and f.id in cls._TQ001_PYTEST_ASSERT_ATTRS:
                    return True
        return False

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        # NM002 — `mocker` / `monkeypatch` fixture parameters (no exceptions).
        for arg in (
            list(node.args.args)
            + list(node.args.kwonlyargs)
            + list(getattr(node.args, "posonlyargs", []))
        ):
            if arg.arg in self._MOCK_FIXTURE_PARAMS:
                line = self._get_source(arg.lineno)
                self._add(rules.NM002, arg.lineno, arg.col_offset, line)
        # TQ001 / TQ002 / TQ003 / TQ006 / TQ007 — test-function rules
        # (gated on test files).
        if node.name.startswith("test_") and self._tq001_is_test_file():
            # TQ001 — no assertion → green-bar theater.
            assertion_count = self._tq007_count_assertions(node)
            if assertion_count == 0:
                line = self._get_source(node.lineno)
                self._add(rules.TQ001, node.lineno, node.col_offset, line)
            # TQ007 — more than one assertion in one test (when first
            # assert fails, the rest is silently skipped).
            elif assertion_count > 1:
                line = self._get_source(node.lineno)
                self._add(rules.TQ007, node.lineno, node.col_offset, line)
            # TQ002 — AAA marker comments must be present and in order.
            aaa_reason = self._tq002_missing_aaa_markers(node)
            if aaa_reason:
                line = self._get_source(node.lineno)
                self._add(rules.TQ002, node.lineno, node.col_offset, line)
            # TQ003 — test name has <3 word-tokens after `test_`.
            if self._tq003_name_word_count(node.name) < 3:
                line = self._get_source(node.lineno)
                self._add(rules.TQ003, node.lineno, node.col_offset, line)
            # TQ006 — top-level if/else inside a parametrized test.
            if self._tq_has_parametrize(node) and self._tq006_body_has_toplevel_if(
                node
            ):
                line = self._get_source(node.lineno)
                self._add(rules.TQ006, node.lineno, node.col_offset, line)

        # TQ004 / TQ005 — fixture rules (gated on test files; any function
        # with @pytest.fixture, name doesn't have to start with `test_`).
        if self._tq001_is_test_file():
            is_fixture, scope = self._tq_is_pytest_fixture(node)
            if is_fixture:
                # TQ004 — session/module scope + state-mutation body.
                if scope in {"session", "module", "package"} and (
                    self._tq004_body_mutates_state(node)
                ):
                    line = self._get_source(node.lineno)
                    self._add(rules.TQ004, node.lineno, node.col_offset, line)
                # TQ005 — resource acquisition + return-not-yield.
                if self._tq005_acquires_resource(
                    node
                ) and self._tq005_returns_not_yields(node):
                    line = self._get_source(node.lineno)
                    self._add(rules.TQ005, node.lineno, node.col_offset, line)

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
                    and deco.value.id in ("stx", "scitex", "scitex_io")
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
                    and deco.func.value.id in ("stx", "scitex", "scitex_io")
                    and deco.func.attr == "module"
                ):
                    return True
            # @stx.module (bare, no parens)
            if isinstance(deco, ast.Attribute):
                if (
                    isinstance(deco.value, ast.Name)
                    and deco.value.id in ("stx", "scitex", "scitex_io")
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

    def _add(self, rule: Rule | None, line: int, col: int, source_line: str) -> None:
        if rule is None:
            return
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
