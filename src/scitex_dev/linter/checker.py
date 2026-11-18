"""AST-based checker that detects SciTeX anti-patterns."""

from __future__ import annotations

__all__ = ["Issue", "is_script", "lint_file", "lint_source"]

import ast
from dataclasses import replace

from . import rules
from ._checks import (
    CallChecksMixin,
    ErrorHandlingMixin,
    ImportChecksMixin,
    LiteralChecksMixin,
    TestQualityMixin,
    own_scitex_package,
)
from ._issue import Issue
from ._rules import lookup as _lk
from ._source_helpers import _is_allowed_by_comment, is_script
from .rules import Rule


class SciTeXChecker(
    ImportChecksMixin,
    CallChecksMixin,
    ErrorHandlingMixin,
    TestQualityMixin,
    LiteralChecksMixin,
    ast.NodeVisitor,
):
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
        self._own_package = own_scitex_package(filepath)  # for STX-I008
        self._is_script = is_script(filepath, self.config)
        self._func_depth = 0  # >0 means inside a function body
        self._tree = None  # set by visit_Module; STX-S008 scans it post-visit
        # STX-P010 — top-level figrecipe usage inside an @stx.session
        # module. Recorded during the visit (import + call sites) and
        # emitted in get_issues() ONCE the whole module is seen, because
        # the `import figrecipe as fr` line is visited BEFORE the
        # `@stx.session def main` further down — we can't know the module
        # is session-decorated at import-visit time. (line, col, src) tuples.
        self._figrecipe_usages: list = []
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
        groups = _plugins.get("call_rule_groups", {})
        self._plugin_call_rule_groups = {
            key: tuple(
                rule
                for rule in group
                if rule.category not in _CAT_ENABLE
                or _CAT_ENABLE[rule.category] in _enabled
            )
            for key, group in groups.items()
        }
        self._plugin_checkers = _plugins["checkers"]
        self._plugin_axes_hints = _plugins.get("axes_hints", {})

    # -- Module visitor (STX-S008 needs the whole tree) --

    def visit_Module(self, node: ast.Module) -> None:
        self._tree = node
        self.generic_visit(node)

    # -- Assignment visitors --

    def visit_Assign(self, node: ast.Assign) -> None:
        from ._naming_checker import check_assignment

        check_assignment(self, node)
        self.generic_visit(node)

    # -- Function/decorator visitors --

    @property
    def _REQUIRED_INJECTED(self):
        return set(self.config.required_injected)

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
            # TQ001 — no assertion (skip/skipif-decorated tests exempt).
            assertion_count = self._tq007_count_assertions(node)
            if assertion_count == 0 and not self._tq001_is_skip_decorated(node):
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
        """Check that @stx.session function declares all INJECTED parameters.

        Considers positional, positional-only, AND keyword-only args — the
        injected pattern can legitimately live behind a ``*`` separator
        (e.g. ``def main(data: str, *, CONFIG=stx.session.INJECTED, ...)``).
        The previous ``args.args``-only scan missed kwonly INJECTED decls
        and produced false-positive S006s on neurovista-style scripts.

        Argument *values/annotations* are never dereferenced here — only
        the bare ``arg.arg`` name string is read. This avoids the
        ``AttributeError: 'NoneType' object has no attribute 'id'`` NPE
        the legacy ``scitex._linter_plugin`` S006 raised on annotated
        injected params (#60).
        """
        declared = {
            arg.arg
            for arg in (
                list(node.args.args)
                + list(node.args.kwonlyargs)
                + list(getattr(node.args, "posonlyargs", []))
            )
        }
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

    def is_research_script(self) -> bool:
        """The ``research-script`` scope verdict (valid after the visit)."""
        from ._research_scope import is_research_script

        return is_research_script(
            self.filepath,
            self.config,
            has_entry_decorator=(
                self._has_session_decorator or self._has_module_decorator
            ),
        )

    def get_issues(self) -> list:
        """Return all issues, including post-visit structural checks."""
        # Rule scopes (plugin SPI): drop `scope="research-script"` findings
        # — from engine call rules AND plugin checkers, both already in
        # self.issues — unless this module is a research script. Decided
        # here, once the whole module is seen, because the @stx.session
        # main usually sits below the helpers that do the I/O.
        from ._research_scope import apply_scopes

        self.issues = apply_scopes(
            self.issues, research_script=self.is_research_script()
        )
        # STX-S009 / STX-S010 — research script-organization (path/filename
        # rules). They target files UNDER a configured script dir, which
        # is_script() deliberately excludes, so they run BEFORE the is_script
        # early-return and are gated on the research project-type instead.
        if "research" in (getattr(self.config, "project_types", None) or ()):
            from ._rules._script_organization import check_script_organization

            check_script_organization(self)

        # STX-S008 — hard-coded analysis parameters. Runs for plain scripts
        # AND research scripts: a research project's analysis code lives
        # under `scripts/`, which is_script() excludes, so the research-script
        # verdict (decided only after the whole module is seen) is needed too.
        from ._research_scope import is_test_file

        if (
            self._tree is not None
            and not is_test_file(self.filepath)
            and (self._is_script or self.is_research_script())
        ):
            from ._magic_numbers import check_hardcoded_parameters

            check_hardcoded_parameters(self, self._tree)
            self._tree = None  # idempotent if get_issues() is called again

        from ._severity_promotion import finalize_issues

        if not self._is_script:
            # NOT a bare `return self.issues`: the category-severity floor must
            # run here too, or figrecipe plugin-emitted figure/plot rules stay
            # `warning` for every file under `scripts/`. See finalize_issues.
            self.issues = finalize_issues(self.issues, self.config)
            return self.issues

        if not self._has_main_guard:
            self._add(_lk("STX-S002"), 1, 0, "")

        if self._has_main_guard and not (
            self._has_session_decorator or self._has_module_decorator
        ):
            self._add(_lk("STX-S001"), 1, 0, "")

        if self._has_main_guard and not self._has_stx_import:
            self._add(_lk("STX-S005"), 1, 0, "")

        # STX-P010 — top-level figrecipe used inside an @stx.session module.
        # Only emit when the module actually declares a session-decorated
        # main; otherwise top-level figrecipe is the *correct* API (e.g. a
        # plain plotting script or library helper) and must NOT be flagged.
        if self._has_session_decorator and self._figrecipe_usages:
            p010 = _lk("STX-P010")
            for line, col, src in self._figrecipe_usages:
                self._add(p010, line, col, src)

        # Category-severity floor + sort. Same helper as the early-return
        # above, so both exit paths finalize identically.
        self.issues = finalize_issues(self.issues, self.config)
        return self.issues

    def _add(self, rule: Rule | None, line: int, col: int, source_line: str) -> None:
        if rule is None:
            return
        if rule.requires and not self._available.get(rule.requires, False):
            # Pillar-0 fail-loud (#TBD): tally the silent-skip so the
            # health module can emit an L2 stderr summary the first
            # time the count goes non-zero. Without this the
            # `requires=` gate evaporates IO0xx coverage with zero
            # indication — exactly the 2026-06-12 ripple-wm class.
            try:
                from ._health import record_rule_skip

                record_rule_skip(rule.requires)
            except Exception:  # pragma: no cover
                pass
            return
        if rule.id in self.config.disable:
            return
        if _is_allowed_by_comment(source_line, rule.id):
            return
        sev = self.config.per_rule_severity.get(rule.id)
        if not sev:
            # Pillar 3 (#TBD) — category-wide severity override (e.g.
            # research project-type flips io/path from warning→error).
            # Per-rule override (above) still wins; category map is the
            # floor not the ceiling. See LinterConfig.
            cat_override = getattr(self.config, "category_severity_override", {}) or {}
            sev = cat_override.get(rule.category)
        if sev:
            rule = replace(rule, severity=sev)
        self.issues.append(
            Issue(rule=rule, line=line, col=col, source_line=source_line)
        )

    def _get_source(self, lineno: int) -> str:
        if 1 <= lineno <= len(self.source_lines):
            return self.source_lines[lineno - 1].rstrip()
        return ""


