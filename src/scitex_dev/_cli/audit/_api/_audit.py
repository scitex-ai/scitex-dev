"""Static auditor for SciTeX Python APIs — engine + rule definitions.

Rules cover the `(A)`-marked items from
`scitex-python/src/scitex/_skills/general/03_interface_01_python-api/12_audit-checklist.md`.

Numbering: `PA<§><idx>` (e.g. PA101 = §1 rule 01). Mirrors the `S<n>` / `M<n>`
rule-numbering used elsewhere in scitex-dev.
"""

from __future__ import annotations

import ast
import importlib.metadata as im
import importlib.util
from dataclasses import dataclass
from pathlib import Path

import click


@dataclass(frozen=True)
class Rule:
    code: str
    section: str
    message: str
    slug: str = ""  # short, human-readable kebab-case name


RULES: dict[str, Rule] = {
    r.code: r
    for r in [
        # §1 Naming and visibility
        Rule("PA101", "§1", "`__all__` is missing from __init__.py", "all-missing"),
        Rule(
            "PA102",
            "§1",
            "name listed in __all__ is not bound in __init__.py",
            "all-name-unbound",
        ),
        Rule(
            "PA103",
            "§1",
            "name in __all__ starts with underscore",
            "all-private-name",
        ),
        Rule(
            "PA104",
            "§1",
            "third-party symbol is re-exported via __all__",
            "all-third-party",
        ),
        # §2 Version strategy
        Rule(
            "PA201",
            "§2",
            "`__version__` is missing from __all__",
            "version-not-in-all",
        ),
        Rule(
            "PA202",
            "§2",
            "`__version__` not derived from importlib.metadata.version(...)",
            "version-not-from-metadata",
        ),
        Rule(
            "PA203",
            "§2",
            'fallback for __version__ should be "0.0.0+local"',
            "version-fallback-wrong",
        ),
        # §3 Lazy imports / optional deps
        Rule(
            "PA301",
            "§3",
            "top-level `import` outside try/except may break on missing optional dep",
            "top-level-optional-import",
        ),
        Rule(
            "PA304",
            "§3",
            "umbrella import `scitex.<sub>` / `import scitex` inside standalone "
            "source — drags the umbrella `__init__.py` and its lazy re-export "
            "machinery into every call. Use `scitex_<sub>` (peer standalone) "
            "instead. See _skills/general/03_interface_01_python-api/"
            "11_import-conventions.md.",
            "umbrella-import-in-standalone",
        ),
        Rule(
            "PA305",
            "§3",
            "module imports `playwright.async_api` (live browser automation) "
            "but does not call `capture_debug_artifacts_async` — every "
            "decision point in a Playwright flow must capture screenshot + "
            "HTML so selector regressions are diagnosable post-mortem. See "
            "`_skills/general/02_package_09_browser-automation-debugging.md`. "
            "Wire via `from scitex_browser.debugging import "
            "capture_debug_artifacts_async`.",
            "playwright-without-debug-capture",
        ),
        # §5 Type hints
        Rule(
            "PA501",
            "§5",
            "`from __future__ import annotations` is missing",
            "missing-future-annotations",
        ),
    ]
}


@dataclass
class Violation:
    rule: str
    where: str
    detail: str

    def format(self) -> str:
        r = RULES.get(self.rule)
        section = r.section if r else "?"
        slug = f" {r.slug}" if r and r.slug else ""
        return f"  [{self.rule} {section}{slug}] {self.where}: {self.detail}"


# Heuristic: imports from these packages are "third-party" — symbols pulled
# from them and re-exported via __all__ violate PA104.
_THIRD_PARTY_ROOTS = frozenset(
    {
        "numpy",
        "np",
        "pandas",
        "pd",
        "torch",
        "scipy",
        "sklearn",
        "matplotlib",
        "plotly",
        "h5py",
        "xarray",
        "polars",
    }
)

