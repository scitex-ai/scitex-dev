---
description: |
  [TOPIC] Interface Cli Help Format
  [DETAILS] SciTeX CLI required `--help` output structure — description, synopsis, example, flags, exit codes.
tags: [scitex-general-interface-cli-help-format]
---

# §4. Help output format

`--help` always includes:

1. One-line description.
2. Usage synopsis: `Usage: <cli> <noun> <verb> [OPTIONS] ARG`.
3. **At least one concrete example.**
4. Flag list with descriptions.
5. Exit-code summary (if non-trivial).
6. **Categorized command list** when the top-level group exposes ≥6
   commands. Group commands under named sections (e.g. `Ecosystem:`,
   `Development:`, `Documentation:`, `Interface:`, `Shell:`, `Other:`)
   so a fresh agent can scan by intent instead of reading a flat 40-row
   list. Use `scitex_dev.click_helpers.CategorizedGroup` (Click `Group`
   subclass that overrides `format_commands`); pass a `COMMAND_CATEGORIES`
   list of `(section_name, [cmd_names])`. Anything not listed falls to
   `Other`. Auditor rule `C7`.
