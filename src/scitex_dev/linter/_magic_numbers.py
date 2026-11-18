"""STX-S008 — hard-coded analysis parameters (magic numbers) in scripts.

In a SciTeX research project every parameter that shapes a result — a
threshold, a window size, a seed, a significance level, a bootstrap count,
a frequency band — lives in ``config/*.yaml`` and is read from the
``CONFIG`` that ``@stx.session`` injects. This module finds numbers that
are written into the script instead.

What counts as an analysis parameter (flagged):

- a name bound to a number, or to a list/tuple/set/dict of numbers, at ANY
  scope — module, ``main()``, helper function, class body
  (``window_size = 256``, ``BANDS = {"alpha": (8, 13)}``,
  ``alpha: float = 0.05``);
- a keyword argument given a number (``welch(x, fs=512, nperseg=128)``);
- a default in a function signature (``def bandpass(x, low=1.5)``), the
  ``@stx.session`` ``main`` included — its CLI defaults are parameters too;
- a float threshold in a comparison (``if p < 0.01``, ``mask = r > 0.3``);
- a seed, in any form: ``seed=0``, ``random_state=42``, ``np.random.seed(7)``,
  ``default_rng(42)`` — a seed is a parameter even when it is 0 or 1.

What is deliberately NOT flagged (harmless literals):

- 0, 1, -1 and 2 (and their float forms) — indexing, identity, halving;
- positional call arguments (``np.zeros((n, 3))``, ``round(x, 3)``,
  ``plt.subplots(2, 3)``) and arithmetic (``x * 1000``) — dominated by
  shapes, indices, layout and unit conversions;
- integer comparisons (``len(x) > 10``, ``status == 200``) and numerical
  tolerances in comparisons (``abs(a - b) < 1e-12``);
- array-structure and infrastructure keywords (``axis=``, ``ddof=``,
  ``decimals=``, ``indent=``, ``timeout=``, ``n_jobs=``, ...);
- every keyword of a plotting call (``ax.plot(..., alpha=0.3)``) —
  presentation is figrecipe's domain (STX-P007..P009 / STX-FM001);
- private (``_X``) and dunder names, version names, index names, and names
  or keywords carrying a layout / display / identity / tolerance /
  infrastructure token (``n_cols``, ``max_colwidth``, ``n_hash_chars``,
  ``abs_tol``, ``n_workers``, ``timeout_s``);
- async code and classes driving it (UI / browser automation), and the
  test of a conditional choosing between strings (``"p<.001" if p < .001``);
- strings, booleans, ``None``; test files.

A deliberate constant is suppressed per line with ``# stx-allow: STX-S008``.
"""

from __future__ import annotations

import ast

from ._magic_numbers_vocab import (
    _ENUM_BASES,
    _EXEMPT_CALLEES,
    _EXEMPT_KEYWORDS,
    _EXEMPT_TOKENS,
    _LAYOUT_UNIT_SUFFIXES,
    _PLOT_METHODS,
    _PLOT_PARAMS,
    _PLOT_MODULES,
    _PLOT_RECEIVER,
    _SEED_CALLEES,
    _SEED_KEYWORDS,
    _SKIP_NAMES,
    _STYLE_KEYWORDS,
    _TRIVIAL_NUMBERS,
    _UNIT_CONVERSION,
)
from ._rules import lookup as _lk
from ._rules._base import Rule

__all__ = ["check_hardcoded_parameters", "find_hardcoded_parameters"]


def _number(node: ast.AST):
    """The numeric value of a literal (``3``, ``-0.5``, ``+2``), else None."""
    sign = 1
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        sign = -1 if isinstance(node.op, ast.USub) else 1
        node = node.operand
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    ):
        return sign * node.value
    return None