# Stdlib roots whose top-level `import x` is benign and should not trigger
# PA301 even outside try/except.
_STDLIB_SAFE_ROOTS = frozenset(
    {
        "os",
        "sys",
        "io",
        "re",
        "json",
        "logging",
        "pathlib",
        "typing",
        "warnings",
        "functools",
        "itertools",
        "dataclasses",
        "enum",
        "collections",
        "contextlib",
        "inspect",
        "importlib",
        "abc",
        "math",
        "datetime",
        "time",
        "string",
        "textwrap",
        "shutil",
        "tempfile",
        "subprocess",
        "ast",
        "copy",
        "weakref",
        "traceback",
        "uuid",
        "hashlib",
        "base64",
        "struct",
        "operator",
        "asyncio",
        "socket",
        "threading",
        "queue",
        "select",
        "signal",
        "fcntl",
        "termios",
        "platform",
        "getpass",
        "argparse",
        "csv",
        "shlex",
        "glob",
        "fnmatch",
        "pickle",
        "random",
        "secrets",
        "ssl",
        "urllib",
        "http",
        "email",
        "html",
        "xml",
        "configparser",
        "tomllib",
        "zipfile",
        "tarfile",
        "gzip",
        "bz2",
        "lzma",
    }
)


def _import_name(distribution: str) -> str:
    """`scitex-io` → `scitex_io` (canonical SciTeX convention)."""
    return distribution.replace("-", "_")


def _locate_init(import_name: str) -> Path | None:
    spec = importlib.util.find_spec(import_name)
    if spec is None or spec.origin is None:
        return None
    origin = Path(spec.origin)
    return origin if origin.name == "__init__.py" else None


def _audit_playwright_capture(
    init_path: Path, distribution: str, import_name: str
) -> list[Violation]:
    """PA305 — every module that imports `playwright.async_api` (a sign
    of live browser automation) must contain at least one
    `capture_debug_artifacts_async` call. Helper-routed callers can opt
    in via `from scitex_browser.debugging import capture_debug_artifacts_async`
    (presence-only check; semantics not enforced).

    The auditor doesn't check call frequency or coverage — just
    presence-or-absence. Reviewers should still apply the stepwise
    rule from `02_package_09_browser-automation-debugging.md`.
    """
    out: list[Violation] = []
    # The rule applies to packages that USE playwright in production. We
    # exempt scitex-browser itself (it's the home of the helper and may
    # have helper-implementation modules without consumer-style calls).
    if import_name == "scitex_browser":
        return out
    pkg_root = init_path.parent
    for py_file in sorted(pkg_root.rglob("*.py")):
        parts = py_file.parts
        if any(
            seg in parts
            for seg in (
                "__pycache__",
                "build",
                "dist",
                ".tox",
                "site-packages",
                "tests",
                "examples",
                "docs",
            )
        ):
            continue
        try:
            text = py_file.read_text(encoding="utf-8")
        except OSError:
            continue
        # Cheap pre-check: skip files that don't even mention playwright.
        if "playwright" not in text:
            continue
        try:
            tree = ast.parse(text, filename=str(py_file))
        except SyntaxError:
            continue
        imports_playwright = False
        calls_capture = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if mod == "playwright.async_api" or mod.startswith(
                    "playwright.async_api."
                ):
                    imports_playwright = True
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "playwright.async_api" or alias.name.startswith(
                        "playwright.async_api."
                    ):
                        imports_playwright = True
            # Calls — both bare `capture_debug_artifacts_async(...)` and
            # `something.capture_debug_artifacts_async(...)` (e.g. via
            # an instance method that delegates).
            elif isinstance(node, ast.Call):
                f = node.func
                if isinstance(f, ast.Name) and f.id == "capture_debug_artifacts_async":
                    calls_capture = True
                elif (
                    isinstance(f, ast.Attribute)
                    and f.attr == "capture_debug_artifacts_async"
                ):
                    calls_capture = True
        if imports_playwright and not calls_capture:
            out.append(
                Violation(
                    "PA305",
                    f"{distribution}: {py_file.relative_to(pkg_root.parent)}",
                    "imports `playwright.async_api` but no "
                    "`capture_debug_artifacts_async` call in module",
                )
            )
    return out


