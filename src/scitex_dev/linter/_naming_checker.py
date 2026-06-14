"""Naming convention and hardcoding checks for SciTeX linter.

Rules:
  _lk("STX-S007") — load_configs() result should use UPPER_CASE variable name
  _lk("STX-S008") — Magic number in module scope; consider moving to config/
  _lk("STX-S009") — String literal outside config/ — hardcoded provenance
  _lk("STX-S010") — Path-like string literal outside config/
  _lk("STX-S011") — Hardcoded parameter (UPPER_CASE = literal) in script
  _lk("STX-S012") — Redundant print/logger after a scitex save() call

S009-S012 are part of the HARDCODE-LINT extension (operator directive
2026-06-15). Their severity is upgraded from "warning" to "error" when
the repo's ``.scitex/dev/config.yaml`` lists ``project-type: research``
(see ``_resolve_hardcode_severity()``).

``config/`` is the ONLY exempt directory tree (provenance-bearing
values legitimately live there). Anything outside ``config/`` that
hardcodes is flagged.
"""

from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path
from typing import Optional

from ._rules import lookup as _lk
from ._rules._base import Rule

# Trivial numeric constants that are not magic numbers
_TRIVIAL_NUMBERS = frozenset({0, 1, -1, 0.0, 1.0, -1.0, 2, 0.5, 100})

# Hardcode-lint rule ids whose severity is project-type-driven.
_HARDCODE_RULE_IDS = frozenset(
    {"STX-S008", "STX-S009", "STX-S010", "STX-S011", "STX-S012"}
)

# String-literal carve-outs — bodies that are obviously not hardcoded
# provenance values.
_TRIVIAL_STRINGS = frozenset(
    {
        "",
        " ",
        "\n",
        "\t",
        ".",
        ",",
        ":",
        ";",
        "/",
        "-",
        "_",
        "=",
        "*",
        "%",
        "?",
        "!",
        "(",
        ")",
        "[",
        "]",
        "{",
        "}",
        "__main__",
    }
)

# Path-extension hints — a string literal containing one of these is
# treated as a path-literal (STX-S010) instead of a generic string
# (STX-S009). Keep the list conservative.
_PATH_EXTENSIONS = (
    ".csv",
    ".tsv",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".npy",
    ".npz",
    ".parquet",
    ".pkl",
    ".pickle",
    ".h5",
    ".hdf5",
    ".png",
    ".jpg",
    ".jpeg",
    ".pdf",
    ".svg",
    ".tiff",
    ".tif",
    ".gif",
    ".txt",
    ".md",
    ".log",
    ".xml",
    ".html",
    ".mp4",
)

# Project-type → severity table for the hardcode-lint family.
# Default ("library", "package", "other", or unknown) → keep declared
# severity ("warning"). "research" → upgrade to "error" (blocking).
_RESEARCH_TYPES = frozenset({"research"})


def _read_project_type(filepath: str) -> Optional[frozenset]:
    """Walk up from *filepath* looking for ``.scitex/dev/config.yaml``.

    Returns the set of declared project types (frozenset of strings) or
    ``None`` if no config is found. Mirrors the resolution logic in
    ``scitex_dev._cli.audit._config._loader`` but lives here so the
    linter doesn't pull the audit CLI as a hard dep.
    """
    try:
        start = Path(filepath).resolve()
    except OSError:
        return None
    if start.is_file():
        start = start.parent
    current = start
    while True:
        cfg = current / ".scitex" / "dev" / "config.yaml"
        if cfg.is_file():
            return _parse_project_type(cfg)
        parent = current.parent
        if parent == current:
            return None
        current = parent


