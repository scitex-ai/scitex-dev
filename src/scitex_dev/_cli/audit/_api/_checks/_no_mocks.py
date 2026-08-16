"""PA-306 no-mocks check for the Python API auditor.

Split out of `_audit.py` — pure refactor, no behaviour change. Flags any
mock-library import, symbol, or fixture parameter anywhere in the repo. The
no-mock rule is intentionally exception-free. Re-exported from `_audit` so
existing imports (`from ..._audit import _audit_no_mocks`) keep resolving.
"""

from __future__ import annotations

import ast
from pathlib import Path

from ._model import (
    _MOCK_FIXTURE_PARAMS_AUDIT,
    _MOCK_MODULES_AUDIT,
    _MOCK_SYMBOLS_AUDIT,
    Violation,
)


def _audit_no_mocks(
    init_path: Path,
    distribution: str,
    import_name: str,
    *,
    repo_root: Path | None = None,
    inspected: "set[Path] | None" = None,
) -> list[Violation]:
    """PA-306 — flag any mock-library import, symbol, or fixture
    parameter anywhere in the repo (src/, tests/, examples/, dev
    scripts). The no-mock rule is intentionally exception-free.

    `repo_root` is the resolved `--path` target and MUST be passed when the
    caller knows it. Without it this check derives the root from
    ``init_path``, and when the target package is IMPORTABLE by the auditing
    interpreter that path points into site-packages — where the derivation
    below collapses ``repo_root`` to site-packages ITSELF. Since
    ``site-packages/tests`` generally exists (belonging to some unrelated
    distribution), the check then walks a FOREIGN tree and reports the result
    as this distribution's verdict: not a silent zero but a wrong answer
    wearing the right label.

    Measured 2026-08-16 — one package reported PA-306 = 0 from an interpreter
    that had it installed as a wheel, and 298 from the same commit read as a
    source checkout. Two other packages were unaffected purely because that
    interpreter could not import them. The predicate is INSTALLED-vs-NOT in
    the auditing interpreter, not wheel-vs-editable.

    This is the same defect `_audit_test_quality` was given `repo_root` for in
    #435 ("would report a silent 0"); the sibling check one line away in
    `_audit.py` was left behind. A partial fix of a known bug class.
    """
    out: list[Violation] = []
    pkg_root = init_path.parent  # <repo>/src/<pkg>/
    # Try to locate the repo root so tests/ and examples/ are also scanned.
    # init_path layout is conventionally `<repo>/src/<pkg>/__init__.py`,
    # but a couple of packages keep the source flat at `<repo>/<pkg>/`.
    if repo_root is None:
        src_parent = pkg_root.parent
        repo_root = src_parent.parent if src_parent.name == "src" else src_parent
    scan_roots: list[Path] = [pkg_root]
    for extra in ("tests", "examples", "scripts"):
        candidate = repo_root / extra
        if candidate.is_dir() and candidate not in scan_roots:
            scan_roots.append(candidate)

    # `seen` doubles as this auditor's DENOMINATOR. It is filled in place when
    # the caller passes a set, the same way `out` accumulates violations — so
    # a verdict can state how many files it actually read instead of leaving a
    # reader unable to tell a clean tree from a tree nothing reached. This is
    # the widest walk in the API auditor (package + tests + examples +
    # scripts); the other checks read subsets of it.
    seen: set[Path] = set() if inspected is None else inspected
    rel_anchor = repo_root if repo_root != pkg_root else pkg_root.parent
    for root in scan_roots:
        for py_file in sorted(root.rglob("*.py")):
            if py_file in seen:
                continue
            seen.add(py_file)
            parts = py_file.parts
            if any(
                seg in parts
                for seg in (
                    "__pycache__",
                    "build",
                    "dist",
                    ".tox",
                    "site-packages",
                    ".venv",
                    "venv",
                )
            ):
                continue
            try:
                text = py_file.read_text(encoding="utf-8")
            except OSError:
                continue
            if not any(
                tok in text
                for tok in ("mock", "Mock", "patch", "monkeypatch", "mocker")
            ):
                continue
            try:
                tree = ast.parse(text, filename=str(py_file))
            except SyntaxError:
                continue
            try:
                rel = py_file.relative_to(rel_anchor)
            except ValueError:
                rel = py_file
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name in _MOCK_MODULES_AUDIT:
                            out.append(
                                Violation(
                                    "PA-306",
                                    f"{distribution}: {rel}:{node.lineno}",
                                    f"`import {alias.name}` — mocks are forbidden",
                                )
                            )
                elif isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                    if mod in _MOCK_MODULES_AUDIT:
                        out.append(
                            Violation(
                                "PA-306",
                                f"{distribution}: {rel}:{node.lineno}",
                                f"`from {mod} import ...` — mocks are forbidden",
                            )
                        )
                    elif mod == "unittest":
                        for alias in node.names:
                            if alias.name == "mock":
                                out.append(
                                    Violation(
                                        "PA-306",
                                        f"{distribution}: {rel}:{node.lineno}",
                                        "`from unittest import mock` — mocks are forbidden",
                                    )
                                )
                                break
                    for alias in node.names:
                        if alias.name in _MOCK_SYMBOLS_AUDIT:
                            out.append(
                                Violation(
                                    "PA-306",
                                    f"{distribution}: {rel}:{node.lineno}",
                                    f"imports mock symbol `{alias.name}` — forbidden",
                                )
                            )
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for arg in (
                        list(node.args.args)
                        + list(node.args.kwonlyargs)
                        + list(getattr(node.args, "posonlyargs", []))
                    ):
                        if arg.arg in _MOCK_FIXTURE_PARAMS_AUDIT:
                            out.append(
                                Violation(
                                    "PA-306",
                                    f"{distribution}: {rel}:{arg.lineno}",
                                    f"`{arg.arg}` fixture parameter — mocks are forbidden",
                                )
                            )
    return out


__all__ = ["_audit_no_mocks"]
