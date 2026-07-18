---
description: |
  [TOPIC] Interface Cli Command Categories
  [DETAILS] SciTeX CLI fixed ordered help categories — Core / Data & Sync / Service / Diagnostics / Introspection / Shell / Other (must be empty at audit-clean). Mechanism: CategorizedGroup in scitex_dev/_ecosystem/click_helpers.py.
tags: [scitex-general-interface-cli-command-categories]
---

# §4a. Command categories — fixed ordered help sections

Every top-level group help lists its commands under a **fixed, ordered
set of category headers** (operator-confirmed 2026-07-07). Same names,
same order, every `scitex-*` CLI — a user scanning any package's help
finds lifecycle commands, diagnostics, and completion in the same place.

## The seven categories (names and order are canonical)

| # | Category         | Holds                                                                                       |
|---|------------------|----------------------------------------------------------------------------------------------|
| 1 | `Core`           | The package's primary domain noun groups and verbs — what the package *is for*.             |
| 2 | `Data & Sync`    | `import`/`export`, `push`/`pull`, `sync-<object>`, upload/download.                          |
| 3 | `Service`        | Daemonized/long-running surfaces: `mcp`, `gui` (§12), servers, tunnels.                      |
| 4 | `Diagnostics`    | `doctor`, `status`/`logs` leaves, audit and health commands.                                 |
| 5 | `Introspection`  | `dev` subgroup (§11), `skills`, `docs` — discovering the package's surface.                  |
| 6 | `Shell`          | `completion` group (§1b), `repl`/`shell`.                                                    |
| 7 | `Other`          | Auto-catch-all for anything not explicitly categorized. **Must be empty at audit-clean.**    |

- Categories **1–4** hold package-specific commands; which command goes
  where is the package's call, but the header names are not negotiable.
- Categories **5–7** (`Introspection` / `Shell` / `Other`) are **fixed
  names ecosystem-wide with fixed membership** — the same required
  commands (§1a, §1b, §11) appear under the same headers in every
  package.
- A category with no commands is **omitted** from help output — no
  empty headers.
- `Other` is where uncategorized commands fall. A non-empty `Other` is
  an audit finding: every command must be explicitly assigned. At
  audit-clean, `Other` never renders.

## Mechanism — `CategorizedGroup`

Use `CategorizedGroup` from `scitex_dev/_ecosystem/click_helpers.py`
(a Click `Group` subclass overriding `format_commands`). Pass
`COMMAND_CATEGORIES`, a list of `(section_name, [cmd_names])` in the
canonical order; anything not listed falls to `Other`.

```python
from scitex_dev._ecosystem.click_helpers import CategorizedGroup

COMMAND_CATEGORIES = [
    ("Core",          ["figure", "image", "diagram", "style", "font"]),
    ("Service",       ["gui", "mcp"]),
    ("Diagnostics",   ["doctor"]),
    ("Introspection", ["dev", "skills", "docs"]),
    ("Shell",         ["completion"]),
]

@click.group(cls=CategorizedGroup, command_categories=COMMAND_CATEGORIES)
def main():
    ...
```

## Relation to §4 help format

§4 [10_help-format.md](10_help-format.md) already requires a
categorized command list on groups with ≥6 commands; this section fixes
*which* categories. Free-form section names (`Ecosystem:`,
`Development:`, …) are superseded by the canonical seven.

## Audit

- Auditor rule `C7` checks that large groups use `CategorizedGroup`.
- Planned (slice 4 of the CLI-standardization plan): verify header
  names/order against this table and fail on a non-empty `Other`.