def _audit_umbrella_imports(
    init_path: Path, distribution: str, import_name: str
) -> list[Violation]:
    """PA304 — flag `from scitex.X` / `import scitex.X` / `import scitex`
    inside standalone source.

    Only **module-level** imports are flagged. Function-scoped (lazy)
    imports don't drag the umbrella when the package is imported as a
    library — they fire only when the function is actually called.
    The PA304 cost concern is module-import time, not call time.

    Exemptions:
    - The umbrella `scitex` package itself (its source legitimately
      references `scitex.<sub>`).
    - Function-scoped imports (`def f(): import scitex …`).
    - Class-method-scoped imports.
    - Imports inside `if __name__ == "__main__":` blocks (only run on
      direct module invocation).
    """
    out: list[Violation] = []
    if import_name == "scitex":
        return out
    pkg_root = init_path.parent

    def _is_dunder_main_if(node: ast.AST) -> bool:
        if not isinstance(node, ast.If):
            return False
        test = node.test
        if not isinstance(test, ast.Compare) or len(test.comparators) != 1:
            return False
        if not isinstance(test.ops[0], ast.Eq):
            return False
        for a, b in (
            (test.left, test.comparators[0]),
            (test.comparators[0], test.left),
        ):
            if (
                isinstance(a, ast.Name)
                and a.id == "__name__"
                and isinstance(b, ast.Constant)
                and b.value == "__main__"
            ):
                return True
        return False

    def _is_umbrella_private(mod: str) -> bool:
        """`scitex._<name>[…]` — umbrella-private (no peer standalone)."""
        if not mod.startswith("scitex."):
            return False
        first = mod[len("scitex.") :].split(".", 1)[0]
        return first.startswith("_")

    def _flag(mod: str) -> bool:
        if mod == "scitex":
            return True
        if mod.startswith("scitex.") and not _is_umbrella_private(mod):
            return True
        return False

    def _scan_module_level(body: list[ast.stmt], py_file: Path) -> None:
        """Walk only top-level statements + control-flow descendants.
        Skip function and class bodies (lazy) and `if __name__ == ...`."""
        for stmt in body:
            if _is_dunder_main_if(stmt):
                continue
            # Recurse into module-level if/try/with — imports there ARE
            # eager. Skip Function/AsyncFunction/ClassDef bodies.
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if isinstance(stmt, ast.ImportFrom):
                mod = stmt.module or ""
                if _flag(mod):
                    out.append(
                        Violation(
                            "PA304",
                            f"{distribution}: {py_file.relative_to(pkg_root.parent)}:{stmt.lineno}",
                            f"from {mod} import ... — replace with peer standalone import",
                        )
                    )
            elif isinstance(stmt, ast.Import):
                for alias in stmt.names:
                    name = alias.name
                    if _flag(name):
                        out.append(
                            Violation(
                                "PA304",
                                f"{distribution}: {py_file.relative_to(pkg_root.parent)}:{stmt.lineno}",
                                f"import {name} — replace with peer standalone import",
                            )
                        )
            elif isinstance(stmt, (ast.If, ast.Try, ast.With, ast.AsyncWith)):
                # Module-level if/try/with — descend into bodies.
                children: list[ast.stmt] = []
                children.extend(getattr(stmt, "body", []) or [])
                children.extend(getattr(stmt, "orelse", []) or [])
                children.extend(getattr(stmt, "finalbody", []) or [])
                for h in getattr(stmt, "handlers", []) or []:
                    children.extend(getattr(h, "body", []) or [])
                _scan_module_level(children, py_file)

    for py_file in sorted(pkg_root.rglob("*.py")):
        parts = py_file.parts
        if any(
            seg in parts
            for seg in (
                "__pycache__",
                "build",
                "dist",
                ".tox",
                "site-packages",
                # Tutorial/demo subpackages — `import scitex` is the
                # canonical end-user idiom, not a library-cost concern.
                "examples",
                "docs",
            )
        ):
            continue
        # Filename pattern for in-tree demos (e.g. scitex-stats's
        # tests/categorical/_demo_chi2.py). Same exemption as `examples/`
        # — these are runnable demonstrations of the API surface, not
        # library code that consumers import.
        if py_file.name.startswith("_demo_") or py_file.name.startswith("demo_"):
            continue
        try:
            text = py_file.read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            tree = ast.parse(text, filename=str(py_file))
        except SyntaxError:
            continue
        if isinstance(tree, ast.Module):
            _scan_module_level(tree.body, py_file)
    return out


