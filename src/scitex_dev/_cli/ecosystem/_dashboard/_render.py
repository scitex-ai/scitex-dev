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
    # Logical groups: identity → audit (E,W,Bypassed) → version
    # (pyproject,tag,PyPI) → test (pytest,coverage,CI) → git → code.
    # Version mismatches are shown via cell-colour, not separate
    # drift columns — any cell whose value differs from pyproject's
    # is rendered red.
    # 0 — at-a-glance
    ["pkg", "audit", "warn", "ver", "tag", "ci"],
    # 1 — default
    [
        "pkg",
        "audit",
        "warn",
        "skip",
        "ver",
        "tag",
        "pypi",
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
        "tests",
        "cov",
        "ci",
        "branch",
        "ahead",
        "last",
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
        "tests",
        "cov",
        "ci",
        "rtd",
        "branch",
        "ahead",
        "last",
        "skills",
        "mcp_tools",
        "py_apis",
        "loc",
    ],
]


# Each column has (a) a group label (top line, shared across the
# group) and (b) a column name (bottom line). The renderer prints the
# group label only on the FIRST column of each group; subsequent
# columns in the same group leave the top line blank, producing a
# visual "Audit | | |" / "Version | | | |" effect under Rich's box
# drawing.
_COL_GROUP = {
    "pkg": "",
    "category": "",
    "audit": "Audit",
    "warn": "Audit",
    "skip": "Audit",
    "ver": "Version",
    "tag": "Version",
    "pypi": "Version",
    "drift_local": "Version",
    "drift_pypi": "Version",
    "tests": "Test",
    "cov": "Test",
    "ci": "Test",
    "rtd": "Test",
    "branch": "Git",
    "ahead": "Git",
    "last": "Git",
    "skills": "Code",
    "mcp_tools": "Code",
    "py_apis": "Code",
    "loc": "Code",
}

_COL_NAMES = {
    "pkg": "Package",
    "category": "Category",
    "audit": "Error",
    "warn": "Warning",
    "skip": "Bypassed",
    "ver": "pyproject.toml",
    "tag": "git tag",
    "pypi": "PyPI",
    "drift_local": "Drift",
    "drift_pypi": "PyPI Drift",
    "tests": "pytest",
    "cov": "Coverage",
    "ci": "CI",
    "rtd": "RTD",
    "branch": "branch",
    "ahead": "ahead",
    "last": "last commit",
    "skills": "skills",
    "mcp_tools": "MCP tools",
    "py_apis": "Python APIs",
    "loc": "LOC",
}


def _column_header(cols: list[str], idx: int) -> str:
    """Two-line header for column at index `idx` in `cols`.

    Top line carries the group label only when this column is the
    leading column of a new group (i.e. the previous column belongs
    to a different group, or this is column 0). Subsequent same-group
    columns leave the top line blank so the group reads visually.
    """
    col = cols[idx]
    group = _COL_GROUP.get(col, "")
    prev_group = _COL_GROUP.get(cols[idx - 1], "") if idx > 0 else None
    top = group if (group and group != prev_group) else ""
    return f"{top}\n{_COL_NAMES.get(col, col)}"


def _legend_text() -> Text:
    """Compact glyph legend. Column headers are self-descriptive
    after the two-line group rename, so we no longer need a per-
    column glossary — just remind users what the value glyphs mean.
    """
    parts: list[Text] = []
    parts.append(Text("Glyphs: ", style="bold dim"))
    parts.append(Text("N/C", style="dim"))
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


def _color_count(n: int, *, error: bool = False) -> Text:
    if n < 0:
        return Text("N/C", style="dim")
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


def _normalise_version(s: str) -> str:
    """Trim leading `v` and trailing `-alpha`/`-beta`/etc. for equality
    checks. `0.2.7` ≡ `v0.2.7`."""
    if not s:
        return ""
    s = s.lstrip("v")
    return s


def _color_version_cell(state: "PackageState", col: str) -> Text:
    """Render a version cell coloured red iff it disagrees with the
    canonical (pyproject.toml) version.

    `pyproject.toml` is the source of truth. `git tag` and `PyPI` are
    expected to match it; any divergence is shown by reddening the
    offending cell. Empty/unknown values render dim.
    """
    val_raw = {
        "ver": state.version_pyproject,
        "tag": state.tag_latest,
        "pypi": state.pypi_latest,
    }.get(col, "")

    if not val_raw:
        # `-` for missing tag/pyproject; `N/C` for not-fetched PyPI.
        placeholder = "N/C" if col == "pypi" else "-"
        return Text(placeholder, style="dim")

    canonical = _normalise_version(state.version_pyproject)
    own = _normalise_version(val_raw)

    if col == "ver":
        # The canonical column itself — always rendered neutral
        # (cyan when dynamic, plain otherwise). Mismatch is shown by
        # the OTHER columns going red.
        return Text(val_raw, style="cyan" if state.version_dynamic else "")

    if canonical and own and canonical != own:
        return Text(val_raw, style="red")
    return Text(val_raw, style="green" if canonical and own else "")


def _color_ci(s: str) -> Text:
    return {
        "success": Text("✓", style="green"),
        "failure": Text("✗", style="red bold"),
        "in_progress": Text("…", style="yellow"),
        "cancelled": Text("⊘", style="dim"),
        "": Text("N/C", style="dim"),
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
    if col in ("ver", "tag", "pypi"):
        return _color_version_cell(state, col)
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
        return state.rtd_status or Text("N/C", style="dim")
    if col == "skills":
        return _color_count(state.skills_count)
    if col == "mcp_tools":
        return _color_count(state.mcp_tools)
    if col == "py_apis":
        return _color_count(state.py_apis)
    if col == "tests":
        return _color_count(state.tests_count)
    if col == "cov":
        return (
            f"{state.coverage:.0%}" if state.coverage >= 0 else Text("N/C", style="dim")
        )
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
        caption=_legend_text(),
        caption_justify="left",
        caption_style="",
        expand=False,
    )
    for i, col in enumerate(cols):
        table.add_column(_column_header(cols, i), no_wrap=True)
    for state in sorted(states, key=_key):
        table.add_row(*[_cell(state, c) for c in cols])
    return table