def _parse_project_type(cfg: Path) -> Optional[frozenset]:
    """Parse ``project-type`` (list or scalar) from the YAML config."""
    try:
        text = cfg.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    try:
        import yaml  # type: ignore[import-untyped]

        data = yaml.safe_load(text) or {}
    except ImportError:
        data = _minimal_yaml_top_level(text)
    raw = data.get("project-type") if isinstance(data, dict) else None
    if raw is None:
        return None
    if isinstance(raw, str):
        return frozenset({raw})
    if isinstance(raw, list):
        return frozenset(str(x) for x in raw if isinstance(x, str))
    return None


def _minimal_yaml_top_level(text: str) -> dict:
    """Fallback YAML parser: reads ``project-type`` (scalar or list-of-strings)."""
    result: dict = {}
    current_key: Optional[str] = None
    current_list: list = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if line.startswith("  - "):
            current_list.append(line[4:].strip().strip('"').strip("'"))
            continue
        if line.startswith("- ") and current_key is not None:
            current_list.append(line[2:].strip().strip('"').strip("'"))
            continue
        if ":" in line and not line.startswith(" "):
            if current_key and current_list:
                result[current_key] = current_list
                current_list = []
            key, _, val = line.partition(":")
            current_key = key.strip()
            val = val.strip()
            if val:
                result[current_key] = val.strip('"').strip("'")
                current_key = None
    if current_key and current_list:
        result[current_key] = current_list
    return result


def _resolve_hardcode_severity(checker, base_rule: Optional[Rule]) -> Optional[Rule]:
    """Return *base_rule* with severity adjusted for the host project-type.

    project-type: research → upgrade S009-S012 (and S008) to "error".
    Otherwise → keep the declared severity ("warning" / "info").

    Result is cached on the checker so we only walk the filesystem once
    per linted file.
    """
    if base_rule is None:
        return None
    if base_rule.id not in _HARDCODE_RULE_IDS:
        return base_rule
    if not hasattr(checker, "_project_type_cache"):
        checker._project_type_cache = _read_project_type(checker.filepath)
    types = checker._project_type_cache
    if types and (types & _RESEARCH_TYPES):
        if base_rule.severity != "error":
            return replace(base_rule, severity="error")
    return base_rule


def _is_under_config_dir(filepath: str) -> bool:
    """True iff *filepath* lives under a ``config/`` directory.

    The ``config/`` tree legitimately holds provenance-bearing literal
    values (model dims, cohort names, paths). The hardcode-lint family
    is exempt there.
    """
    try:
        parts = Path(filepath).resolve().parts
    except OSError:
        parts = Path(filepath).parts
    return "config" in parts


# Variable names that commonly hold non-config numeric values
_SKIP_NAMES = frozenset(
    {
        "i",
        "j",
        "k",
        "n",
        "x",
        "y",
        "z",
        "idx",
        "count",
        "step",
        "argc",
        "pid",
        "fd",
        "rc",
        "status",
        "exit_code",
        "retval",
    }
)


def check_assignment(checker, node: ast.Assign) -> None:
    """Run all assignment-level checks.

    Legacy S008 (magic numbers) keeps the original ``_is_script`` gate;
    the HARDCODE-LINT extension uses ``not in config/`` instead, so
    research scripts under ``scripts/`` / ``src/`` are covered. The
    ``config/`` directory is the single source-of-truth carve-out.
    """
    check_config_naming(checker, node)
    if checker._is_script:
        check_magic_numbers(checker, node)
    if not _is_under_config_dir(checker.filepath):
        check_hardcoded_param(checker, node)


def check_config_naming(checker, node: ast.Assign) -> None:
    """Warn when load_configs() result is assigned to a non-UPPER_CASE name."""
    if not isinstance(node.value, ast.Call):
        return

    func = node.value.func
    is_load_configs = False

    # bare load_configs()
    if isinstance(func, ast.Name) and func.id == "load_configs":
        is_load_configs = True
    # stx.io.load_configs() / scitex.io.load_configs() / any.load_configs()
    elif isinstance(func, ast.Attribute) and func.attr == "load_configs":
        is_load_configs = True

    if not is_load_configs:
        return

    for target in node.targets:
        if isinstance(target, ast.Name) and not target.id.isupper():
            line = checker._get_source(node.lineno)
            checker._add(_lk("STX-S007"), node.lineno, node.col_offset, line)