def _audit_init(init_path: Path, distribution: str) -> list[Violation]:
    src = init_path.read_text()
    tree = ast.parse(src, filename=str(init_path))
    out: list[Violation] = []

    where = f"{distribution}/__init__.py"

    # Collect: __all__, bound names, imports (with try/except context),
    # presence of `from __future__ import annotations`, __version__ details.
    all_names: list[str] | None = None
    bound_names: set[str] = set()
    third_party_bound: set[str] = set()
    state: dict[str, object] = {
        "future": False,
        "all": None,
        "version_nodes": [],
        # Local names bound to `importlib.metadata.version` (incl. aliases like
        # `from importlib.metadata import version as _v`). Used by PA202.
        "version_aliases": {"version"},
    }

    def _record_import(node: ast.AST, in_try: bool) -> None:
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                local = alias.asname or alias.name.split(".", 1)[0]
                bound_names.add(local)
                if root in _THIRD_PARTY_ROOTS:
                    third_party_bound.add(local)
                if (
                    not in_try
                    and root not in _STDLIB_SAFE_ROOTS
                    and not root.startswith("scitex")
                    and root != distribution.replace("-", "_").split("_")[0]
                ):
                    out.append(
                        Violation(
                            "PA301",
                            where,
                            f"`import {alias.name}` at module top-level "
                            "(wrap in try/except ImportError if optional)",
                        )
                    )
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            root = mod.split(".", 1)[0] if mod else ""
            if mod == "__future__" and any(a.name == "annotations" for a in node.names):
                state["future"] = True
                return
            for alias in node.names:
                local = alias.asname or alias.name
                bound_names.add(local)
                # Record `from importlib.metadata import version [as X]` aliases
                # so PA202 recognizes the canonical pattern through any alias.
                if mod == "importlib.metadata" and alias.name == "version":
                    aliases = state["version_aliases"]
                    assert isinstance(aliases, set)
                    aliases.add(local)
                if root in _THIRD_PARTY_ROOTS:
                    third_party_bound.add(local)
                if (
                    not in_try
                    and root
                    and root not in _STDLIB_SAFE_ROOTS
                    and not root.startswith("scitex")
                    and not mod.startswith(".")
                    and root != ""
                ):
                    # Relative imports have empty `module` resolved to "" —
                    # ast.ImportFrom.level > 0 marks them.
                    if node.level == 0:
                        out.append(
                            Violation(
                                "PA301",
                                where,
                                f"`from {mod} import ...` at module top-level "
                                "(wrap in try/except ImportError if optional)",
                            )
                        )

    def _walk(body: list[ast.stmt], in_try: bool) -> None:
        for node in body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                _record_import(node, in_try)
            elif isinstance(node, ast.Try):
                _walk(node.body, in_try=True)
                for handler in node.handlers:
                    _walk(handler.body, in_try=True)
                _walk(node.orelse, in_try=in_try)
                _walk(node.finalbody, in_try=in_try)
            elif isinstance(node, ast.If):
                _walk(node.body, in_try)
                _walk(node.orelse, in_try)
            elif isinstance(node, ast.Assign):
                # Capture __all__, bound names, __version__ pattern.
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        bound_names.add(target.id)
                        if target.id == "__all__" and isinstance(
                            node.value, (ast.List, ast.Tuple)
                        ):
                            state["all"] = [
                                elt.value
                                for elt in node.value.elts
                                if isinstance(elt, ast.Constant)
                                and isinstance(elt.value, str)
                            ]
                        if target.id == "__version__":
                            nodes = state.setdefault("version_nodes", [])
                            assert isinstance(nodes, list)
                            nodes.append(node)
                        # Track string-keyed dict literals at module level —
                        # these are commonly used by PEP 562 dispatch tables
                        # like `_LAZY_ATTRS = {"foo": "submod", ...}`.
                        if isinstance(node.value, ast.Dict):
                            keys = [
                                k.value
                                for k in node.value.keys
                                if isinstance(k, ast.Constant)
                                and isinstance(k.value, str)
                            ]
                            if keys:
                                tables = state.setdefault("dispatch_tables", {})
                                assert isinstance(tables, dict)
                                tables[target.id] = keys
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                # Annotated assignments: `__all__: list[str] = [...]`,
                # `__version__: str = ...`, `_LAZY_ATTRS: dict[str, str] = {...}`.
                # Treat them like ast.Assign.
                bound_names.add(node.target.id)
                if (
                    node.target.id == "__all__"
                    and node.value is not None
                    and isinstance(node.value, (ast.List, ast.Tuple))
                ):
                    state["all"] = [
                        elt.value
                        for elt in node.value.elts
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                    ]
                # Annotated dispatch table: `_LAZY_ATTRS: dict[str, str] = {...}`.
                if isinstance(node.value, ast.Dict):
                    keys = [
                        k.value
                        for k in node.value.keys
                        if isinstance(k, ast.Constant) and isinstance(k.value, str)
                    ]
                    if keys:
                        tables = state.setdefault("dispatch_tables", {})
                        assert isinstance(tables, dict)
                        tables[node.target.id] = keys
            elif isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            ):
                bound_names.add(node.name)
                # Recognise PEP 562 lazy-load: `def __getattr__(name): if name == "X": ...`.
                # Pytest collects any module-level callable; PEP 562 lets a
                # module expose names dynamically without binding them at
                # import time. Treat each `name == "..."` literal inside
                # __getattr__ as a bound name so PA102 doesn't false-fire.
                if node.name == "__getattr__":
                    for sub in ast.walk(node):
                        # Pattern A: `if name == "X":`
                        if (
                            isinstance(sub, ast.Compare)
                            and len(sub.ops) == 1
                            and isinstance(sub.ops[0], ast.Eq)
                            and isinstance(sub.left, ast.Name)
                            and sub.left.id == "name"
                            and len(sub.comparators) == 1
                            and isinstance(sub.comparators[0], ast.Constant)
                            and isinstance(sub.comparators[0].value, str)
                        ):
                            bound_names.add(sub.comparators[0].value)
                        # Pattern B: `_LAZY_ATTRS.get(name)` / `_LAZY_ATTRS[name]`
                        # — pull keys from the module-level dispatch table.
                        ref_name = None
                        if (
                            isinstance(sub, ast.Call)
                            and isinstance(sub.func, ast.Attribute)
                            and sub.func.attr in ("get", "__getitem__")
                            and isinstance(sub.func.value, ast.Name)
                        ):
                            ref_name = sub.func.value.id
                        elif isinstance(sub, ast.Subscript) and isinstance(
                            sub.value, ast.Name
                        ):
                            ref_name = sub.value.id
                        if ref_name:
                            tables = state.get("dispatch_tables", {})
                            if isinstance(tables, dict):
                                for k in tables.get(ref_name, []):
                                    bound_names.add(k)

    _walk(tree.body, in_try=False)

    has_future_annotations = bool(state["future"])
    raw_all = state["all"]
    all_names: list[str] | None = raw_all if isinstance(raw_all, list) else None
    raw_versions = state["version_nodes"]
    version_nodes: list[ast.Assign] = (
        [n for n in raw_versions if isinstance(n, ast.Assign)]
        if isinstance(raw_versions, list)
        else []
    )

    # §5
    if not has_future_annotations:
        out.append(
            Violation("PA501", where, "add `from __future__ import annotations`")
        )

    # §1
    if all_names is None:
        out.append(Violation("PA101", where, "declare `__all__ = [...]`"))
    else:
        for n in all_names:
            if n.startswith("_") and n not in {"__version__"}:
                out.append(
                    Violation("PA103", where, f"'{n}' is private but listed in __all__")
                )
            if n not in bound_names:
                out.append(
                    Violation(
                        "PA102",
                        where,
                        f"'{n}' is in __all__ but not imported/defined in __init__.py",
                    )
                )
            if n in third_party_bound:
                out.append(
                    Violation(
                        "PA104",
                        where,
                        f"'{n}' resolves to a third-party symbol — re-export breaks the API surface",
                    )
                )

    # §2 — version strategy
    # PA201 only fires when __version__ is actually defined. Modules that
    # delegate everything (sys.modules aliases, e.g. scitex-plt → figrecipe)
    # don't define __version__ themselves.
    if (
        all_names is not None
        and "__version__" not in all_names
        and "__version__" in bound_names
    ):
        out.append(Violation("PA201", where, "add `__version__` to __all__"))

    if version_nodes:
        raw_aliases = state["version_aliases"]
        version_aliases: set[str] = (
            raw_aliases if isinstance(raw_aliases, set) else {"version"}
        )
        results = [_inspect_version_pattern(n, version_aliases) for n in version_nodes]
        uses_metadata = any(ok for ok, _ in results)
        fallbacks = [fb for _, fb in results if fb is not None]
        if not uses_metadata:
            out.append(
                Violation(
                    "PA202",
                    where,
                    "compute __version__ via importlib.metadata.version('<dist>') "
                    "with PackageNotFoundError fallback",
                )
            )
        for fb in fallbacks:
            if fb != "0.0.0+local":
                out.append(
                    Violation(
                        "PA203",
                        where,
                        f"fallback is {fb!r}; use '0.0.0+local' (PEP 440 local segment)",
                    )
                )

    return out


