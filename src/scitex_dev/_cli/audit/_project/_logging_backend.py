# -*- coding: utf-8 -*-
"""Static PS-220 proof for scitex-logging's own stdlib backend.

The public logger is implemented on top of stdlib logging. Routing its
initialization through its own public API would create an import cycle.
This proof covers individual backend operations, never a package or file.
Caller diagnostics, including other output in these modules, still fire.
"""

from __future__ import annotations

import ast
from pathlib import Path

try:
    import tomllib
except ImportError:  # Python 3.9/3.10
    import tomli as tomllib


# Exact package-root module, lexical scope, and backend statement. Unknown
# shapes fail closed, including a diagnostic acquisition in a known module.
_BACKEND_STATEMENTS = {
    ("_logger.py", ("setup_logger_class",)): (
        "root = logging.getLogger()",
    ),
    ("_config.py", ("set_level",)): (
        "logging.getLogger().setLevel(level)",
        "for handler in logging.getLogger().handlers:\n    handler.setLevel(level)",
    ),
    ("_config.py", ("get_level",)): (
        "return _GLOBAL_LEVEL or logging.getLogger().level",
    ),
    ("_config.py", ("configure",)): (
        "root_logger = logging.getLogger()",
    ),
    ("_config.py", ("get_log_path",)): (
        "for handler in logging.getLogger().handlers:\n"
        "    if hasattr(handler, 'baseFilename'):\n"
        "        return handler.baseFilename",
    ),
    ("_context.py", ("log_to_file",)): (
        "root_logger = _logging.getLogger()",
    ),
    ("_console.py", ("getConsole",)): (
        "console = logging.getLogger(name or DEFAULT_CONSOLE_NAME)",
    ),
    ("_print_capture.py", ("PrintCapture", "__init__")): (
        "self.logger = logging.getLogger(logger_name)",
    ),
}


def _shape(node: ast.AST) -> str:
    return ast.dump(node, include_attributes=False)


def _statement(text: str) -> str:
    return _shape(ast.parse(text).body[0])


_BACKEND_SHAPES = {
    key: frozenset(_statement(text) for text in statements)
    for key, statements in _BACKEND_STATEMENTS.items()
}


def _read_tree(path: Path, repo: Path) -> ast.Module | None:
    # A symlink to a foreign implementation is not evidence of ownership.
    try:
        if path.resolve() != repo.resolve() / path.relative_to(repo):
            return None
        return ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, RuntimeError, SyntaxError, UnicodeError):
        return None


def owns_logging_backend(repo: Path) -> bool:
    """Require declared distribution AND the actual public backend wiring.

    Names alone are insufficient: a folder named scitex_logging in another
    project, or a project with only a copied name/path, gets no allowance.
    Source is parsed only; importing the audited package is never necessary.
    """
    try:
        project = tomllib.loads((repo / "pyproject.toml").read_text()).get("project")
    except (OSError, ValueError, UnicodeError):
        return False
    if not isinstance(project, dict) or project.get("name") != "scitex-logging":
        return False
    package = repo / "src" / "scitex_logging"
    init = _read_tree(package / "__init__.py", repo)
    logger = _read_tree(package / "_logger.py", repo)
    if init is None or logger is None:
        return False
    init_shapes = {_shape(node) for node in init.body}
    if not {
        _statement("import logging as _logging"),
        _statement("getLogger = _logging.getLogger"),
        _statement("from ._logger import setup_logger_class as _setup_logger_class"),
    } <= init_shapes:
        return False
    classes = [
        node for node in logger.body
        if isinstance(node, ast.ClassDef) and node.name == "SciTeXLogger"
    ]
    if len(classes) != 1 or not any(
        _shape(base) == _shape(ast.parse("logging.Logger", mode="eval").body)
        for base in classes[0].bases
    ):
        return False
    setup = [
        node for node in logger.body
        if isinstance(node, ast.FunctionDef) and node.name == "setup_logger_class"
    ]
    return len(setup) == 1 and {
        _statement("logging.setLoggerClass(SciTeXLogger)"),
        _statement("root = logging.getLogger()"),
        _statement("root.__class__ = SciTeXLogger"),
    } <= {_shape(node) for node in setup[0].body}


def is_logging_backend_call(
    repo: Path, path: Path, tree: ast.AST, call: ast.Call
) -> bool:
    """Recognize one scoped backend statement in the owning distribution."""
    package = repo / "src" / "scitex_logging"
    if path.parent != package or path.resolve() != package.resolve() / path.name:
        return False
    parents = {
        child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)
    }
    ancestors = []
    node = call
    while node in parents:
        node = parents[node]
        ancestors.append(node)
    scope = tuple(
        node.name for node in reversed(ancestors)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    )
    shapes = _BACKEND_SHAPES.get((path.name, scope), ())
    # A For statement owns its iter expression; body statements are tested
    # separately, so adding output inside that loop never gains an exemption.
    statement = next((node for node in ancestors if isinstance(node, ast.stmt)), None)
    return statement is not None and _shape(statement) in shapes


# EOF