def _is_param_literal(node: ast.AST) -> bool:
    """A non-trivial number, or a pure literal container holding one.

    Dict KEYS are ignored (``{4: "theta"}`` maps codes to labels); only
    values count. Containers mixing in non-literals (names, calls) are not
    treated as parameter literals.
    """
    value = _number(node)
    if value is not None:
        return value not in _TRIVIAL_NUMBERS
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        elts = node.elts
    elif isinstance(node, ast.Dict):
        if any(k is not None and not _is_literal(k) for k in node.keys):
            return False
        elts = node.values
    else:
        return False
    if not elts or not all(_is_literal(e) for e in elts):
        return False
    return any(_is_param_literal(e) for e in elts)


def _is_literal(node: ast.AST) -> bool:
    if _number(node) is not None:
        return True
    if isinstance(node, ast.Constant):
        return True  # str / bytes / bool / None
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return all(_is_literal(e) for e in node.elts)
    if isinstance(node, ast.Dict):
        return all(k is None or _is_literal(k) for k in node.keys) and all(
            _is_literal(v) for v in node.values
        )
    return False


def _is_seed_name(name: str) -> bool:
    low = name.lower()
    return low in _SEED_KEYWORDS or low.endswith("_seed")


def _is_int_literal(node: ast.AST) -> bool:
    value = _number(node)
    return value is not None and isinstance(value, int)


def _exempt_keyword(name: str) -> bool:
    low = name.lower()
    if low in _EXEMPT_KEYWORDS or low in _STYLE_KEYWORDS:
        return True
    if low.endswith(_LAYOUT_UNIT_SUFFIXES):
        return True
    return any(tok in _EXEMPT_TOKENS for tok in low.split("_"))


def _skip_name(name: str) -> bool:
    low = name.lower()
    return (
        name.startswith("_")
        or len(name) == 1  # scratch locals (w, h, k, ...)
        or _UNIT_CONVERSION.match(low) is not None
        or low in _SKIP_NAMES
        or _exempt_keyword(name)
        or "version" in low
        or low.endswith(("idx", "index", "_rc", "_code", "_status"))
    )


def _is_text(node: ast.AST) -> bool:
    return isinstance(node, ast.JoinedStr) or (
        isinstance(node, ast.Constant) and isinstance(node.value, str)
    )


def _is_text_expr(node) -> bool:
    if isinstance(node, ast.IfExp):
        return _is_text_expr(node.body) and _is_text_expr(node.orelse)
    return _is_text(node)


def _returns_only_text(func) -> bool:
    """A formatter: every ``return`` of *func* (not nested defs) yields text."""
    returns = []
    stack = list(func.body)
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        if isinstance(node, ast.Return):
            returns.append(node.value)
        stack.extend(ast.iter_child_nodes(node))
    return bool(returns) and all(v is not None and _is_text_expr(v) for v in returns)


def _option_name(call: ast.Call) -> str:
    """``add_argument("--older-than-days", ...)`` -> ``older_than_days``."""
    for arg in call.args:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            if arg.value.startswith("--") or not arg.value.startswith("-"):
                return arg.value.lstrip("-").replace("-", "_")
    return ""


def _callee_chain(func: ast.AST) -> list:
    """Dotted name parts of a call target, root first (subscripts skipped)."""
    parts = []
    node = func
    while True:
        if isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        elif isinstance(node, ast.Subscript):
            node = node.value
        elif isinstance(node, ast.Call):
            node = node.func
        elif isinstance(node, ast.Name):
            parts.append(node.id)
            break
        else:
            break
    return parts[::-1]


def _is_plotting_call(chain: list) -> bool:
    if not chain:
        return False
    if any(p in _PLOT_MODULES for p in chain):
        return True
    if len(chain) > 1 and _PLOT_RECEIVER.match(chain[0]):
        return True
    return len(chain) > 1 and chain[-1] in _PLOT_METHODS


def _target_names(target: ast.AST) -> list:
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
        # self.threshold = 0.7 / cfg.alpha = 0.05
        return [target.attr]
    return []


