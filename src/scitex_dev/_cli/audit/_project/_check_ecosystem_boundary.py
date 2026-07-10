"""PS-183 — ecosystem-boundary a2 smell (unguarded top-level private cross-import).

Implements the a2 edge-kind from
`docs/adr/0003-ecosystem-boundary-ports-and-producers.md` and
`_skills/general/01_ecosystem/16_boundary-ports-and-producers.md`:

  PS-183 fires when `src/` contains an UNGUARDED, TOP-LEVEL,
  LATERAL/UPWARD import from this leaf package reaching into ANOTHER
  leaf package's PRIVATE internals — i.e. a `_private`-prefixed
  submodule/attribute of a peer `scitex_<other>` package that is not in
  the foundational tier (io/config/logging/str/dict/context/path/types).

Per the ADR's methodology caveat, a static import scan cannot by itself
tell a hard runtime dependency from a guarded one — so this check
classifies the AST CONTEXT of each import, not just its presence, and
deliberately does NOT fire for:

  - Guarded imports: inside a `try/except` block whose handler(s) could
    plausibly catch an import failure (`ImportError`, `ModuleNotFoundError`,
    `Exception`, `BaseException`, or a bare `except:`). These are kind d
    (optional try-import) — the ports pattern working correctly.
  - Lazy imports: inside a function/method/lambda body (any nesting
    depth). Also kind d.
  - `TYPE_CHECKING`-only imports: inside `if TYPE_CHECKING:` (or
    `if typing.TYPE_CHECKING:`). Zero runtime edge.
  - Imports of a foundational-tier peer (io/config/logging/str/dict/
    context/path/types) — always kind a1, never a smell, even when the
    import reaches a private submodule/attribute.
  - Imports of the package's own modules (self-imports).
  - The umbrella package itself (`scitex-python`) — its `src/scitex/`
    tree is an intentional giant cross-import graph of thin re-export
    bridges; PS-139/PS-140 already carve this out and PS-183 mirrors
    that exemption.
"""

from __future__ import annotations

import ast
from pathlib import Path

from ._check_umbrella_dep_and_integration import _is_umbrella, _own_import_name

# Foundational-tier packages — always a1 (fine), per ADR-0003 / skill 16.
# Direct OR private-reaching imports of these are never the a2 smell.
FOUNDATIONAL_TIER = frozenset(
    {"io", "config", "logging", "str", "dict", "context", "path", "types"}
)

_IMPORT_ERROR_NAMES = frozenset(
    {"ImportError", "ModuleNotFoundError", "Exception", "BaseException"}
)


def _src_files(repo: Path) -> list[Path]:
    src = repo / "src"
    if not src.is_dir():
        return []
    return [p for p in src.rglob("*.py") if "__pycache__" not in p.parts]


def _handles_import_failure(try_node: ast.Try) -> bool:
    """True iff any handler on this Try could plausibly catch an import
    failure — a bare `except:`, or a name/tuple including ImportError,
    ModuleNotFoundError, Exception, or BaseException."""
    for handler in try_node.handlers:
        if handler.type is None:
            return True  # bare except
        names: list[ast.AST] = []
        if isinstance(handler.type, ast.Tuple):
            names.extend(handler.type.elts)
        else:
            names.append(handler.type)
        for n in names:
            if isinstance(n, ast.Name) and n.id in _IMPORT_ERROR_NAMES:
                return True
            if isinstance(n, ast.Attribute) and n.attr in _IMPORT_ERROR_NAMES:
                return True
    return False


def _is_type_checking_test(test: ast.expr) -> bool:
    if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
        return True
    if isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING":
        return True
    return False


