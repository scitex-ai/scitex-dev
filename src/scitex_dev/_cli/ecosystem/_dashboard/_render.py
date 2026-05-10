"""Rich-based table renderer for the ecosystem dashboard.

Verbosity → column visibility:

  0     PKG, AUDIT, DRIFT, CI                       (4 cols, at-a-glance)
  1     + W, SKIP, VER, TAG                         (8 cols, default)
  2     + PYPI, DRIFT_PYPI, BRANCH, AHEAD, LAST     (13 cols, deep triage)
  3     + every remaining field                     (export-equivalent)

`render_table(states, verbosity)` returns a `rich.table.Table` ready
to print or pass to `rich.live.Live`. Cell coloring is severity-based:
red on errors / drift, yellow on warnings / skip > 0, green on ✓.
"""

from __future__ import annotations

from rich.table import Table
from rich.text import Text

from ._state import PackageState

_TIERS: list[list[str]] = [
    # Logical groups: identity → audit (E,W,SKIP) → version (VER,TAG,DRIFT)
    # → branch (BRANCH,↑,LAST) → health (CI,RTD) → deep counts.
    # 0 — at-a-glance
    ["pkg", "audit", "warn", "drift_local", "ci"],
    # 1 — default
    [
        "pkg",
        "audit",
        "warn",
        "skip",
        "ver",
        "tag",
        "drift_local",
        "ci",
    ],
    # 2 — deep triage
    [
        "pkg",
        "audit",
        "warn",
        "skip",
        "ver",
        "tag",
        "pypi",
        "drift_local",
        "drift_pypi",
        "branch",
        "ahead",
        "last",
        "ci",
    ],
    # 3 — everything
    [
        "pkg",
        "category",
        "audit",
        "warn",
        "skip",
        "ver",
        "tag",
        "pypi",
        "drift_local",
        "drift_pypi",
        "branch",
        "ahead",
        "last",
        "ci",
        "rtd",
        "skills",
        "mcp_tools",
        "py_apis",
        "tests",
        "cov",
        "loc",
    ],
]


_COL_HEADERS = {
    "pkg": "PKG",
    "category": "CAT",
    "audit": "E",
    "warn": "W",
    "skip": "SKIP",
    "ver": "VER",
    "tag": "TAG",
    "pypi": "PYPI",
    "drift_local": "DRIFT",
    "drift_pypi": "DRIFT₂",
    "branch": "BRANCH",
    "ahead": "↑",
    "last": "LAST",
    "ci": "CI",
    "rtd": "RTD",
    "skills": "SK",
    "mcp_tools": "MCP",
    "py_apis": "API",
    "tests": "T",
    "cov": "COV",
    "loc": "LOC",
}


# Legend strings — what each column header means. Shown as a caption
# below the rendered table so users don't have to grep the source to
# read the row. Wording matches the CLI `--help` epilog.
_COL_LEGEND = {
    "pkg": "package name",
    "category": "umbrella / library / dataset / template / external-lib",
    "audit": "audit-project E-severity finding count (-v fills)",
    "warn": "audit-project W-severity finding count (-v fills)",
    "skip": "rule codes silenced via `audit.skip` in <repo>/.scitex/dev/config.yaml",
    "ver": "pyproject.toml [project] version",
    "tag": "latest git tag",
    "pypi": "latest version on PyPI (-vv fills)",
    "drift_local": "pyproject ↔ latest tag mismatch  (`✓` = synced)",
    "drift_pypi": "pyproject ↔ PyPI mismatch        (`✓` = synced)",
    "branch": "current branch (yellow if not develop/main)",
    "ahead": "commits ahead of origin",
    "last": "last-commit ISO timestamp",
    "ci": "GitHub Actions latest run",
    "rtd": "Read-the-Docs build status",
    "skills": "_skills/ leaf count",
    "mcp_tools": "MCP tool count",
    "py_apis": "public Python API count",
    "tests": "test count (-vvv fills)",
    "cov": "coverage % (-vvv fills)",
    "loc": "source lines of code",
}