def _src(node: ast.AST, lines: list) -> str:
    lineno = getattr(node, "lineno", 0)
    if 1 <= lineno <= len(lines):
        return lines[lineno - 1].rstrip()
    return ""


def _segment(node: ast.AST, source: str) -> str:
    text = ast.get_source_segment(source, node) or ""
    text = " ".join(text.split())
    return text if len(text) <= 60 else text[:57] + "..."


class _Finder(ast.NodeVisitor):
    """Collect ``(node, label)`` pairs for every hard-coded parameter."""

    def __init__(self, source: str):
        self.source = source
        self.found: list = []
        self._enum_depth = 0
        # >0 inside regions whose literals are never analysis parameters:
        # async code (UI / browser / network automation), classes that drive
        # it, and the test of a display-string conditional.
        self._quiet = 0

    def _hit(self, node: ast.AST, label: str) -> None:
        if not self._quiet:
            self.found.append((node, label))

    def _visit_quietly(self, node: ast.AST) -> None:
        self._quiet += 1
        self.visit(node)
        self._quiet -= 1

    # -- bindings --

    def visit_Assign(self, node: ast.Assign) -> None:
        if not self._enum_depth and _is_param_literal(node.value):
            for target in node.targets:
                for name in _target_names(target):
                    if not _skip_name(name):
                        self._hit(node, f"{name} = {_segment(node.value, self.source)}")
        elif not self._enum_depth:
            self._seed_binding(node.targets, node.value, node)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None and not self._enum_depth:
            if _is_param_literal(node.value):
                for name in _target_names(node.target):
                    if not _skip_name(name):
                        self._hit(node, f"{name} = {_segment(node.value, self.source)}")
            else:
                self._seed_binding([node.target], node.value, node)
        self.generic_visit(node)

    def _seed_binding(self, targets, value, node) -> None:
        # SEED = 0 — a seed is a parameter even when trivial.
        if not _is_int_literal(value):
            return
        for target in targets:
            for name in _target_names(target):
                if _is_seed_name(name):
                    self._hit(node, f"{name} = {_segment(value, self.source)}")

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        is_enum = any(
            (isinstance(b, ast.Name) and b.id in _ENUM_BASES)
            or (isinstance(b, ast.Attribute) and b.attr in _ENUM_BASES)
            for b in node.bases
        )
        drives_async = any(isinstance(b, ast.AsyncFunctionDef) for b in node.body)
        self._enum_depth += is_enum
        self._quiet += drives_async
        self.generic_visit(node)
        self._quiet -= drives_async
        self._enum_depth -= is_enum

    # -- signatures --

    def _check_defaults(self, args: ast.arguments) -> None:
        positional = list(getattr(args, "posonlyargs", [])) + list(args.args)
        pairs = list(
            zip(positional[len(positional) - len(args.defaults) :], args.defaults)
        )
        pairs += [(a, d) for a, d in zip(args.kwonlyargs, args.kw_defaults) if d]
        for arg, default in pairs:
            name = arg.arg
            seed = _is_seed_name(name) and _is_int_literal(default)
            if seed or (_is_param_literal(default) and not _skip_name(name)):
                self._hit(default, f"{name}={_segment(default, self.source)}")

    def visit_FunctionDef(self, node) -> None:
        # A helper taking an axes / figure is a plotting helper: its defaults
        # (``def box(ax, x, y, fontsize=8)``) are presentation.
        params = {a.arg for a in node.args.args + node.args.kwonlyargs}
        # A formatter (``def fmt(v, nd=3): return f"{v:.{nd}f}"``) is display.
        if not params & _PLOT_PARAMS and not _returns_only_text(node):
            self._check_defaults(node.args)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        # Numerical analysis is not written as coroutines; async bodies are
        # UI / browser / network orchestration (``await page.wait(0.5)``).
        self._visit_quietly_children(node)

    def _visit_quietly_children(self, node: ast.AST) -> None:
        self._quiet += 1
        self.generic_visit(node)
        self._quiet -= 1

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self._check_defaults(node.args)
        self.generic_visit(node)

    # -- calls --

    def visit_Call(self, node: ast.Call) -> None:
        chain = _callee_chain(node.func)
        callee = chain[-1] if chain else ""
        if callee in _SEED_CALLEES:
            for arg in node.args:
                if _is_int_literal(arg):
                    self._hit(arg, f"{callee}({_segment(arg, self.source)})")
        plotting = (
            _is_plotting_call(chain)
            or any(kw.arg in _STYLE_KEYWORDS for kw in node.keywords)
            # a helper handed an axes / figure draws: ``_draw_scalebar(ax, x=60)``
            or any(
                isinstance(a, ast.Name) and _PLOT_RECEIVER.match(a.id)
                for a in node.args
            )
        )
        # An argparse option is judged by its own name (``--timeout``).
        option = _option_name(node) if callee == "add_argument" else ""
        if option and _exempt_keyword(option):
            plotting = True
        for kw in node.keywords:
            if kw.arg is None:
                continue
            if _is_seed_name(kw.arg) and _is_int_literal(kw.value):
                self._hit(kw.value, f"{kw.arg}={_segment(kw.value, self.source)}")
                continue
            if plotting or callee in _EXEMPT_CALLEES:
                continue
            if _exempt_keyword(kw.arg):
                continue
            if _is_param_literal(kw.value):
                self._hit(kw.value, f"{kw.arg}={_segment(kw.value, self.source)}")
        self.generic_visit(node)

    # -- thresholds --

    def visit_IfExp(self, node: ast.IfExp) -> None:
        # ``"p<0.001" if p < 0.001 else f"p={p:.3f}"`` / ``"white" if v > 0.45
        # else "black"``: a comparison choosing between strings is display.
        if _is_text(node.body) and _is_text(node.orelse):
            self._visit_quietly(node.test)
            self.visit(node.body)
            self.visit(node.orelse)
            return
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        for operand in [node.left, *node.comparators]:
            value = _number(operand)
            # |v| <= 1e-6 is a numerical tolerance (``gap < best - 1e-12``).
            if (
                isinstance(value, float)
                and value not in _TRIVIAL_NUMBERS
                and abs(value) > 1e-6
            ):
                self._hit(operand, f"threshold {_segment(node, self.source)}")
        self.generic_visit(node)


