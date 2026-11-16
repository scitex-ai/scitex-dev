"""File-level, auditable rule exemptions: ``# stx-allow-file: <IDS> (reason: ...)``.

The line-level ``# stx-allow: STX-<ID>`` opt-out (``_source_helpers``)
cannot reach whole-file rules such as STX-S001 (missing ``@stx.session``):
those are emitted at line 1 with no source line, so there is no line to
annotate. Until now the only escape was ``library_dirs`` — a silent,
directory-wide exemption that no review sees.

This module adds an explicit, file-level pragma that MUST carry a reason::

    #!/usr/bin/env python3
    # stx-allow-file: STX-S001, STX-S005  (reason: measures the clew store; a session would record itself)
    \"\"\"Benchmark the store.\"\"\"

or, equivalently, a module-docstring line that BEGINS with the marker
(``stx-allow-file: STX-S001  (reason: ...)``, no ``#``).

Placement: a comment before the first non-docstring statement, or a line
of the module docstring. A pragma anywhere else is reported (STX-EX001)
and NOT applied, as is one with no ids, no/empty reason, an unknown id, or
a ``testing``-category id (no-mocks / test-quality forbid suppression).

Applied exemptions are not silent: ``validate-files`` lists every one
(text output's "File-level exemptions" block; JSON ``_meta.exemptions``).
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
from dataclasses import dataclass, field, replace
from pathlib import Path

__all__ = [
    "ExemptionScan",
    "FileExemption",
    "apply_file_exemptions",
    "file_exemptions",
    "scan_file_exemptions",
]

_MARKER = "stx-allow-file"
_COMMENT_RE = re.compile(r"#\s*stx-allow-file\b(?P<rest>.*)$")
_DOCSTRING_LINE_RE = re.compile(
    r"^\s*(?:[rRuUbB]{0,2}(?:\"\"\"|'''))?\s*stx-allow-file\b(?P<rest>.*)$"
)
_REASON_RE = re.compile(r"\(\s*reason\s*:\s*(?P<reason>.*)\)\s*$", re.DOTALL)
_ID_RE = re.compile(r"^[A-Z][A-Z0-9]*-[A-Z0-9][A-Z0-9-]*$")
# Rules whose own contract is "no suppression" (see _rules/_no_mocks.py,
# _rules/_test_quality.py) — a file-level pragma must not defeat them.
_NON_EXEMPTABLE_CATEGORIES = frozenset({"testing"})


@dataclass(frozen=True)
class FileExemption:
    """One applied file-level exemption."""

    rule_ids: tuple
    reason: str
    line: int

    def to_dict(self) -> dict:
        return {"rules": list(self.rule_ids), "reason": self.reason, "line": self.line}


@dataclass
class ExemptionScan:
    """Result of scanning a module: valid exemptions + rejected pragmas."""

    exemptions: list = field(default_factory=list)
    # (line, source_line, why-rejected)
    problems: list = field(default_factory=list)

    @property
    def exempted_ids(self) -> frozenset:
        return frozenset(rid for ex in self.exemptions for rid in ex.rule_ids)


def _header_end_line(tree: ast.Module, n_lines: int) -> int:
    """1-indexed line of the first statement after the module docstring."""
    body = list(tree.body)
    if body and _is_docstring(body[0]):
        body = body[1:]
    return body[0].lineno if body else n_lines + 1


def _is_docstring(node: ast.stmt) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def _parse_rest(rest: str):
    """Parse ``: IDS (reason: TEXT)`` -> (ids, reason, error-or-None)."""
    rest = rest.strip()
    if not rest.startswith(":"):
        return (), "", "missing `:` and rule ids after `stx-allow-file`"
    rest = rest[1:].strip()
    m = _REASON_RE.search(rest)
    if m is None:
        return (), "", "missing `(reason: ...)` — an exemption must say why"
    reason = m.group("reason").strip()
    ids_part = rest[: m.start()].strip()
    ids = tuple(t for t in re.split(r"[\s,]+", ids_part) if t)
    if not ids:
        return (), reason, "names no rule id"
    if not reason:
        return ids, "", "empty reason — an exemption must say why"
    bad = [t for t in ids if not _ID_RE.match(t)]
    if bad:
        return ids, reason, f"malformed rule id(s): {', '.join(bad)}"
    from ._rules import lookup

    unknown = [t for t in ids if lookup(t) is None]
    if unknown:
        return ids, reason, f"unknown rule id(s): {', '.join(unknown)}"
    locked = [t for t in ids if lookup(t).category in _NON_EXEMPTABLE_CATEGORIES]
    if locked:
        return ids, reason, f"rule(s) that forbid suppression: {', '.join(locked)}"
    return ids, reason, None


def _comment_pragmas(source: str):
    """Yield (line, comment_text) for every real ``#`` comment with the marker."""
    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type == tokenize.COMMENT and _MARKER in tok.string:
                yield tok.start[0], tok.string
    except (tokenize.TokenError, IndentationError):
        return


def scan_file_exemptions(source: str, tree: ast.Module | None = None) -> ExemptionScan:
    """Find every ``stx-allow-file`` pragma in *source* and validate it."""
    scan = ExemptionScan()
    if _MARKER not in source:
        return scan
    if tree is None:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return scan
    lines = source.splitlines()
    header_end = _header_end_line(tree, len(lines))

    candidates = []  # (line, rest, source_line)
    for lineno, text in _comment_pragmas(source):
        m = _COMMENT_RE.search(text)
        src = lines[lineno - 1] if lineno - 1 < len(lines) else text
        if m is None:
            continue
        if lineno >= header_end:
            scan.problems.append(
                (
                    lineno,
                    src,
                    "outside the module header (must precede the first statement)",
                )
            )
            continue
        candidates.append((lineno, m.group("rest"), src))

    if tree.body and _is_docstring(tree.body[0]):
        doc = tree.body[0]
        for lineno in range(doc.lineno, (doc.end_lineno or doc.lineno) + 1):
            src = lines[lineno - 1]
            m = _DOCSTRING_LINE_RE.match(src)
            if m is not None:
                candidates.append((lineno, m.group("rest").rstrip("\"' "), src))

    for lineno, rest, src in sorted(candidates):
        ids, reason, err = _parse_rest(rest)
        if err:
            scan.problems.append((lineno, src, err))
        else:
            scan.exemptions.append(FileExemption(ids, reason, lineno))
    return scan


def _ex001_issue(lineno: int, src: str, why: str):
    from ._issue import Issue
    from ._rules._exemption import EX001

    rule = replace(EX001, message=f"{EX001.message}: {why}")
    return Issue(rule=rule, line=lineno, col=0, source_line=src.rstrip())


def apply_file_exemptions(issues: list, source: str, tree=None) -> list:
    """Drop issues exempted file-wide; add STX-EX001 for rejected pragmas."""
    scan = scan_file_exemptions(source, tree)
    if not scan.exemptions and not scan.problems:
        return issues
    from .rules import SEVERITY_ORDER

    exempted = scan.exempted_ids
    out = [i for i in issues if i.rule.id not in exempted]
    out.extend(_ex001_issue(*p) for p in scan.problems)
    out.sort(key=lambda i: (-SEVERITY_ORDER[i.rule.severity], i.line))
    return out


def file_exemptions(path) -> list:
    """Applied exemptions of a ``.py`` file (for audit reporting)."""
    p = Path(path)
    if p.suffix != ".py" or not p.is_file():
        return []
    try:
        source = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    return scan_file_exemptions(source).exemptions


# EOF