def _inspect_version_pattern(
    node: ast.Assign,
    version_aliases: set[str] = frozenset({"version"}),  # type: ignore[assignment]
) -> tuple[bool, str | None]:
    """Return (uses_importlib_metadata, fallback_string_if_present).

    Recognized patterns:
        try:
            __version__ = version("<dist>")          # bare or aliased import
        except PackageNotFoundError:
            __version__ = "0.0.0+local"

        __version__ = importlib.metadata.version("<dist>")

    ``version_aliases`` is the set of local names bound to
    ``importlib.metadata.version`` (e.g. ``{"version", "_v"}`` after
    ``from importlib.metadata import version as _v``).
    """
    value = node.value
    if isinstance(value, ast.Call):
        callee = value.func
        if isinstance(callee, ast.Name) and callee.id in version_aliases:
            return True, None
        if (
            isinstance(callee, ast.Attribute)
            and callee.attr == "version"
            and isinstance(callee.value, ast.Attribute)
            and callee.value.attr == "metadata"
        ):
            return True, None
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        # Bare literal — considered drift unless it's exactly the local fallback.
        return False, value.value
    return False, None


def audit_api(
    distribution: str,
    *,
    json_out: bool = False,
    rules: set[str] | None = None,
) -> int:
    """Audit `<distribution>` against the Python API checklist. Warn-only.

    Parameters
    ----------
    distribution : str
        Distribution name (e.g. ``"scitex-io"``).
    json_out : bool
        Emit machine-readable output on stdout.
    rules : set of str, optional
        If given, only run these rule codes.

    Returns
    -------
    int
        Exit code: 0 = no violations, 1 = violations, 2 = could not import.
    """
    # Category-aware skip — see `should_skip_audit` in _ecosystem._core.
    try:
        from ...._ecosystem import should_skip_audit
    except ImportError:
        should_skip_audit = lambda *_a, **_k: (False, "")  # noqa: E731
    skip, reason = should_skip_audit(distribution, "audit-python-apis")
    if skip:
        if json_out:
            import json

            click.echo(
                json.dumps(
                    {
                        "distribution": distribution,
                        "init": None,
                        "skipped": reason,
                        "violations": [],
                    },
                    indent=2,
                )
            )
        else:
            click.echo(f"skip  {distribution}: {reason}")
        return 0

    import_name = _import_name(distribution)
    init_path = _locate_init(import_name)
    if init_path is None:
        click.echo(
            f"audit-api: cannot locate __init__.py for '{distribution}' "
            f"(import name '{import_name}'). Is it installed?",
            err=True,
        )
        return 2

    # Probe distribution metadata to surface missing-install issues early.
    try:
        im.version(distribution)
    except im.PackageNotFoundError:
        click.echo(
            f"audit-api: warn — distribution metadata for '{distribution}' "
            "not found (continuing with source-only checks)",
            err=True,
        )

    violations = _audit_init(init_path, distribution)
    violations.extend(_audit_umbrella_imports(init_path, distribution, import_name))
    violations.extend(_audit_playwright_capture(init_path, distribution, import_name))
    if rules:
        violations = [v for v in violations if v.rule in rules]

    if json_out:
        import json

        click.echo(
            json.dumps(
                {
                    "distribution": distribution,
                    "init": str(init_path),
                    "violations": [
                        {"rule": v.rule, "where": v.where, "detail": v.detail}
                        for v in violations
                    ],
                },
                indent=2,
            )
        )
        return 0 if not violations else 1

    from ...._audit_disclaimer import emit_disclaimer, emit_skill_hints

    if not violations:
        click.echo(f"ok  {distribution}: no Python API violations")
        emit_disclaimer()
        return 0

    click.echo(f"warn  {distribution}: {len(violations)} violation(s)")
    for v in violations:
        click.echo(v.format())
    emit_disclaimer()
    emit_skill_hints()
    return 1
