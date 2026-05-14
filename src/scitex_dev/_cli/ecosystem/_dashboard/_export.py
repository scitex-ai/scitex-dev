"""Export dashboard state to JSON / CSV / Markdown."""

from __future__ import annotations

import csv
import io
import json

from ._state import PackageState


def to_json(states: list[PackageState], *, indent: int = 2) -> str:
    return json.dumps([s.to_dict() for s in states], indent=indent, default=str)


def to_csv(states: list[PackageState]) -> str:
    if not states:
        return ""
    rows = [s.to_dict() for s in states]
    # Stable column order: dataclass field order from the first row.
    fieldnames = list(rows[0].keys())
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        # CSV can't carry lists — join skip_rules with ';'.
        safe = {k: (";".join(v) if isinstance(v, list) else v) for k, v in row.items()}
        writer.writerow(safe)
    return buf.getvalue()


def to_markdown(states: list[PackageState]) -> str:
    """Compact MD table — pick the columns reviewers usually want."""
    cols = [
        ("PKG", lambda s: s.pkg),
        ("VER", lambda s: s.version_pyproject or "-"),
        ("TAG", lambda s: s.tag_latest or "-"),
        ("PYPI", lambda s: s.pypi_latest or "-"),
        ("DRIFT", lambda s: s.drift_local or "-"),
        ("BRANCH", lambda s: s.branch or "-"),
        ("AHEAD", lambda s: str(s.ahead)),
        ("SKIP", lambda s: str(len(s.skip_rules))),
    ]
    out: list[str] = []
    out.append("| " + " | ".join(c[0] for c in cols) + " |")
    out.append("| " + " | ".join("---" for _ in cols) + " |")
    for s in sorted(states, key=lambda x: x.pkg):
        out.append("| " + " | ".join(c[1](s) for c in cols) + " |")
    return "\n".join(out) + "\n"
