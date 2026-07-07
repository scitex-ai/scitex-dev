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

## Idiom — version-in-help via importlib.metadata

```python
from importlib.metadata import version as _v

@click.group(help=f"scitex-io (v{_v('scitex-io')}) — Universal scientific data I/O.")
def main():
    ...
```

Pass-through entry points (Click `ignore_unknown_options=True` +
`allow_extra_args=True`) are exempt — their help is forwarded
verbatim from the upstream tool.

## Spec-built help — the `CliHelp` dataclass (enforced construction method)

Free-form help strings drift: examples go missing, exit codes are
documented in three different shapes, config precedence appears in some
roots and not others. The canonical construction method (operator msg
505, confirmed 2026-07-07) is a **help spec dataclass** — help text is
*data*, validated at import time, rendered uniformly.

Lives in `scitex_dev/_ecosystem/help_spec.py` (slice 3 of the
CLI-standardization plan — **not built yet**; this section is the
contract it implements).

```python
@dataclass
class Example:
    cmd: str            # "{prog} figure create spec.yaml"
    note: str = ""      # "Create a figure from a YAML spec."

@dataclass
class CliHelp:
    summary: str                          # one line, <=78 chars
    description: str = ""                 # long-form body
    examples: list[Example] = field(default_factory=list)
    exit_codes: dict[int, str] = field(default_factory=dict)
    config_resolution: str = ""           # §6 precedence chain, if any
    see_also: list[str] = field(default_factory=list)
    version_of: str = ""                  # dist name for version-in-help
```

- `SpecCommand` (Click `Command` subclass) and `SpecGroup`
  (`CategorizedGroup` subclass, §4a
  [10a_command-categories.md](10a_command-categories.md)) take
  `help_spec=CliHelp(...)` and render the sections in a uniform order:
  summary line (with version via `version_of` +
  `importlib.metadata.version`), description, usage, options, examples,
  exit codes, config resolution, see-also.
- **Validation in `__post_init__`** (fails at import, not at runtime):
  - `summary` is one line and ≤78 characters.
  - Leaf commands declare **at least one example**.
  - Examples use the `{prog}` placeholder, never a hardcoded brand
    (`scitex-plt …` ✗, `{prog} …` ✓) — the renderer substitutes
    `ctx.find_root().info_name`, so the same spec shows the right
    invocation under the umbrella (`scitex plt …`) and standalone
    (`scitex-plt …`) mounts.

Spec-built help is the **enforced construction method**: audit rule
`4b` (planned, slice 4) warns on any command whose help is not built
from a `CliHelp` spec. It subsumes today's `_has_example` heuristic
(§4 auditor greps for "example"/"$ ") and implements rule `C7`'s
categorized rendering via `SpecGroup`.