def _legend_text(cols: list[str]) -> Text:
    """Build a caption explaining the visible columns + value glyphs.

    Adapts to verbosity — only legends visible columns. The glyph
    glossary is constant since the colour scheme is shared across
    cells.
    """
    parts: list[Text] = []
    parts.append(Text("Columns: ", style="bold dim"))
    for i, c in enumerate(cols):
        if c not in _COL_LEGEND:
            continue
        if i:
            parts.append(Text(" · ", style="dim"))
        parts.append(Text(_COL_HEADERS[c], style="bold"))
        parts.append(Text(f" = {_COL_LEGEND[c]}", style="dim"))
    parts.append(Text("\n", style=""))
    parts.append(Text("Glyphs: ", style="bold dim"))
    parts.append(Text("·", style="dim"))
    parts.append(Text(" not computed at this verbosity  ·  ", style="dim"))
    parts.append(Text("0", style="green"))
    parts.append(Text(" clean  ·  ", style="dim"))
    parts.append(Text("N", style="yellow"))
    parts.append(Text(" warnings  ·  ", style="dim"))
    parts.append(Text("N", style="red"))
    parts.append(Text(" errors  ·  ", style="dim"))
    parts.append(Text("✓", style="green"))
    parts.append(Text(" synced / pass  ·  ", style="dim"))
    parts.append(Text("✗", style="red"))
    parts.append(Text(" failed  ·  ", style="dim"))
    parts.append(Text("…", style="yellow"))
    parts.append(Text(" in progress", style="dim"))
    out = Text("")
    for p in parts:
        out.append_text(p)
    return out


def _color_drift(s: str) -> Text:
    if s == "✓":
        return Text("✓", style="green")
    if not s:
        return Text("", style="dim")
    return Text(s, style="red")


def _color_count(n: int, *, error: bool = False) -> Text:
    if n < 0:
        return Text("·", style="dim")
    if n == 0:
        return Text("0", style="green")
    return Text(str(n), style="red" if error else "yellow")


def _color_skip(skip_rules: list[str]) -> Text:
    # `audit.skip` is an intentional opt-out, not an error. Yellow flags
    # "review periodically" without screaming. Red bold is reserved for
    # actual failures (E counts, CI ✗).
    n = len(skip_rules)
    if n == 0:
        return Text("0", style="green")
    return Text(str(n), style="yellow")


def _color_ci(s: str) -> Text:
    return {
        "success": Text("✓", style="green"),
        "failure": Text("✗", style="red bold"),
        "in_progress": Text("…", style="yellow"),
        "cancelled": Text("⊘", style="dim"),
        "": Text("·", style="dim"),
    }.get(s, Text(s, style="dim"))


def _cell(state: PackageState, col: str) -> Text | str:
    if col == "pkg":
        if not state.exists_locally:
            return Text(state.pkg, style="dim")
        return Text(state.pkg, style="bold")
    if col == "category":
        return state.category or "-"
    if col == "audit":
        return _color_count(state.audit_errors, error=True)
    if col == "warn":
        return _color_count(state.audit_warnings)
    if col == "skip":
        return _color_skip(state.skip_rules)
    if col == "ver":
        v = state.version_pyproject or "-"
        return Text(v, style="cyan" if state.version_dynamic else "")
    if col == "tag":
        return state.tag_latest or "-"
    if col == "pypi":
        return state.pypi_latest or "·"
    if col == "drift_local":
        return _color_drift(state.drift_local)
    if col == "drift_pypi":
        return _color_drift(state.drift_pypi)
    if col == "branch":
        b = state.branch or "-"
        return Text(b, style="" if b in ("develop", "main") else "yellow")
    if col == "ahead":
        return _color_count(state.ahead) if state.ahead else Text("0", style="dim")
    if col == "last":
        return state.last_commit_iso[:10] if state.last_commit_iso else "-"
    if col == "ci":
        return _color_ci(state.ci_status)
    if col == "rtd":
        return state.rtd_status or "·"
    if col == "skills":
        return _color_count(state.skills_count)
    if col == "mcp_tools":
        return _color_count(state.mcp_tools)
    if col == "py_apis":
        return _color_count(state.py_apis)
    if col == "tests":
        return _color_count(state.tests_count)
    if col == "cov":
        return f"{state.coverage:.0%}" if state.coverage >= 0 else "·"
    if col == "loc":
        return _color_count(state.loc)
    return "?"


def render_table(states: list[PackageState], verbosity: int = 1) -> Table:
    """Return a Rich Table for the requested verbosity tier.

    Sorts: drift first (red rows on top), then by audit errors, then
    by name. Stable within ties.
    """
    cols = _TIERS[max(0, min(verbosity, len(_TIERS) - 1))]

    def _key(s: PackageState) -> tuple:
        drift_bad = 0 if s.drift_local in ("", "✓") else 1
        return (-drift_bad, -max(s.audit_errors, 0), s.pkg)

    table = Table(
        title=f"scitex ecosystem  ·  v={verbosity}  ·  {len(states)} packages",
        title_style="bold cyan",
        header_style="bold",
        caption=_legend_text(cols),
        caption_justify="left",
        caption_style="",
        expand=False,
    )
    for col in cols:
        table.add_column(_COL_HEADERS[col], no_wrap=True)
    for state in sorted(states, key=_key):
        table.add_row(*[_cell(state, c) for c in cols])
    return table