class _BoundaryVisitor(ast.NodeVisitor):
    """Collects only HARD (unguarded, top-level, non-type-checking-only)
    Import/ImportFrom nodes. Everything guarded, lazy (inside a function
    body), or TYPE_CHECKING-only is walked but excluded from the result —
    per the ADR-0003 methodology caveat, those are kind d, not a2."""

    def __init__(self) -> None:
        self.hard_imports: list[ast.Import | ast.ImportFrom] = []
        self._func_depth = 0
        self._guard_depth = 0
        self._type_checking_depth = 0

    def _is_hard_context(self) -> bool:
        return (
            self._func_depth == 0
            and self._guard_depth == 0
            and self._type_checking_depth == 0
        )

    def visit_FunctionDef(self, node: ast.AST) -> None:
        self._func_depth += 1
        self.generic_visit(node)
        self._func_depth -= 1

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_Lambda(self, node: ast.AST) -> None:
        self._func_depth += 1
        self.generic_visit(node)
        self._func_depth -= 1

    def visit_Try(self, node: ast.Try) -> None:
        guarded = _handles_import_failure(node)
        if guarded:
            self._guard_depth += 1
        for stmt in node.body:
            self.visit(stmt)
        if guarded:
            self._guard_depth -= 1
        for handler in node.handlers:
            self.visit(handler)
        for stmt in node.orelse:
            self.visit(stmt)
        for stmt in node.finalbody:
            self.visit(stmt)

    def visit_If(self, node: ast.If) -> None:
        if _is_type_checking_test(node.test):
            self._type_checking_depth += 1
            for stmt in node.body:
                self.visit(stmt)
            self._type_checking_depth -= 1
            for stmt in node.orelse:
                self.visit(stmt)
        else:
            self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        if self._is_hard_context():
            self.hard_imports.append(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if self._is_hard_context():
            self.hard_imports.append(node)


def _peer_short(first_segment: str) -> str | None:
    """`scitex_io` -> `io`; anything not `scitex_<x>`-shaped -> None."""
    if not first_segment.startswith("scitex_"):
        return None
    short = first_segment[len("scitex_") :]
    return short or None


def _classify_import_from(node: ast.ImportFrom, own_import: str) -> str | None:
    if node.level != 0 or not node.module:
        return None  # relative import — cannot cross a package boundary
    segments = node.module.split(".")
    short = _peer_short(segments[0])
    if short is None:
        return None
    if segments[0] == own_import:
        return None  # self-import
    if short in FOUNDATIONAL_TIER:
        return None  # a1 — always fine

    private_module_reach = any(seg.startswith("_") for seg in segments[1:])
    private_attrs = [
        a.name for a in node.names if a.name != "*" and a.name.startswith("_")
    ]
    if not private_module_reach and not private_attrs:
        return None  # public surface — not the a2 smell

    if private_attrs:
        detail_target = f"{node.module} import {', '.join(private_attrs)}"
    else:
        detail_target = node.module
    return (
        f"unguarded top-level `from {detail_target}` reaches "
        f"`{short}`'s private internals (line {node.lineno})"
    )


def _classify_import(node: ast.Import, own_import: str) -> str | None:
    for alias in node.names:
        segments = alias.name.split(".")
        short = _peer_short(segments[0])
        if short is None:
            continue
        if segments[0] == own_import:
            continue
        if short in FOUNDATIONAL_TIER:
            continue
        private_module_reach = any(seg.startswith("_") for seg in segments[1:])
        if not private_module_reach:
            continue
        return (
            f"unguarded top-level `import {alias.name}` reaches "
            f"`{short}`'s private internals (line {node.lineno})"
        )
    return None


def check_ps183_ecosystem_boundary(
    repo: Path,
    distribution: str,
    violation_cls: type,
    out: list,
) -> None:
    if _is_umbrella(repo):
        return
    own_import = _own_import_name(repo)
    for py in _src_files(repo):
        try:
            text = py.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        try:
            tree = ast.parse(text, filename=str(py))
        except SyntaxError:
            continue
        visitor = _BoundaryVisitor()
        visitor.visit(tree)
        for node in visitor.hard_imports:
            if isinstance(node, ast.ImportFrom):
                detail = _classify_import_from(node, own_import)
            else:
                detail = _classify_import(node, own_import)
            if detail is None:
                continue
            out.append(
                violation_cls(
                    "PS-183",
                    f"{py}:{node.lineno}",
                    (
                        f"{detail}. This is the a2 ecosystem-boundary smell "
                        "(ADR-0003) — either import the peer's public "
                        "surface instead, or introduce a `_ports`/"
                        "`_providers` module holding a guarded/lazy import "
                        "(the `scitex_writer -> scitex_scholar` exemplar). "
                        "Foundational-tier peers (io/config/logging/str/"
                        "dict/context/path/types), guarded try/except "
                        "imports, lazy in-function imports, and "
                        "TYPE_CHECKING-only imports are never flagged — see "
                        "_skills/general/01_ecosystem/"
                        "16_boundary-ports-and-producers.md."
                    ),
                )
            )