def check_magic_numbers(checker, node: ast.Assign) -> None:
    """Warn on UPPER_CASE = <numeric literal> in module scope (not inside functions).

    Only fires for assignments that look like user-defined constants:
    - UPPER_CASE variable name
    - Numeric literal value (int or float)
    - Module scope only (not inside a function or class body)
    - Not a trivial value (0, 1, -1, etc.)
    """
    # Only at module scope
    if checker._func_depth > 0:
        return

    # Only check simple name targets
    if len(node.targets) != 1:
        return
    target = node.targets[0]
    if not isinstance(target, ast.Name):
        return

    name = target.id

    # Skip non-UPPER_CASE names (lowercase assignments are fine — they're local vars)
    # We specifically want to catch UPPER_CASE = 256 patterns (user-defined constants)
    if not name.isupper() or name.startswith("_"):
        return

    # Skip names that are clearly not config values
    if name in _SKIP_NAMES:
        return

    # Check if value is a numeric literal
    value = node.value
    if not isinstance(value, ast.Constant):
        return
    if not isinstance(value.value, (int, float)):
        return

    # Skip trivial numbers
    if value.value in _TRIVIAL_NUMBERS:
        return

    line = checker._get_source(node.lineno)
    rule = _resolve_hardcode_severity(checker, _lk("STX-S008"))
    checker._add(rule, node.lineno, node.col_offset, line)


# ---------------------------------------------------------------------------
# STX-S009 / S010 / S011 / S012 — HARDCODE-LINT extension
# ---------------------------------------------------------------------------


def check_hardcoded_param(checker, node: ast.Assign) -> None:
    """STX-S011 — Hardcoded UPPER_CASE = <literal> at module scope.

    Covers strings (any non-trivial), paths (anything with ``/``, ``\\``,
    or a known file extension), and numerics that S008 already covers
    (we delegate numerics to S008 to avoid double-firing — S011 focuses
    on strings/paths). ``config/`` directory is fully exempt.
    """
    if _is_under_config_dir(checker.filepath):
        return
    if checker._func_depth > 0:
        return
    if len(node.targets) != 1:
        return
    target = node.targets[0]
    if not isinstance(target, ast.Name):
        return
    name = target.id
    if not name.isupper() or name.startswith("_"):
        return
    if name in _SKIP_NAMES:
        return
    value = node.value
    if not isinstance(value, ast.Constant):
        return
    # Numeric literals → already covered by STX-S008.
    if isinstance(value.value, (int, float)) and not isinstance(value.value, bool):
        return
    # Only flag strings here.
    if not isinstance(value.value, str):
        return
    if value.value in _TRIVIAL_STRINGS:
        return
    line = checker._get_source(node.lineno)
    rule = _resolve_hardcode_severity(checker, _lk("STX-S011"))
    checker._add(rule, node.lineno, node.col_offset, line)


