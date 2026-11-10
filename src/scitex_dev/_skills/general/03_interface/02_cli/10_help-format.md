---
description: |
  [TOPIC] Interface Cli Help Format
  [DETAILS] SciTeX CLI required `--help` output structure — description, synopsis, example, flags, exit codes, fixed command categories, spec-built help via the CliHelp dataclass (enforced construction method).
tags: [scitex-general-interface-cli-help-format]
---

# §4. Help output format

`--help` always includes:

1. One-line description **with the package version inline.** The
   canonical opening line is `<cli> (vX.Y.Z) — <description>`. The
   literal must come from `importlib.metadata.version("<dist>")` so
   pyproject.toml stays the single source of truth — never hardcode a
   string. Operators reading `<cli> --help` see which version they're
   on without a separate `--version` call. Auditor rule `§4`
   (`audit-cli`); the regex accepts pre-release suffixes
   (`rc1`/`dev0`/`post1`).
2. Usage synopsis: `Usage: <cli> <noun> <verb> [OPTIONS] ARG`.
3. **At least one concrete example.**
4. Flag list with descriptions.
5. Exit-code summary (if non-trivial).
6. **Categorized command list** when the top-level group exposes ≥6
   commands, so a fresh agent can scan by intent instead of reading a
   flat 40-row list. Section names and order are FIXED ecosystem-wide —
   `Core` / `Data & Sync` / `Service` / `Diagnostics` / `Introspection`
   / `Shell` / `Other` — see §4a
   [10a_command-categories.md](10a_command-categories.md). Use
   `scitex_dev.click_helpers.CategorizedGroup` (Click `Group` subclass
   that overrides `format_commands`); pass a `COMMAND_CATEGORIES` list
   of `(section_name, [cmd_names])`. Anything not listed falls to
   `Other`, which must be empty at audit-clean. Auditor rule `C7`.

Use `CliHelp(version_of="<distribution-name>")` with `SpecGroup` or
`SpecCommand` to render the installed version. Do not resolve the version
in a decorator yourself: an uninstalled source checkout must still load.
The renderer states `version unresolved: no installed distribution` when
metadata is absent; it never invents a version. Other metadata errors are
not converted into that missing-distribution result.

Pass-through entry points (Click `ignore_unknown_options=True` +
`allow_extra_args=True`) are exempt — their help is forwarded
verbatim from the upstream tool.

## Spec-built help — the `CliHelp` dataclass (enforced construction method)

Free-form help strings drift: examples go missing, exit codes are
documented in three different shapes, config precedence appears in some
roots and not others. The canonical construction method (operator msg
505, confirmed 2026-07-07) is a **help spec dataclass** — help text is
*data*, validated at import time, rendered uniformly.

Implemented in `scitex_dev/_ecosystem/help_spec.py` and exported through
`scitex_dev.ecosystem`, which is a module, not a package. Import from this
public facade; `scitex_dev.ecosystem.help_spec` is not an importable path.
Check the installed Dev version and exports before adopting it in a leaf.
The following example constructs and renders help data without running a
command or its examples:

```python
from scitex_dev.ecosystem import CliHelp, Example, render_epilog, render_help

spec = CliHelp(
    summary="List documentation providers.",
    examples=(Example("{prog} docs list-providers --json"),),
    version_of="scitex-dev",
)
print(render_help(spec))
print(render_epilog(spec, prog="scitex dev"))
```

`CliHelp` and `Example` are frozen dataclasses. Description and config strings
are split into paragraphs; sequence inputs are normalized to tuples. Exit
codes accept a mapping or `(code, meaning)` pairs. Constructing help validates
its structure; it does not execute examples or verify a command's behavior.

- `SpecCommand` (Click `Command` subclass) and `SpecGroup`
  (`CategorizedGroup` subclass, §4a
  [10a_command-categories.md](10a_command-categories.md)) take
  `help_spec=CliHelp(...)` and render the sections in a uniform order:
  summary line (with version via `version_of` +
  `importlib.metadata.version`), description, usage, options, examples,
  exit codes, config resolution, see-also.
- **Validation when help is constructed** (often during module import):
  - `summary` is one line and ≤78 characters.
  - `SpecCommand` requires **at least one example**; `CliHelp` alone and
    `SpecGroup` permit none.
  - Examples use the `{prog}` placeholder, never a hardcoded brand
    (`scitex-plt …` ✗, `{prog} …` ✓) — the renderer substitutes
    `ctx.find_root().info_name`, so the same spec shows the right
    invocation under the umbrella (`scitex plt …`) and standalone
    (`scitex-plt …`) mounts.

Spec-built help is the **enforced construction method**: audit rule
`§4b`, implemented in `_cli/audit/_summary/_std_rules.py`, warns on a command
whose help is not built
from a `CliHelp` spec. It subsumes today's `_has_example` heuristic
(§4 auditor greps for "example"/"$ ") and implements rule `C7`'s
categorized rendering via `SpecGroup`.

Behavioral controls are in
`tests/scitex_dev/_ecosystem/test_help_spec.py`,
`tests/scitex_dev/_ecosystem/test_help_spec_uninstalled_dist.py` and
`tests/scitex_dev/_cli/audit/_summary/test__std_rules.py`. They cover
construction, rendering, missing metadata and the audit rule. A valid spec
or quiet help-format finding does not establish that the documented operation
works or that the complete CLI audit passes.
