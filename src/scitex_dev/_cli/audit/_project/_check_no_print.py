# -*- coding: utf-8 -*-
"""PS-220 — `print(...)` in scitex package SOURCE (use scitex-logging).

Operator mandate: SciTeX code must NEVER emit user-facing messages with
the builtin `print`. A bare `print(...)` is invisible to the ecosystem's
structured, searchable, level-aware logging: it carries no level, no
aligned `WARN:` / `ERRO:` / `SUCC:` prefix, no colour, and cannot be
filtered or silenced by a downstream consumer. The canonical form is
scitex-logging::

    import scitex_logging as slogging
    log = slogging.getLogger(__name__)
    log.warning("...")   # WARN:  aligned, coloured, searchable
    log.error("...")     # ERRO:
    log.success("...")   # SUCC:

This rule statically AST-scans the importable package source tree
(`src/<pkg>/**.py`) for `print(` calls and flags each one. It reads the
source with `ast.parse` and never imports the package, so it is safe to
run against a broken tree.

Scope / exclusions
------------------

Only the *shippable* library source is graded — the tree that ends up in
the wheel and runs on a user's machine. `_src_files` walks `src/` only,
which already excludes repo-root `tests/`, `scripts/`, `examples/`, and
`docs/`; on top of that, any path component named `tests`, `scripts`,
`examples`, or `docs` (an in-package copy, e.g. `src/<pkg>/scripts/`) is
skipped too. `print` in a throwaway script or an example demo is fine —
this rule is about library code that logs.

Inline opt-out
--------------

A single line may opt out with a `# noqa` comment (mirroring the repo's
existing `# noqa` convention), e.g. for a CLI command whose entire job is
to write plain text to stdout::

    print(rendered_report)  # noqa: print is the CLI's stdout payload

The opt-out is recognised anywhere on the physical line(s) spanned by the
call, so multi-line calls can carry it on the closing line.

Severity
--------

W (warn) during ecosystem adoption. Existing scitex packages still carry
many `print` calls; shipping at E would wedge every publish at once. The
rule surfaces the debt now and promotes to E once the ecosystem is
brought into compliance (the `_SEVERITY_OVERRIDES` doctrine).
"""

from __future__ import annotations

import ast
from pathlib import Path

# Path components that mark a non-shippable subtree (an in-package copy of
# a dev-only area). Repo-root tests/scripts/examples/docs are already out
# of scope because `_src_files` walks `src/` only.
_EXCLUDED_PARTS = frozenset({"tests", "scripts", "examples", "docs"})


def _src_files(repo: Path) -> list[Path]:
    """Yield shippable .py files under `src/` (gitignore-naive, best-effort).

    Excludes `__pycache__` and any in-package `tests/`, `scripts/`,
    `examples/`, or `docs/` subtree.
    """
    src = repo / "src"
    if not src.is_dir():
        return []
    out: list[Path] = []
    for p in src.rglob("*.py"):
        parts = set(p.parts)
        if "__pycache__" in parts:
            continue
        if parts & _EXCLUDED_PARTS:
            continue
        out.append(p)
    return out


def _line_opts_out(lines: list[str], node: ast.AST) -> bool:
    """True iff any physical line spanned by `node` carries a `# noqa`."""
    start = getattr(node, "lineno", None)
    if start is None:
        return False
    end = getattr(node, "end_lineno", start) or start
    for lineno in range(start, end + 1):
        idx = lineno - 1
        if 0 <= idx < len(lines) and "noqa" in lines[idx]:
            return True
    return False


def _print_calls(text: str) -> list[ast.Call]:
    """Return every bare `print(...)` call node in `text`.

    A `print` call is an `ast.Call` whose `func` is the bare name `print`.
    Attribute forms (`x.print(...)`) are intentionally NOT matched — only
    the builtin is the target.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    hits: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "print":
            hits.append(node)
    return hits


def check_ps220_no_print(
    repo: Path,
    violation_cls: type,
    out: list,
) -> None:
    """Append PS-220 violations for `print(...)` calls in package source.

    Parameters
    ----------
    repo : Path
        Repository root (the dir containing `src/`).
    violation_cls : type
        The auditor's `Violation` dataclass `(rule, where, detail)`.
    out : list
        Violations are appended in place (project-auditor convention).
    """
    for py in _src_files(repo):
        try:
            text = py.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        calls = _print_calls(text)
        if not calls:
            continue
        lines = text.splitlines()
        for node in calls:
            if _line_opts_out(lines, node):
                continue
            line_no = getattr(node, "lineno", 0)
            out.append(
                violation_cls(
                    "PS-220",
                    f"{py}:{line_no}",
                    (
                        f"`print(...)` in package source (line {line_no}). "
                        f"SciTeX code must not emit messages with the builtin "
                        f"`print` — it carries no level, no aligned "
                        f"`WARN:`/`ERRO:`/`SUCC:` prefix, no colour, and cannot "
                        f"be filtered by a consumer. Use scitex-logging: "
                        f"`import scitex_logging as slogging; "
                        f"log = slogging.getLogger(__name__)` then "
                        f"`log.warning(...)` / `log.error(...)` / "
                        f"`log.success(...)`. If a line legitimately writes "
                        f"plain text to stdout (e.g. a CLI's payload), opt out "
                        f"with a `# noqa` comment on that line."
                    ),
                )
            )


# Rule definition, CO-LOCATED with its check (same pattern as
# `_check_no_url_deps.URL_DEP_RULES` / `_check_version_flag.VERSION_FLAG_RULES`);
# `_registry.py` merges `PRINT_FORBIDDEN_RULES` on the same terms.
#
# Severity W during ecosystem adoption: existing scitex packages still carry
# `print` calls, so shipping at E would wedge every publish. Promote to E once
# the ecosystem is compliant (the `_SEVERITY_OVERRIDES` doctrine).
#
# (code, section, message, severity, slug)
PRINT_FORBIDDEN_RULES: list[tuple[str, str, str, str, str]] = [
    (
        "PS-220",
        "§2",
        (
            "`print(...)` in scitex package source. SciTeX code must emit "
            "messages through scitex-logging, never the builtin `print`: "
            "`import scitex_logging as slogging; "
            "log = slogging.getLogger(__name__)` then `log.warning(...)` / "
            "`log.error(...)` / `log.success(...)` for aligned, coloured, "
            "searchable `WARN:`/`ERRO:`/`SUCC:` output. A bare `print` has no "
            "level, no prefix, and cannot be filtered by a downstream "
            "consumer. Scope is the shippable `src/<pkg>/**.py` tree "
            "(tests/scripts/examples/docs excluded); a line that legitimately "
            "writes plain stdout (e.g. a CLI payload) opts out with `# noqa`."
        ),
        "W",
        "source-uses-print-not-scitex-logging",
    ),
]


# EOF
