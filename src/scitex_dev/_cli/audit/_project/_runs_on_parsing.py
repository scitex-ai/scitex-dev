# -*- coding: utf-8 -*-
"""Pure parsing layer for GitHub Actions ``runs-on`` destinations (PS-224).

Extracted from ``_check_runner_destinations.py`` (line-limit refactor) — pure
move, no behaviour change. Everything here is STATIC and dependency-free: it
reads YAML values and workflow paths, and knows nothing about the machine
registry, the auditor's ``Violation`` type, or ``audit.exemptions``. The rule
module owns those.

Supported ``runs-on`` forms
---------------------------
::

    runs-on: ubuntu-latest                              # bare string
    runs-on: [self-hosted, Linux, X64, scitex-ci]       # list
    runs-on: {labels: [self-hosted, scitex-ci]}         # mapping
    runs-on: ${{ fromJSON(vars.CI_RUNS_ON || '["self-hosted","Linux","X64","scitex-ci"]') }}

The last is the fleet idiom; the LITERAL FALLBACK inside the expression is
what gets resolved. That fallback is what actually runs whenever the
``CI_RUNS_ON`` repo/org variable is unset, which is the common case — so
reading it is reading the real destination, not a decoration.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

#: A ``${{ ... }}`` expression block (contents captured).
_RE_EXPR_BLOCK = re.compile(r"\$\{\{\s*(.+?)\s*\}\}", re.DOTALL)

#: ``fromJSON( ... )`` — the scitex CI idiom; args captured for default mining.
_RE_FROMJSON = re.compile(r"fromJSON\s*\((.*)\)", re.IGNORECASE | re.DOTALL)

#: A single-level JSON array literal, e.g. ``["self-hosted","Linux"]``.
_RE_JSON_ARRAY = re.compile(r"(\[[^\[\]]*\])")


def as_labels(value: Any) -> list[str]:
    """Flatten a raw ``runs-on`` value into its label strings.

    Handles the scalar, sequence and ``labels:``/``group:`` mapping forms.
    Returns the labels VERBATIM — expression resolution happens later, in
    :func:`resolve_destination`.
    """
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value if isinstance(v, (str, int, float))]
    if isinstance(value, dict):
        out: list[str] = []
        for key in ("labels", "group"):
            got = value.get(key)
            if isinstance(got, str):
                out.append(got)
            elif isinstance(got, list):
                out.extend(str(v) for v in got if isinstance(v, str))
        return out
    return []


def fromjson_literal(args: str) -> list[str] | None:
    """Resolve ``fromJSON(... || '<json-array>')`` to its literal fallback.

    Returns the FIRST JSON-array literal in the ``fromJSON`` arguments —
    the fleet idiom's ``|| '[...]'`` default, or a direct
    ``fromJSON('[...]')``. ``None`` when there is no array literal to read,
    which makes the destination unresolvable.
    """
    for match in _RE_JSON_ARRAY.finditer(args):
        try:
            parsed = json.loads(match.group(1))
        except ValueError:
            continue
        if isinstance(parsed, list):
            return [str(x) for x in parsed if isinstance(x, str)]
    return None


def resolve_destination(runs_on: Any) -> list[str] | None:
    """Resolve one ``runs-on`` to the concrete label set it requests.

    Returns ``None`` when the destination is NOT statically resolvable —
    an expression carrying no literal to read. The caller reports that as
    a violation in its own right (the workflow does not name its
    destination explicitly), never as a silent pass.
    """
    raw_labels = as_labels(runs_on)
    if not raw_labels:
        return None
    resolved: list[str] = []
    for label in raw_labels:
        block = _RE_EXPR_BLOCK.search(label)
        if block is None:
            resolved.append(label.strip())
            continue
        from_json = _RE_FROMJSON.search(block.group(1))
        if from_json is None:
            return None
        literal = fromjson_literal(from_json.group(1))
        if literal is None:
            return None
        resolved.extend(x.strip() for x in literal)
    concrete = [label for label in resolved if label]
    return concrete or None


def workflow_files(repo: Path) -> list[Path]:
    """Every ``.github/workflows/*.y{a,}ml`` file, sorted.

    ``.github`` is a HIDDEN directory: a walker that skips dotted dirs
    returns zero matches here, which is indistinguishable from "this repo
    has no workflows". The path is therefore built explicitly, never
    discovered by a recursive scan.
    """
    wf_dir = repo / ".github" / "workflows"
    if not wf_dir.is_dir():
        return []
    return sorted(
        path
        for path in wf_dir.iterdir()
        if path.is_file() and path.suffix in {".yml", ".yaml"}
    )


def describe_destinations(destinations: list[tuple[str, frozenset[str]]]) -> str:
    """Render the registry's legal destinations for a violation message."""
    return "; ".join(
        f"{host}: [{', '.join(sorted(labels))}]" for host, labels in destinations
    )


__all__ = [
    "as_labels",
    "fromjson_literal",
    "resolve_destination",
    "workflow_files",
    "describe_destinations",
]

# EOF