def lint_source(
    source: str, filepath: str = "<stdin>", config=None, plugins=None
) -> list:
    """Lint Python source code and return list of Issues.

    ``plugins`` is the plugin-payload seam (defaults to ``load_plugins()``);
    tests pass a hand-rolled payload to drive the fail-loud path without
    patching the loader (PA-306: real fakes, no monkeypatch).
    """
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

    payload = load_plugins()
    plugin_checkers = list(payload["checkers"])
    if plugins is not None:
        # The injection seam may select optional checkers, but cannot remove
        # mandatory source coverage from the actual installed owner.
        plugin_checkers = [
            cls for cls in plugin_checkers if getattr(cls, "mandatory", False)
        ]
        plugin_checkers.extend(
            cls for cls in plugins["checkers"] if cls not in plugin_checkers
        )
    _enabled = set(config.enable) if config else set()
    for checker_cls in plugin_checkers:
        # Gate FM-category checkers behind config.enable=["FM"]
        cat = getattr(checker_cls, "category", None)
        if cat == "figure" and "FM" not in _enabled:
            continue
        try:
            # Pass the RESOLVED config (never None): SciTeXChecker defaults a
            # None config via load_config(), but plugin checkers deref
            # self.config.disable directly — a raw None here crashes them.
            if getattr(checker_cls, "accepts_filepath", False):
                extra = checker_cls(lines, checker.config, filepath=filepath)
            else:
                extra = checker_cls(lines, checker.config)
            extra.visit(tree)
            checker.issues.extend(extra.issues)
        except Exception as exc:
            _name = getattr(checker_cls, "__name__", repr(checker_cls))
            from ._plugin_loader import LinterPluginError

            raise LinterPluginError(
                f"linter checker {_name} failed for {filepath}: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

    # File-level exemption pragmas (see `_exemptions.py`) apply to
    # engine AND plugin findings; malformed pragmas surface as STX-EX001.
    from ._exemptions import apply_file_exemptions

    return apply_file_exemptions(checker.get_issues(), source, tree)


from ._dispatch import lint_file