def check_string_literal(checker, node: ast.Constant) -> None:
    """STX-S009 / STX-S010 — string-literal hardcoding outside config/.

    Distinguishes path-like strings (extension match or ``/`` / ``\\``
    separators) from generic strings. Fires only for scripts (config-/
    library-trees skipped). Carve-outs:
      * trivial strings (whitespace, single punct, ``__main__``)
      * docstrings (the parent is an ``Expr`` whose only value is this
        Constant) — handled at visitor level
      * f-string / format placeholder atoms (joined-string children are
        bypassed at visitor level)
      * keyword args (e.g., ``logger.info("msg")``) — too noisy; users
        suppress via ``# stx-allow``
    """
    if not isinstance(node.value, str):
        return
    val = node.value
    if val in _TRIVIAL_STRINGS:
        return
    if _is_under_config_dir(checker.filepath):
        return
    # The hardcode-lint family fires anywhere EXCEPT ``config/``. We do
    # NOT gate on ``_is_script`` because research repos hold their
    # work scripts under ``scripts/`` and ``src/`` (both excluded from
    # ``is_script()`` for the legacy STX-S001-S008 rules).
    line = checker._get_source(node.lineno)
    # Path-like detection: has a path separator, or ends with / contains
    # a known extension. Strings with whitespace are almost always
    # natural-language (log messages, errors) — not paths.
    lower = val.lower()
    has_whitespace = any(c.isspace() for c in val)
    is_path = (not has_whitespace) and (
        "/" in val
        or "\\" in val
        or any(lower.endswith(ext) for ext in _PATH_EXTENSIONS)
    )
    if is_path:
        rule = _resolve_hardcode_severity(checker, _lk("STX-S010"))
    else:
        # Skip extremely short non-path strings — almost certainly not
        # provenance (single tokens like "a", "ok").
        if len(val) < 4:
            return
        rule = _resolve_hardcode_severity(checker, _lk("STX-S009"))
    checker._add(rule, node.lineno, node.col_offset, line)


# ---------------------------------------------------------------------------
# STX-S012 — redundant log after a scitex save() call
# ---------------------------------------------------------------------------

# Keywords whose presence in a print/logger.* argument string suggests
# the call is duplicating the save's auto-log.
_SAVE_LOG_KEYWORDS = ("saved", "wrote", "stored", "written", "dumped")


def _is_scitex_save_call(node: ast.AST) -> bool:
    """True iff *node* is a ``<x>.save(...)`` call on stx/scitex/io chains.

    Matches:
      stx.io.save(...)        scitex.io.save(...)
      stx.save(...)           scitex.save(...)
      io.save(...)            <something>.save(...) (lenient)
    The lenient last form is intentional — many session scripts alias
    the io module locally.
    """
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if not isinstance(func, ast.Attribute) or func.attr != "save":
        return False
    return True


def _is_redundant_log_call(node: ast.AST) -> bool:
    """True iff *node* is a ``print(...)`` / ``logger.*(...)`` whose first
    str-literal arg contains a save-keyword (case-insensitive)."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    is_print = isinstance(func, ast.Name) and func.id == "print"
    is_logger = (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Name)
        and func.value.id in ("logger", "log", "logging")
        and func.attr in ("info", "debug", "success", "warning", "log", "print")
    )
    if not (is_print or is_logger):
        return False
    for arg in node.args:
        text = _flatten_string_arg(arg)
        if text is None:
            continue
        low = text.lower()
        if any(kw in low for kw in _SAVE_LOG_KEYWORDS):
            return True
    return False


def _flatten_string_arg(node: ast.AST) -> Optional[str]:
    """Return a string approximation of *node* if it's a literal / f-string."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for v in node.values:
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                parts.append(v.value)
        return "".join(parts) if parts else None
    return None


def check_redundant_save_log(checker, body: list) -> None:
    """STX-S012 — scan a statement *body* for ``save(); print('saved')`` pairs.

    Visits each consecutive pair: if statement N is an Expr whose value
    is a scitex ``save()`` Call AND statement N+1 is an Expr whose value
    is a ``print(...)`` / ``logger.*(...)`` Call containing a save-
    keyword string, flag N+1.
    """
    if _is_under_config_dir(checker.filepath):
        return
    for prev, curr in zip(body, body[1:]):
        # We expect both to be Expr-wrapped Calls (statements).
        if not (isinstance(prev, ast.Expr) and isinstance(curr, ast.Expr)):
            continue
        if not _is_scitex_save_call(prev.value):
            continue
        if not _is_redundant_log_call(curr.value):
            continue
        line = checker._get_source(curr.lineno)
        rule = _resolve_hardcode_severity(checker, _lk("STX-S012"))
        checker._add(rule, curr.lineno, curr.col_offset, line)