def find_hardcoded_parameters(tree: ast.AST, source: str) -> list:
    """Return ``(node, label)`` per source line holding hard-coded parameters.

    One finding per line: ``welch(x, fs=512, nperseg=128)`` is reported once
    as ``fs=512, nperseg=128`` (anchored at the first value), so a dense
    call does not drown the report.
    """
    finder = _Finder(source)
    finder.visit(tree)
    by_line: dict = {}
    for node, label in finder.found:
        lineno = getattr(node, "lineno", 0)
        first, labels = by_line.setdefault(lineno, (node, []))
        if label not in labels:
            labels.append(label)
    return [
        (node, ", ".join(labels)) for _, (node, labels) in sorted(by_line.items())
    ]


def check_hardcoded_parameters(checker, tree: ast.AST) -> None:
    """Emit STX-S008 for each hard-coded parameter (one finding per value)."""
    base = _lk("STX-S008")
    if base is None:
        return
    source = "\n".join(checker.source_lines)
    for node, label in find_hardcoded_parameters(tree, source):
        rule = Rule(
            id=base.id,
            severity=base.severity,
            category=base.category,
            message=(
                f"Hard-coded parameter `{label}` — move it to config/*.yaml "
                "and read it from CONFIG"
            ),
            suggestion=base.suggestion,
            requires=base.requires,
            scope=base.scope,
        )
        checker._add(
            rule,
            node.lineno,
            node.col_offset,
            _src(node, checker.source_lines),
        )


# EOF
